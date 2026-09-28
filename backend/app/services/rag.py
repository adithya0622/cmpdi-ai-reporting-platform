import datetime
import re

from sqlalchemy import text as sqltext

from ..config import settings
from ..db import SessionLocal
from ..extraction_schemas import field_period_type, parse_report_date
from . import embeddings, llm, rerank
from .analytics import STOP

WORD_RE = re.compile(r"[a-z\u0900-\u097F]{3,}")

FIELD_SYNONYMS = {
    "production": "production_lt",
    "dispatch": "dispatch_lt",
    "offtake": "offtake_lt",
    "rom": "rom_lt",
    "reserves": "reserves_mt",
    "output": "washery_output_lt",
    "depth": "depth_m",
    "thickness": "seam_thickness_m",
    "lignite": "total_lignite_mt",
    "overburden": "total_ob_m3",
    "ob": "total_ob_m3",
    "generation": "power_generation_mw",
}

# which doc types a figure field legitimately comes from (keeps daily tonnages out of quarterly averages)
FIELD_DOC_TYPES = {
    "production_lt": ("production_report",),
    "dispatch_lt": ("production_report",),
    "offtake_lt": ("production_report",),
    "rom_lt": ("production_report",),
    "washery_output_lt": ("production_report",),
    "reserves_mt": ("geological",),
    "depth_m": ("geological",),
    "seam_thickness_m": ("geological",),
    "total_lignite_mt": ("daily_shift_report",),
    "total_ob_m3": ("daily_shift_report",),
    "power_generation_mw": ("daily_shift_report",),
}

YEAR_RE = re.compile(r"(19|20)\d{2}")

QUERY_STOP = {
    "tell", "me", "about", "what", "was", "were", "is", "are", "the", "a", "an", "of", "in",
    "for", "to", "on", "how", "much", "many", "did", "do", "does", "give", "show", "please",
}


def _fts_query(query: str) -> str:
    """Strip conversational filler so AND-semantics of plainto_tsquery don't kill matches."""
    kept = " ".join(w for w in query.split() if w.lower() not in QUERY_STOP)
    return kept or query


