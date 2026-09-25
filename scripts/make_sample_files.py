"""Create sample files that exercise the non-TXT ingest paths:

  1. XLSX  - real monthly production workbook (openpyxl table extraction path)
  2. PDF   - image-only "scanned" report (proves scanned-page detection + graceful
             OCR degradation to the manual-review queue; the PDF text-layer path is
             already covered by the real NLC PDFs in the DB)

Grounded in real public figures: MCL produced 193.262 MT in FY2022-23
(evals/anchors.json) -> a plausible single month is ~16.1 MT; MCL's two flagship
opencast mines are Kaniha and Lingaraj (public knowledge). Every synthetic number
carries a SYNTHETIC marker.

Usage: python scripts/make_sample_files.py [--out demo_data/samples]
"""
import argparse
import io
import json
import os
import random
import sys

ANCHORS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "evals", "anchors.json")


def make_xlsx(out_dir: str, rng: random.Random) -> str:
    from openpyxl import Workbook

    with open(ANCHORS_PATH, encoding="utf-8") as fh:
        anchors = json.load(fh)
    mcl_annual = anchors["company_production_mt_2022_23"]["MCL"]  # 193.262 MT, real

    wb = Workbook()
    ws = wb.active
    ws.title = "Monthly Production"
    ws.append(["MCL - Mahanadi Coalfields Limited"])
    ws.append(["Monthly Coal Production Report - March 2023 (SYNTHETIC DEMO - anchored to "
               f"real MCL FY2022-23 total of {mcl_annual} MT, evals/anchors.json)"])
    ws.append([])
    ws.append(["Mine", "Type", "OC Production (MT)", "UG Production (MT)", "Total (MT)", "Target (MT)", "Achievement %"])
    mines = [
        ("Kaniha", "Opencast", 0.31),
        ("Lingaraj", "Opencast", 0.26),
        ("Ananta", "Opencast", 0.18),
        ("Bharatpur", "Opencast", 0.15),
        ("Hingula", "Opencast", 0.10),
    ]
    # 16.1 MT plausible month; split across mines with noise
    month_total = round(mcl_annual / 12 * rng.uniform(0.92, 1.02), 3)
    weights = [w for _, _, w in mines]
    s = sum(weights)
    rows = []
    for name, mtype, w in mines:
        total = round(month_total * w / s, 3)
        ug = round(total * rng.uniform(0.0, 0.03), 3)
        oc = round(total - ug, 3)
        target = round(total * rng.uniform(0.95, 1.05), 3)
        rows.append((name, mtype, oc, ug, total, target, round(total / target * 100, 1)))
    for r in rows:
        ws.append(list(r))
    ws.append(["TOTAL", "", round(sum(r[2] for r in rows), 3), round(sum(r[3] for r in rows), 3),
               round(month_total, 3), round(sum(r[5] for r in rows), 3),
               round(month_total / sum(r[5] for r in rows) * 100, 1)])
    path = os.path.join(out_dir, "MCL_monthly_production_03-2023_SYNTHETIC.xlsx")
    wb.save(path)
    return path


def make_scanned_pdf(out_dir: str, rng: random.Random) -> str:
    """Image-only PDF: rendered text page with no text layer (the 'scan' simulation)."""
    import io as _io

    from PIL import Image, ImageDraw, ImageFont

    lines = [
        "NLC INDIA LTD - MINE-I",
        "Daily Shift & Stoppage Summary",
        "Date: 15.03.2026",
        "",
        "Machine: LBS/BWE-1029 / LIGNITE / TWH: 15.50 /EWH: 12.10",
        "Output: 6292.000 t / Rate: 520.000 t/h",
        "Stoppage From Stoppage To Duration Stoppage Description",
        "0815 0945 1.50 Daily maintenance",
        "1120 1235 1.25 Conveyor sequence feeding point changing",
        "1630 1745 1.25 M/C LT tripped while steering",
        "",
        "NOTE: SYNTHETIC DEMO DOCUMENT (scanned-image simulation).",
    ]
    img = Image.new("RGB", (1240, 900), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 28)
    except OSError:
        font = ImageFont.load_default()
    y = 60
    for ln in lines:
        draw.text((70, y), ln, fill="black", font=font)
        y += 46
    buf = _io.BytesIO()
    img.save(buf, format="JPEG", quality=92)

    # Pillow writes a valid image-only PDF directly (no text layer -> scanned-page path)
    path = os.path.join(out_dir, "M-1 SHIFT on 15.03.2026 SCANNED-SYNTHETIC.pdf")
    img.save(path, format="PDF", resolution=100)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join("demo_data", "samples"))
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    rng = random.Random(args.seed)
    xlsx = make_xlsx(args.out, rng)
    pdf = make_scanned_pdf(args.out, rng)
    print("wrote:", xlsx)
    print("wrote:", pdf)


if __name__ == "__main__":
    main()
