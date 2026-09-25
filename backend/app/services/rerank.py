from ..config import settings

_model = None


def _load():
    global _model
    if _model is None:
        from sentence_transformers import CrossEncoder

        _model = CrossEncoder(settings.reranker_model)
    return _model


def available() -> bool:
    try:
        _load()
        return True
    except Exception:
        return False


def rerank(query: str, hits: list[dict], top_k: int = 8) -> list[dict]:
    """Cross-encoder rerank of hybrid-search hits. Falls back to retrieval order if unavailable."""
    if not settings.reranker_enabled or not hits:
        return hits[:top_k]
    try:
        model = _load()
    except Exception:
        return hits[:top_k]
    pairs = [[query, h["text"]] for h in hits]
    scores = model.predict(pairs)
    ranked = sorted(zip(scores, hits, strict=False), key=lambda x: -float(x[0]))
    out = []
    for score, h in ranked[:top_k]:
        h = dict(h)
        h["rerank_score"] = round(float(score), 4)
        out.append(h)
    return out
