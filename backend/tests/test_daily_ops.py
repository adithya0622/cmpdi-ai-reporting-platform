import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "scripts"))

from app.extraction_schemas import (
    expand_items,
    field_period_type,
    field_unit,
    get_schema,
    parse_extraction,
    parse_report_date,
)
from app.services.analytics import classify_stoppage
from app.services.ingest import _render_table, infer_doc_type, parse_filename_date
from app.services.validation import check_range

# ---------- date parsing ----------

def test_parse_report_date_variants():
    assert parse_report_date("DATE : 08.09.2026 SHIFT : I RELAY : B - 1") == "2026-09-08"
    assert parse_report_date("Stoppage Report for MINE-I Date:07.09.2026") == "2026-09-07"
    assert parse_report_date("dated 7/9/2026 shift report") == "2026-09-07"
    assert parse_report_date("dated 07-09-2026") == "2026-09-07"
    assert parse_report_date("no date here") == ""
    assert parse_report_date("bogus 99.99.2026 date") == ""


def test_parse_filename_date():
    assert parse_filename_date("08-09-2026-B1 RELAY- 1st SHIFT -LBS-M1.pdf") == datetime.date(2026, 9, 8)
    assert parse_filename_date("M-1 STOPPAGE on 07.09.2026.pdf") == datetime.date(2026, 9, 7)
    assert parse_filename_date("C:\\archive\\report 1.2.2026.pdf") == datetime.date(2026, 2, 1)
    assert parse_filename_date("production_report_Q1_2024.pdf") is None
    assert parse_filename_date("99.99.2026.pdf") is None


def test_infer_doc_type():
    assert infer_doc_type("M-1 STOPPAGE on 07.09.2026.pdf", "") == "stoppage_report"
    assert infer_doc_type("08-09-2026-B1 RELAY- 1st SHIFT -LBS-M1.pdf", "") == "daily_shift_report"
    assert infer_doc_type("scan001.pdf", "NLC INDIA LTD\nStoppage Report for MINE-I") == "stoppage_report"
    assert infer_doc_type("notes.pdf", "quarterly production figures") == "other"


# ---------- schema registry ----------

def test_get_schema_new_types():
    daily = get_schema("daily_shift_report")
    assert daily["period_type"] == "daily" and daily["items_key"] is None
    stop = get_schema("stoppage_report")
    assert stop["items_key"] == "machines" and stop["period_type"] == "daily"
    # existing types untouched
    assert get_schema("production_report")["items_key"] is None


def test_field_units_and_periods():
    assert field_unit("production_lt") == "lakh_tonnes"
    assert field_unit("total_lignite_mt") == "tonnes"
    assert field_unit("total_ob_m3") == "m3"
    assert field_unit("twh_h") == "hours"
    assert field_unit("output_mt") == "tonnes"
    assert field_unit("rate") == "tonnes_per_hour"
    assert field_period_type("total_lignite_mt") == "daily"
    assert field_period_type("twh_h") == "daily"
    assert field_period_type("production_lt") == "quarterly"
    assert field_period_type("reserves_mt") == "point_in_time"
    assert field_period_type("depth_m") == "quarterly"  # unknown -> default


def test_check_range_daily_ops():
    assert check_range("twh_h", 18.45)
    assert not check_range("twh_h", 30)
    assert check_range("output_mt", 9600)
    assert not check_range("output_mt", 200000)
    assert check_range("stoppage_duration_h", 8.0)
    assert not check_range("stoppage_duration_h", 25)
    assert check_range("power_generation_mw", 148)


# ---------- parse_extraction for stoppage reports ----------

STOPPAGE_RAW = """
```json
{"fields": {"report_date": "07.09.2026", "mine": "MINE-I",
  "machines": [
    {"machine_id": "LBS/BWE-1029", "material": "LIGNITE", "twh_h": 18.45, "ewh_h": 18.45,
     "output_mt": 9600.0, "rate": 512.0,
     "stoppages": [
       {"from_hhmm": "1000", "to_hhmm": "1200", "duration_h": 2.0, "reason": "Daily maintenance"},
       {"from_hhmm": "1200", "to_hhmm": "1300", "duration_h": 1.0, "reason": "L7 roller structure welding"}
     ]},
    {"machine_id": "MBS/BWE-1356", "material": "OVER BURDEN", "twh_h": 0.0, "ewh_h": 0.0,
     "output_mt": 0.0,
     "stoppages": [{"from_hhmm": "0545", "to_hhmm": "1345", "duration_h": 8.0,
                    "reason": "Major OH work ( stoppage from 16.07.2026)"}]}
  ]},
 "confidence": {"report_date": 0.95, "mine": 0.9, "machines": 0.8}}
```
"""


def test_parse_extraction_stoppage_report():
    out = parse_extraction(STOPPAGE_RAW, "stoppage_report")
    f = out["fields"]
    assert f["mine"] == "MINE-I"
    assert len(f["machines"]) == 2
    assert f["machines"][0]["machine_id"] == "LBS/BWE-1029"
    assert f["machines"][0]["stoppages"][0]["duration_h"] == 2.0


