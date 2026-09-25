import datetime
import os
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import text as sqltext

from ..auth import require_min_role, scoped_subsidiary
from ..config import settings
from ..db import SessionLocal
from ..services import jobs

router = APIRouter(prefix="/documents", tags=["documents"])

MAX_UPLOAD = 200 * 1024 * 1024


@router.post("/upload")
def upload(
    file: UploadFile = File(...),
    title: str = Form(""),
    doc_type: str = Form("other"),
    subsidiary: str = Form(""),
    doc_year: int | None = Form(None),
    doc_date: str | None = Form(None),
    user=Depends(require_min_role("analyst")),
):
    data = file.file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(status_code=413, detail="file too large (max 200MB)")
    parsed_date = None
    if doc_date:
        try:
            parsed_date = datetime.date.fromisoformat(doc_date)
        except ValueError as e:
            raise HTTPException(status_code=400, detail="doc_date must be YYYY-MM-DD") from e
    up_dir = os.path.join(settings.data_dir, "uploads")
    os.makedirs(up_dir, exist_ok=True)
    fname = f"{uuid.uuid4().hex}_{os.path.basename(file.filename or 'upload')}"
    path = os.path.join(up_dir, fname)
    with open(path, "wb") as fh:
        fh.write(data)
    job_id = jobs.enqueue(
        "ingest_document",
        {
            "path": path,
            "filename": file.filename or "upload",
            "title": title,
            "doc_type": doc_type,
            "subsidiary": subsidiary,
            "doc_year": doc_year,
            "doc_date": parsed_date.isoformat() if parsed_date else "",
        },
    )
    from ..services.audit import log as audit_log

    audit_log("upload", user.username, {"file": file.filename, "subsidiary": subsidiary, "doc_year": doc_year, "doc_date": doc_date})
    return {"job_id": str(job_id), "status": "queued"}


@router.get("")
def list_documents(
    subsidiary: str = "",
    doc_type: str = "",
    limit: int = 100,
    offset: int = 0,
    user=Depends(require_min_role("viewer")),
):
    subsidiary = scoped_subsidiary(user, subsidiary)
    db = SessionLocal()
    try:
        q = "SELECT id, title, doc_type, subsidiary, doc_year, doc_date, status, created_at FROM documents WHERE 1=1"
        params: dict = {"limit": limit, "offset": offset}
        if subsidiary:
            q += " AND subsidiary = :sub"
            params["sub"] = subsidiary
        if doc_type:
            q += " AND doc_type = :dt"
            params["dt"] = doc_type
        q += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
        rows = db.execute(sqltext(q), params).mappings().all()
        return [dict(r) for r in rows]
    finally:
        db.close()
