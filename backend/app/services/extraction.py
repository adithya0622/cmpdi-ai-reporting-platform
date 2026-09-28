import contextlib
import datetime
import re
import uuid

from ..config import settings
from ..db import SessionLocal
from ..extraction_schemas import (
    expand_items,
    field_unit,
    get_schema,
    parse_extraction,
    parse_report_date,
)
from ..models import Chunk, Document, ExtractionField, ExtractionRun
from . import llm, validation


SUBSIDIARY_CANONICAL: dict[str, str] = {
    "eastern coalfields": "ECL", "eastern coalfields limited": "ECL", "ecl": "ECL",
    "bharat coking coal": "BCCL", "bharat coking coal limited": "BCCL", "bccl": "BCCL",
    "central coalfields": "CCL", "central coalfields limited": "CCL", "ccl": "CCL",
    "northern coalfields": "NCL", "northern coalfields limited": "NCL", "ncl": "NCL",
    "western coalfields": "WCL", "western coalfields limited": "WCL", "wcl": "WCL",
    "south eastern coalfields": "SECL", "south eastern coalfields limited": "SECL", "secl": "SECL",
    "mahanadi coalfields": "MCL", "mahanadi coalfields limited": "MCL", "mcl": "MCL",
    "neyveli lignite": "NLC", "neyveli lignite corporation": "NLC", "nlc india": "NLC", "nlc": "NLC",
    "coal india": "CIL", "coal india limited": "CIL", "cil": "CIL",
    "cmpdi": "CMPDI", "central mine planning": "CMPDI",
    "central mine planning and design institute": "CMPDI",
}


def normalize_subsidiary(name: str) -> str:
    if not name:
        return ""
    return SUBSIDIARY_CANONICAL.get(name.strip().lower(), name.strip())


def _clean_subsidiary(raw) -> str:
    """Sanitize LLM-extracted subsidiary values before storing: cap length, drop
    shell-redirect junk (e.g. '1>>D:\\...log 2>&1' leaked from a mis-quoted command),
    and keep only plausible short org-name tokens."""
    s = str(raw or "").strip()
    if not s or len(s) > 40 or any(m in s for m in (">>", "<<", "2>&1", ".log", ":\\", "/mnt/", "--")):
        return ""
    return normalize_subsidiary(s)


def _to_doc_date(text: str, report_date: str) -> datetime.date | None:
    """Best-effort doc date: DD.MM.YYYY found in text or the extracted report_date field."""
    iso = parse_report_date(text) or parse_report_date(report_date or "")
    if not iso:
        iso = (report_date or "").strip()[:10]
    if not iso:
        return None
    try:
        return datetime.date.fromisoformat(iso)
    except ValueError:
        return None


# machine section headers in stoppage reports, e.g. "LBS/BWE-1029 / LIGNITE / TWH: 18.45 ..."
_MACHINE_HEADER_RE = re.compile(r"(?m)(?=^[A-Z]{2,4}/[A-Z]{2,}-\S+\s+/ )")
_TABLE_BLOCK_RE = re.compile(r"\n?\[TABLE\]\n.*?(?=\n\n|\Z)", re.DOTALL)


def _extract_stoppage_sectioned(text: str, schema: dict) -> dict:
    """Stoppage reports repeat the same table per machine; one big LLM call loses machines.
    Split on machine headers and extract each section separately, then merge.
    Each section holds exactly ONE machine - keep the entry matching the header
    (or the first), so repeated/hallucinated entries per line cannot inflate totals."""
    clean = _TABLE_BLOCK_RE.sub("", text)  # raw text already contains the same rows
    headers = list(_MACHINE_HEADER_RE.finditer(clean))
    if len(headers) < 2:
        raw = _chat_json(schema, clean, 2048)
        return _parse_repaired(raw, "stoppage_report")

    preamble = clean[: headers[0].start()].strip()
    merged: list[dict] = []
    seen_ids: set[str] = set()
    base: dict = {}
    confs: list[float] = []
    for i, h in enumerate(headers):
        end = headers[i + 1].start() if i + 1 < len(headers) else len(clean)
        section = (preamble + "\n\n" + clean[h.start() : end]).strip()
        header_id = clean[h.start():].split(" ", 1)[0].rstrip("/").strip()
        raw = llm.chat(schema["prompt"] + "\n\nDocument text:\n" + section[:4000], max_tokens=1200)
        try:
            res = parse_extraction(raw, "stoppage_report")
        except ValueError:
            continue  # unparseable section - the others still count
        machines = res["fields"].get("machines") or []
        pick = next((m for m in machines if isinstance(m, dict) and str(m.get("machine_id", "")).strip() == header_id), None)
        if pick is None:
            pick = next((m for m in machines if isinstance(m, dict)), None)
        if pick is not None and pick.get("machine_id") and str(pick["machine_id"]) not in seen_ids:
            seen_ids.add(str(pick["machine_id"]))
            merged.append(pick)
        confs.append(float(res["confidence"].get("machines", 0.5) or 0.5))
        for k in ("report_date", "mine"):
            if res["fields"].get(k) and not base.get(k):
                base[k] = res["fields"][k]
    if not merged:
        raise ValueError("no machines extracted from any section")
    model = schema["model"]
    validated = model(**{k: v for k, v in {**base, "machines": merged}.items() if k in model.model_fields}).model_dump()
    return {"fields": validated, "confidence": {"report_date": 0.8, "mine": 0.8, "machines": min(confs) if confs else 0.5}}


