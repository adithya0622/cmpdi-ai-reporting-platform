import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from app.services.ingest import index_document, parse_filename_date

SUPPORTED = {".pdf", ".docx", ".xlsx", ".xls", ".txt", ".md", ".csv", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
YEAR_RE = re.compile(r"(19|20)\d{2}")

# filename -> doc_type hints for real corpus files whose type isn't inferable from content
DOC_TYPE_HINTS = [
    (re.compile(r"coal_directory|msg-|monthly|production", re.I), "production_report"),
    (re.compile(r"national_inventory|geological|borehole", re.I), "geological"),
    (re.compile(r"lok_sabha|rajya_sabha|parliamentary|_pq", re.I), "parliamentary_q"),
]


def main():
    if len(sys.argv) < 2:
        print("usage: python batch_ingest.py <folder> [subsidiary]")
        sys.exit(1)
    root = sys.argv[1]
    subsidiary = sys.argv[2] if len(sys.argv) > 2 else ""
    ok = failed = 0
    for dirpath, _, files in os.walk(root):
        for fn in files:
            path = os.path.join(dirpath, fn)
            ext = os.path.splitext(fn)[1].lower()
            if ext not in SUPPORTED:
                continue
            m = YEAR_RE.search(fn)
            year = int(m.group(0)) if m else None
            doc_date = parse_filename_date(fn)
            if doc_date is not None and year is None:
                year = doc_date.year
            doc_type = next((dt for pat, dt in DOC_TYPE_HINTS if pat.search(fn)), "other")
            try:
                with open(path, "rb") as f:
                    data = f.read()
                doc_id = index_document(
                    fn, data, subsidiary=subsidiary, doc_type=doc_type, doc_year=year, doc_date=doc_date,
                    source_path=os.path.relpath(path, root),
                )
                print(f"[ok] {path} -> {doc_id}")
                ok += 1
            except Exception as e:
                print(f"[failed] {path}: {e}")
                failed += 1
    print(f"done: {ok} ingested, {failed} failed")


if __name__ == "__main__":
    main()
