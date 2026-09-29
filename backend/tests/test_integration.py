"""Integration tests: full logic pipeline without a live database.
Tests pure functions across auth, extraction, RAG meta-routing, validation,
analytics, and Hindi support."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "scripts"))

from app.auth import LEVELS, hash_password, make_token, parse_token, verify_password
from app.extraction_schemas import expand_items, parse_extraction, parse_report_date
from app.services.analytics import classify_stoppage, count_terms
from app.services.extraction import (
    SUBSIDIARY_CANONICAL,
    _clean_subsidiary,
    normalize_subsidiary,
)
from app.services.rag import (
    _fix_hi_units,
    _fts_query,
    faithfulness,
    handle_conversational_or_meta,
)
from app.services.validation import check_range

# ── 1. RAG meta handler routing ─────────────────────────────────────────────

class TestMetaHandler:
    def test_greeting_hello(self):
        r = handle_conversational_or_meta("hello")
        assert r is not None
        assert r["mode"] == "meta"
        assert "CMPDI" in r["answer"] or "Hello" in r["answer"]

    def test_greeting_hi_there(self):
        r = handle_conversational_or_meta("hi there")
        assert r is not None and r["mode"] == "meta"

    def test_greeting_good_morning(self):
        r = handle_conversational_or_meta("good morning")
        assert r is not None and r["mode"] == "meta"

    def test_thanks(self):
        r = handle_conversational_or_meta("thank you")
        assert r is not None and "welcome" in r["answer"].lower()

    def test_model_identity_who_are_you(self):
        r = handle_conversational_or_meta("who are you")
        assert r is not None
        assert r["mode"] == "meta"
        assert "Sovereign" in r["answer"] or "CMPDI" in r["answer"]

    def test_model_identity_what_can_you_do(self):
        r = handle_conversational_or_meta("what can you do")
        assert r is not None and r["mode"] == "meta"

    def test_model_identity_are_you_ai(self):
        r = handle_conversational_or_meta("are you an ai")
        assert r is not None and r["mode"] == "meta"

    def test_banter_are_you_mental(self):
        r = handle_conversational_or_meta("are you mental")
        assert r is not None
        assert r["mode"] == "meta"
        assert "GPU" in r["answer"] or "ready" in r["answer"].lower()

    def test_banter_typo_r_u_crazy(self):
        r = handle_conversational_or_meta("r u crazy")
        assert r is not None and r["mode"] == "meta"

    def test_banter_you_are_stupid(self):
        r = handle_conversational_or_meta("you are stupid")
        assert r is not None and r["mode"] == "meta"

    def test_banter_standalone_nonsense(self):
        r = handle_conversational_or_meta("nonsense")
        assert r is not None and r["mode"] == "meta"

    def test_provenance_where_data_from(self):
        r = handle_conversational_or_meta("where does the data come from")
        assert r is not None
        assert r["mode"] == "meta"
        assert "hallucination" in r["answer"].lower() or "verified" in r["answer"].lower()

    def test_provenance_typo_where_did_u_get_data(self):
        r = handle_conversational_or_meta("where did u get the data from")
        assert r is not None and r["mode"] == "meta"

    def test_provenance_are_you_hallucinating(self):
        r = handle_conversational_or_meta("are you hallucinating")
        assert r is not None and r["mode"] == "meta"

    def test_provenance_is_this_made_up(self):
        r = handle_conversational_or_meta("is this made up")
        assert r is not None and r["mode"] == "meta"

    def test_capability_what_does_platform_give(self):
        r = handle_conversational_or_meta("what does the platform provide")
        assert r is not None
        assert r["mode"] == "meta"
        assert "production" in r["answer"].lower()

    def test_shifts_how_many(self):
        r = handle_conversational_or_meta("how many shifts in a day")
        assert r is not None
        assert r["mode"] == "meta"
        assert "3" in r["answer"] or "three" in r["answer"].lower()

    def test_shifts_what_shifts_are_there(self):
        r = handle_conversational_or_meta("what shifts are there")
        assert r is not None and r["mode"] == "meta"

    def test_domain_query_falls_through(self):
        assert handle_conversational_or_meta("coal production of ECL") is None

    def test_domain_query_reserves_falls_through(self):
        assert handle_conversational_or_meta("total coal reserves in India") is None

    def test_domain_query_stoppage_falls_through(self):
        assert handle_conversational_or_meta("stoppage analysis for September 2026") is None

    def test_hindi_greeting_handled(self):
        r = handle_conversational_or_meta("नमस्ते")
        assert r is not None
        assert r["mode"] == "meta"
        assert "CMPDI" in r["answer"]

    def test_feedback_still_broken(self):
        r = handle_conversational_or_meta("still broken")
        assert r is not None and r["mode"] == "meta"

    def test_banter_does_not_trigger_on_domain_word(self):
        # 'crazy' is a banter word but 'coal mine data' is domain context
        r = handle_conversational_or_meta("this coal mine data is crazy accurate")
        assert r is None  # domain words suppress banter handler


# ── 2. Faithfulness scoring ──────────────────────────────────────────────────

class TestFaithfulness:
    def test_high_overlap(self):
        score = faithfulness(
            "Coal production was 45.2 LT [source p.1].",
            [{"text": "coal production 45.2 lakh tonnes ECL"}],
        )
        assert score >= 0.5

    def test_low_overlap(self):
        score = faithfulness(
            "I made this up entirely about random things.",
            [{"text": "unrelated geological borehole exploration seam"}],
        )
        assert score < 0.5

    def test_empty_answer(self):
        assert faithfulness("", []) == 1.0

    def test_citation_only_sentence(self):
        # a sentence that is purely a citation bracket should count as grounded
        score = faithfulness("[National Inventory p.12].", [{"text": "coal data"}])
        assert score == 1.0

    def test_devanagari_excluded(self):
        # Hindi tokens can't match the English corpus; they should be excluded
        score = faithfulness(
            "कोयला भंडार total was 400.72 billion tonne.",
            [{"text": "total 400.72 billion tonne coal reserves"}],
        )
        assert score >= 0.5


# ── 3. Hindi unit fix ────────────────────────────────────────────────────────

class TestHindiUnitFix:
    def test_corrects_billion_to_arab(self):
        ans = "भारत में कुल कोयला संसाधन 400.72 मिलियन टन हैं।"
        hits = [{"text": "Total coal resources of India are 400.72 billion tonne as per CMPDI National Inventory"}]
        fixed = _fix_hi_units(ans, hits)
        assert "अरब टन" in fixed
        assert "400.72" in fixed

    def test_does_not_change_actual_million(self):
        ans = "उत्पादन 5.2 मिलियन टन था।"
        hits = [{"text": "production was 5.2 million tonne during the year"}]
        fixed = _fix_hi_units(ans, hits)
        assert "मिलियन टन" in fixed

    def test_no_hindi_unchanged(self):
        ans = "Total coal resources are 400.72 billion tonnes."
        fixed = _fix_hi_units(ans, [{"text": "400.72 billion tonne"}])
        assert fixed == ans


# ── 4. FTS query cleanup ────────────────────────────────────────────────────

class TestFtsQuery:
    def test_strips_stop_words(self):
        result = _fts_query("what is the coal production")
        assert "what" not in result.split()
        assert "is" not in result.split()
        assert "the" not in result.split()
        assert "coal" in result
        assert "production" in result

    def test_preserves_domain_words(self):
        result = _fts_query("tell me about BCCL dispatch figures")
        assert "BCCL" in result
        assert "dispatch" in result
        assert "figures" in result

    def test_hindi_bridge_appends_english(self):
        result = _fts_query("कोयला भंडार")
        assert "coal" in result
        assert "reserves" in result

    def test_empty_after_strip_returns_original(self):
        result = _fts_query("what is the")
        assert result == "what is the"

    def test_all_stop_words_returns_original(self):
        q = "tell me about the"
        result = _fts_query(q)
        assert result == q


# ── 5. Extraction edge cases ────────────────────────────────────────────────

class TestExtraction:
    def test_parse_extraction_trailing_whitespace(self):
        raw = '  {"fields": {"production_lt": 45.2, "subsidiary": "ECL"}, "confidence": {"production_lt": 0.9}}  '
        out = parse_extraction(raw, "production_report")
        assert out["fields"]["production_lt"] == 45.2

    def test_parse_extraction_fenced_json(self):
        raw = '```json\n{"fields": {"production_lt": 10}, "confidence": {}}\n```'
        out = parse_extraction(raw, "production_report")
        assert out["fields"]["production_lt"] == 10

    def test_parse_extraction_filters_unknown_fields(self):
        raw = '{"fields": {"production_lt": 10, "bogus_field": "x"}, "confidence": {}}'
        out = parse_extraction(raw, "production_report")
        assert "bogus_field" not in out["fields"]
        assert out["fields"]["production_lt"] == 10

    def test_parse_extraction_invalid_json_raises(self):
        try:
            parse_extraction("no json here at all", "production_report")
            assert False, "should have raised ValueError"
        except ValueError:
            pass

    def test_parse_extraction_schema_violation_raises(self):
        raw = '{"fields": {"production_lt": "not-a-number"}, "confidence": {}}'
        try:
            parse_extraction(raw, "production_report")
            assert False, "should have raised ValueError"
        except ValueError:
            pass

    def test_parse_report_date_dd_mm_yyyy(self):
        assert parse_report_date("DATE : 08.09.2026 SHIFT : I") == "2026-09-08"

    def test_parse_report_date_dd_dash_mm_yyyy(self):
        assert parse_report_date("dated 07-09-2026") == "2026-09-07"

    def test_parse_report_date_dd_slash_mm_yyyy(self):
        assert parse_report_date("dated 7/9/2026 shift report") == "2026-09-07"

    def test_parse_report_date_two_digit_year(self):
        assert parse_report_date("report 9.10.22 shift") == "2022-10-09"

    def test_parse_report_date_no_date(self):
        assert parse_report_date("no date here") == ""

    def test_parse_report_date_impossible_date(self):
        assert parse_report_date("bogus 99.99.2026 date") == ""

    def test_expand_items_stoppage_nil_stoppages(self):
        raw = '{"fields": {"report_date": "01.01.2026", "mine": "MINE-I", "machines": [{"machine_id": "BWE-1029", "twh_h": 10.0, "ewh_h": 8.0, "output_mt": 5000.0, "rate": 500.0, "stoppages": []}]}, "confidence": {"machines": 0.9}}'
        out = parse_extraction(raw, "stoppage_report")
        records = expand_items(out["fields"], out["confidence"], "stoppage_report")
        field_names = {r["field_name"] for r in records}
        assert "twh_h" in field_names
        assert "ewh_h" in field_names
        assert "stoppage_duration_h" not in field_names

    def test_expand_items_stoppage_no_stoppages_key(self):
        raw = '{"fields": {"report_date": "01.01.2026", "mine": "MINE-I", "machines": [{"machine_id": "M1", "twh_h": 5.0, "ewh_h": 5.0, "output_mt": 100.0, "rate": 20.0}]}, "confidence": {}}'
        out = parse_extraction(raw, "stoppage_report")
        records = expand_items(out["fields"], out["confidence"], "stoppage_report")
        assert any(r["field_name"] == "twh_h" for r in records)

    def test_clean_subsidiary_junk_shell_redirect(self):
        assert _clean_subsidiary("1>>D:\\.log 2>&1") == ""

    def test_clean_subsidiary_normal(self):
        assert _clean_subsidiary("ECL") == "ECL"

    def test_clean_subsidiary_empty(self):
        assert _clean_subsidiary("") == ""
        assert _clean_subsidiary(None) == ""

    def test_clean_subsidiary_too_long(self):
        assert _clean_subsidiary("x" * 50) == ""

    def test_clean_subsidiary_path(self):
        assert _clean_subsidiary("C:\\Users\\data\\output") == ""
        assert _clean_subsidiary("/mnt/data/results") == ""

    def test_clean_subsidiary_double_dash(self):
        assert _clean_subsidiary("--verbose") == ""


# ── 6. Auth ──────────────────────────────────────────────────────────────────

class TestAuth:
    def test_password_roundtrip(self):
        h = hash_password("s3cret")
        assert h != "s3cret"
        assert "$" in h
        assert verify_password("s3cret", h)

    def test_wrong_password(self):
        h = hash_password("correct")
        assert not verify_password("wrong", h)

    def test_verify_garbage_hash(self):
        assert not verify_password("anything", "garbage")

    def test_token_roundtrip(self):
        tok = make_token("alice", "analyst", "ECL")
        p = parse_token(tok)
        assert p is not None
        assert p["sub"] == "alice"
        assert p["role"] == "analyst"
        assert p["sub_level"] == "ECL"

    def test_expired_token(self):
        tok = make_token("bob", "viewer", "", ttl_seconds=-10)
        assert parse_token(tok) is None

    def test_tampered_token(self):
        tok = make_token("alice", "admin", "")
        tampered = tok[:-2] + "XX"
        assert parse_token(tampered) is None

    def test_role_hierarchy(self):
        assert LEVELS["viewer"] < LEVELS["analyst"] < LEVELS["admin"]


# ── 7. Validation ────────────────────────────────────────────────────────────

class TestValidation:
    def test_production_lt_in_range(self):
        assert check_range("production_lt", 45.2)

    def test_production_lt_out_of_range(self):
        assert not check_range("production_lt", 99999)

    def test_twh_h_valid(self):
        assert check_range("twh_h", 18.45)
        assert check_range("twh_h", 0)
        assert check_range("twh_h", 24)

    def test_twh_h_invalid(self):
        assert not check_range("twh_h", 30)
        assert not check_range("twh_h", -1)

    def test_ewh_h_valid(self):
        assert check_range("ewh_h", 12.5)

    def test_ewh_h_invalid(self):
        assert not check_range("ewh_h", 25)

    def test_output_mt_valid(self):
        assert check_range("output_mt", 9600)

    def test_output_mt_invalid(self):
        assert not check_range("output_mt", 200000)

    def test_stoppage_duration_h_valid(self):
        assert check_range("stoppage_duration_h", 8.0)
        assert check_range("stoppage_duration_h", 0)

    def test_stoppage_duration_h_invalid(self):
        assert not check_range("stoppage_duration_h", 25)

    def test_unknown_field_always_passes(self):
        assert check_range("unknown_field", 12345)
        assert check_range("unknown_field", -999)

    def test_depth_m_valid(self):
        assert check_range("depth_m", 302.5)

    def test_depth_m_invalid(self):
        assert not check_range("depth_m", 5000)

    def test_reserves_mt_valid(self):
        assert check_range("reserves_mt", 52.3)

    def test_power_generation_mw_valid(self):
        assert check_range("power_generation_mw", 148)

    def test_power_generation_mw_invalid(self):
        assert not check_range("power_generation_mw", 10000)


# ── 8. Analytics ─────────────────────────────────────────────────────────────

class TestAnalytics:
    def test_classify_stoppage_maintenance(self):
        assert classify_stoppage("Daily maintenance") == "maintenance"
        assert classify_stoppage("Major OH work ( stoppage from 16.07.2026)") == "maintenance"
        assert classify_stoppage("1st TOP ROLLER CHANGING") == "maintenance"

    def test_classify_stoppage_planned_shifting(self):
        assert classify_stoppage("P/S - Spr. MAN-III & Trip. 232 movement to proposed NS5") == "planned_shifting"

    def test_classify_stoppage_awaiting_infra(self):
        assert classify_stoppage("Waiting for NNTPP conveyor") == "awaiting_infrastructure"
        assert classify_stoppage("Expansion bunker full & waiting for Expansion") == "awaiting_infrastructure"

    def test_classify_stoppage_standby(self):
        assert classify_stoppage("Stand by due to mine-1A working for NNTPP") == "standby"

    def test_classify_stoppage_electrical_trip(self):
        assert classify_stoppage("Cum stop.- M/C LT tripped while steering") == "electrical_trip"

    def test_classify_stoppage_repositioning(self):
        assert classify_stoppage("BWE Track Area Preparation & repositioning") == "repositioning"

    def test_classify_stoppage_other(self):
        assert classify_stoppage("something entirely new") == "other"
        assert classify_stoppage("") == "other"

    def test_count_terms_english(self):
        c = count_terms(["The production of coal and the dispatch of raw coal"])
        assert c["production"] == 1
        assert c["coal"] == 2
        assert "the" not in c
        assert "and" not in c

    def test_count_terms_hindi(self):
        c = count_terms(["कोयला उत्पादन और कोयला भंडार"])
        assert c["कोयला"] == 2
        assert c["उत्पादन"] == 1
        assert c["भंडार"] == 1


# ── 9. Subsidiary normalization ─────────────────────────────────────────────

class TestSubsidiaryNormalization:
    def test_canonical_mapping_ecl(self):
        assert normalize_subsidiary("Eastern Coalfields") == "ECL"
        assert normalize_subsidiary("eastern coalfields limited") == "ECL"
        assert normalize_subsidiary("ECL") == "ECL"

    def test_canonical_mapping_bccl(self):
        assert normalize_subsidiary("Bharat Coking Coal") == "BCCL"
        assert normalize_subsidiary("bccl") == "BCCL"

    def test_canonical_mapping_nlc(self):
        assert normalize_subsidiary("NLC India") == "NLC"
        assert normalize_subsidiary("Neyveli Lignite") == "NLC"

    def test_canonical_mapping_cmpdi(self):
        assert normalize_subsidiary("Central Mine Planning and Design Institute") == "CMPDI"
        assert normalize_subsidiary("CMPDI") == "CMPDI"

    def test_unknown_passes_through(self):
        assert normalize_subsidiary("Some New Subsidiary") == "Some New Subsidiary"

    def test_empty_returns_empty(self):
        assert normalize_subsidiary("") == ""

    def test_whitespace_stripped(self):
        assert normalize_subsidiary("  ECL  ") == "ECL"

    def test_all_subsidiaries_present(self):
        expected = {"ECL", "BCCL", "CCL", "NCL", "WCL", "SECL", "MCL", "NLC", "CIL", "CMPDI"}
        mapped = set(SUBSIDIARY_CANONICAL.values())
        assert expected == mapped