def _vec_str(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def _ilike_fallback(db, base: str, params: dict, query: str, top_k: int) -> list:
    """FTS AND-semantics zero-match fallback: OR over content words via ILIKE."""
    words = [w for w in _fts_query(query).split() if len(w) >= 4][:6]
    if not words:
        return []
    conds = " OR ".join(f"c.text ILIKE :w{i}" for i in range(len(words)))
    wparams = {f"w{i}": f"%{w}%" for i, w in enumerate(words)}
    rows = db.execute(
        sqltext(f"{base}AND ({conds}) LIMIT :k"),
        {**params, **wparams, "k": top_k},
    ).mappings().all()
    return [(1.0 / (60 + i + 1), dict(r)) for i, r in enumerate(rows)]


def search(query: str, subsidiary: str = "", top_k: int = 20) -> list[dict]:
    """Hybrid search: Postgres full-text + vector cosine, fused with RRF."""
    db = SessionLocal()
    try:
        base = (
            "SELECT c.id, c.page, c.text, d.title, d.subsidiary, d.doc_type, d.approved_by, d.approved_at, d.doc_date "
            "FROM chunks c JOIN documents d ON d.id = c.document_id "
            "WHERE d.status LIKE 'indexed%' "
        )
        params: dict = {"k": top_k}
        if subsidiary:
            base += "AND (d.subsidiary ILIKE :sub OR d.subsidiary = '' OR d.subsidiary IS NULL OR d.doc_type IN ('parliamentary_q', 'other', 'national')) "
            params["sub"] = f"%{subsidiary}%"

        ranked: list[list[tuple[float, dict]]] = []

        ft = db.execute(
            sqltext(
                base + "AND c.tsv @@ plainto_tsquery('english', :q) "
                "ORDER BY ts_rank(c.tsv, plainto_tsquery('english', :q)) DESC LIMIT :k"
            ),
            {**params, "q": _fts_query(query)},
        ).mappings().all()
        if ft:
            ranked.append([(1.0 / (60 + i + 1), dict(r)) for i, r in enumerate(ft)])
        else:
            ranked.append(_ilike_fallback(db, base, params, query, top_k))

        qvec = embeddings.embed_query(query) if settings.vector_enabled else None
        if qvec is not None:
            vec = db.execute(
                sqltext(
                    base + "AND c.embedding IS NOT NULL "
                    "ORDER BY c.embedding <=> CAST(:qv AS vector) LIMIT :k"
                ),
                {**params, "qv": _vec_str(qvec)},
            ).mappings().all()
            ranked.append([(1.0 / (60 + i + 1), dict(r)) for i, r in enumerate(vec)])

        scores: dict[int, dict] = {}
        for lst in ranked:
            for score, row in lst:
                entry = scores.setdefault(row["id"], {"row": row, "score": 0.0})
                entry["score"] += score
        out = sorted(scores.values(), key=lambda x: -x["score"])[:top_k]
        return [{**v["row"], "score": round(v["score"], 4)} for v in out]
    finally:
        db.close()


def lookup_shift(query: str, subsidiary: str = "") -> dict | None:
    """Deterministic lookup for queries regarding mine shifts, relays, and shift approvals."""
    q = query.lower()

    # Parliamentary or annual inquiries route to RAG
    if any(k in q for k in ("lok sabha", "rajya sabha", "parliament", "unstarred", "starred")):
        return None

    # Check if query is asking about a shift, relay, or approver
    shift_triggers = (
        "shift", "relay", "approved by", "who approved", "approver", "approval",
        "in-charge", "in charge", "supervisor", "sign off", "signed off", "sign-off"
    )
    is_shift_query = any(t in q for t in shift_triggers)
    if not is_shift_query:
        return None

    db = SessionLocal()
    try:
        qdate = parse_report_date(query)
        if not qdate:
            dm = re.search(r"\b(\d{1,2})[-./](\d{1,2})[-./]((?:20)?\d{2})\b", query)
            if dm:
                d_str, m_str, y_str = dm.group(1), dm.group(2), dm.group(3)
                if len(y_str) == 2:
                    y_str = "20" + y_str
                try:
                    qdate = datetime.date(int(y_str), int(m_str), int(d_str))
                except Exception:
                    pass

        sql = (
            "SELECT d.id, d.title, d.doc_type, d.subsidiary, d.doc_date, d.doc_year, d.approved_by, d.approved_at, d.meta "
            "FROM documents d "
            "WHERE d.doc_type IN ('daily_shift_report', 'stoppage_report') "
        )
        params: dict = {}
        if qdate:
            if isinstance(qdate, str):
                parts = qdate.split("-")
                qd_str = f"{parts[2]}-{parts[1]}-{parts[0]}" if len(parts) == 3 else qdate
                qd_dot = f"{parts[2]}.{parts[1]}.{parts[0]}" if len(parts) == 3 else qdate
            else:
                qd_str = qdate.strftime("%d-%m-%Y")
                qd_dot = qdate.strftime("%d.%m.%Y")
            sql += "AND (d.doc_date = :qd OR d.title ILIKE :qd_str OR d.title ILIKE :qd_dot) "
            params["qd"] = qdate
            params["qd_str"] = f"%{qd_str}%"
            params["qd_dot"] = f"%{qd_dot}%"
        if subsidiary:
            sql += "AND (d.subsidiary ILIKE :sub OR d.subsidiary = '' OR d.subsidiary IS NULL) "
            params["sub"] = f"%{subsidiary}%"

        if "b1" in q or "b-1" in q:
            sql += "AND (d.title ILIKE '%b1%' OR d.title ILIKE '%b-1%' OR d.title ILIKE '%b 1%') "
        if "mine-1" in q or "mine 1" in q or "mine_1" in q or "mine-i" in q or "mine i" in q or "m-1" in q:
            sql += "AND (d.title ILIKE '%mine-1%' OR d.title ILIKE '%mine 1%' OR d.title ILIKE '%m1%' OR d.title ILIKE '%m-1%' OR d.title ILIKE '%mine_i%' OR d.title ILIKE '%mine-i%') "
        elif "mine-2" in q or "mine 2" in q or "mine_2" in q or "mine-ii" in q or "mine ii" in q or "m-2" in q:
            sql += "AND (d.title ILIKE '%mine-2%' OR d.title ILIKE '%mine 2%' OR d.title ILIKE '%m2%' OR d.title ILIKE '%m-2%' OR d.title ILIKE '%mine_ii%' OR d.title ILIKE '%mine-ii%') "

        sql += "ORDER BY d.doc_date DESC NULLS LAST, d.created_at DESC LIMIT 3"
        docs = db.execute(sqltext(sql), params).mappings().all()

        if not docs and qdate:
            sql_fallback = (
                "SELECT d.id, d.title, d.doc_type, d.subsidiary, d.doc_date, d.doc_year, d.approved_by, d.approved_at, d.meta "
                "FROM documents d "
                "WHERE d.doc_type IN ('daily_shift_report', 'stoppage_report') "
                "AND (d.doc_date = :qd OR d.title ILIKE :qd_str OR d.title ILIKE :qd_dot) "
                "ORDER BY d.doc_date DESC NULLS LAST LIMIT 3"
            )
            docs = db.execute(sqltext(sql_fallback), params).mappings().all()

        if not docs:
            sql_any = (
                "SELECT d.id, d.title, d.doc_type, d.subsidiary, d.doc_date, d.doc_year, d.approved_by, d.approved_at, d.meta "
                "FROM documents d "
                "WHERE d.doc_type IN ('daily_shift_report', 'stoppage_report') "
                "ORDER BY d.doc_date DESC NULLS LAST, d.created_at DESC LIMIT 3"
            )
            docs = db.execute(sqltext(sql_any)).mappings().all()

        if not docs:
            return None

        answers = []
        sources = []
        for d in docs:
            fields = db.execute(
                sqltext(
                    "SELECT field_name, item, value_num, value_str, unit, approved_by, status "
                    "FROM extraction_fields WHERE document_id = :did"
                ),
                {"did": d["id"]},
            ).mappings().all()

            f_dict = {}
            field_approver = None
            for f in fields:
                val = f["value_num"] if f["value_num"] is not None else f["value_str"]
                f_dict[f["field_name"]] = val
                if f.get("approved_by") and not field_approver:
                    field_approver = f["approved_by"]

            approver = d["approved_by"] or field_approver or "Pending Verification / Approval"
            app_date_str = f" on {d['approved_at'].strftime('%d.%m.%Y')}" if d["approved_at"] else ""
            status_badge = "Approved & Signed Off" if approver != "Pending Verification / Approval" else "Pending Verification"

            lines = [
                f"Shift Report: {d['title']}",
                f"• Approval Status: {status_badge}",
                f"• Approved By: {approver}{app_date_str}",
            ]
            if d["doc_date"]:
                lines.append(f"• Report Date: {d['doc_date']}")
            if f_dict.get("mine"):
                lines.append(f"• Mine / Section: Mine {f_dict.get('mine')}")
            if f_dict.get("relay") or f_dict.get("shift"):
                lines.append(f"• Relay / Shift: Relay {f_dict.get('relay', 'N/A')}, Shift {f_dict.get('shift', 'N/A')}")

            metrics = []
            if "total_lignite_mt" in f_dict and f_dict["total_lignite_mt"] is not None:
                metrics.append(f"Total Lignite Production: {float(f_dict['total_lignite_mt']):,.2f} MT")
            if "total_ob_m3" in f_dict and f_dict["total_ob_m3"] is not None:
                metrics.append(f"Total Overburden (OB): {float(f_dict['total_ob_m3']):,.2f} m3")
            if "power_generation_mw" in f_dict and f_dict["power_generation_mw"] is not None:
                metrics.append(f"Thermal Power Supply: {float(f_dict['power_generation_mw']):,.2f} MT")
            if "production_lt" in f_dict and f_dict["production_lt"] is not None:
                metrics.append(f"Production: {float(f_dict['production_lt']):,.2f} lakh t")

            if metrics:
                lines.append("• Key Operational Figures:")
                for m in metrics:
                    lines.append(f"  - {m}")

            answers.append("\n".join(lines))
            sources.append({"title": d["title"], "page": 0, "subsidiary": d["subsidiary"] or "Mining Ops", "score": 1.0})

        final_ans = "\n\n---\n\n".join(answers)
        return {
            "answer": final_ans,
            "sources": sources,
            "grounded": True,
            "mode": "shift_figures",
            "grounded_pct": 1.0,
        }
    finally:
        db.close()


def lookup_figures(query: str, subsidiary: str = "") -> dict | None:
    """Route figure questions to the structured extraction tables (exact answer, no hallucination).
    Quarterly fields aggregate per subsidiary/year; daily-ops fields list the latest day(s) instead -
    averaging across days would be meaningless."""
    q = query.lower()

    # Parliamentary or document-specific inquiries should route to RAG over full text
    if any(k in q for k in ("lok sabha", "rajya sabha", "parliament", "unstarred", "starred")) or re.search(r"\b(?:question|q)\s*\d+\b", q):
        return None

    fields = sorted({syn for word, syn in FIELD_SYNONYMS.items() if re.search(rf"\b{word}\b", q)})
    if not fields:
        return None
    m = YEAR_RE.search(query)
    year = int(m.group(0)) if m else None
    qdate = parse_report_date(query)
    daily_fields = [f for f in fields if field_period_type(f) == "daily"]
    quarterly_fields = [f for f in fields if field_period_type(f) != "daily"]

    lines: list[str] = []
    sources: list[dict] = []
    db = SessionLocal()
    try:
        for f in quarterly_fields:
            sql = (
                "SELECT ef.subsidiary, AVG(ef.value_num) AS v, MIN(d.title) AS title, COUNT(*) AS n "
                "FROM extraction_fields ef JOIN documents d ON d.id = ef.document_id "
                "WHERE ef.field_name = :f AND ef.value_num IS NOT NULL "
                "AND ef.status IN ('auto', 'confirmed', 'review') "
            )
            params: dict = {"f": f}
            dts = FIELD_DOC_TYPES.get(f)
            if dts:
                ph = ", ".join(f":dt{i}" for i in range(len(dts)))
                sql += f"AND d.doc_type IN ({ph}) "
                params.update({f"dt{i}": dt for i, dt in enumerate(dts)})
            if subsidiary:
                sql += "AND (ef.subsidiary ILIKE :s OR d.subsidiary ILIKE :s) "
                params["s"] = f"%{subsidiary}%"
            if year:
                sql += "AND d.doc_year = :y "
                params["y"] = year
            sql += "GROUP BY ef.subsidiary ORDER BY ef.subsidiary LIMIT 40"
            rows = db.execute(sqltext(sql), params).mappings().all()
            if not rows and dts:
                # doc-type filter matched nothing (e.g. legacy docs with another type) - drop it
                sql = sql.replace(f"AND d.doc_type IN ({ph}) ", "")
                rows = db.execute(sqltext(sql), params).mappings().all()
            for r in rows:
                unit = "lakh t" if f.endswith("_lt") else ("MT" if f.endswith("_mt") else "")
                lines.append(f"{f} ({r['subsidiary'] or 'all'}): {r['v']:.2f} {unit} - source: {r['title']} ({r['n']} docs)")
                sources.append({"title": r["title"], "page": 0, "subsidiary": r["subsidiary"], "score": 1.0})

        for f in daily_fields:
            sql = (
                "SELECT ef.value_num, ef.item, ef.unit, ef.approved_by, d.title, d.doc_date, d.doc_year, d.approved_by AS doc_approved_by "
                "FROM extraction_fields ef JOIN documents d ON d.id = ef.document_id "
                "WHERE ef.field_name = :f AND ef.value_num IS NOT NULL "
                "AND ef.status IN ('auto', 'confirmed', 'review') "
            )
            params = {"f": f}
            if subsidiary:
                sql += "AND (ef.subsidiary ILIKE :s OR d.subsidiary ILIKE :s) "
                params["s"] = f"%{subsidiary}%"
            if qdate:
                sql += "AND d.doc_date = :dd "
                params["dd"] = qdate
            elif year:
                sql += "AND d.doc_year = :y "
                params["y"] = year
            sql += "ORDER BY d.doc_date DESC NULLS LAST, d.created_at DESC LIMIT 8"
            for r in db.execute(sqltext(sql), params).mappings().all():
                when = f" on {r['doc_date']}" if r["doc_date"] else (f" ({r['doc_year']})" if r["doc_year"] else "")
                item = f" [{r['item']}]" if r["item"] else ""
                approver = r.get("approved_by") or r.get("doc_approved_by")
                approver_str = f" (Approved by: {approver})" if approver else ""
                lines.append(f"{f}{item}: {r['value_num']:,.2f} {r['unit']}{when}{approver_str} - source: {r['title']}")
                sources.append({"title": r["title"], "page": 0, "subsidiary": "", "score": 1.0})
    finally:
        db.close()
    if not lines:
        return None
    ans = "Extracted figures" + (f" for {year}" if year else "") + (f" on {qdate}" if qdate else "") + ":\n" + "\n".join(lines[:20])
    return {"answer": ans, "sources": sources[:8], "grounded": True, "mode": "figures"}


def faithfulness(answer_text: str, hits: list[dict]) -> float:
    """Share of answer sentences whose content words appear in the cited chunks. Catches hallucination."""
    corpus_tokens: set[str] = set()
    for h in hits:
        corpus_tokens.update(WORD_RE.findall(h["text"].lower()))
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", answer_text) if s.strip()]
    if not sentences:
        return 1.0
    ok = 0
    for s in sentences:
        words = [w for w in WORD_RE.findall(s.lower()) if w not in STOP]
        if not words:
            ok += 1
            continue
        if sum(1 for w in words if w in corpus_tokens) / len(words) >= 0.5:
            ok += 1
    return ok / len(sentences)


def answer(query: str, subsidiary: str = "", history: list[dict] | None = None) -> dict:
    shift_res = lookup_shift(query, subsidiary)
    if shift_res:
        shift_res["grounded_pct"] = 1.0
        return shift_res

    fig = lookup_figures(query, subsidiary)
    if fig:
        fig["grounded_pct"] = 1.0
        return fig

    hits = rerank.rerank(query, search(query, subsidiary=subsidiary))
    sources = [
        {"title": h["title"], "page": h["page"], "subsidiary": h["subsidiary"], "score": h["score"]}
        for h in hits
    ]
    if not hits:
        return {"answer": "No relevant documents found in the indexed corpus.", "sources": [], "grounded": False, "mode": "rag", "grounded_pct": None}
    if llm.available():
        context_parts = []
        for h in hits:
            hdr = f"[{h['title']} p.{h['page']}"
            if h.get("approved_by"):
                hdr += f" | Shift Approved By: {h['approved_by']}"
            elif h.get("doc_type") in ("daily_shift_report", "stoppage_report"):
                hdr += " | Shift Approval Status: Pending Verification"
            hdr += "]"
            context_parts.append(f"{hdr}\n{h['text']}")
        context = "\n\n".join(context_parts)
        prompt = ""
        if history:
            turns = "\n".join(f"{t.get('role', 'user')}: {t.get('content', '')}" for t in history[-6:])
            prompt += f"Conversation so far:\n{turns}\n\n"
        prompt += (
            "Answer the question using ONLY the context below. Cite sources as [title p.page]. "
            "If the question is about a mine shift, relay, or daily operational report, ALWAYS state the name of the person who approved the shift and the approval status. "
            "If the context does not contain the answer, say so.\n\n"
            f"Context:\n{context}\n\nQuestion: {query}"
        )
        ans = llm.chat(prompt)
    else:
        # extractive fallback so RAG works before the LLM server is up
        ans = "LLM unavailable. Top matching passages:\n\n" + "\n\n".join(
            f"[{h['title']} p.{h['page']}] {h['text'][:300]}" for h in hits[:3]
        )
    grounded_pct = faithfulness(ans, hits)
    return {
        "answer": ans,
        "sources": sources,
        "grounded": True,
        "mode": "rag",
        "grounded_pct": round(grounded_pct, 2),
    }


def log_query(question: str, answer_text: str, sources: list, username: str = "", subsidiary: str = "", latency_ms: int = 0, mode: str = "", grounded_pct: float | None = None) -> None:
    from ..models import QueryLog

    try:
        db = SessionLocal()
        try:
            db.add(QueryLog(
                question=question[:2000], answer=answer_text[:8000], sources=sources,
                username=username or "", subsidiary=subsidiary or "",
                latency_ms=latency_ms, mode=mode, grounded_pct=grounded_pct,
            ))
            db.commit()
        finally:
            db.close()
    except Exception:
        pass
