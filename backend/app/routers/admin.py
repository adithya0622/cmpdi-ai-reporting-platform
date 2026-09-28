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
        feedback_up = db.execute(sqltext("SELECT COUNT(*) FROM query_log WHERE rating = 1")).scalar() or 0
        feedback_down = db.execute(sqltext("SELECT COUNT(*) FROM query_log WHERE rating = -1")).scalar() or 0
        total_queries = db.execute(sqltext("SELECT COUNT(*) FROM query_log")).scalar() or 0
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
        "feedback": {"positive": feedback_up, "negative": feedback_down, "total_queries": total_queries},
    }


@router.get("/data_quality")
def data_quality(_user=Depends(require_min_role("admin"))):
    """Data-quality monitor: anomalies caught by validation, review-queue state, and
    the latest integrity scrubs - makes the validation story visible in the demo."""
    db = SessionLocal()
    try:
        review_fields = db.execute(
            sqltext("SELECT COUNT(*) FROM extraction_fields WHERE status = 'review'")
        ).scalar()
        anomalies = db.execute(
            sqltext(
                "SELECT ef.field_name, ef.value_num, ef.unit, ef.confidence, d.title, d.subsidiary "
                "FROM extraction_fields ef JOIN documents d ON d.id = ef.document_id "
                "WHERE ef.status = 'review' "
                "ORDER BY ef.confidence ASC LIMIT 20"
            )
        ).mappings().all()
        junk_subs = db.execute(
            sqltext(
                "SELECT COUNT(*) FROM extraction_fields "
                "WHERE subsidiary LIKE '%>>%' OR subsidiary LIKE '%2>&1%'"
            )
        ).scalar()
        doc_status = db.execute(
            sqltext("SELECT status, COUNT(*) AS n FROM documents GROUP BY status ORDER BY n DESC")
        ).mappings().all()
        return {
            "fields_awaiting_review": review_fields,
            "junk_subsidiary_values": junk_subs,
            "document_status": [dict(r) for r in doc_status],
            "flagged_anomalies": [dict(r) for r in anomalies],
        }
    finally:
        db.close()


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
                "SELECT id, ts, username, question, subsidiary, latency_ms, grounded_pct, mode, rating "
                "FROM query_log ORDER BY ts DESC LIMIT :l"
            ),
            {"l": limit},
        ).mappings().all()
        return [dict(r) for r in rows]
    finally:
        db.close()
