import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))


def build_training_set(out_path: str, limit: int = 5000) -> int:
    """Compile clean training pairs from confirmed + high-confidence extractions: doc text -> fields JSON."""
    import re

    from app.db import SessionLocal
    from app.models import Chunk, Document, ExtractionField
    from sqlalchemy import text as sqltext

    db = SessionLocal()
    try:
        docs = db.execute(
            sqltext(
                "SELECT DISTINCT ef.document_id FROM extraction_fields ef "
                "WHERE ef.status IN ('confirmed', 'auto') AND ef.confidence >= 0.9 LIMIT :l"
            ),
            {"l": limit},
        ).fetchall()
        n = 0
        with open(out_path, "w", encoding="utf-8") as fh:
            for (doc_id,) in docs:
                doc = db.get(Document, doc_id)
                chunks = db.query(Chunk).filter(Chunk.document_id == doc_id).order_by(Chunk.page, Chunk.id).all()
                fields = db.query(ExtractionField).filter(
                    ExtractionField.document_id == doc_id,
                    ExtractionField.status.in_(["confirmed", "auto"]),
                    ExtractionField.confidence >= 0.9,
                ).all()
                if not chunks or not fields:
                    continue

                raw_text = "\n".join(c.text for c in chunks)
                # 1. Sanitize: Remove synthetic generator disclaimers & anchor notes
                clean_text = re.sub(r"NOTE:\s*SYNTHETIC\s*DEMO\s*DOCUMENT.*?(?:\n|$)", "", raw_text, flags=re.I)
                clean_text = re.sub(r"(?:[/\w.-]*anchors\.json\)?\.?\s*)+", "", clean_text)

                # 2. Deduplicate consecutive identical lines from chunk overlaps
                lines = [l.strip() for l in clean_text.split("\n") if l.strip()]
                deduped = []
                for l in lines:
                    if not deduped or l != deduped[-1]:
                        deduped.append(l)
                final_text = "\n".join(deduped)[:10000]
                if len(final_text.strip()) < 40:
                    continue

                # 3. Reconstruct schema-compliant structured payload
                doc_type = doc.doc_type if doc else "other"
                if doc_type == "stoppage_report":
                    machines: dict[str, dict] = {}
                    scalars: dict[str, any] = {}
                    for f in fields:
                        val = f.value_num if f.value_num is not None else f.value_str
                        if f.item and "|" in f.item:
                            mid = f.item.split("|")[0].strip()
                            machines.setdefault(mid, {})
                            if f.field_name == "stoppage_duration_h":
                                reason = f.item.split("|")[-1].strip()
                                machines[mid].setdefault("stoppages", []).append({
                                    "duration_h": val,
                                    "reason": reason,
                                })
                            else:
                                machines[mid][f.field_name] = val
                        elif f.item:
                            mid = f.item.strip()
                            machines.setdefault(mid, {})[f.field_name] = val
                        else:
                            scalars[f.field_name] = val

                    payload = {
                        **scalars,
                        "machines": [{"machine_id": k, **v} for k, v in machines.items()]
                    }
                else:
                    payload = {}
                    for f in fields:
                        val = f.value_num if f.value_num is not None else f.value_str
                        payload[f.field_name] = val

                fh.write(json.dumps({"text": final_text, "fields": payload}, ensure_ascii=False) + "\n")
                n += 1
        return n
    finally:
        db.close()


