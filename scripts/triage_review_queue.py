"""Auto-triage review-queue extraction fields.

Rules (conservative: anything uncertain stays pending for human eyes):
  1. Machine-level consistency (stoppage reports): group the four machine fields
     (twh_h, ewh_h, output_mt, rate) per (document, machine); confirm the group when
     0 <= EWH <= TWH <= 24 and output ~= rate x EWH (±2%); reject the group when
     EWH > TWH or TWH > 24 (physically impossible); otherwise leave pending.
  2. Anchored real-data scalars: production/dispatch fields from the Coal Directory
     documents are confirmed only when the value matches a published subsidiary
     annual figure from evals/anchors.json within 1%.

Dry-run by default; --apply commits changes.

Usage: python scripts/triage_review_queue.py [--apply] [--verbose]
"""
import argparse
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from sqlalchemy import text as sqltext

from app.db import SessionLocal

ANCHORS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "evals", "anchors.json")
REL_TOL = 0.02
ANCHOR_TOL = 0.01


def load_anchors() -> dict:
    with open(ANCHORS_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="commit decisions (default: dry run)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    anchors = load_anchors()
    prod = anchors.get("company_production_mt_2022_23", {})
    despatch = anchors.get("company_despatch_mt_2022_23", {})
    # lakh tonnes: 1 MT = 10 lakh tonnes
    anchored_lt = {}
    for sub, mt in prod.items():
        anchored_lt.setdefault("production_lt", {})[sub] = mt * 10
    for sub, mt in despatch.items():
        anchored_lt.setdefault("dispatch_lt", {})[sub] = mt * 10

    db = SessionLocal()
    stats: Counter = Counter()
    decisions: list[tuple[int, str]] = []

    try:
        # ---- rule 1: machine-level groups from stoppage reports ----
        machine_fields = db.execute(sqltext(
            "SELECT ef.id, ef.document_id, ef.field_name, ef.value_num, ef.item "
            "FROM extraction_fields ef JOIN documents d ON d.id = ef.document_id "
            "WHERE ef.status = 'review' AND ef.field_name IN ('twh_h','ewh_h','output_mt','rate') "
            "AND ef.value_num IS NOT NULL AND ef.item <> ''"
        )).mappings().all()

        groups: dict[tuple, dict] = {}
        for r in machine_fields:
            machine = (r["item"] or "").split("|")[0].strip()
            groups.setdefault((r["document_id"], machine), {})[r["field_name"]] = (r["id"], float(r["value_num"]))

        for (doc_id, machine), g in groups.items():
            if not {"twh_h", "ewh_h", "output_mt", "rate"}.issubset(g):
                stats["machine_group_incomplete"] += 1
                continue
            twh, ewh = g["twh_h"][1], g["ewh_h"][1]
            out, rate = g["output_mt"][1], g["rate"][1]
            identity = abs(out - rate * ewh) <= REL_TOL * max(abs(rate * ewh), 1.0)
            if ewh > twh or twh > 24:
                verdict = "reject"
            elif identity and 0 <= ewh:
                verdict = "confirm"
            else:
                stats["machine_group_uncertain"] += 1
                continue
            stats[f"machine_{verdict}"] += 1
            for fid, _ in g.values():
                decisions.append((fid, verdict))
            if args.verbose:
                print(f"  machine {machine} doc={doc_id}: {verdict} (twh={twh} ewh={ewh} out={out} rate={rate})")

        # ---- rule 2: anchored real-data scalar fields (Coal Directory docs) ----
        rows = db.execute(sqltext(
            "SELECT ef.id, ef.field_name, ef.value_num, d.title "
            "FROM extraction_fields ef JOIN documents d ON d.id = ef.document_id "
            "WHERE ef.status = 'review' AND ef.field_name IN ('production_lt','dispatch_lt') "
            "AND ef.value_num IS NOT NULL AND (d.title LIKE '%Coal_Directory%' OR d.title LIKE '%Coal Directory%')"
        )).mappings().all()

        for r in rows:
            value = float(r["value_num"])
            table = anchored_lt.get(r["field_name"], {})
            hit = next((sub for sub, v in table.items()
                        if abs(value - v) <= ANCHOR_TOL * max(abs(v), 1e-9)), None)
            if hit:
                decisions.append((r["id"], "confirm"))
                stats[f"anchored_{r['field_name']}_confirm"] += 1
                if args.verbose:
                    print(f"  anchored {r['field_name']}={value} matches {hit} -> confirm")
            else:
                stats[f"anchored_{r['field_name']}_pending"] += 1
    finally:
        db.close()

    confirms = [i for i, v in decisions if v == "confirm"]
    rejects = [i for i, v in decisions if v == "reject"]
    print(f"\ndecisions: {len(confirms)} confirm, {len(rejects)} reject, "
          f"{stats['machine_group_incomplete']} incomplete groups skipped, "
          f"{stats['machine_group_uncertain']} uncertain left pending")
    print("field status counts:", dict(stats))

    if not args.apply:
        print("\ndry run - pass --apply to commit")
        return

    db = SessionLocal()
    try:
        if confirms:
            db.execute(sqltext(
                "UPDATE extraction_fields SET status = 'confirmed' WHERE id = ANY(:ids)"),
                {"ids": confirms})
        if rejects:
            db.execute(sqltext(
                "UPDATE extraction_fields SET status = 'rejected' WHERE id = ANY(:ids)"),
                {"ids": rejects})
        db.commit()
        print(f"committed: {len(confirms)} confirmed, {len(rejects)} rejected")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
