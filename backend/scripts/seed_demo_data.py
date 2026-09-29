#!/usr/bin/env python3
"""Seed demo data for CMPDI AI Reporting Platform hackathon demo.

Generates realistic Coal India records directly into PostgreSQL via SQLAlchemy.
Run:  python backend/scripts/seed_demo_data.py

Requirements: DATABASE_URL env var pointing at a running PostgreSQL+pgvector instance.
Tables must already exist (run alembic/create_all first).
"""
import datetime
import os
import random
import sys
import uuid

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_SCRIPT_DIR)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

random.seed(2026)

# ---------------------------------------------------------------------------
# Demo constants
# ---------------------------------------------------------------------------
APPROVERS = [
    ("Rajesh Kumar", "Chief Mining Engineer"),
    ("A. K. Singh", "General Manager (Production)"),
    ("S. Chatterjee", "Dy. Chief Mining Engineer"),
    ("P. K. Mishra", "Area General Manager"),
    ("Dr. M. N. Tiwari", "Director (Technical)"),
    ("V. Raghavan", "Chief of Safety"),
]

MINES = [
    ("Rajmahal OCP", "ECL"),
    ("Sonepur-Bazari OCP", "ECL"),
    ("Jhanjra UG", "ECL"),
    ("Moonidih UG", "BCCL"),
    ("Govindpur OCP", "BCCL"),
    ("Dhanbad Washery", "BCCL"),
    ("Gevra OCP", "SECL"),
    ("Kusmunda OCP", "SECL"),
    ("Jayant OCP", "NCL"),
    ("Nigahi OCP", "NCL"),
    ("Lakhanpur OCP", "MCL"),
    ("Mine-I", "NLC"),
    ("Mine-II", "NLC"),
]

EQUIPMENT_TAGS = [
    "BWE-1357", "BWE-1029", "BWE-2105", "Shovel-42", "Shovel-67",
    "Dragline-08", "Dumper-DK21", "Dumper-DK43", "Crusher-C1",
    "Conveyor-A7", "Dozer-D9R", "Drill-RD45",
]

DELAY_REASONS = [
    ("HYD-LEAK", "Hydraulic hose burst on boom cylinder"),
    ("RAIN-SLIP", "Operations halted due to heavy rainfall and slippery bench"),
    ("BELT-ALIGN", "Conveyor belt alignment issue on main trunk"),
    ("POWER-FAIL", "Grid power failure from CSEB"),
    ("DRILL-BIT", "Drill bit replacement and alignment"),
    ("BLASTING", "Planned controlled blasting, safety zone clearance"),
    ("MAINT-PREV", "Scheduled preventive maintenance"),
    ("CABLE-SHIFT", "Cable shifting for dragline repositioning"),
    ("DEWATER", "Pit dewatering due to water accumulation"),
    ("SAFETY-AUD", "Safety audit and inspection by DGMS team"),
]

BOREHOLE_BLOCKS = [
    ("Garjanbahal", "SECL", "Seam-IV", "G5"),
    ("Garjanbahal", "SECL", "Seam-V", "G6"),
    ("Amlohri", "NCL", "Turra", "G3"),
    ("Amlohri", "NCL", "Purewa", "G4"),
    ("Chuperi", "SECL", "Seam-III", "G5"),
    ("Jharia", "BCCL", "Seam-XII", "Steel Grade I"),
    ("Raniganj", "ECL", "Seam-R-VI", "G9"),
    ("Talcher", "MCL", "Bharatpur-I", "G11"),
    ("Singrauli", "NCL", "Dudhichua", "G3"),
    ("Korba", "SECL", "Gevra Extension", "G5"),
]

SUBSIDIARIES_QUARTERLY = {
    "BCCL": {"base_prod": 38.0, "growth": 1.06},
    "ECL":  {"base_prod": 44.0, "growth": 1.04},
    "CCL":  {"base_prod": 62.0, "growth": 1.05},
    "SECL": {"base_prod": 155.0, "growth": 1.07},
    "NCL":  {"base_prod": 120.0, "growth": 1.06},
    "MCL":  {"base_prod": 165.0, "growth": 1.08},
    "WCL":  {"base_prod": 52.0, "growth": 1.03},
}


