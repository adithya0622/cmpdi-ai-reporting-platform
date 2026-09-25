import argparse
import os

SUBSIDIARIES = {
    "ECL": "Eastern Coalfields Limited",
    "BCCL": "Bharat Coking Coal Limited",
    "CIL": "Coal India Limited",
}

# quarterly production (lakh tonnes): [year][sub] -> base production
BASE = {
    2022: {"ECL": 43.0, "BCCL": 37.5},
    2023: {"ECL": 46.5, "BCCL": 40.2},
    2024: {"ECL": 50.1, "BCCL": 44.0},
}
QUARTER_GROWTH = 0.8  # lakh tonnes added per quarter within a year


def prod_report(sub: str, year: int, quarter: int) -> str:
    name = SUBSIDIARIES[sub]
    prod = BASE[year][sub] + QUARTER_GROWTH * (quarter - 1)
    dispatch = round(prod * 0.98, 1)
    offtake = round(prod * 0.13, 1)
    rom = round(prod * 1.12, 1)
    washery = round(prod * 0.09, 1)
    target = round(prod * 1.04, 1)
    if sub == "BCCL":
        grade_desc = (
            "Coking coal washery grades W-II and W-III (metallurgical coking product for steel plants); "
            "Raw coal thermal blend G4/G5."
        )
    else:
        grade_desc = "Non-coking thermal coal grades G2, G3 and G4 (GCV based, power sector allocation)."
    return (
        f"{name} ({sub})\nQuarterly Production Report Q{quarter} {year}\n\n"
        f"Raw coal production for the quarter stood at {prod} lakh tonnes against a target of {target} lakh tonnes.\n"
        f"Dispatch was {dispatch} lakh tonnes and offtake of washed coal was {offtake} lakh tonnes.\n"
        f"Run-of-mine (ROM) production was {rom} lakh tonnes. Washery output was {washery} lakh tonnes.\n"
        f"Grade mix: {grade_desc} Performance reviewed by the subsidiary board."
    )


def prod_report_cil(year: int, quarter: int) -> str:
    total = round(sum(BASE[year][s] for s in ("ECL", "BCCL")) + 210 + QUARTER_GROWTH * 2 * (quarter - 1), 1)
    return (
        f"Coal India Limited\nQuarterly Production Summary Q{quarter} {year}\n\n"
        f"Consolidated raw coal production of Coal India Limited was {total} lakh tonnes for the quarter.\n"
        f"Subsidiary-wise performance was reviewed and production increased over the previous year."
    )


def geo_report(i: int) -> str:
    blocks = ["Sariya", "Rohne", "Kerkatta", "Chuperi"]
    seams = ["Seam IV", "Seam V", "Seam VI", "Seam III"]
    depth = 250 + i * 37.5
    thickness = 6.5 + i * 0.7
    reserves = 45 + i * 12.3
    grades = ["G3", "G4", "G2", "G5"][i % 4]
    subs = ["ECL", "BCCL", "ECL", "BCCL"][i % 4]
    return (
        f"Geological report - Borehole BH-{21 + i}\n\n"
        f"Borehole BH-{21 + i} was drilled at Block {blocks[i]} in the {SUBSIDIARIES[subs]} command area "
        f"during the exploration campaign of 2023.\n"
        f"The borehole reached a final depth of {depth} m. {seams[i]} was intersected with a thickness of "
        f"{thickness} m.\nInferred reserves were estimated at {reserves} million tonnes with grade {grades}. "
        f"The seam dips at 4 degrees."
    )


def parl_report(i: int) -> str:
    years = [2022, 2023]
    return (
        f"Lok Sabha Unstarred Question {4471 + i * 317}\n\n"
        f"The Minister of Coal was asked about coal production trends and dispatch performance during {years[i]}. "
        f"The reply stated that production increased over the previous year, driven by improved evacuation "
        f"and subsidiary performance. Details of subsidiary-wise production were laid on the table of the House."
    )


def main():
    ap = argparse.ArgumentParser(description="Generate synthetic demo documents (safe: no real data)")
    ap.add_argument("--out", default="demo_data")
    ap.add_argument("--ingest", action="store_true", help="also ingest into the running platform (needs DB + worker or direct DB)")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    count = 0
    files: list[tuple[str, str, int, str]] = []  # (filename, text, year, subsidiary)

    for year in (2022, 2023, 2024):
        for sub in ("ECL", "BCCL"):
            for q in range(1, 5):
                fn = f"{sub}_production_report_Q{q}_{year}.txt"
                files.append((fn, prod_report(sub, year, q), year, sub))
    for year in (2023, 2024):
        for q in (1, 2):
            fn = f"CIL_production_summary_Q{q}_{year}.txt"
            files.append((fn, prod_report_cil(year, q), year, "CIL"))
    for i in range(4):
        files.append((f"geological_report_BH{21 + i}_2023.txt", geo_report(i), 2023, ""))
    for i in range(2):
        files.append((f"parliamentary_question_{4471 + i * 317}_{2022 + i}.txt", parl_report(i), 2022 + i, ""))

    for fn, text, _, _ in files:
        with open(os.path.join(args.out, fn), "w", encoding="utf-8") as fh:
            fh.write(text)
        count += 1
    print(f"wrote {count} demo documents to {args.out}/")

    if args.ingest:
        import sys

        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
        from app.services.ingest import index_document

        ok = failed = 0
        for fn, text, year, sub in files:
            try:
                doc_id = index_document(fn, text.encode(), subsidiary=sub, doc_year=year)
                print(f"[ok] {fn} -> {doc_id}")
                ok += 1
            except Exception as e:
                print(f"[failed] {fn}: {e}")
                failed += 1
        print(f"ingested {ok}, failed {failed}")


if __name__ == "__main__":
    main()