def finetune(
    data_path: str,
    out_dir: str,
    model_id: str = "Qwen/Qwen2.5-0.5B-Instruct",
    epochs: int = 1,
    batch_size: int = 4,
    lr: float = 3e-4,
    grad_accum: int = 2,
    max_length: int = 512,
) -> None:
    """End-to-end native PyTorch LoRA fine-tuning loop for Qwen 2.5 on CMPDI/CIL extractions."""
    import math
    import time
    try:
        import torch
        try:
            import torch.distributed
            import torch.distributed.tensor
        except Exception:
            pass
        from peft import LoraConfig, TaskType, get_peft_model
        from torch.utils.data import DataLoader, Dataset
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as e:
        print(f"Required ML library missing ({e}). Run: pip install torch transformers peft accelerate")
        sys.exit(1)

    device = "cpu"
    if torch.cuda.is_available():
        try:
            _probe = torch.zeros(1, device="cuda")
            device = "cuda"
            print(f"[*] Training Device: CUDA ({torch.cuda.get_device_name(0)})", flush=True)
        except Exception:
            print("[*] Note: NVIDIA RTX 5060 has Blackwell sm_120 architecture (requires PyTorch nightly for native kernels).", flush=True)
            print("[*] Utilizing 16-core parallel CPU compute for stable local execution.", flush=True)
            device = "cpu"
    else:
        print("[*] Training Device: CPU", flush=True)

    import os
    local_snap = os.path.expanduser(r"~/.cache/huggingface/hub/models--Qwen--Qwen2.5-0.5B-Instruct/snapshots/7ae557604adf67be50417f59c2c2f167def9a775")
    if os.path.exists(local_snap):
        model_id = local_snap
        print(f"[*] Detected local cached snapshot: {model_id}", flush=True)

    print(f"[*] Loading tokenizer for {model_id}...", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    print(f"[*] Loading base model {model_id}...", flush=True)
    if device == "cuda":
        torch_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        print(f"[*] Utilizing GPU mixed precision: {torch_dtype}", flush=True)
    else:
        torch_dtype = torch.float32

    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        torch_dtype=torch_dtype,
        trust_remote_code=True,
    )
    model.to(device)

    # Configure LoRA targeting linear projection matrices
    print("[*] Applying LoRA configuration (r=16, alpha=32)...", flush=True)
    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    print(f"[*] Tokenizing dataset from {data_path} into ChatML conversations...", flush=True)
    system_msg = (
        "You are CMPDI's expert geological and mining document extraction engine. "
        "Extract all verified production figures, borehole reserves, depths, and operational metrics into structured JSON."
    )
    all_input_ids = []
    with open(data_path, "r", encoding="utf-8") as fh:
        for line in fh:
            item = json.loads(line)
            text_content = item.get("text", "").strip()
            fields = item.get("fields", {})
            if not text_content or not fields:
                continue
            chat = [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": f"Extract structured figures from this document text:\n\n{text_content}"},
                {"role": "assistant", "content": json.dumps(fields, ensure_ascii=False, indent=2)},
            ]
            formatted_text = tokenizer.apply_chat_template(chat, tokenize=False)
            tokens = tokenizer(
                formatted_text,
                truncation=True,
                max_length=max_length,
                return_tensors=None,
            )["input_ids"]
            all_input_ids.append(tokens)

    print(f"[+] Successfully tokenized {len(all_input_ids)} high-confidence training samples.", flush=True)

    class MiningDataset(Dataset):
        def __init__(self, tokenized_items):
            self.items = tokenized_items

        def __len__(self):
            return len(self.items)

        def __getitem__(self, idx):
            return self.items[idx]

    def collate_fn(batch):
        max_len = max(len(x) for x in batch)
        padded_ids, attention_masks, labels = [], [], []
        pad_id = tokenizer.pad_token_id or 0
        for item in batch:
            pad_len = max_len - len(item)
            p_ids = item + [pad_id] * pad_len
            attn = [1] * len(item) + [0] * pad_len
            lbls = [x for x in item] + [-100] * pad_len
            padded_ids.append(p_ids)
            attention_masks.append(attn)
            labels.append(lbls)
        return {
            "input_ids": torch.tensor(padded_ids, dtype=torch.long, device=device),
            "attention_mask": torch.tensor(attention_masks, dtype=torch.long, device=device),
            "labels": torch.tensor(labels, dtype=torch.long, device=device),
        }

    dataset = MiningDataset(all_input_ids)
    dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True, collate_fn=collate_fn)

    class SimpleAdamW:
        def __init__(self, params, lr=1e-4, beta1=0.9, beta2=0.999, eps=1e-8, weight_decay=0.01):
            self.params = [p for p in params if p.requires_grad]
            self.lr = lr
            self.beta1 = beta1
            self.beta2 = beta2
            self.eps = eps
            self.weight_decay = weight_decay
            self.m = {p: torch.zeros_like(p.data, dtype=torch.float32) for p in self.params}
            self.v = {p: torch.zeros_like(p.data, dtype=torch.float32) for p in self.params}
            self.t = 0

        def zero_grad(self):
            for p in self.params:
                if p.grad is not None:
                    p.grad.detach_()
                    p.grad.zero_()

        def step(self):
            self.t += 1
            with torch.no_grad():
                for p in self.params:
                    if p.grad is None:
                        continue
                    orig_dtype = p.data.dtype
                    grad = p.grad.data.float()
                    p_data = p.data.float()
                    if self.weight_decay != 0:
                        p_data.mul_(1.0 - self.lr * self.weight_decay)
                    m = self.m[p]
                    v = self.v[p]
                    m.mul_(self.beta1).add_(grad, alpha=1.0 - self.beta1)
                    v.mul_(self.beta2).addcmul_(grad, grad, value=1.0 - self.beta2)
                    m_hat = m / (1.0 - (self.beta1 ** self.t))
                    v_hat = v / (1.0 - (self.beta2 ** self.t))
                    p_data.addcdiv_(m_hat, v_hat.sqrt().add_(self.eps), value=-self.lr)
                    p.data.copy_(p_data.to(orig_dtype))

    total_steps = (len(dataloader) // grad_accum + 1) * epochs
    optimizer = SimpleAdamW(model.parameters(), lr=lr, weight_decay=0.01)

    print(f"[*] Commencing training loop: {epochs} epochs, {len(dataloader)} batches/epoch (batch_size={batch_size}, grad_accum={grad_accum})...", flush=True)
    model.train()
    global_step = 0
    t0 = time.time()

    for epoch in range(1, epochs + 1):
        running_loss = 0.0
        for step, batch in enumerate(dataloader, start=1):
            outputs = model(**batch)
            loss = outputs.loss / grad_accum
            loss.backward()
            running_loss += loss.item() * grad_accum

            if step % grad_accum == 0 or step == len(dataloader):
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                # Cosine LR decay
                optimizer.lr = max(lr * 0.1, lr * (0.5 * (1.0 + math.cos(math.pi * global_step / max(total_steps, 1)))))
                optimizer.step()
                optimizer.zero_grad()
                global_step += 1

                avg_loss = running_loss / step
                elapsed = time.time() - t0
                print(f"  [Epoch {epoch}/{epochs} | Batch {step}/{len(dataloader)}] Loss: {avg_loss:.4f} | LR: {optimizer.lr:.2e} | Elapsed: {elapsed:.1f}s", flush=True)

    total_time = time.time() - t0
    print(f"[+] LoRA Training completed in {total_time:.1f} seconds!", flush=True)

    print(f"[*] Saving fine-tuned adapter weights to {out_dir}...", flush=True)
    os.makedirs(out_dir, exist_ok=True)
    model.save_pretrained(out_dir)
    tokenizer.save_pretrained(out_dir)
    print(f"[+] Adapter saved successfully to: {out_dir}", flush=True)

    # Run quick validation on unseen test document
    print("\n" + "=" * 60, flush=True)
    print(" [*] Benchmark Test: Running inference on unseen test snippet...", flush=True)
    print("=" * 60, flush=True)
    model.eval()
    test_snippet = (
        "NLC INDIA LTD Mine-II 28.08.2026 NSB/BWE-1361 TWH: 16.50 EWH: 11.20 "
        "Stoppage: 0815 to 0945 (1.50h) Track preparation & repositioning"
    )
    test_messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": f"Extract structured figures from this document text:\n\n{test_snippet}"},
    ]
    prompt_str = tokenizer.apply_chat_template(test_messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(prompt_str, return_tensors="pt").to(device)
    with torch.no_grad():
        gen_tokens = model.generate(
            **inputs,
            max_new_tokens=256,
            temperature=0.1,
            do_sample=False,
            pad_token_id=tokenizer.pad_token_id,
        )
    gen_text = tokenizer.decode(gen_tokens[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    print(gen_text)
    print("=" * 60 + "\n")


def main():
    ap = argparse.ArgumentParser(description="LoRA fine-tuning pipeline for CMPDI / CIL (Phase D)")
    ap.add_argument("--build-only", action="store_true", help="only build training JSONL from confirmed extractions")
    ap.add_argument("--data", default=os.path.join("data", "finetune", "train.jsonl"))
    ap.add_argument("--out", default=os.path.join("data", "finetune", "adapter"))
    ap.add_argument("--model", default="Qwen/Qwen2.5-0.5B-Instruct", help="base HuggingFace model")
    ap.add_argument("--epochs", type=int, default=1, help="number of training epochs")
    ap.add_argument("--batch-size", type=int, default=4, help="batch size")
    ap.add_argument("--lr", type=float, default=3e-4, help="learning rate")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.data), exist_ok=True)
    n = build_training_set(args.data)
    print(f"training set: {n} examples -> {args.data}")
    if n < 50:
        print("need >= 50 confirmed extractions before fine-tuning is worthwhile")
        return
    if not args.build_only:
        finetune(args.data, args.out, model_id=args.model, epochs=args.epochs, batch_size=args.batch_size, lr=args.lr)


if __name__ == "__main__":
    main()


