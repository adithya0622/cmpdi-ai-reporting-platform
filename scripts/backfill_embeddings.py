"""Backfill embeddings for all indexed chunks missing vectors.

Safe to re-run: only touches chunks with embedding IS NULL. Commits in batches so an
interrupted run keeps its progress.

Usage: python scripts/backfill_embeddings.py [--batch 256] [--limit 0]
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from app.db import SessionLocal
from app.models import Chunk, Document
from app.services import embeddings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=256, help="chunks per embed+commit cycle")
    ap.add_argument("--limit", type=int, default=0, help="max chunks (0 = all)")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        total = db.query(Chunk).filter(Chunk.embedding.is_(None)).count()
    finally:
        db.close()
    if args.limit:
        total = min(total, args.limit)
    print(f"chunks to embed: {total}")
    if total == 0:
        return

    done = 0
    t0 = time.time()
    while done < total:
        n = min(args.batch, total - done)
        db = SessionLocal()
        try:
            chunks = db.query(Chunk).filter(Chunk.embedding.is_(None)).limit(n).all()
            if not chunks:
                break
            vecs = embeddings.embed([c.text for c in chunks])
            if vecs is None:
                print("[fail] embedding model unavailable - aborting (nothing corrupted)")
                return
            for c, v in zip(chunks, vecs, strict=False):
                c.embedding = v
            db.commit()
            done += len(chunks)
            if done % 1024 < args.batch or done == total:
                rate = done / (time.time() - t0) * 60
                print(f"  {done}/{total} embedded ({rate:.0f}/min, eta {max(0, (total - done) / max(rate, 1)):.0f} min)")
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    db = SessionLocal()
    try:
        remaining = db.query(Chunk).filter(Chunk.embedding.is_(None)).count()
        docs_no_emb = db.query(Document).filter(Document.status == "indexed_no_embeddings").count()
        if remaining == 0 and docs_no_emb:
            db.query(Document).filter(Document.status == "indexed_no_embeddings").update({"status": "indexed"})
            db.commit()
            print(f"flipped {docs_no_emb} docs from indexed_no_embeddings -> indexed")
    finally:
        db.close()
    print(f"done: {done} chunks embedded in {(time.time() - t0) / 60:.1f} min; {remaining} remain without vectors")


if __name__ == "__main__":
    main()
