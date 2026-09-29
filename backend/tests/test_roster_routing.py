"""Regression tests for roster/approver aggregation routing.

Covers the failure reported by the user: paraphrases of
"give me the names of all the people who have approved the shifts in the
past 4 years" were falling through to generic RAG because the LLM intent
classifier missed them and the deterministic detector only ran when the
classifier already said "roster".

Strategy (mirrors existing test suites - DB-free where possible):
- pure predicate tests for _is_roster_query (no DB, no LLM)
- DB-backed detector tests that SKIP when Postgres is unreachable
- answer() misroute-rescue tests with llm.chat monkeypatched
- _regex_fallback_intent coverage (LLM-down path)
"""
import pytest

from app.services import rag
from app.services.rag import (
    _is_roster_query,
    _parse_year_scope,
    _regex_fallback_intent,
    _roster_relative_years,
    lookup_roster_or_approvers,
)


# ── 1. Predicate: the exact reported failure + variants ──────────────────────

class TestRosterPredicate:
    @pytest.mark.parametrize(
        "query",
        [
            # the user's exact phrasing
            "give m the names of all the people who have approved the shifts in the past 4 years",
            # the 5 paraphrases that failed live before the fix
            "name the people responsible for approving shifts since 2022",
            "engineers who approved shifts in 2024 and 2025",
            "who were the shift in-charges during 2023",
            "show me the approval history for all shifts",
            "how many different officers have signed shifts acorss the yars",
            "list everyone who has ever signed off a shift report",
            # typos that must stay caught
            "who aproved the shifts acorss the yars",
            "names of ppl who verfied shifts over the period",
        ],
    )
    def test_matches(self, query):
        assert _is_roster_query(query), f"should be roster: {query!r}"

    @pytest.mark.parametrize(
        "query",
        [
            # single-date lookups belong to individual_shift
            "who approved the shift on 08.09.2026",
            "who was the approver for 07-09-2026 relay",
            # superlatives belong to top_approver
            "who approved the most shifts",
            "which engineer signed the highest number of shifts",
            # plain figure/knowledge questions
            "what is India total coal reserve",
            "coal production of ECL in 2024",
            # banter/meta
            "hello",
            "who are you",
        ],
    )
    def test_non_matches(self, query):
        assert not _is_roster_query(query), f"should NOT be roster: {query!r}"


# ── 2. Year-scope parsing ────────────────────────────────────────────────────

class TestYearScope:
    def test_single_year(self):
        assert _parse_year_scope("shift in-charges during 2023") == (2023, 2023)

    def test_two_years_spans(self):
        assert _parse_year_scope("engineers who approved shifts in 2024 and 2025") == (2024, 2025)

    def test_since_year(self):
        assert _parse_year_scope("approving shifts since 2022") == (2022, 2022)

    def test_no_year_returns_none(self):
        assert _parse_year_scope("everyone who approved shifts across the years") is None

    def test_relative_window(self):
        assert _roster_relative_years("approved the shifts in the past 4 years") == 4
        assert _roster_relative_years("approved shifts in recent years") == 4
        assert _roster_relative_years("approved shifts since 2022") is None


# ── DB helpers ───────────────────────────────────────────────────────────────

def _db_reachable() -> bool:
    try:
        from app.db import get_engine

        with get_engine().connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        return True
    except Exception:
        return False


DB = pytest.mark.skipif(not _db_reachable(), reason="Postgres not reachable")


# ── 3. End-to-end detector (DB-derived roster) ───────────────────────────────

