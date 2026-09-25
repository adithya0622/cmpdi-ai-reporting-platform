import datetime
import io
import os
import re
import uuid

from ..config import settings
from ..db import SessionLocal
from ..models import Chunk, Document
from . import embeddings

# filename prefixes of operational reports, e.g. "M-1 STOPPAGE on 07.09.2026.pdf"
_STOPPAGE_FILE_RE = re.compile(r"stoppage", re.IGNORECASE)
_SHIFT_FILE_RE = re.compile(r"(relay|shift)", re.IGNORECASE)
_DATE_STEM_RE = re.compile(r"\b(\d{1,2})[.\-\/](\d{1,2})[.\-\/](\d{4})\b")


def parse_filename_date(filename: str) -> datetime.date | None:
    """DD.MM.YYYY / DD-MM-YYYY / DD/MM/YYYY anywhere in the filename."""
    m = _DATE_STEM_RE.search(os.path.basename(filename or ""))
    if not m:
        return None
    try:
        return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def infer_doc_type(filename: str, first_page_text: str = "") -> str:
    """Doc type from filename or first-page content; 'other' when unsure."""
    name = (filename or "").lower()
    page = (first_page_text or "").lower()
    if _STOPPAGE_FILE_RE.search(filename or "") or "stoppage report" in page:
        return "stoppage_report"
    if _SHIFT_FILE_RE.search(filename or ""):
        return "daily_shift_report"
    if "production" in name or "production report" in page:
        return "production_report"
    if "geological" in name or "borehole" in name or "borehole" in page:
        return "geological"
    if "question" in name or "lok sabha" in name or "rajya sabha" in name:
        return "parliamentary_q"
    return "other"


def extract_pages(filename: str, data: bytes) -> list[tuple[int, str]]:
    """Return [(page_no, text)]. Scanned PDF pages and images fall back to OCR."""
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".pdf":
        return _pdf_pages(data)
    if ext == ".docx":
        import docx

        d = docx.Document(io.BytesIO(data))
        return [(1, "\n".join(p.text for p in d.paragraphs if p.text.strip()))]
    if ext in (".xlsx", ".xls"):
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        pages = []
        for i, ws in enumerate(wb.worksheets, 1):
            rows = [", ".join("" if c is None else str(c) for c in row) for row in ws.iter_rows(values_only=True)]
            pages.append((i, "\n".join(r for r in rows if r.strip())))
        return pages
    if ext in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"):
        return [(1, _ocr_image(data))]
    if ext in (".txt", ".md", ".csv"):
        return [(1, data.decode("utf-8", errors="replace"))]
    raise ValueError(f"unsupported file type: {ext}")


def _render_table(table: list[list]) -> str:
    """pdfplumber table -> aligned text block; None cells become ''."""
    rows = [["" if c is None else str(c).strip() for c in row] for row in table]
    rows = [r for r in rows if any(r)]
    if not rows:
        return ""
    widths = [max(len(r[c]) if c < len(r) else 0 for r in rows) for c in range(max(len(r) for r in rows))]
    return "\n".join(" | ".join((r[c] if c < len(r) else "").ljust(widths[c]) for c in range(len(widths))).rstrip() for r in rows)


def _pdf_pages(data: bytes) -> list[tuple[int, str]]:
    import pdfplumber

    pages = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            txt = page.extract_text() or ""
            tables = page.extract_tables() or []
            rendered = "\n\n".join(filter(None, (_render_table(t) for t in tables)))
            # tables win when present (column alignment survives; raw text flow scrambles rows)
            if rendered:
                txt = f"{txt}\n\n[TABLE]\n{rendered}" if txt else rendered
            if len(txt.strip()) < 20:
                img = page.to_image(resolution=300).original
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                txt = _ocr_safe(buf.getvalue(), i)
            pages.append((i, txt))
    return pages


def _ocr_image(data: bytes) -> str:
    import pytesseract
    from PIL import Image

    return pytesseract.image_to_string(Image.open(io.BytesIO(data)), lang=settings.ocr_lang)


def _ocr_safe(data: bytes, page_no: int) -> str:
    """OCR with graceful degradation: a missing/failed Tesseract must not kill ingestion
    of an otherwise-readable document - text pages still index, scanned pages are flagged."""
    try:
        return _ocr_image(data)
    except Exception as e:
        print(f"[warn] OCR unavailable on page {page_no} ({e.__class__.__name__}: {str(e)[:80]}) - marking for manual review")
        return "[scanned page - OCR unavailable - manual review needed]"


def chunk_text(text: str, size: int | None = None, overlap: int | None = None) -> list[str]:
    """Heading/table-aware chunking: blank-line-separated blocks packed into chunks; table rows
    (single-newline separated) stay together. Oversized blocks fall back to sliding window."""
    import re

    size = size or settings.chunk_size
    overlap = overlap if overlap is not None else settings.chunk_overlap
    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    chunks: list[str] = []
    cur = ""
    for b in blocks:
        if len(b) > size:
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.extend(_window(b, size, overlap))
            continue
        if cur and len(cur) + len(b) + 2 > size:
            chunks.append(cur)
            cur = b
        else:
            cur = f"{cur}\n\n{b}" if cur else b
    if cur:
        chunks.append(cur)
    return [c for c in chunks if c]


def _window(text: str, size: int, overlap: int) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            cut = text.rfind("\n", start + size // 2, end)
            if cut > start:
                end = cut
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [c for c in chunks if c]


def index_document(
    filename: str,
    data: bytes,
    title: str = "",
    doc_type: str = "other",
    subsidiary: str = "",
    doc_year: int | None = None,
    doc_date: datetime.date | None = None,
    source_path: str = "",
    meta_extra: dict | None = None,
) -> uuid.UUID:
    pages = extract_pages(filename, data)
    first_page = pages[0][1] if pages else ""
    if doc_type == "other":
        doc_type = infer_doc_type(filename, first_page)
    if doc_date is None:
        doc_date = parse_filename_date(filename)
    if doc_date is not None and doc_year is None:
        doc_year = doc_date.year
    db = SessionLocal()
    try:
        doc = Document(
            title=title or filename,
            doc_type=doc_type,
            subsidiary=subsidiary,
            doc_year=doc_year,
            doc_date=doc_date,
            source_path=source_path or filename,
            meta=dict(meta_extra or {}),
            status="indexing",
        )
        db.add(doc)
        db.flush()
        for page_no, ptext in pages:
            for chunk in chunk_text(ptext):
                db.add(Chunk(document_id=doc.id, page=page_no, text=chunk))
        doc_id = doc.id
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    _add_embeddings(doc_id)
    return doc_id


def _add_embeddings(doc_id: uuid.UUID) -> None:
    """Second pass so ingestion succeeds even when the embedding model is unavailable."""
    if not settings.vector_enabled:
        db = SessionLocal()
        try:
            db.query(Document).filter(Document.id == doc_id).update({"status": "indexed"})
            db.commit()
        finally:
            db.close()
        return
    db = SessionLocal()
    try:
        doc = db.get(Document, doc_id)
        chunks = db.query(Chunk).filter(Chunk.document_id == doc_id, Chunk.embedding.is_(None)).all()
        if not chunks:
            doc.status = "indexed"
            db.commit()
            return
        vecs = embeddings.embed([c.text for c in chunks])
        if vecs is None:
            doc.status = "indexed_no_embeddings"
        else:
            for c, v in zip(chunks, vecs, strict=False):
                c.embedding = v
            doc.status = "indexed"
        db.commit()
    finally:
        db.close()
