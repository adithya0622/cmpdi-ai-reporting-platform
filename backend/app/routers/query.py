import json
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..auth import require_min_role, scoped_subsidiary
from ..db import SessionLocal, get_engine
from ..schemas import QueryIn
from ..services import llm, rag

router = APIRouter(prefix="/query", tags=["query"])


def _dedupe_sources(sources: list | None) -> list:
    """Collapse repeated (title, page) citations so answers never show the same
    source twice."""
    seen: set[tuple] = set()
    out = []
    for s in sources or []:
        key = (s.get("title"), s.get("page"))
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


@router.post("")
def query(body: QueryIn, user=Depends(require_min_role("viewer"))):
    t0 = time.time()
    sub = scoped_subsidiary(user, body.subsidiary)
    result = rag.answer(body.question, sub, history=body.history)
    result["sources"] = _dedupe_sources(result.get("sources"))
    latency_ms = int((time.time() - t0) * 1000)
    result["latency_ms"] = latency_ms
    ql_id = rag.log_query(
        body.question,
        result.get("answer", ""),
        result.get("sources", []),
        username=user.username if user else "",
        subsidiary=sub,
        latency_ms=latency_ms,
        mode=result.get("mode", ""),
        grounded_pct=result.get("grounded_pct"),
    )
    if ql_id is not None:
        result["query_log_id"] = ql_id
    return result


@router.post("/stream")
def query_stream(body: QueryIn, user=Depends(require_min_role("viewer"))):
    """SSE stream: sources event, then token events, then a final done event with the
    complete result (answer, grounding) for logging/history. Non-RAG question types
    arrive as a single done event, same shape as POST /query."""
    sub = scoped_subsidiary(user, body.subsidiary)

    def gen():
        t0 = time.time()
        final = None
        try:
            for ev in rag.rag_stream(body.question, sub, history=body.history):
                if ev["type"] == "done":
                    final = ev["result"]
                yield f"data: {json.dumps(ev, default=str)}\n\n"
        finally:
            if final:
                latency_ms = int((time.time() - t0) * 1000)
                final["latency_ms"] = latency_ms
                final["sources"] = _dedupe_sources(final.get("sources"))
                ql_id = rag.log_query(
                    body.question,
                    final.get("answer", ""),
                    final.get("sources", []),
                    username=user.username if user else "",
                    subsidiary=sub,
                    latency_ms=latency_ms,
                    mode=final.get("mode", ""),
                    grounded_pct=final.get("grounded_pct"),
                )
                if ql_id is not None:
                    yield f"data: {json.dumps({'type': 'query_log_id', 'id': ql_id})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


class FeedbackIn(BaseModel):
    rating: int  # 1 = helpful, -1 = unhelpful
    comment: str = ""


@router.post("/{query_id}/feedback")
def submit_feedback(query_id: int, body: FeedbackIn, user=Depends(require_min_role("viewer"))):
    if body.rating not in (1, -1):
        raise HTTPException(status_code=400, detail="rating must be 1 or -1")
    from ..models import QueryLog
    db = SessionLocal()
    try:
        ql = db.get(QueryLog, query_id)
        if ql is None:
            raise HTTPException(status_code=404, detail="query not found")
        ql.rating = body.rating
        ql.feedback_text = body.comment[:1000] if body.comment else None
        db.commit()
        return {"id": query_id, "rating": body.rating}
    finally:
        db.close()


@router.get("/health")
def health(_user=Depends(require_min_role("viewer"))):
    db_ok = True
    try:
        with get_engine().connect() as conn:
            conn.exec_driver_sql("SELECT 1")
    except Exception:
        db_ok = False
    return {"db": db_ok, "llm": llm.available()}