def _rand_date(year: int, month: int) -> datetime.date:
    day = random.randint(1, 28)
    return datetime.date(year, month, day)


def _quarter_label(year: int, q: int) -> str:
    return f"Q{q} {year}"


# ---------------------------------------------------------------------------
# Record builders (return dicts matching ORM column names)
# ---------------------------------------------------------------------------

def build_shift_records() -> list[dict]:
    """20+ daily shift / stoppage records spanning 2022–2026."""
    records = []
    for year in range(2022, 2027):
        months = random.sample(range(1, 13), k=min(5, 12))
        for month in sorted(months):
            mine_name, subsidiary = random.choice(MINES)
            approver_name, designation = random.choice(APPROVERS)
            relay = random.choice(["A", "B", "C"])
            shift = random.choice(["I", "II", "III"])
            doc_date = _rand_date(year, month)

            ob_m3 = round(random.uniform(0, 12000), 1)
            lignite_mt = round(random.uniform(500, 9800), 1)
            power_mw = round(random.uniform(80, 210), 1) if "NLC" in subsidiary else None

            equip = random.sample(EQUIPMENT_TAGS, k=random.randint(2, 4))
            delay_code, delay_desc = random.choice(DELAY_REASONS)

            title = f"Daily Shift Report — {mine_name} — {doc_date.strftime('%d.%m.%Y')} — Relay {relay} Shift {shift}"

            chunk_text = (
                f"DAILY SHIFT REPORT\n"
                f"Mine: {mine_name}\n"
                f"Date: {doc_date.strftime('%d.%m.%Y')}\n"
                f"Relay: {relay}  Shift: {shift}\n"
                f"Approved By: {approver_name}, {designation}\n\n"
                f"PRODUCTION SUMMARY\n"
                f"TOTAL OB: {ob_m3} m3\n"
                f"TOTAL LIGNITE: {lignite_mt} mt\n"
                + (f"Power Generation: {power_mw} MW\n" if power_mw else "")
                + f"\nEQUIPMENT DEPLOYED: {', '.join(equip)}\n"
                f"\nSTOPPAGES:\n"
                f"{equip[0]} — {delay_code}: {delay_desc} — {random.uniform(0.5, 4.0):.1f} hours\n"
            )

            records.append({
                "title": title,
                "doc_type": "daily_shift_report",
                "subsidiary": subsidiary,
                "doc_year": year,
                "doc_date": doc_date,
                "approved_by": approver_name,
                "specified_by": designation,
                "chunk_text": chunk_text,
                "fields": {
                    "total_ob_m3": ob_m3,
                    "total_lignite_mt": lignite_mt,
                    **({"power_generation_mw": power_mw} if power_mw else {}),
                },
            })
    return records


def build_borehole_records() -> list[dict]:
    """19 CMPDI borehole / geological survey records (BH-21 through BH-24+ across blocks)."""
    records = []
    bh_num = 21
    for block, subsidiary, seam, grade in BOREHOLE_BLOCKS:
        n_holes = random.randint(1, 3)
        for _ in range(n_holes):
            bh_id = f"{block}-BH{bh_num:02d}"
            bh_num += 1
            depth = round(random.uniform(80, 450), 1)
            thickness = round(random.uniform(1.5, 18.0), 2)
            reserves = round(random.uniform(12.0, 320.0), 2)
            year = random.choice([2022, 2023, 2024, 2025])
            doc_date = _rand_date(year, random.randint(1, 12))

            title = f"Geological Survey — {block} Block — {bh_id}"
            chunk_text = (
                f"CENTRAL MINE PLANNING & DESIGN INSTITUTE LIMITED\n"
                f"GEOLOGICAL SURVEY REPORT\n\n"
                f"Block: {block}\n"
                f"Subsidiary: {subsidiary}\n"
                f"Borehole ID: {bh_id}\n"
                f"Seam: {seam}\n"
                f"Depth: {depth} m\n"
                f"Seam Thickness: {thickness} m\n"
                f"Estimated Reserves: {reserves} MT\n"
                f"Grade: {grade}\n"
                f"Date of Survey: {doc_date.strftime('%d.%m.%Y')}\n"
            )
            records.append({
                "title": title,
                "doc_type": "geological",
                "subsidiary": subsidiary,
                "doc_year": year,
                "doc_date": doc_date,
                "chunk_text": chunk_text,
                "fields": {
                    "depth_m": depth,
                    "seam_thickness_m": thickness,
                    "reserves_mt": reserves,
                },
            })
            if len(records) >= 19:
                return records
    return records


