import itertools
import json
import os
import re
from collections import Counter

from sqlalchemy import text as sqltext

from ..config import settings
from ..db import SessionLocal
from . import llm

STOP = {
    "the", "and", "of", "to", "in", "a", "for", "on", "is", "with", "as", "by", "at", "from",
    "an", "be", "are", "were", "was", "this", "that", "it", "or", "not", "has", "have", "had",
    "no", "but", "all", "also", "than", "then", "its", "their", "there", "been", "will",
    "would", "can", "may", "during", "per", "total", "etc", "his", "her", "him", "she",
}

WORD_RE = re.compile(r"[a-z\u0900-\u097F]{3,}")


def count_terms(texts) -> Counter:
    counts = Counter()
    for t in texts:
        counts.update(w for w in WORD_RE.findall(t.lower()) if w not in STOP)
    return counts


def _rows(subsidiary: str = "", year_from: int | None = None, year_to: int | None = None):
    db = SessionLocal()
    try:
        q = (
            "SELECT d.subsidiary, d.doc_year, c.text FROM chunks c "
            "JOIN documents d ON d.id = c.document_id WHERE (d.status IN ('indexed', 'approved') OR d.status LIKE 'indexed%')"
        )
        params: dict = {}
        if subsidiary:
            q += " AND d.subsidiary = :sub"
            params["sub"] = subsidiary
        if year_from is not None:
            q += " AND d.doc_year >= :yf"
            params["yf"] = year_from
        if year_to is not None:
            q += " AND d.doc_year <= :yt"
            params["yt"] = year_to
        return db.execute(sqltext(q), params).mappings().all()
    finally:
        db.close()


def wordcloud(subsidiary: str = "", year_from: int | None = None, year_to: int | None = None, top_n: int = 60) -> list[dict]:
    counts = count_terms(r["text"] for r in _rows(subsidiary, year_from, year_to))
    return [{"term": w, "count": c} for w, c in counts.most_common(top_n)]


def topics(subsidiary: str = "", year_from: int | None = None, year_to: int | None = None, top_n: int = 15) -> dict:
    rows = _rows(subsidiary, year_from, year_to)
    counts: Counter = Counter()
    for r in rows:
        words = [w for w in WORD_RE.findall(r["text"].lower()) if w not in STOP]
        counts.update(itertools.pairwise(words))
    bigrams = [{"term": f"{a} {b}", "count": c} for (a, b), c in counts.most_common(top_n)]
    summary = ""
    if llm.available() and rows:
        sample = "\n\n".join(r["text"][:500] for r in rows[:20])
        summary = llm.chat(
            "Identify the main topics in these excerpts from Coal India mining/geological documents. "
            "Reply with a short bullet list.\n\n" + sample,
            max_tokens=512,
        )
    # ponytail: bigram counts instead of KeyBERT/BERTopic; swap in when topic quality matters
    return {"topics": bigrams, "summary": summary}


def trends(field_name: str, subsidiary: str = "") -> list[dict]:
    """Yearly average of an extracted field - chart data for the dashboard."""
    db = SessionLocal()
    try:
        sql = (
            "SELECT d.doc_year AS year, AVG(ef.value_num) AS v, COUNT(*) AS n "
            "FROM extraction_fields ef JOIN documents d ON d.id = ef.document_id "
            "WHERE ef.field_name = :f AND ef.value_num IS NOT NULL AND d.doc_year IS NOT NULL "
            "AND ef.status IN ('auto', 'confirmed', 'review') "
        )
        params: dict = {"f": field_name}
        if subsidiary:
            sql += "AND ef.subsidiary = :s "
            params["subsidiary"] = subsidiary
        sql += "GROUP BY d.doc_year ORDER BY d.doc_year"
        return [
            {"year": int(r["year"]), "value": round(float(r["v"]), 3), "n": r["n"]}
            for r in db.execute(sqltext(sql), params).mappings().all()
        ]
    finally:
        db.close()


def topic_trends(subsidiary: str = "", year_from: int | None = None, year_to: int | None = None, per_year: int = 5) -> list[dict]:
    """Top bigrams per year - topics over time."""
    counts_by_year: dict[int, Counter] = {}
    for r in _rows(subsidiary, year_from, year_to):
        y = r["doc_year"] or 0
        words = [w for w in WORD_RE.findall(r["text"].lower()) if w not in STOP]
        counts_by_year.setdefault(y, Counter()).update(itertools.pairwise(words))
    return [
        {
            "year": y,
            "topics": [{"term": f"{a} {b}", "count": c} for (a, b), c in cnt.most_common(per_year)],
        }
        for y, cnt in sorted(counts_by_year.items())
    ]


