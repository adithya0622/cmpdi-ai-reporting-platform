import time

from fastapi import APIRouter, Depends

from ..auth import require_min_role, scoped_subsidiary
from ..db import get_engine
from ..schemas import QueryIn
from ..services import llm, rag

router = APIRouter(prefix="/query", tags=["query"])


@router.post("")
def query(body: QueryIn, user=Depends(require_min_role("viewer"))):
    t0 = time.time()
    sub = scoped_subsidiary(user, body.subsidiary)
    result = rag.answer(body.question, sub, history=body.history)
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


@router.get("/health")
def health(_user=Depends(require_min_role("viewer"))):
    db_ok = True
    try:
        with get_engine().connect() as conn:
            conn.exec_driver_sql("SELECT 1")
    except Exception:
        db_ok = False
    return {"db": db_ok, "llm": llm.available()}