def build_quarterly_records() -> list[dict]:
    """Multi-year quarterly production for BCCL and ECL (2022–2024), plus a few others."""
    records = []
    for subsidiary in ["BCCL", "ECL", "SECL", "NCL"]:
        info = SUBSIDIARIES_QUARTERLY[subsidiary]
        prod = info["base_prod"]
        for year in range(2022, 2025):
            for q in range(1, 5):
                seasonal = {"1": 1.05, "2": 0.92, "3": 0.88, "4": 1.10}[str(q)]
                production = round(prod * seasonal + random.uniform(-3, 3), 2)
                dispatch = round(production * random.uniform(0.88, 0.97), 2)
                offtake = round(dispatch * random.uniform(0.95, 1.02), 2)
                rom = round(production * random.uniform(1.02, 1.12), 2)
                washery = round(production * random.uniform(0.15, 0.35), 2) if subsidiary in ("BCCL", "ECL") else None

                period = _quarter_label(year, q)
                q_month = {1: 4, 2: 7, 3: 10, 4: 1}[q]
                q_year = year + 1 if q == 4 else year
                doc_date = _rand_date(q_year, q_month)

                title = f"Quarterly Production Report — {subsidiary} — {period}"
                chunk_text = (
                    f"COAL INDIA LIMITED\n"
                    f"QUARTERLY PRODUCTION REPORT\n"
                    f"Subsidiary: {subsidiary}\n"
                    f"Period: {period}\n\n"
                    f"Production: {production} lakh tonnes\n"
                    f"Dispatch: {dispatch} lakh tonnes\n"
                    f"Offtake: {offtake} lakh tonnes\n"
                    f"ROM: {rom} lakh tonnes\n"
                    + (f"Washery Output: {washery} lakh tonnes\n" if washery else "")
                )

                records.append({
                    "title": title,
                    "doc_type": "production_report",
                    "subsidiary": subsidiary,
                    "doc_year": year,
                    "doc_date": doc_date,
                    "chunk_text": chunk_text,
                    "fields": {
                        "production_lt": production,
                        "dispatch_lt": dispatch,
                        "offtake_lt": offtake,
                        "rom_lt": rom,
                        **({"washery_output_lt": washery} if washery else {}),
                    },
                })
            prod *= info["growth"]
    return records


def build_memo_records() -> list[dict]:
    """A few administrative memo records for demo."""
    memos = [
        {
            "subject": "Revised Safety Protocol for Underground Mines",
            "issuing_authority": "Director General of Mines Safety",
            "ref": "DGMS/SAFETY/2024/1147",
            "subsidiary": "BCCL",
            "summary": "Mandatory adoption of real-time gas monitoring in all UG panels effective 01.01.2025.",
            "year": 2024,
        },
        {
            "subject": "Shift Roster Revision for September 2026",
            "issuing_authority": "Chief Mining Engineer, NLC",
            "ref": "NLC/HR/ROSTER/2026-09",
            "subsidiary": "NLC",
            "summary": "Three-shift roster updated with additional rest day allocation per DGMS directive.",
            "year": 2026,
        },
        {
            "subject": "Coal Quality Monitoring — Washery Output Sampling",
            "issuing_authority": "GM (Quality Control), BCCL",
            "ref": "BCCL/QC/2023/089",
            "subsidiary": "BCCL",
            "summary": "All washery dispatch lots above 500 tonnes to be sampled at loading point.",
            "year": 2023,
        },
    ]
    records = []
    for m in memos:
        doc_date = _rand_date(m["year"], random.randint(1, 12))
        chunk_text = (
            f"OFFICE MEMORANDUM\n"
            f"Reference: {m['ref']}\n"
            f"Date: {doc_date.strftime('%d.%m.%Y')}\n"
            f"Issuing Authority: {m['issuing_authority']}\n\n"
            f"Subject: {m['subject']}\n\n"
            f"{m['summary']}\n"
        )
        records.append({
            "title": f"Memo — {m['subject'][:60]}",
            "doc_type": "administrative_memo",
            "subsidiary": m["subsidiary"],
            "doc_year": m["year"],
            "doc_date": doc_date,
            "chunk_text": chunk_text,
            "fields": {},
        })
    return records


