"""Bulk-extract all indexed documents. Idempotent: docs with a completed run for the
chosen doc_type are skipped.

Usage:
    python scripts/bulk_extract.py                # all docs, 3 parallel workers
    python scripts/bulk_extract.py --workers 2 --doc-types production_report,geological
"""
import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from app.db import SessionLocal
from app.models import Document, ExtractionRun
from app.services import extraction

# auto doc_type from document.doc_type when possible
DOC_TYPE_MAP = {
    "production_report": "production_report",
    "geological": "geological",
    "parliamentary_q": "parliamentary_q",
    "daily_shift_report": "daily_shift_report",
    "stoppage_report": "stoppage_report",
}


def pick_doc_type(doc: Document) -> str | None:
    if doc.doc_type in DOC_TYPE_MAP:
        return doc.doc_type
    title = doc.title.lower()
    if "production" in title:
        return "production_report"
    if "geological" in title or "borehole" in title:
        return "geological"
    if "question" in title or "lok sabha" in title:
        return "parliamentary_q"
    if "stoppage" in title:
        return "stoppage_report"
    if "relay" in title or "shift" in title:
        return "daily_shift_report"
    return None


def has_done_run(db, doc_id, doc_type) -> bool:
    return (
        db.query(ExtractionRun)
        .filter(ExtractionRun.document_id == doc_id, ExtractionRun.doc_type == doc_type, ExtractionRun.status == "done")
        .count()
        > 0
    )


def extract_one(doc_id, doc_type) -> tuple[str, str, str]:
    run_id = extraction.create_run(doc_id, doc_type)
    extraction.execute_run(run_id)
    db = SessionLocal()
    try:
        run = db.get(ExtractionRun, run_id)
        return str(doc_id), doc_type, run.status if run else "unknown"
    finally:
        db.close()


def main():
    ap = argparse.ArgumentParser(description="Bulk extraction over all indexed documents (idempotent)")
    ap.add_argument("--workers", type=int, default=3, help="parallel LLM extractions (default 3)")
    ap.add_argument("--doc-types", default="", help="comma-separated filter, e.g. production_report,geological")
    ap.add_argument("--limit", type=int, default=0, help="max documents (0 = all)")
    args = ap.parse_args()

    wanted = {t.strip() for t in args.doc_types.split(",") if t.strip()}
    db = SessionLocal()
    try:
        docs = db.query(Document).filter(Document.status.like("indexed%")).all()
        jobs = []
        for d in docs:
            dt = pick_doc_type(d)
            if not dt or (wanted and dt not in wanted):
                continue
            if has_done_run(db, d.id, dt):
                continue
            jobs.append((d.id, dt, d.title))
    finally:
        db.close()

    if args.limit:
        jobs = jobs[: args.limit]
    print(f"{len(jobs)} documents to extract (skipping already-done)")

    ok = failed = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(extract_one, doc_id, dt): (doc_id, dt, title) for doc_id, dt, title in jobs}
        for fut in as_completed(futures):
            _, dt, title = futures[fut]
            try:
                _, _, status = fut.result()
                if status == "done":
                    ok += 1
                    print(f"[ok] {status:7} {dt:20} {title[:60]}")
                else:
                    failed += 1
                    print(f"[!!] {status:7} {dt:20} {title[:60]}")
            except Exception as e:
                failed += 1
                print(f"[!!] error   {dt:20} {title[:60]}: {str(e)[:90]}")
    print(f"done: {ok} extracted, {failed} failed")


if __name__ == "__main__":
    main()
