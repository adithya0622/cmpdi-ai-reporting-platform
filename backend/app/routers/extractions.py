import uuid as uuidlib

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text as sqltext

from ..auth import require_min_role
from ..db import SessionLocal
from ..models import ExtractionField
from ..services import extraction, jobs, validation

router = APIRouter(prefix="/extractions", tags=["extractions"])


class RunIn(BaseModel):
    document_id: str
    doc_type: str


class ReviewIn(BaseModel):
    action: str  # "confirm" | "reject"
    value: float | str | None = None
    approved_by: str | None = None


@router.post("/run")
def run(body: RunIn, user=Depends(require_min_role("analyst"))):
    try:
        doc_id = uuidlib.UUID(body.document_id)
        run_id = extraction.create_run(doc_id, body.doc_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    from ..services.audit import log as audit_log

    jobs.enqueue("extract_run", {"run_id": str(run_id)})
    audit_log("extraction_run", user.username, {"document_id": body.document_id, "doc_type": body.doc_type})
    return {"run_id": str(run_id), "status": "queued"}


@router.get("/runs")
def list_runs(status: str = "", limit: int = 50, _user=Depends(require_min_role("viewer"))):
    db = SessionLocal()
    try:
        q = (
            "SELECT r.id, r.document_id, r.doc_type, r.status, r.error, r.created_at, d.title "
            "FROM extraction_runs r JOIN documents d ON d.id = r.document_id"
        )
        params: dict = {"l": limit}
        if status:
            q += " WHERE r.status = :st"
            params["st"] = status
        q += " ORDER BY r.created_at DESC LIMIT :l"
        return [dict(r) for r in db.execute(sqltext(q), params).mappings().all()]
    finally:
        db.close()


@router.get("/runs/{run_id}")
def get_run(run_id: str, _user=Depends(require_min_role("viewer"))):
    db = SessionLocal()
    try:
        run = db.execute(sqltext("SELECT * FROM extraction_runs WHERE id = :id"), {"id": run_id}).mappings().first()
        if not run:
            raise HTTPException(status_code=404, detail="run not found")
        fields = db.execute(
            sqltext(
                "SELECT id, field_name, value_num, value_str, unit, confidence, status "
                "FROM extraction_fields WHERE run_id = :id"
            ),
            {"id": run_id},
        ).mappings().all()
        return {"run": dict(run), "fields": [dict(f) for f in fields]}
    finally:
        db.close()


@router.get("/review")
def review_queue(_user=Depends(require_min_role("viewer"))):
    db = SessionLocal()
    try:
        rows = db.execute(
            sqltext(
                "SELECT f.id, f.field_name, f.item, f.value_num, f.value_str, f.unit, f.confidence, f.status, "
                "f.specified_by, f.approved_by, f.document_id, d.title, d.doc_type, d.specified_by AS doc_specified_by, d.approved_by AS doc_approved_by "
                "FROM extraction_fields f JOIN documents d ON d.id = f.document_id "
                "WHERE f.status = 'review' ORDER BY f.confidence ASC LIMIT 200"
            )
        ).mappings().all()
        return [dict(r) for r in rows]
    finally:
        db.close()


@router.post("/fields/{field_id}/review")
def review_field(field_id: int, body: ReviewIn, user=Depends(require_min_role("analyst"))):
    import datetime
    from ..models import Document
    from ..services.audit import log as audit_log

    db = SessionLocal()
    try:
        f = db.get(ExtractionField, field_id)
        if not f:
            raise HTTPException(status_code=404, detail="field not found")
        approver = (body.approved_by or "").strip() or f"{user.username} (Verified Officer)"
        if body.action == "reject":
            f.status = "rejected"
        elif body.action == "confirm":
            if isinstance(body.value, bool):
                raise HTTPException(status_code=400, detail="invalid value")
            if isinstance(body.value, (int, float)):
                f.value_num = float(body.value)
                f.value_str = None
            elif isinstance(body.value, str) and body.value.strip():
                f.value_str = body.value.strip()
            f.status = "confirmed"
            f.confidence = 1.0
            f.approved_by = approver
            
            # Synchronize to document
            doc = db.get(Document, f.document_id)
            if doc:
                doc.approved_by = approver
                doc.approved_at = datetime.datetime.now(datetime.timezone.utc)
                if not doc.meta:
                    doc.meta = {}
                doc.meta["approved_by"] = approver
        else:
            raise HTTPException(status_code=400, detail="action must be 'confirm' or 'reject'")
        db.commit()
        audit_log("review", user.username, {
            "field_id": field_id,
            "action": body.action,
            "value": body.value,
            "approved_by": approver,
        })
        return {"id": f.id, "status": f.status, "approved_by": f.approved_by}
    finally:
        db.close()


@router.get("/validation/totals")
def totals(field_name: str, year: int, _user=Depends(require_min_role("viewer"))):
    db = SessionLocal()
    try:
        result = validation.totals_crosscheck(field_name, year, db)
        if result is None:
            return {"consistent": None, "detail": "insufficient data for cross-check (need a CIL total + subsidiary entries)"}
        return result
    finally:
        db.close()
