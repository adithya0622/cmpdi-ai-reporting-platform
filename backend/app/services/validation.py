from sqlalchemy import text as sqltext

RANGES = {
    "production_lt": (0, 2000),
    "dispatch_lt": (0, 2000),
    "offtake_lt": (0, 2000),
    "rom_lt": (0, 2000),
    "washery_output_lt": (0, 500),
    "reserves_mt": (0, 100_000),
    "depth_m": (0, 3000),
    "seam_thickness_m": (0, 100),
    # daily operations (NLC/CIL mine reports)
    "total_lignite_mt": (0, 100_000),
    "total_ob_m3": (0, 1_000_000),
    "power_generation_mw": (0, 5_000),
    "twh_h": (0, 24),
    "ewh_h": (0, 24),
    "output_mt": (0, 100_000),
    "rate": (0, 5_000),
    "stoppage_duration_h": (0, 24),
}

Z_THRESHOLD = 3.0
MIN_HISTORY = 5
TOTALS_TOLERANCE = 0.05


def check_range(field_name: str, value: float) -> bool:
    rng = RANGES.get(field_name)
    if rng is None:
        return True
    return rng[0] <= value <= rng[1]


def zscore(field_name: str, subsidiary: str, value: float, db) -> float | None:
    if not subsidiary:
        return None
    rows = db.execute(
        sqltext(
            "SELECT value_num FROM extraction_fields "
            "WHERE field_name = :f AND subsidiary = :s AND value_num IS NOT NULL"
        ),
        {"f": field_name, "s": subsidiary},
    ).fetchall()
    values = [r[0] for r in rows]
    if len(values) < MIN_HISTORY:
        return None
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    std = var ** 0.5
    if std == 0:
        return 0.0 if value == mean else Z_THRESHOLD + 1
    return (value - mean) / std


def flag_fields(db, document_id) -> int:
    """Range + z-score anomaly checks on a document's numeric fields. Flags to review; never silent-fails."""
    from ..models import ExtractionField

    fields = (
        db.query(ExtractionField)
        .filter(ExtractionField.document_id == document_id, ExtractionField.value_num.isnot(None))
        .all()
    )
    flagged = 0
    for f in fields:
        reasons = []
        if not check_range(f.field_name, f.value_num):
            reasons.append("out of range")
        z = zscore(f.field_name, f.subsidiary or "", f.value_num, db)
        if z is not None and abs(z) > Z_THRESHOLD:
            reasons.append(f"anomaly (z={z:.1f})")
        if reasons:
            f.status = "review"
            flagged += 1
    return flagged


def totals_crosscheck(field_name: str, year: int, db) -> dict | None:
    """Compare CIL total vs sum of subsidiary averages for one field+year."""
    rows = db.execute(
        sqltext(
            "SELECT ef.subsidiary, AVG(ef.value_num) AS v FROM extraction_fields ef "
            "JOIN documents d ON d.id = ef.document_id "
            "WHERE ef.field_name = :f AND d.doc_year = :y AND ef.value_num IS NOT NULL "
            "GROUP BY ef.subsidiary"
        ),
        {"f": field_name, "y": year},
    ).fetchall()
    entries = {r[0] or "": float(r[1]) for r in rows}
    total = next((v for k, v in entries.items() if k.upper() in ("CIL", "")), None)
    parts = {k: round(v, 3) for k, v in entries.items() if k.upper() not in ("CIL",)}
    if total is None or not parts:
        return None
    s = sum(parts.values())
    diff = abs(total - s) / max(total, 1e-9)
    return {
        "field": field_name,
        "year": year,
        "total": round(total, 3),
        "sum_of_subsidiaries": round(s, 3),
        "gap_pct": round(diff * 100, 2),
        "consistent": diff <= TOTALS_TOLERANCE,
        "parts": parts,
    }