# ---------------------------------------------------------------------------
# Database insertion
# ---------------------------------------------------------------------------

def seed_to_database(all_records: list[dict]) -> None:
    """Insert records into PostgreSQL using SQLAlchemy ORM."""
    from app.db import SessionLocal, engine, Base
    from app.models import Document, Chunk, ExtractionRun, ExtractionField

    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        doc_count = 0
        field_count = 0
        for rec in all_records:
            doc_id = uuid.uuid4()
            doc = Document(
                id=doc_id,
                title=rec["title"],
                doc_type=rec["doc_type"],
                subsidiary=rec["subsidiary"],
                doc_year=rec["doc_year"],
                doc_date=rec["doc_date"],
                source_path=f"demo/seed/{rec['doc_type']}/{doc_id}.pdf",
                status="ingested",
                approved_by=rec.get("approved_by", ""),
                specified_by=rec.get("specified_by", ""),
            )
            db.add(doc)

            chunk = Chunk(
                document_id=doc_id,
                page=0,
                text=rec["chunk_text"],
            )
            db.add(chunk)

            if rec.get("fields"):
                run_id = uuid.uuid4()
                run = ExtractionRun(
                    id=run_id,
                    document_id=doc_id,
                    doc_type=rec["doc_type"],
                    status="done",
                )
                db.add(run)

                from app.extraction_schemas import field_unit
                for fname, value in rec["fields"].items():
                    is_num = isinstance(value, (int, float))
                    ef = ExtractionField(
                        run_id=run_id,
                        document_id=doc_id,
                        field_name=fname,
                        item="",
                        subsidiary=rec["subsidiary"],
                        value_num=float(value) if is_num else None,
                        value_str=None if is_num else str(value),
                        unit=field_unit(fname),
                        confidence=round(random.uniform(0.82, 0.98), 2),
                        status="auto",
                    )
                    db.add(ef)
                    field_count += 1

            doc_count += 1

        db.commit()
        print(f"  Seeded {doc_count} documents with {field_count} extraction fields.")
    except Exception as e:
        db.rollback()
        raise
    finally:
        db.close()


def seed_to_json(all_records: list[dict], out_path: str) -> None:
    """Export records as JSON (no DB required) for offline demo."""
    import json

    serializable = []
    for rec in all_records:
        r = dict(rec)
        if isinstance(r.get("doc_date"), datetime.date):
            r["doc_date"] = r["doc_date"].isoformat()
        serializable.append(r)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2, ensure_ascii=False)
    print(f"  Exported {len(serializable)} records to {out_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("="*60)
    print("  CMPDI AI Platform — Demo Data Seeder")
    print("="*60)

    shifts = build_shift_records()
    boreholes = build_borehole_records()
    quarterly = build_quarterly_records()
    memos = build_memo_records()

    all_records = shifts + boreholes + quarterly + memos

    print(f"\n  Generated records:")
    print(f"    Daily shift/stoppage:  {len(shifts)}")
    print(f"    Geological boreholes:  {len(boreholes)}")
    print(f"    Quarterly production:  {len(quarterly)}")
    print(f"    Administrative memos:  {len(memos)}")
    print(f"    TOTAL:                 {len(all_records)}")

    db_url = os.environ.get("DATABASE_URL", "")
    if db_url:
        print(f"\n  Inserting into database...")
        seed_to_database(all_records)
    else:
        out_path = os.path.join(_SCRIPT_DIR, "demo_seed_data.json")
        print(f"\n  No DATABASE_URL set — exporting to JSON instead.")
        seed_to_json(all_records, out_path)

    print(f"\n  Done.")


if __name__ == "__main__":
    main()
