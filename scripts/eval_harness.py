import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from app.services.extraction import extract_fields

REL_TOL = 0.01


def load_gold(path: str) -> list[dict]:
    entries = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                entries.append(json.loads(line))
    return entries


def match_field(expected, actual, rel_tol: float = REL_TOL) -> bool:
    if expected is None:
        return actual is None
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        return (
            isinstance(actual, (int, float))
            and not isinstance(actual, bool)
            and abs(expected - actual) <= rel_tol * max(abs(expected), 1e-9)
        )
    return actual is not None and str(actual).strip().lower() == str(expected).strip().lower()


def evaluate(entries: list[dict], extract_fn, misses: list[dict] | None = None) -> dict:
    results: dict[str, dict] = {}
    for e in entries:
        doc_type = e["doc_type"]
        r = results.setdefault(doc_type, {"runs": 0, "llm_fail": 0, "expected": 0, "extracted": 0, "matched": 0})
        r["runs"] += 1
        try:
            got = extract_fn(e["text"], doc_type)
        except Exception:
            got = None
        if got is None:
            r["llm_fail"] += 1
        got_fields = (got or {}).get("fields", {})
        for field, exp in e["expected"].items():
            r["expected"] += 1
            if field in got_fields:
                r["extracted"] += 1
                if match_field(exp, got_fields[field]):
                    r["matched"] += 1
                elif misses is not None:
                    misses.append({"doc_type": doc_type, "field": field, "kind": "wrong", "expected": exp, "actual": got_fields[field]})
            elif misses is not None:
                misses.append({"doc_type": doc_type, "field": field, "kind": "missing", "expected": exp, "actual": None})
    out = {}
    for doc_type, r in results.items():
        precision = r["matched"] / r["extracted"] if r["extracted"] else 0.0
        recall = r["matched"] / r["expected"] if r["expected"] else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        out[doc_type] = {
            **r,
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
        }
    return out


def main():
    ap = argparse.ArgumentParser(description="Field-level extraction eval against gold-standard set")
    ap.add_argument("--gold", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "evals", "gold_set.jsonl"))
    ap.add_argument("--save", action="store_true", help="write evals/latest_eval.json for the /analytics/kpis endpoint")
    ap.add_argument("--show-misses", action="store_true", help="print each field-level mismatch (doc_type, field, expected vs actual)")
    args = ap.parse_args()
    entries = load_gold(args.gold)
    if not entries:
        print("no gold entries found")
        sys.exit(1)
    misses: list[dict] = []
    if not extract_fields("test", "production_report"):
        print("LLM unavailable - start the LLM server first")
        sys.exit(2)
    stats = evaluate(entries, extract_fields, misses if args.show_misses else None)
    print(f"{'doc_type':<20} {'runs':>5} {'prec':>7} {'recall':>7} {'f1':>7} {'llm_fail':>9}")
    for dt, r in sorted(stats.items()):
        print(f"{dt:<20} {r['runs']:>5} {r['precision']:>7.3f} {r['recall']:>7.3f} {r['f1']:>7.3f} {r['llm_fail']:>9}")
    overall_p = sum(r["matched"] for r in stats.values()) / max(sum(r["extracted"] for r in stats.values()), 1)
    overall_r = sum(r["matched"] for r in stats.values()) / max(sum(r["expected"] for r in stats.values()), 1)
    print(f"\noverall precision {overall_p:.3f} / recall {overall_r:.3f} over {len(entries)} gold entries")

    if misses:
        print(f"\nfield-level misses ({len(misses)}):")
        for m in misses:
            print(f"  [{m['doc_type']}] {m['field']:<18} expected={m['expected']!r}  actual={m['actual']!r}")

    if args.save:
        out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "evals", "latest_eval.json")
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump({
                "entries": len(entries),
                "precision": round(overall_p, 3),
                "recall": round(overall_r, 3),
                "per_doc_type": stats,
                "saved_at": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
            }, fh, indent=2)
        print(f"saved: {out_path}")


if __name__ == "__main__":
    main()
