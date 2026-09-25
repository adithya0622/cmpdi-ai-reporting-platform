"""Correctness gates for the demo corpus. Fails (exit 1) if any check trips.

Gates:
  1. Anchors self-consistency: subsidiaries sum to the published CIL total.
  2. Daily reports parse and obey physics: 0 <= EWH <= TWH <= 24; lignite output ~= rate x EWH (±5%);
     stoppage durations match from/to times; each mine appears with a stable machine fleet.
  3. Reconciliation: each synthetic mine's annualized output is a plausible single-mine share
     (3-25%) of the real subsidiary annual anchor (NLC lignite 24.491 MT - the company operates
     several mines, so one mine must NOT equal 100% of the anchor).
  4. Boreholes: depth/reserves/thickness within realistic published ranges; required fields present.

Usage: python scripts/verify_corpus.py [--corpus demo_data/realistic]
"""
import argparse
import json
import os
import re
import sys

ANCHORS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "evals", "anchors.json")
HEAD_RE = re.compile(
    r"^(?P<id>\S+) / (?P<mat>[A-Z ]+) / TWH: (?P<twh>[\d.]+) /EWH:(?P<ewh>[\d.]+) "
    r"/ Output: (?P<out>[\d,.]+) / Rate: (?P<rate>[\d.]+)"
)
ROW_RE = re.compile(r"^(?P<f>\d{4}) (?P<t>\d{4}) (?P<d>[\d.]+) (?P<reason>.+)$")
TOL = 0.05
MINE_SHARE_MIN, MINE_SHARE_MAX = 0.03, 0.25

errors: list[str] = []


def err(msg: str):
    errors.append(msg)
    print(f"[FAIL] {msg}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=os.path.join("demo_data", "realistic"))
    args = ap.parse_args()

    with open(ANCHORS_PATH, encoding="utf-8") as fh:
        anchors = json.load(fh)
    with open(os.path.join(args.corpus, "manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)

    # ---- gate 1: anchors self-consistency ----
    prod = anchors["company_production_mt_2022_23"]
    cil = anchors["cil_production_mt"]["2022-23"]
    s = round(sum(prod.values()), 3)
    if abs(s - cil) > 0.01:
        err(f"anchors: subsidiaries sum {s} != CIL total {cil}")
    else:
        print(f"[ok] anchors: subsidiaries sum {s} MT == CIL published {cil} MT")

    # ---- gate 2: daily report physics ----
    n_reports = n_machines = n_stops = 0
    mine_lignite: dict[str, float] = {}
    fleet: dict[str, set] = {}
    for entry in manifest["daily_reports"]:
        path = os.path.join(args.corpus, entry["file"])
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        if "SYNTHETIC" not in text:
            err(f"{entry['file']}: missing SYNTHETIC provenance marker")
        current = None
        for line in text.splitlines():
            m = HEAD_RE.match(line.strip())
            if m:
                n_machines += 1
                twh, ewh = float(m["twh"]), float(m["ewh"])
                out = float(m["out"].replace(",", ""))
                rate = float(m["rate"])
                if not (0 <= ewh <= twh <= 24):
                    err(f"{entry['file']} {m['id']}: EWH/TWH out of range (TWH={twh}, EWH={ewh})")
                if m["mat"].strip() == "LIGNITE":
                    if ewh > 0.5 and abs(rate * ewh - out) > TOL * max(rate * ewh, 1):
                        err(f"{entry['file']} {m['id']}: output {out} != rate*EWH {rate*ewh:.0f} (±{TOL:.0%})")
                    if out > 0 and rate <= 0:
                        err(f"{entry['file']} {m['id']}: output without rate")
                    mine_lignite[entry["mine"]] = mine_lignite.get(entry["mine"], 0.0) + out
                fleet.setdefault(entry["mine"], set()).add(m["id"])
                current = m["id"]
                continue
            r = ROW_RE.match(line.strip())
            if r and current:
                n_stops += 1
                dur = float(r["d"])
                f_min = int(r["f"][:2]) * 60 + int(r["f"][2:])
                t_min = int(r["t"][:2]) * 60 + int(r["t"][2:])
                span = (t_min - f_min) % (24 * 60) / 60
                if dur > 24:
                    err(f"{entry['file']} {current}: stoppage duration {dur} h > 24")
                if abs(span - dur) > 0.02 + 1 / 60:
                    err(f"{entry['file']} {current}: duration {dur} h != from/to span {span:.2f} h ({r['f']}-{r['t']})")
        n_reports += 1

    if not errors:
        print(f"[ok] physics: {n_reports} reports, {n_machines} machine-days, {n_stops} stoppages - all constraints hold")

    # ---- gate 3: reconciliation to real anchors ----
    nlc_annual_t = anchors["nlc_lignite_mt_2022_23"] * 1_000_000
    days = len(manifest["daily_reports"]) // len(mine_lignite) if mine_lignite else 0
    for mine, total_t in sorted(mine_lignite.items()):
        annualized = total_t / days * 365
        share = annualized / nlc_annual_t
        ok = MINE_SHARE_MIN <= share <= MINE_SHARE_MAX
        if not ok:
            err(f"{mine}: annualized {annualized/1e6:.2f} MT = {share:.1%} of NLC anchor - outside plausible single-mine band [{MINE_SHARE_MIN:.0%}-{MINE_SHARE_MAX:.0%}]")
        else:
            print(f"[ok] reconcile {mine}: {annualized/1e6:.2f} MT/yr = {share:.1%} of real NLC 24.49 MT anchor (plausible single-mine share)")
        if len(fleet.get(mine, set())) < 3:
            err(f"{mine}: fleet too small ({fleet.get(mine)})")

    # ---- gate 4: boreholes ----
    for bh in manifest["boreholes"]:
        if not (30 <= bh["depth_m"] <= 600):
            err(f"{bh['borehole_id']}: depth {bh['depth_m']} m out of range")
        if not (0.5 <= bh["seam_thickness_m"] <= 25):
            err(f"{bh['borehole_id']}: seam thickness {bh['seam_thickness_m']} m out of range")
        if not (1 <= bh["reserves_mt"] <= 250):
            err(f"{bh['borehole_id']}: reserves {bh['reserves_mt']} MT out of range")
        if bh["grade"] not in ("G1", "G2", "G3", "G4", "G5", "G6", "G7"):
            err(f"{bh['borehole_id']}: bad grade {bh['grade']}")
    if not errors:
        print(f"[ok] boreholes: {len(manifest['boreholes'])} logs within published ranges")

    print()
    if errors:
        print(f"VERIFICATION FAILED: {len(errors)} error(s)")
        sys.exit(1)
    print(f"VERIFICATION PASSED: corpus consistent with evals/anchors.json ({n_reports} daily reports, {len(manifest['boreholes'])} boreholes)")


if __name__ == "__main__":
    main()
