import json
import time

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ..auth import require_min_role, scoped_subsidiary
from ..db import get_engine
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
    rag.log_query(
        body.question,
        result.get("answer", ""),
        result.get("sources", []),
        username=user.username if user else "",
        subsidiary=sub,
        latency_ms=latency_ms,
        mode=result.get("mode", ""),
        grounded_pct=result.get("grounded_pct"),
    )
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
                rag.log_query(
                    body.question,
                    final.get("answer", ""),
                    final.get("sources", []),
                    username=user.username if user else "",
                    subsidiary=sub,
                    latency_ms=latency_ms,
                    mode=final.get("mode", ""),
                    grounded_pct=final.get("grounded_pct"),
                )

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/health")
def health(_user=Depends(require_min_role("viewer"))):
    db_ok = True
    try:
        with get_engine().connect() as conn:
            conn.exec_driver_sql("SELECT 1")
    except Exception:
        db_ok = False
    return {"db": db_ok, "llm": llm.available()}
