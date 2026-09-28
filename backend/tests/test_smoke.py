import os
import tempfile

from app.services.analytics import count_terms
from app.services.ingest import chunk_text, extract_pages


def test_chunk_text_small():
    assert chunk_text("hello world") == ["hello world"]


def test_chunk_text_empty():
    assert chunk_text("   \n  ") == []


def test_chunk_text_long_respects_boundaries():
    text = "\n".join(f"line {i} " + "x" * 40 for i in range(60))
    chunks = chunk_text(text, size=800, overlap=100)
    assert all(len(c) <= 800 for c in chunks)
    assert len(chunks) > 1
    assert "line 59" in "\n".join(chunks)


def test_count_terms_stops_fillers():
    c = count_terms(["The production of coal and the dispatch of raw coal"])
    assert c["production"] == 1
    assert c["coal"] == 2
    assert "the" not in c
    assert "and" not in c


def test_extract_pages_txt():
    pages = extract_pages("notes.txt", b"yearly production figures")
    assert pages == [(1, "yearly production figures")]


def test_extract_pages_rejects_unknown():
    try:
        extract_pages("file.exe", b"MZ")
        raise AssertionError("should have raised ValueError")
    except ValueError:
        pass


def test_report_template_renders():
    from app.services.report_gen import make_default_template
    from docxtpl import DocxTemplate

    with tempfile.TemporaryDirectory() as td:
        tpath = os.path.join(td, "template.docx")
        make_default_template(tpath)
        tpl = DocxTemplate(tpath)
        tpl.render({
            "title": "Production Review",
            "subsidiary": "ECL",
            "period": "2023 - 2024",
            "generated_on": "2026-09-23",
            "doc_count": 2,
            "summary": "Summary text.",
            "figures": ['{"production": 10}', '{"production": 20}'],
            "ops": [],
        })
        out = os.path.join(td, "out.docx")
        tpl.save(out)
        assert os.path.getsize(out) > 1000


def test_friendly_name():
    from app.services.report_gen import _friendly_name

    assert _friendly_name("ECL_production_report_Q2_2022.txt") == "ECL Production Report Q2 2022"
    assert _friendly_name("C:\\data\\ECL_production_report_Q4_2024.docx") == "ECL Production Report Q4 2024"
    assert _friendly_name("/uploads/daily_shift_report.txt") == "Daily Shift Report"
    # hyphens inside identifiers survive (borehole ids, machine ids)
    assert _friendly_name("Suliyari-BH02_report.txt") == "Suliyari-BH02 Report"
    assert _friendly_name("") == "Document"


def test_fmt_value_and_field():
    from app.services.report_gen import _fmt_field, _fmt_value

    class F:
        def __init__(self, **kw):
            self.field_name = kw.get("field_name", "")
            self.value_num = kw.get("value_num")
            self.value_str = kw.get("value_str")
            self.unit = kw.get("unit", "")
            self.item = kw.get("item", "")

    assert _fmt_value(F(field_name="rom_lt", value_num=49.1, unit="lakh_tonnes")) == "49.1 lakh t"
    assert _fmt_value(F(field_name="total_ob_m3", value_num=0, unit="m3")) == "0 m³"
    assert _fmt_value(F(field_name="output_mt", value_num=9600.0, unit="tonnes")) == "9,600 t"
    assert _fmt_value(F(field_name="grades", value_str="G2, G3 and G4 grades")) == "G2, G3 and G4"
    assert _fmt_value(F(field_name="depth_m", value_num=210.5, unit="")) == "210.5"
    assert _fmt_field(F(field_name="washery_output_lt", value_num=4.1, unit="lakh_tonnes")) == "Washery output: 4.1 lakh t"
    assert _fmt_field(F(field_name="output_mt", value_num=9600.0, unit="tonnes", item="LBS/BWE-1029")) == "LBS/BWE-1029 - Output: 9,600 t"
    # stoppage labels carry meta info (machine|stop#1|1000-1200) - no machine prefix
    assert _fmt_field(F(field_name="stoppage_duration_h", value_num=2.0, unit="hours", item="BWE-1|stop#1|1000-1200|maint")) == "Stoppage: 2 h"
    assert _fmt_field(F(field_name="x", value_num=None)) is None


def test_tfidf_keyphrases_basic():
    from app.services.analytics import _tfidf_keyphrases

    texts = [
        "Coal production increased in Eastern Coalfields with higher output from underground mines",
        "Eastern Coalfields coal production exceeded targets in the fiscal quarter",
        "Northern Coalfields reported record coal dispatch and offtake figures",
        "Coal dispatch from Northern Coalfields grew by eight percent this year",
        "Western Coalfields maintained steady coal production levels throughout the year",
    ]
    result = _tfidf_keyphrases(texts, top_n=5)
    assert len(result) >= 1
    assert all("term" in r and "count" in r for r in result)
    terms = [r["term"] for r in result]
    assert any("coal" in t for t in terms)


def test_tfidf_keyphrases_too_few_docs():
    from app.services.analytics import _tfidf_keyphrases

    assert _tfidf_keyphrases(["single document only"], top_n=5) == []
    assert _tfidf_keyphrases([], top_n=5) == []
