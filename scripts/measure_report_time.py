"""Measure automated report-generation wall-clock time for the PS "report prep time
reduction" metric.

Generates the standard ops report N times (docx build + download) using the real
production-report service, writes data/metrics/report_timing.json:
  median_seconds, mean_seconds, runs, reduction_pct vs the documented manual baseline.

Manual baseline assumption (recorded in the output): compiling the same monthly ops
report by hand from raw mine PDFs/spreadsheets (find docs, read tables, compute Pareto,
aggregate production, format docx) takes ~3.5 h = 12,600 s. Adjust --baseline as needed.

Usage: python scripts/measure_report_time.py [--runs 5] [--baseline 12600]
"""
import argparse
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from app.services import report_gen

BASELINE_ASSUMPTION = (
    "Manual compilation of the same monthly ops report (locate source docs, read tables, "
    "compute stoppage Pareto, aggregate production, format docx) - estimated 3.5 hours."
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--baseline", type=float, default=12600.0, help="manual prep seconds")
    ap.add_argument("--subsidiary", default="")
    ap.add_argument("--year-from", type=int, default=None)
    ap.add_argument("--year-to", type=int, default=None)
    args = ap.parse_args()

    times = []
    for i in range(1, args.runs + 1):
        t0 = time.perf_counter()
        rid = report_gen.generate(
            title=f"Timing Harness Ops Report #{i}", subsidiary=args.subsidiary,
            year_from=args.year_from, year_to=args.year_to,
        )
        dt = time.perf_counter() - t0
        times.append(dt)
        print(f"run {i}: {dt:.2f}s (report {rid})")

    median = statistics.median(times)
    mean = statistics.mean(times)
    reduction = round((1 - median / args.baseline) * 100, 2)
    out = {
        "runs": args.runs,
        "times_seconds": [round(t, 3) for t in times],
        "median_seconds": round(median, 3),
        "mean_seconds": round(mean, 3),
        "baseline_seconds": args.baseline,
        "baseline_assumption": BASELINE_ASSUMPTION,
        "reduction_pct": reduction,
        "measured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    dest = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "metrics")
    os.makedirs(dest, exist_ok=True)
    path = os.path.join(dest, "report_timing.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    print(f"\nmedian {median:.2f}s vs manual baseline {args.baseline:.0f}s -> {reduction}% reduction")
    print(f"saved: {path}")


if __name__ == "__main__":
    main()
