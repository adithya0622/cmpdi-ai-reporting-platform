import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "scripts"))

from app.auth import hash_password, make_token, parse_token, verify_password
from app.extraction_schemas import get_schema, parse_extraction
from app.services.validation import check_range


def test_password_roundtrip():
    h = hash_password("s3cret")
    assert h != "s3cret" and "$" in h
    assert verify_password("s3cret", h)
    assert not verify_password("wrong", h)
    assert not verify_password("s3cret", "garbage")


def test_token_roundtrip_and_tamper():
    tok = make_token("alice", "analyst", "ECL")
    p = parse_token(tok)
    assert p["sub"] == "alice" and p["role"] == "analyst" and p["sub_level"] == "ECL"
    assert parse_token(tok[:-2] + "AA") is None
    expired = make_token("bob", "viewer", "", ttl_seconds=-10)
    assert parse_token(expired) is None


def test_schema_registry_unknown_type():
    try:
        get_schema("unknown")
        raise AssertionError("should have raised ValueError")
    except ValueError:
        pass


def test_parse_extraction_fenced_json():
    raw = '```json\n{"fields": {"production_lt": "45.2", "subsidiary": "ECL"}, "confidence": {"production_lt": 0.9}}\n```'
    out = parse_extraction(raw, "production_report")
    assert out["fields"]["production_lt"] == 45.2
    assert out["fields"]["subsidiary"] == "ECL"
    assert out["confidence"]["production_lt"] == 0.9


def test_parse_extraction_extra_keys_filtered():
    raw = '{"fields": {"production_lt": 10, "bogus": "x"}, "confidence": {}}'
    out = parse_extraction(raw, "production_report")
    assert "bogus" not in out["fields"]
    assert out["fields"]["production_lt"] == 10


def test_parse_extraction_no_json():
    try:
        parse_extraction("no json here", "production_report")
        raise AssertionError("should have raised ValueError")
    except ValueError:
        pass


def test_parse_extraction_schema_violation():
    raw = '{"fields": {"production_lt": "not-a-number"}, "confidence": {}}'
    try:
        parse_extraction(raw, "production_report")
        raise AssertionError("should have raised ValueError")
    except ValueError:
        pass


def test_check_range():
    assert check_range("production_lt", 45.2)
    assert not check_range("production_lt", 99999)
    assert check_range("unknown_field", 12345)


def test_eval_match_and_aggregate():
    from eval_harness import evaluate, match_field

    assert match_field(45.2, 45.2)
    assert match_field(45.2, 45.3)
    assert not match_field(45.2, 50.0)
    assert match_field("ECL", "ecl ")
    out = evaluate(
        [{"doc_type": "t", "text": "x", "expected": {"a": 1, "b": "s"}}],
        lambda text, dt: {"fields": {"a": 1.0, "b": "S", "c": 3}, "confidence": {}},
    )
    r = out["t"]
    assert r["precision"] == 1.0 and r["recall"] == 1.0
