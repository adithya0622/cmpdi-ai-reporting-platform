"""Text-to-SQL engine for the CMPDI AI Reporting Platform.

Generates read-only SQL from natural language using the local LLM,
executes against PostgreSQL with strict safety guards, and returns
structured results for the LLM to narrate."""

import logging
import re

from sqlalchemy import text as sqltext

from ..db import SessionLocal
from . import llm

log = logging.getLogger(__name__)

DB_SCHEMA = """
-- documents: ingested statutory documents
CREATE TABLE documents (
    id UUID PRIMARY KEY,
    title VARCHAR(500),
    doc_type VARCHAR(50),      -- 'production_report','geological','parliamentary_q','daily_shift_report','stoppage_report','administrative_memo','other'
    subsidiary VARCHAR(100),   -- 'ECL','BCCL','CCL','NCL','WCL','SECL','MCL','NLC','CIL','CMPDI',''
    doc_year INTEGER,          -- calendar year e.g. 2024
    doc_date DATE,             -- exact date for daily reports
    status VARCHAR(30),        -- 'indexed','approved','indexed_extracted'
    approved_by VARCHAR(200),
    specified_by VARCHAR(200)
);

-- extraction_fields: structured data extracted from documents
CREATE TABLE extraction_fields (
    id SERIAL PRIMARY KEY,
    document_id UUID REFERENCES documents(id),
    field_name VARCHAR(100),   -- see FIELD REFERENCE
    subsidiary VARCHAR(100),
    item VARCHAR(200),         -- machine ID or sub-item label
    value_num FLOAT,           -- numeric value (NULL if text-only)
    value_str TEXT,            -- text value (NULL if numeric)
    unit VARCHAR(30),          -- 'lakh_tonnes','mt','tonnes','m3','mw','hours','tonnes_per_hour'
    confidence FLOAT,
    status VARCHAR(20),        -- 'auto','confirmed','review','rejected'
    approved_by VARCHAR(200),
    specified_by VARCHAR(200)
);

FIELD REFERENCE (extraction_fields.field_name):
  Quarterly production: production_lt, dispatch_lt, offtake_lt, rom_lt, washery_output_lt  (unit: lakh_tonnes)
  Geological: reserves_mt (mt), depth_m (m), seam_thickness_m (m)
  Daily shift output: total_lignite_mt (tonnes per shift), total_ob_m3 (m3), power_generation_mw (mw)
  Stoppage/ops: twh_h, ewh_h (hours), output_mt (tonnes), rate (tonnes_per_hour), stoppage_duration_h (hours)

UNIT CONVERSIONS:
  1 MT (million tonnes) = 10 lakh tonnes
  production_lt is in lakh tonnes; reserves_mt is in million tonnes
  total_lignite_mt is metric tonnes per individual shift
"""

_FORBIDDEN_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|EXECUTE|COPY"
    r"|SET\s+ROLE|SET\s+SESSION|pg_sleep|pg_read_file|pg_write_file|lo_import|lo_export)\b",
    re.IGNORECASE,
)

_MAX_ROWS = 100
_STATEMENT_TIMEOUT_MS = 5000


def generate_sql(query: str, history: list[dict] | None = None) -> str | None:
    if not llm.available():
        return None

    history_hint = ""
    if history:
        for msg in reversed(history[-4:]):
            if msg.get("role") == "user":
                history_hint = f"\nPrevious question: {msg.get('content', '')[:200]}"
                break

    prompt = (
        f"Given this PostgreSQL schema:\n{DB_SCHEMA}\n\n"
        f"Write a single read-only SQL SELECT query to answer the question below.\n"
        f"Rules:\n"
        f"- Output ONLY the SQL, no explanation, no markdown fences.\n"
        f"- Only SELECT. Never INSERT, UPDATE, DELETE, DROP, or DDL.\n"
        f"- Always filter: ef.status IN ('auto','confirmed') for extraction_fields.\n"
        f"- JOIN documents d ON d.id = ef.document_id when querying extraction_fields.\n"
        f"- For production/dispatch/offtake: use d.doc_type = 'production_report'.\n"
        f"- For shift counts: COUNT documents WHERE doc_type IN ('daily_shift_report','stoppage_report').\n"
        f"- For geological: d.doc_type = 'geological'.\n"
        f"- Use ILIKE for subsidiary matching.\n"
        f"- LIMIT {_MAX_ROWS}.\n"
        f"{history_hint}\n"
        f"Question: {query}\nSQL:"
    )
    raw = llm.chat(
        prompt,
        system="You are a SQL query generator. Output only valid PostgreSQL SELECT queries.",
        max_tokens=512,
    )

    sql = raw.strip()
    if sql.startswith("```"):
        sql = sql.strip("`").removeprefix("sql").removeprefix("SQL").strip()
    m = re.search(r"(SELECT\b.+?)(?:;|\Z)", sql, re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    return m.group(1).strip().rstrip(";")


def _is_safe(sql: str) -> bool:
    return not bool(_FORBIDDEN_RE.search(sql))


def execute_readonly_query(sql: str) -> list[dict] | None:
    if not sql or not _is_safe(sql):
        return None

    db = SessionLocal()
    try:
        db.execute(sqltext(f"SET LOCAL statement_timeout = '{_STATEMENT_TIMEOUT_MS}'"))
        result = db.execute(sqltext(sql))
        columns = list(result.keys())
        rows = [dict(zip(columns, row)) for row in result.fetchmany(_MAX_ROWS)]
        return rows
    except Exception:
        log.debug("Text-to-SQL execution failed", exc_info=True)
        return None
    finally:
        db.close()


def text_to_sql_context(query: str, subsidiary: str = "", history: list[dict] | None = None) -> str | None:
    """Full pipeline: generate SQL, execute, format as context string for LLM narration.
    Returns context string or None on failure (caller should fall back to RAG)."""
    sql = generate_sql(query, history)
    if not sql or not _is_safe(sql):
        return None

    rows = execute_readonly_query(sql)
    if not rows:
        return None

    columns = list(rows[0].keys())
    lines = [
        f"[SQL Query Result — {len(rows)} row(s)]",
        f"Query: {sql[:500]}",
        "",
        "Results:",
    ]
    for i, row in enumerate(rows[:50]):
        parts = [f"{col}: {row[col]}" for col in columns if row[col] is not None]
        lines.append(f"  {i + 1}. {'; '.join(parts)}")

    lines.append("")
    lines.append(
        "Present these database results clearly. "
        "Cite every number exactly as shown. "
        "State units (lakh tonnes, MT, m3, hours) explicitly."
    )
    return "\n".join(lines)
