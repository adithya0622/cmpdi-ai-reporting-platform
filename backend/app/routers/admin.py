import uuid as uuidlib

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text as sqltext

from ..auth import require_min_role
from ..db import SessionLocal
from ..models import Document, User
from ..services import jobs, llm

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/overview")
def overview(_user=Depends(require_min_role("admin"))):
    db = SessionLocal()
    try:
        users = db.query(User).count()
        docs = db.query(Document).count()
        indexed = db.query(Document).filter(Document.status.like("indexed%")).count()
        pending_runs = db.execute(sqltext("SELECT COUNT(*) FROM extraction_runs WHERE status IN ('queued','running')")).scalar()
        review_fields = db.execute(sqltext("SELECT COUNT(*) FROM extraction_fields WHERE status = 'review'")).scalar()
        gold = 0
        try:
            import os

            gold_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "evals", "gold_set.jsonl")
            if os.path.exists(gold_path):
                with open(gold_path, "r", encoding="utf-8") as fh:
                    gold = sum(1 for line in fh if line.strip() and not line.startswith("#"))
        except Exception:
            pass
    finally:
        db.close()
    return {
        "users": users,
        "documents": docs,
        "documents_indexed": indexed,
        "extraction_runs_pending": pending_runs,
        "fields_awaiting_review": review_fields,
        "gold_entries": gold,
        "jobs": jobs.queue_stats(),
        "db": True,
        "llm": llm.available(),
    }


@router.get("/jobs")
def list_jobs(limit: int = 100, _user=Depends(require_min_role("admin"))):
    db = SessionLocal()
    try:
        rows = db.execute(
            sqltext("SELECT id, kind, status, error, created_at FROM jobs ORDER BY created_at DESC LIMIT :l"),
            {"l": limit},
        ).mappings().all()
        return [dict(r) for r in rows]
    finally:
        db.close()


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: str, _user=Depends(require_min_role("admin"))):
    try:
        jid = uuidlib.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid job id")
    jobs.requeue(jid)
    from ..services.audit import log as audit_log

    audit_log("job_retry", _user.username, {"job_id": job_id})
    return {"id": job_id, "status": "queued"}


@router.get("/audit")
def audit_log(limit: int = 100, _user=Depends(require_min_role("admin"))):
    db = SessionLocal()
    try:
        rows = db.execute(
            sqltext("SELECT id, ts, username, action, detail FROM audit_log ORDER BY ts DESC LIMIT :l"),
            {"l": limit},
        ).mappings().all()
        return [dict(r) for r in rows]
    finally:
        db.close()


@router.get("/queries")
def query_log(limit: int = 100, _user=Depends(require_min_role("admin"))):
    db = SessionLocal()
    try:
        rows = db.execute(
            sqltext(
                "SELECT id, ts, username, question, subsidiary, latency_ms, grounded_pct, mode "
                "FROM query_log ORDER BY ts DESC LIMIT :l"
            ),
            {"l": limit},
        ).mappings().all()
        return [dict(r) for r in rows]
    finally:
        db.close()