# Stoppage reason classification (ordered; first match wins). Tuned on NLC Mine-I reports.
_STOP_CATEGORIES: list[tuple[str, tuple[str, ...]]] = [
    ("maintenance", ("maintenance", "d/m", "oh work", "overhaul", "roller changing", "welding", "core cutting", "work by m.base")),
    ("planned_shifting", ("p/s", "proposed", "shifting", "movement to")),
    ("awaiting_infrastructure", ("waiting", "bunker full", "conveyor", "sequence feeding")),
    ("standby", ("stand by", "standby")),
    ("electrical_trip", ("trip",)),
    ("repositioning", ("reposition", "track area", "change over", "c/o")),
]


def classify_stoppage(reason: str) -> str:
    r = (reason or "").lower()
    for cat, kws in _STOP_CATEGORIES:
        if any(k in r for k in kws):
            return cat
    return "other"


def _date_clause_and_params(subsidiary: str, date_from, date_to) -> tuple[str, dict]:
    sql, params = "", {}
    if subsidiary:
        sql += " AND ef.subsidiary = :s "
        params["s"] = subsidiary
    if date_from is not None:
        sql += " AND d.doc_date >= :df "
        params["df"] = date_from
    if date_to is not None:
        sql += " AND d.doc_date <= :dt "
        params["dt"] = date_to
    return sql, params


def stoppage_pareto(subsidiary: str = "", date_from=None, date_to=None, top_n: int = 15) -> dict:
    """Total downtime by stoppage-reason category (Pareto) + per-machine breakdown.
    Rows are stoppage_duration_h extraction fields whose item encodes
    'MACHINE|stop#N|HHMM-HHMM|reason'."""
    db = SessionLocal()
    try:
        sql = (
            "SELECT ef.item, ef.value_num, d.doc_date, d.title FROM extraction_fields ef "
            "JOIN documents d ON d.id = ef.document_id "
            "WHERE ef.field_name = 'stoppage_duration_h' AND ef.value_num IS NOT NULL "
            "AND ef.status IN ('auto', 'confirmed', 'review')"
        )
        extra, params = _date_clause_and_params(subsidiary, date_from, date_to)
        rows = db.execute(sqltext(sql + extra), params).mappings().all()
    finally:
        db.close()

    by_cat: Counter = Counter()
    by_machine: dict[str, float] = {}
    reasons: dict[str, float] = {}
    n = 0
    for r in rows:
        parts = (r["item"] or "").split("|")
        machine = parts[0] if parts else ""
        reason = parts[3] if len(parts) > 3 else ""
        h = float(r["value_num"] or 0)
        by_cat[classify_stoppage(reason)] += h
        by_machine[machine] = by_machine.get(machine, 0.0) + h
        if reason:
            key = reason[:80]
            reasons[key] = reasons.get(key, 0.0) + h
        n += 1
    total = sum(by_cat.values())
    pareto, cum = [], 0.0
    for cat, h in by_cat.most_common(top_n):
        cum += h
        pareto.append({
            "category": cat,
            "hours": round(h, 2),
            "share_pct": round(h / total * 100, 1) if total else 0.0,
            "cumulative_pct": round(cum / total * 100, 1) if total else 0.0,
        })
    top_reasons = [{"reason": k, "hours": round(v, 2)} for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])[:top_n]]
    return {
        "total_stoppage_h": round(total, 2),
        "stoppage_events": n,
        "categories": pareto,
        "top_reasons": top_reasons,
        "machines": [{"machine_id": m, "stoppage_h": round(h, 2)} for m, h in sorted(by_machine.items(), key=lambda kv: -kv[1])[:top_n]],
    }


