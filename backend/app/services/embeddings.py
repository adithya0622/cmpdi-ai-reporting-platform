import threading

import torch
from transformers import AutoModel, AutoTokenizer

from ..config import settings

DIM = 384

_model = None
_tokenizer = None
_lock = threading.Lock()

# e5 models expect a task prefix; mismatched prefixes degrade retrieval quality
_PREFIX_PASSAGE = "passage: "
_PREFIX_QUERY = "query: "
_MAX_LEN = 512
_BATCH = 32


def _load():
    """Load once, process-wide. Raises on failure; callers degrade gracefully."""
    global _model, _tokenizer
    with _lock:
        if _model is None:
            _tokenizer = AutoTokenizer.from_pretrained(settings.embedding_model)
            model = AutoModel.from_pretrained(settings.embedding_model)
            model.eval()
            torch.set_num_threads(max(1, (torch.get_num_threads() or 1)))
            _model = model
    return _model, _tokenizer


def _encode(texts: list[str]) -> list[list[float]]:
    model, tokenizer = _load()
    out: list[list[float]] = []
    for i in range(0, len(texts), _BATCH):
        batch = tokenizer(
            texts[i : i + _BATCH],
            padding=True,
            truncation=True,
            max_length=_MAX_LEN,
            return_tensors="pt",
        )
        with torch.no_grad():
            hidden = model(**batch).last_hidden_state
        mask = batch["attention_mask"].unsqueeze(-1).to(hidden.dtype)
        emb = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-9)
        emb = torch.nn.functional.normalize(emb, p=2, dim=1)
        out.extend(emb.tolist())
    return out


def embed(texts: list[str]) -> list[list[float]] | None:
    """Embed passages. Returns None if the model is unavailable (offline / not downloaded)."""
    try:
        return _encode([_PREFIX_PASSAGE + t for t in texts])
    except Exception:
        return None


def embed_query(text: str) -> list[float] | None:
    try:
        return _encode([_PREFIX_QUERY + text])[0]
    except Exception:
        return None