@DB
class TestRosterDetectionEndToEnd:
    def test_exact_user_query(self):
        r = lookup_roster_or_approvers(
            "give m the names of all the people who have approved the shifts in the past 4 years"
        )
        assert r is not None
        assert r["mode"] == "roster_aggregation"
        assert r["grounded"] is True
        # roster must be DB-derived: at least one officer name present
        assert "Certified Statutory Shift Approvers" in r["answer"]
        assert "**Er." in r["answer"] or "**Dr." in r["answer"] or "1." in r["answer"]

    def test_year_scoped_query_runs_scoped_sql(self):
        r = lookup_roster_or_approvers("engineers who approved shifts in 2024 and 2025")
        assert r is not None and r["mode"] == "roster_aggregation"
        assert "2024" in r["answer"] and "2025" in r["answer"]

    def test_specifier_focused_query_leads_with_specifiers(self):
        r = lookup_roster_or_approvers("who were the shift in-charges during 2023")
        if r is None:
            pytest.skip("no 2023 shift records in DB")
        assert r["mode"] == "roster_aggregation"
        assert "Specifiers" in r["answer"]
        # specifiers section must come BEFORE approvers section
        assert r["answer"].find("Specifiers") < r["answer"].find("Approvers")

    def test_scoped_empty_returns_helpful_note(self):
        r = lookup_roster_or_approvers("people who approved shifts in 1999")
        assert r is not None and r["mode"] == "roster_aggregation"
        assert "1999" in r["answer"]
        assert "No shift approvals are recorded" in r["answer"]

    def test_followup_exclusive_probe(self):
        # standalone the probe phrase lacks an approval verb, so it must include
        # enough roster context to pass the gate - as real follow-ups do
        r = lookup_roster_or_approvers("are these the only people who approved shifts")
        assert r is not None and r["mode"] == "roster_aggregation"
        assert r["answer"].startswith("**No.**")


# ── 4. answer() misroute rescue (classifier says 'rag', detector saves it) ───

class TestAnswerRescue:
    def _force_classifier_rag(self, monkeypatch):
        monkeypatch.setattr(rag.llm, "chat", lambda *a, **k: "rag")
        monkeypatch.setattr(rag.llm, "available", lambda: True)

    def test_rescue_on_misroute(self, monkeypatch):
        self._force_classifier_rag(monkeypatch)
        r = rag.answer("show me the approval history for all shifts")
        assert r["mode"] == "roster_aggregation"
        assert "Approvers" in r["answer"] or "Statutory roster" in r["answer"]

    def test_rescue_on_garbage_intent(self, monkeypatch):
        monkeypatch.setattr(rag.llm, "chat", lambda *a, **k: "zzz nonsense")
        monkeypatch.setattr(rag.llm, "available", lambda: True)
        r = rag.answer("name the people responsible for approving shifts since 2022")
        assert r["mode"] == "roster_aggregation"

    def test_no_rescue_for_plain_rag_question(self, monkeypatch):
        # non-roster questions must still reach the RAG path, not the rescue
        self._force_classifier_rag(monkeypatch)
        r = rag.answer("what is India total coal reserve")
        assert r["mode"] == "rag"


# ── 5. rag_stream rescue yields a done event ────────────────────────────────

class TestStreamRescue:
    def test_stream_rescue_on_misroute(self, monkeypatch):
        monkeypatch.setattr(rag.llm, "chat", lambda *a, **k: "rag")
        monkeypatch.setattr(rag.llm, "available", lambda: True)
        events = list(rag.rag_stream("list everyone who has ever signed off a shift report"))
        done = [e for e in events if e["type"] == "done"]
        assert done, "expected a done event"
        assert done[0]["result"]["mode"] == "roster_aggregation"


# ── 6. Regex fallback (LLM down) routes roster queries ──────────────────────

class TestRegexFallback:
    def test_roster_variants_route_to_roster(self):
        assert _regex_fallback_intent("who were the shift in-charges during 2023", {}) == "roster"
        assert _regex_fallback_intent("show me the approval history for all shifts", {}) == "roster"

    def test_non_roster_still_routes_correctly(self):
        assert _regex_fallback_intent("describe the geology of the Jharia coalfield", {}) == "rag"
        assert _regex_fallback_intent("who approved the shift on 08.09.2026", {}) == "individual_shift"