# max document chars fed to the LLM in one call. 3B-model context is 8192 tokens;
# real government spreadsheets (Coal Directory chapters) are token-dense, so keep headroom
# for the prompt + generated JSON.
_XCHAR = 6000
_XCHAR_MIN = 2500
_REPAIR_SUFFIX = (
    "\n\nYour previous reply was not a single valid JSON object. "
    "Return ONLY one valid JSON object matching the requested schema - no prose, no code fences, no trailing text."
)


def _context_overflow(e: Exception) -> bool:
    s = str(e).lower()
    return "exceed" in s and ("context" in s or "token" in s)


def _chat_json(schema: dict, text: str, max_tokens: int) -> str:
    """LLM call with automatic input shrink when the request would overflow the context."""
    cap = _XCHAR
    while True:
        try:
            return llm.chat(schema["prompt"] + "\n\nDocument text:\n" + text[:cap], max_tokens=max_tokens)
        except Exception as e:
            if cap > _XCHAR_MIN and _context_overflow(e):
                cap = max(_XCHAR_MIN, cap // 2)
                continue
            raise


def _parse_repaired(raw: str, doc_type: str) -> dict:
    """Parse LLM output; on malformed JSON, one repair round-trip before giving up."""
    try:
        return parse_extraction(raw, doc_type)
    except ValueError:
        schema = get_schema(doc_type)
        fixed = llm.chat(
            "Fix this into ONE valid JSON object with keys 'fields' and 'confidence', matching the schema below."
            "\n\nSchema instructions:\n" + schema["prompt"]
            + "\n\nModel output to fix:\n" + raw[:6000],
            max_tokens=2048,
        )
        return parse_extraction(fixed, doc_type)


def extract_fields(text: str, doc_type: str) -> dict | None:
    """Pure LLM extraction (no DB). Returns {"fields": {...}, "confidence": {...}} or None if LLM unavailable."""
    schema = get_schema(doc_type)
    if not llm.available():
        return None
    if doc_type == "stoppage_report":
        return _extract_stoppage_sectioned(text, schema)
    raw = _chat_json(schema, text, 2048)
    return _parse_repaired(raw, doc_type)


def create_run(document_id: uuid.UUID, doc_type: str) -> uuid.UUID:
    get_schema(doc_type)
    db = SessionLocal()
    try:
        run = ExtractionRun(document_id=document_id, doc_type=doc_type, status="queued")
        db.add(run)
        db.commit()
        return run.id
    finally:
        db.close()


def execute_run(run_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        run = db.get(ExtractionRun, run_id)
        if run is None:
            return
        doc = db.get(Document, run.document_id)
        rows = db.query(Chunk).filter(Chunk.document_id == run.document_id).order_by(Chunk.page).all()
        full_text = "\n".join(r.text for r in rows)
        run.status = "running"
        db.commit()

        try:
            result = extract_fields(full_text, run.doc_type)
        except Exception as e:
            run.status = "failed"
            run.error = str(e)[:2000]
            db.commit()
            return
        if result is None:
            run.status = "failed"
            run.error = "LLM unavailable"
            db.commit()
            return

        fields = result["fields"]
        confidence = result["confidence"]
        records = expand_items(fields, confidence, run.doc_type)

        # new run supersedes unconfirmed fields of the same names; confirmed values are kept
        record_names = list({r["field_name"] for r in records})
        if record_names:
            db.query(ExtractionField).filter(
                ExtractionField.document_id == run.document_id,
                ExtractionField.field_name.in_(record_names),
                ExtractionField.status.in_(["auto", "review"]),
            ).delete(synchronize_session=False)
            db.flush()

        threshold = settings.confidence_threshold
        for rec in records:
            value = rec["value"]
            is_num = isinstance(value, (int, float)) and not isinstance(value, bool)
            db.add(
                ExtractionField(
                    run_id=run.id,
                    document_id=run.document_id,
                    field_name=rec["field_name"],
                    item=rec["item"][:200],
                    subsidiary=doc.subsidiary or _clean_subsidiary(fields.get("subsidiary")),
                    value_num=float(value) if is_num else None,
                    value_str=None if is_num else str(value),
                    unit=field_unit(rec["field_name"]),
                    confidence=rec["confidence"],
                    status="auto" if rec["confidence"] >= threshold else "review",
                )
            )
        db.flush()
        validation.flag_fields(db, run.document_id)

        if doc.doc_year is None and fields.get("year"):
            with contextlib.suppress(TypeError, ValueError):
                doc.doc_year = int(fields["year"])

        if doc.doc_date is None:
            doc.doc_date = _to_doc_date(full_text, str(fields.get("report_date") or ""))
            if doc.doc_date is not None and doc.doc_year is None:
                doc.doc_year = doc.doc_date.year

        run.status = "done"
        db.commit()
    finally:
        db.close()
