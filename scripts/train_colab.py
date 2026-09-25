"""
Google Colab / Kaggle / GPU Cloud One-Click Fine-Tuning Script for CMPDI Qwen 2.5 3B.

Usage in Google Colab (with free T4 GPU):
1. Set runtime to GPU: Runtime -> Change runtime type -> T4 GPU
2. Upload this file and train.jsonl
3. Run:
   !pip install -q torch transformers peft datasets trl bitsandbytes accelerate
   !python train_colab.py --data train.jsonl --out adapter
4. Download the 'adapter' folder and place it in 'data/finetune/adapter' on your local system!
"""

import argparse
import json
import os
import sys

def main():
    parser = argparse.ArgumentParser(description="One-Click Fine-Tuning for Qwen 2.5 3B (CMPDI/CIL)")
    parser.add_argument("--data", default="train.jsonl", help="path to train.jsonl")
    parser.add_argument("--out", default="adapter", help="output directory for LoRA adapter")
    parser.add_argument("--epochs", type=int, default=3, help="number of epochs")
    parser.add_argument("--batch-size", type=int, default=2, help="batch size")
    parser.add_argument("--lr", type=float, default=2e-4, help="learning rate")
    args = parser.parse_args()

    try:
        import torch
        from datasets import Dataset
        from peft import LoraConfig, TaskType, get_peft_model
        from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments, BitsAndBytesConfig
        from trl import SFTTrainer
    except ImportError:
        print("Required libraries missing. Installing now...")
        os.system("pip install -q torch transformers peft datasets trl bitsandbytes accelerate")
        import torch
        from datasets import Dataset
        from peft import LoraConfig, TaskType, get_peft_model
        from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments, BitsAndBytesConfig
        from trl import SFTTrainer

    if not torch.cuda.is_available():
        print("ERROR: CUDA GPU not detected. Ensure runtime is set to GPU (T4 / V100 / A100).")
        sys.exit(1)

    print(f"[+] CUDA GPU detected: {torch.cuda.get_device_name(0)}")
    print(f"[+] Training data: {args.data}")
    print(f"[+] Target output: {args.out}")

    model_id = "Qwen/Qwen2.5-3B-Instruct"
    print(f"[*] Loading tokenizer for {model_id}...")
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    print(f"[*] Loading model with 4-bit quantization (QLoRA) for maximum memory efficiency...")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
        bnb_4bit_use_double_quant=True,
    )

    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )

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

    print("[*] Formatting examples into ChatML...")
    formatted_data = []
    with open(args.data, "r", encoding="utf-8") as fh:
        for line in fh:
            item = json.loads(line)
            text_content = item.get("text", "")
            fields = item.get("fields", {})
            if not fields:
                continue

            system_msg = (
                "You are CMPDI's expert geological and mining document extraction engine. "
                "Extract all verified production figures, borehole reserves, depths, and operational metrics into structured JSON."
            )
            chat = [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": f"Extract structured figures from this document text:\n\n{text_content}"},
                {"role": "assistant", "content": json.dumps(fields, ensure_ascii=False, indent=2)},
            ]
            formatted_text = tokenizer.apply_chat_template(chat, tokenize=False)
            formatted_data.append({"text": formatted_text})

    dataset = Dataset.from_list(formatted_data)
    print(f"[+] Loaded {len(dataset)} training examples.")

    training_args = TrainingArguments(
        output_dir="./results",
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=4,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=0.05,
        logging_steps=5,
        save_strategy="epoch",
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        optim="paged_adamw_8bit",
        report_to="none",
    )

    trainer = SFTTrainer(
        model=model,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=4096,
        tokenizer=tokenizer,
        args=training_args,
    )

    print("[*] Training LoRA adapter...")
    trainer.train()

    print(f"[+] Saving fine-tuned adapter to {args.out}...")
    os.makedirs(args.out, exist_ok=True)
    model.save_pretrained(args.out)
    tokenizer.save_pretrained(args.out)

    # Zip output for easy download from Colab
    os.system(f"zip -r {args.out}.zip {args.out}")
    print(f"[SUCCESS] Training complete! Download '{args.out}.zip' and copy files to 'data/finetune/adapter'.")

if __name__ == "__main__":
    main()
