"""One-off dedupe: the realistic corpus was ingested twice (an older batch without the
SYNTHETIC filename suffix, then the current provenance-marked batch). Removes the older,
unsuffixed duplicates and all child rows (chunks, extraction runs/fields/items).

Dry-run by default; pass --apply to delete.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from sqlalchemy import text

from app.db import SessionLocal

# old generator wrote titles like "04-08-2026-MINE_I-SHIFT-REPORT" and
# "geological_report_Garjanbahal_BH01" (no -SYNTHETIC marker)
DUP_LIKES = ["%-MINE_I-SHIFT-REPORT", "%-MINE_II-SHIFT-REPORT", "geological_report_%_BH%"]


def find_dupes(db):
    conds = " OR ".join(["d.title LIKE :p%d" % i for i in range(len(DUP_LIKES))])
    params = {("p%d" % i): pat for i, pat in enumerate(DUP_LIKES)}
    rows = db.execute(
        text(
            f"SELECT d.id, d.title FROM documents d WHERE ({conds}) "
            "AND d.title NOT LIKE '%SYNTHETIC%'"
        ),
        params,
    ).all()
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually delete (default: dry run)")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        dupes = find_dupes(db)
        print(f"found {len(dupes)} duplicate docs (older, unsuffixed)")
        if not dupes:
            return
        if not args.apply:
            for _id, title in dupes[:5]:
                print("  e.g.", title)
            print("dry run - pass --apply to delete")
            return

        total_chunks = 0
        for doc_id, title in dupes:
            n = db.execute(text("DELETE FROM chunks WHERE document_id = :i"), {"i": doc_id}).rowcount
            total_chunks += n
            db.execute(text("DELETE FROM extraction_fields WHERE document_id = :i"), {"i": doc_id})
            db.execute(text("DELETE FROM extraction_runs WHERE document_id = :i"), {"i": doc_id})
            db.execute(text("DELETE FROM documents WHERE id = :i"), {"i": doc_id})
        db.commit()
        print(f"deleted {len(dupes)} docs and {total_chunks} chunks")
    finally:
        db.close()


if __name__ == "__main__":
    main()
