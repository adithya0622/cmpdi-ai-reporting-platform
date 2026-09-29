r"""Scheduled auto-report generator.

Generates the standard production report (.docx) from the extracted corpus on a
schedule, so recurring statutory reporting is automated end-to-end. Run it from
Task Scheduler / cron, e.g. every Monday 07:00:

    Windows Task Scheduler:
      Program:   D:\PS2 - Copy\.venv\Scripts\python.exe
      Arguments: D:\PS2 - Copy\scripts\auto_report.py
      Schedule:  weekly, Monday 07:00

    Linux cron:
      0 7 * * 1  cd /path/to/repo && .venv/bin/python scripts/auto_report.py

Override via CLI flags (all optional):
    python scripts/auto_report.py --title "Weekly Production Report" \
        --subsidiary "" --year-from 2022 --year-to 2026
"""
import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from app.services import report_gen


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate the standard production report from extracted data")
    ap.add_argument("--title", default="")
    ap.add_argument("--subsidiary", default="")
    ap.add_argument("--year-from", type=int, default=2022)
    ap.add_argument("--year-to", type=int, default=datetime.date.today().year)
    args = ap.parse_args()

    title = args.title or f"Auto Production Report {datetime.date.today().isoformat()}"
    report_id = report_gen.generate(title, args.subsidiary, args.year_from, args.year_to)
    print(f"[auto_report] generated report {report_id} ({title})")


if __name__ == "__main__":
    main()
