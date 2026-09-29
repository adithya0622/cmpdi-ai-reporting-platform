import datetime
import time
import uuid

from sqlalchemy import text as sqltext

from ..db import SessionLocal, get_engine
from ..models import Job


def enqueue(kind: str, payload: dict, priority: int = 0) -> uuid.UUID:
    db = SessionLocal()
    try:
        job = Job(kind=kind, payload=payload, status="queued", priority=priority)
        db.add(job)
        db.commit()
        return job.id
    finally:
        db.close()


def claim() -> Job | None:
    """Atomically claim the oldest queued job (safe for multiple workers)."""
    with get_engine().connect() as conn:
        row = conn.execute(
            sqltext(
                "UPDATE jobs SET status = 'running', updated_at = CURRENT_TIMESTAMP "
                "WHERE id = (SELECT id FROM jobs WHERE status = 'queued' ORDER BY priority DESC, created_at LIMIT 1 FOR UPDATE SKIP LOCKED) "
                "RETURNING id"
            )
        ).first()
        conn.commit()
    if not row:
        return None
    db = SessionLocal()
    try:
        return db.get(Job, row[0])
    finally:
        db.close()


def execute(job: Job) -> None:
    from . import extraction, ingest

    try:
        if job.kind == "ingest_document":
            p = job.payload
            doc_date = None
            if p.get("doc_date"):
                try:
                    doc_date = datetime.date.fromisoformat(p["doc_date"])
                except ValueError:
                    doc_date = None
            with open(p["path"], "rb") as fh:
                data = fh.read()
            ingest.index_document(
                p["filename"], data,
                title=p.get("title", ""), doc_type=p.get("doc_type", "other"),
                subsidiary=p.get("subsidiary", ""), doc_year=p.get("doc_year"),
                doc_date=doc_date, source_path=p["path"],
            )
        elif job.kind == "extract_run":
            extraction.execute_run(uuid.UUID(job.payload["run_id"]))
        else:
            raise ValueError(f"unknown job kind: {job.kind}")
        _finish(job.id, "done")
    except Exception as e:
        _finish(job.id, "failed", str(e)[:2000])


def _finish(job_id: uuid.UUID, status: str, error: str = "") -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        job.status = status
        job.error = error
        db.commit()
        _notify_completion(job.kind, status, error, job.payload)
    finally:
        db.close()


def _notify_completion(kind: str, status: str, error: str, payload: dict) -> None:
    try:
        from . import notifications
        if status == "failed":
            notifications.notify(
                "job_failed",
                f"Job failed: {kind}",
                f"Job {kind} failed with error: {error[:500]}",
                {"kind": kind, "error": error[:500], "payload": payload},
            )
        elif kind == "extract_run" and status == "done":
            notifications.notify(
                "extraction_complete",
                f"Extraction complete: {payload.get('run_id', '')}",
                "Extraction run completed successfully.",
                {"kind": kind, "run_id": payload.get("run_id")},
            )
    except Exception:
        pass


def run_worker(poll_seconds: float = 2.0, once: bool = False) -> None:
    while True:
        job = claim()
        if job:
            print(f"[worker] running {job.kind} {job.id}")
            execute(job)
            print(f"[worker] finished {job.id}")
            continue
        if once:
            return
        time.sleep(poll_seconds)


def queue_stats() -> dict:
    db = SessionLocal()
    try:
        rows = db.execute(sqltext("SELECT status, COUNT(*) FROM jobs GROUP BY status")).fetchall()
        return {r[0]: r[1] for r in rows}
    finally:
        db.close()


def requeue(job_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        job.status = "queued"
        job.error = None
        db.commit()
    finally:
        db.close()