def test_expand_items_flat_schema():
    records = expand_items({"production_lt": 45.2, "subsidiary": "ECL"}, {"production_lt": 0.9}, "production_report")
    by_name = {r["field_name"]: r for r in records}
    assert by_name["production_lt"]["item"] == ""
    assert by_name["production_lt"]["value"] == 45.2
    assert by_name["subsidiary"]["value"] == "ECL"


def test_expand_items_machines():
    out = parse_extraction(STOPPAGE_RAW, "stoppage_report")
    records = expand_items(out["fields"], out["confidence"], "stoppage_report")

    by_key = {(r["field_name"], r["item"]): r for r in records}
    twh = by_key[("twh_h", "LBS/BWE-1029")]
    assert twh["value"] == 18.45
    assert by_key[("output_mt", "LBS/BWE-1029")]["value"] == 9600.0
    # machine_id / material / stoppages list itself must not leak as fields
    assert not any(r["field_name"] in ("machine_id", "material", "machines", "stoppages") for r in records)
    # stoppages expanded with machine + slot + reason in the item label
    stop1 = by_key[("stoppage_duration_h", "LBS/BWE-1029|stop#1|1000-1200|Daily maintenance")]
    assert stop1["value"] == 2.0
    assert by_key[("stoppage_duration_h", "MBS/BWE-1356|stop#1|0545-1345|Major OH work ( stoppage from 16.07.2026)")]["value"] == 8.0
    # scalar document fields keep item=""
    assert by_key[("report_date", "")]["value"] == "07.09.2026"
    assert by_key[("mine", "")]["value"] == "MINE-I"
    # confidence flows through per-item
    assert abs(twh["confidence"] - 0.8) < 1e-9


def test_expand_items_skips_nulls():
    out = parse_extraction(
        '{"fields": {"mine": "MINE-I", "machines": [{"machine_id": "M1", "twh_h": null, "rate": 10.0}]}, "confidence": {}}',
        "stoppage_report",
    )
    records = expand_items(out["fields"], out["confidence"], "stoppage_report")
    names = {(r["field_name"], r["item"]) for r in records}
    assert ("twh_h", "M1") not in names
    assert ("rate", "M1") in names


# ---------- stoppage reason classification ----------

def test_classify_stoppage():
    assert classify_stoppage("Daily maintenance") == "maintenance"
    assert classify_stoppage("Major OH work ( stoppage from 16.07.2026)") == "maintenance"
    assert classify_stoppage("1st TOP ROLLER CHANGING") == "maintenance"
    assert classify_stoppage("P/S - Spr. MAN-III & Trip. 232 movement to proposed NS5") == "planned_shifting"
    assert classify_stoppage("Waiting for NNTPP conveyor") == "awaiting_infrastructure"
    assert classify_stoppage("Expansion bunker full & waiting for Expansion") == "awaiting_infrastructure"
    assert classify_stoppage("Stand by due to mine-1A working for NNTPP") == "standby"
    assert classify_stoppage("Cum stop.- M/C LT tripped while steering") == "electrical_trip"
    assert classify_stoppage("BWE Track Area Preparation & repositioning") == "repositioning"
    assert classify_stoppage("something entirely new") == "other"
    assert classify_stoppage("") == "other"


# ---------- table rendering ----------

def test_render_table():
    table = [
        ["UNIT", "supply", None],
        ["MINE-1", "578", ""],
        [None, None, None],
    ]
    out = _render_table(table)
    lines = out.splitlines()
    assert len(lines) == 2
    assert "UNIT" in lines[0] and "578" in lines[1]
    assert "|" in out


def test_render_table_empty():
    assert _render_table([[None, None]]) == ""
    assert _render_table([]) == ""


# ---------- stoppage section splitting ----------

def test_machine_header_split_finds_sections():
    from app.services.extraction import _MACHINE_HEADER_RE, _TABLE_BLOCK_RE

    text = (
        "NLC INDIA LTD\nStoppage Report for MINE-I\nDate:07.09.2026\n"
        "LBS/BWE-1029 / LIGNITE / TWH: 18.45 /EWH:18.45 / Output: 9,600.000 / Rate: 512.000\n"
        "1000 1200 02.00 Daily maintenance\n\n"
        "MBS/BWE-1356 / OVER BURDEN / TWH: 00.00 /EWH:00.00 / Output: 0.000 / Rate: 0.000\n"
        "0545 1345 08.00 Major OH work\n\n"
        "[TABLE]\nLBS/BWE-1029 | LIGNITE | 18.45\n"
    )
    headers = list(_MACHINE_HEADER_RE.finditer(text))
    assert len(headers) == 2
    # table blocks are stripped before splitting (duplicated content)
    clean = _TABLE_BLOCK_RE.sub("", text)
    assert len(list(_MACHINE_HEADER_RE.finditer(clean))) == 2
    sections = [clean[h.start(): (headers[i+1].start() if i+1 < len(headers) else len(clean))] for i, h in enumerate(headers)]
    assert "LBS/BWE-1029" in sections[0] and "Daily maintenance" in sections[0]
    assert "MBS/BWE-1356" in sections[1] and "Major OH work" in sections[1]
