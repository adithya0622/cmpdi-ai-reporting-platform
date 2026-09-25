import os
import sys
import json
from collections import Counter

sys.path.insert(0, os.path.abspath("backend"))

from app.db import SessionLocal
from app.models import Document, Chunk, ExtractionRun, ExtractionField, AuditLog, User
from sqlalchemy import func, text

def run_comprehensive_check():
    db = SessionLocal()
    print("=" * 80)
    print("COMPREHENSIVE DATA & PROBLEM STATEMENT AUDIT REPORT")
    print("=" * 80)

    # 1. Database Document Overview
    total_docs = db.query(Document).count()
    status_counts = dict(db.query(Document.status, func.count(Document.id)).group_by(Document.status).all())
    doc_types = dict(db.query(Document.doc_type, func.count(Document.id)).group_by(Document.doc_type).all())
    subsidiaries = dict(db.query(Document.subsidiary, func.count(Document.id)).group_by(Document.subsidiary).all())
    years = dict(db.query(Document.doc_year, func.count(Document.id)).group_by(Document.doc_year).all())

    print(f"\n[1] DATABASE INGESTION STATUS (Total Documents: {total_docs})")
    print(f"  Statuses: {status_counts}")
    print(f"  Doc Types: {doc_types}")
    print(f"  Subsidiaries: {subsidiaries}")
    print(f"  Years Covered: {sorted([y for y in years if y])}")

    # 2. Chunks and Embeddings
    total_chunks = db.query(Chunk).count()
    embedded_chunks = db.query(Chunk).filter(Chunk.embedding != None).count()
    fts_chunks = db.query(Chunk).filter(Chunk.tsv != None).count()
    avg_chunk_len = db.query(func.avg(func.length(Chunk.text))).scalar() or 0

    print(f"\n[2] VECTOR & FULL-TEXT SEARCH INDEXING")
    print(f"  Total Chunks: {total_chunks:,}")
    print(f"  Embedded Chunks (384-dim pgvector): {embedded_chunks:,} ({embedded_chunks/max(total_chunks,1)*100:.1f}%)")
    print(f"  FTS Searchable Chunks (PostgreSQL tsvector): {fts_chunks:,} ({fts_chunks/max(total_chunks,1)*100:.1f}%)")
    print(f"  Average Chunk Text Length: {int(avg_chunk_len)} characters")

    # 3. Extraction Runs & Structured Fields
    total_runs = db.query(ExtractionRun).count()
    total_fields = db.query(ExtractionField).count()
    field_status = dict(db.query(ExtractionField.status, func.count(ExtractionField.id)).group_by(ExtractionField.status).all())
    avg_conf = db.query(func.avg(ExtractionField.confidence)).scalar() or 0

    # Top field names
    top_fields = db.query(ExtractionField.field_name, func.count(ExtractionField.id))\
                   .group_by(ExtractionField.field_name)\
                   .order_by(func.count(ExtractionField.id).desc())\
                   .limit(15).all()

    print(f"\n[3] STRUCTURED EXTRACTION FIGURES (Traceability & Validation)")
    print(f"  Total Extraction Runs: {total_runs}")
    print(f"  Total Extracted Fields: {total_fields:,}")
    print(f"  Field Statuses: {field_status}")
    print(f"  Average Extraction Confidence: {avg_conf*100:.2f}%")
    print(f"  Key Extracted Fields:")
    for fn, cnt in top_fields:
        print(f"    - {fn}: {cnt} records")

    # 4. Geological & Borehole Data Verification
    boreholes = db.query(ExtractionField).filter(ExtractionField.field_name.ilike("%borehole%")).count()
    depths = db.query(ExtractionField).filter(ExtractionField.field_name.ilike("%depth%")).count()
    reserves = db.query(ExtractionField).filter(ExtractionField.field_name.ilike("%reserve%")).count()
    seams = db.query(ExtractionField).filter(ExtractionField.field_name.ilike("%seam%")).count()
    grades = db.query(ExtractionField).filter(ExtractionField.field_name.ilike("%grade%")).count()

    print(f"\n[4] GEOLOGICAL & MINING EXPLORATION VERIFICATION")
    print(f"  Borehole Records: {boreholes}")
    print(f"  Depth Records: {depths}")
    print(f"  Reserve Estimates: {reserves}")
    print(f"  Coal Seams Identified: {seams}")
    print(f"  Coal Grades Tagged: {grades}")

    # Specific borehole sample inspection
    bh_samples = db.execute(text(
        "SELECT DISTINCT d.title, ef.field_name, ef.value_str, ef.value_num, ef.confidence "
        "FROM extraction_fields ef JOIN documents d ON ef.document_id = d.id "
        "WHERE ef.field_name IN ('borehole_id', 'seam_name', 'coal_block', 'depth_m', 'reserves_mt', 'grade') "
        "LIMIT 10"
    )).fetchall()
    print("  Sample Geological Borehole Extractions:")
    for s in bh_samples[:6]:
        val = s[2] if s[2] is not None else s[3]
        print(f"    [{s[0]}] {s[1]} = {val} (conf: {s[4]})")

    # 5. Production & Operational Records
    prod_fields = db.execute(text(
        "SELECT d.subsidiary, COUNT(*) "
        "FROM extraction_fields ef JOIN documents d ON ef.document_id = d.id "
        "WHERE ef.field_name IN ('production_lt', 'dispatch_lt', 'coal_production_mt', 'output_mt') "
        "GROUP BY d.subsidiary"
    )).fetchall()
    print(f"\n[5] SUBSIDIARY PRODUCTION & OPERATIONS COVERAGE")
    for sub, cnt in prod_fields:
        print(f"  {sub or 'General/CIL'}: {cnt} production/dispatch data points")

    # 6. Parliamentary Inquiries Coverage
    parl_docs = db.query(Document).filter(
        (Document.doc_type == 'parliamentary_q') | 
        (Document.title.ilike('%parliamentary%')) | 
        (Document.title.ilike('%sabha%'))
    ).all()
    print(f"\n[6] PARLIAMENTARY & HIGH-PRIORITY INQUIRIES COVERAGE ({len(parl_docs)} documents)")
    for pd in parl_docs:
        print(f"  - {pd.title} (Type: {pd.doc_type}, Year: {pd.doc_year}, Subsidiary: {pd.subsidiary})")

    # 7. File System Inventory
    print(f"\n[7] FILE SYSTEM INVENTORY ON DISK")
    folders_to_check = [
        "data/real_data",
        "data/real_data_ingested",
        "data/uploads",
        "demo_data",
        "demo_data/realistic",
        "demo_data/samples"
    ]
    total_files = 0
    ext_counter = Counter()
    size_total = 0
    for folder in folders_to_check:
        if os.path.exists(folder):
            files = [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]
            folder_size = sum(os.path.getsize(os.path.join(folder, f)) for f in files)
            size_total += folder_size
            total_files += len(files)
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                ext_counter[ext] += 1
            print(f"  Folder: {folder:28} | Files: {len(files):3} | Size: {folder_size / (1024*1024):8.2f} MB")

    print(f"  Total Files on Disk: {total_files} | Total Storage: {size_total / (1024*1024):.2f} MB")
    print(f"  File Extensions Distribution: {dict(ext_counter)}")

    # 8. Data Validation & Consistency Checks
    print(f"\n[8] DATA VALIDATION & INTEGRITY CHECKS")
    # Check 1: Orphaned chunks
    orphaned_chunks = db.execute(text("SELECT COUNT(*) FROM chunks c LEFT JOIN documents d ON c.document_id = d.id WHERE d.id IS NULL")).scalar()
    # Check 2: Orphaned fields
    orphaned_fields = db.execute(text("SELECT COUNT(*) FROM extraction_fields ef LEFT JOIN documents d ON ef.document_id = d.id WHERE d.id IS NULL")).scalar()
    # Check 3: Extraction runs without doc
    orphaned_runs = db.execute(text("SELECT COUNT(*) FROM extraction_runs er LEFT JOIN documents d ON er.document_id = d.id WHERE d.id IS NULL")).scalar()
    # Check 4: Failed documents
    failed_docs = db.query(Document).filter(Document.status == 'failed').count()

    print(f"  Orphaned Chunks: {orphaned_chunks} (Pass: 0)")
    print(f"  Orphaned Extraction Fields: {orphaned_fields} (Pass: 0)")
    print(f"  Orphaned Extraction Runs: {orphaned_runs} (Pass: 0)")
    print(f"  Failed Documents: {failed_docs} (Pass: 0)")

    db.close()
    print("\n" + "=" * 80)
    print("AUDIT COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    run_comprehensive_check()
