import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from app.services.jobs import run_worker

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="CMPDI platform job worker (ingestion + extraction)")
    ap.add_argument("--once", action="store_true", help="drain the queue and exit")
    ap.add_argument("--poll", type=float, default=2.0, help="poll interval in seconds")
    args = ap.parse_args()
    run_worker(poll_seconds=args.poll, once=args.once)