def _eval_summary() -> dict | None:
    """Latest eval-harness result (written by scripts/eval_harness.py --save)."""
    path = os.path.join(settings.repo_root, "evals", "latest_eval.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def _read_timing() -> dict | None:
    path = os.path.join(settings.data_dir, "metrics", "report_timing.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def kpis() -> dict:
    """PS headline metrics: automation %, extraction accuracy %, report prep-time reduction.
    Everything is computed from live DB state + artifacts written by the eval harness
    (evals/latest_eval.json) and the timing harness (data/metrics/report_timing.json)."""
    db = SessionLocal()
    try:
        total = db.execute(sqltext("SELECT COUNT(*) AS n FROM extraction_fields")).scalar() or 0
        auto = db.execute(sqltext("SELECT COUNT(*) AS n FROM extraction_fields WHERE status = 'auto'")).scalar() or 0
        confirmed = db.execute(sqltext("SELECT COUNT(*) AS n FROM extraction_fields WHERE status = 'confirmed'")).scalar() or 0
        rejected = db.execute(sqltext("SELECT COUNT(*) AS n FROM extraction_fields WHERE status = 'rejected'")).scalar() or 0
        auto_strong = db.execute(
            sqltext("SELECT COUNT(*) AS n FROM extraction_fields WHERE status = 'auto' AND confidence >= :t"),
            {"t": settings.confidence_threshold},
        ).scalar() or 0
        docs = db.execute(sqltext("SELECT COUNT(*) AS n FROM documents")).scalar() or 0
        chunks = db.execute(sqltext("SELECT COUNT(*) AS n FROM chunks")).scalar() or 0
        vec = db.execute(sqltext("SELECT COUNT(*) AS n FROM chunks WHERE embedding IS NOT NULL")).scalar() or 0
    finally:
        db.close()

    decided = confirmed + rejected
    agreement = round(confirmed / decided * 100, 1) if decided else None
    timing = _read_timing() or {}
    return {
        "automation_pct": round(auto / total * 100, 1) if total else 0.0,
        "automation_strong_pct": round(auto_strong / total * 100, 1) if total else 0.0,
        "fields_total": total,
        "fields_auto": auto,
        "fields_confirmed": confirmed,
        "fields_rejected": rejected,
        "fields_review": max(0, total - auto - confirmed - rejected),
        "human_triage_agreement_pct": agreement,
        "eval": _eval_summary(),
        "report_prep_seconds": timing.get("median_seconds"),
        "report_prep_baseline_seconds": timing.get("baseline_seconds"),
        "report_prep_baseline_assumption": timing.get("baseline_assumption"),
        "report_prep_time_reduction_pct": timing.get("reduction_pct"),
        "corpus": {"documents": docs, "chunks": chunks, "vector_chunks": vec},
    }


def machine_utilization(subsidiary: str = "", date_from=None, date_to=None, limit: int = 50) -> list[dict]:
    """Per-machine utilization from stoppage reports: EWH/TWH % and output, aggregated over the period."""
    db = SessionLocal()
    try:
        base = (
            "SELECT ef.item AS machine_id, ef.value_num, d.doc_date FROM extraction_fields ef "
            "JOIN documents d ON d.id = ef.document_id "
            "WHERE ef.value_num IS NOT NULL AND ef.status IN ('auto', 'confirmed', 'review')"
        )
        extra, params = _date_clause_and_params(subsidiary, date_from, date_to)

        def rows_for(field: str):
            return db.execute(
                sqltext(base + f" AND ef.field_name = '{field}'" + extra), params
            ).mappings().all()

        twh = {r["machine_id"]: r["value_num"] for r in rows_for("twh_h")}
        ewh_rows = rows_for("ewh_h")
        out_rows = rows_for("output_mt")
    finally:
        db.close()

    agg: dict[str, dict] = {}
    for r in ewh_rows:
        m = agg.setdefault(r["machine_id"], {"ewh": 0.0, "output": 0.0, "days": 0, "last_date": None})
        m["ewh"] += float(r["value_num"])
        m["days"] += 1
        if r["doc_date"] and (m["last_date"] is None or r["doc_date"] > m["last_date"]):
            m["last_date"] = r["doc_date"]
    for r in out_rows:
        if r["machine_id"] in agg:
            agg[r["machine_id"]]["output"] += float(r["value_num"])

    out = []
    for machine, m in agg.items():
        t = float(twh.get(machine, 0.0))
        util = (m["ewh"] / t * 100) if t > 0 else None
        out.append({
            "machine_id": machine,
            "twh_h": round(t, 2),
            "ewh_h": round(m["ewh"], 2),
            "utilization_pct": round(util, 1) if util is not None else None,
            "output_mt": round(m["output"], 2),
            "days_reported": m["days"],
            "last_date": str(m["last_date"]) if m["last_date"] else "",
        })
    out.sort(key=lambda x: -(x["ewh_h"]))
    return out[:limit]
