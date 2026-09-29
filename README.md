# CMPDI AI Reporting Platform

AI-assisted document processing and reporting for CMPDI/CIL subsidiaries. On-prem, air-gapped capable.

## Modules

| Module | Endpoint | What it does |
|---|---|---|
| Report generation | `POST /reports/generate`, `GET /reports/{id}/download?format=docx\|pdf` | Filters corpus by subsidiary/year, LLM executive summary, Word/PDF report via docxtpl |
| Word cloud + topics | `GET /analytics/wordcloud`, `GET /analytics/topics` | Term frequency cloud (wordcloud lib or matplotlib fallback), MiniBatchKMeans topic clustering |
| Trends | `GET /analytics/trends`, `GET /analytics/topic_trends` | Yearly averages of extracted fields (chart data), topics over time |
| Query & response (RAG) | `POST /query`, `GET /query/stream` | Hybrid search (FTS + pgvector HNSW, RRF) + cross-encoder reranker, Text-to-SQL fallback, figure-question routing, multi-turn, cited answers, faithfulness score, SSE streaming |
| Extraction + review | `POST /extractions/run`, `GET /extractions/review` | Schema-validated LLM extraction with unit normalization, per-field confidence, human review queue, anomaly flags |
| Daily operations analytics | `GET /analytics/stoppage_pareto`, `GET /analytics/machine_utilization` | Downtime Pareto by stoppage-reason category, per-machine EWH/TWH utilization % |
| Admin | `GET /admin/overview\|jobs\|audit\|queries`, `POST /admin/jobs/{id}/retry` | KPIs, job monitor with retry, audit trail, faithfulness monitor |
| Auth / RBAC | `POST /auth/login`, `POST /auth/users` | PBKDF2 passwords, HMAC-signed JWT tokens, roles (viewer/analyst/admin), subsidiary scoping, rate limiting |
| Ingestion | `POST /documents/upload` | PDF (digital + OCR fallback, table-aware), DOCX, XLSX, TXT/CSV, images (OCR eng+hin), chunking + embeddings; doc-type + report-date auto-inference from filename |

## Architecture & Defense

### Intent Router (Two-Phase)
1. **Fast-path regex** — pattern-matches meta, roster, shift count, and corpus-coverage queries directly
2. **LLM classifier** (Qwen3-8B) — categorizes into 11 intent slots: `meta`, `corpus_coverage`, `roster`, `shift_count`, `top_approver`, `aggregate_production`, `ranked_shift`, `individual_shift`, `comparison`, `figures`, `rag`

### Text-to-SQL vs Hybrid RAG
- Structured queries (counts, aggregations, top-N) hit the **Text-to-SQL** engine: LLM generates SQL from a strict schema, SQL injection guard (`_is_safe`) blocks writes/DDL/dangerous functions, readonly execution with `statement_timeout` of 5s and row cap of 100, then LLM narrates the result set
- Unstructured queries fall through to **Hybrid RAG**: pgvector cosine + tsvector BM25, RRF rank fusion, BAAI/bge-reranker-v2-m3 cross-encoder reranking, post-generation grounding check (threshold 0.65)

### Unit Normalization
Extraction and report generation enforce canonical units:
- **Quarterly production** → lakh tonnes (values >100k auto-scaled)
- **Daily shift** → metric tonnes (passthrough, no conversion)
- **Reserves** → MT (passthrough)
- **Overburden** → m³ (passthrough)
- Normalization runs at extraction time (`_normalize_unit`) and at report generation time

### PDF Export
- Windows: `docx2pdf` (COM-based, high fidelity)
- Linux/Docker: `LibreOffice --headless --convert-to pdf`
- Endpoint: `GET /reports/{id}/download?format=pdf`

### Topic Clustering & Word Cloud
- `cluster_topics()` — MiniBatchKMeans over TF-IDF with configurable k (default 5)
- `wordcloud_image()` — `wordcloud` lib (PNG) or matplotlib bar chart fallback
- New doc type: `administrative_memo` (office memos, circulars, office orders)

## API Reference

### Query Router
```
POST /query
  Body: { "question": "...", "subsidiary": "BCCL", "history": [...] }
  Returns: { "answer": "...", "sources": [...], "grounded_pct": 0.87 }

GET  /query/stream?question=...&subsidiary=BCCL
  Returns: SSE stream (text/event-stream), chunked answer tokens
```

### PDF / DOCX Export
```
POST /reports/generate
  Body: { "subsidiary": "ECL", "year": 2024, "doc_types": [...] }
  Returns: { "report_id": "uuid", "title": "..." }

GET  /reports/{id}/download?format=docx   (default)
GET  /reports/{id}/download?format=pdf
```

### Analytics
```
GET /analytics/topics?subsidiary=BCCL&n_clusters=5
GET /analytics/wordcloud?subsidiary=BCCL&format=png
GET /analytics/trends?field=production_lt&subsidiary=ECL
GET /analytics/stoppage_pareto?date_from=2024-01-01&date_to=2024-12-31
GET /analytics/machine_utilization
```

### Extraction
```
POST /extractions/run         { "document_id": "uuid", "doc_type": "production_report" }
GET  /extractions/review      Returns fields needing human review
POST /extractions/fields/{id}/review   { "action": "confirm|reject", "value": ... }
```

Doc types: `production_report`, `geological`, `parliamentary_q`, `daily_shift_report`, `stoppage_report`, `administrative_memo`

## Stack

- Backend: FastAPI, SQLAlchemy 2, PostgreSQL + pgvector (structured data, full-text, vectors — one DB, three jobs)
- LLM: any OpenAI-compatible server - llama.cpp `llama-server` with Qwen3-8B (Q4_K_M) locally, or vLLM; works without LLM (graceful degradation)
- Embeddings: `intfloat/multilingual-e5-small` (384-dim, Hindi + English)
- Reranker: `BAAI/bge-reranker-v2-m3` cross-encoder (disable with `RERANKER_ENABLED=false`)
- OCR: Tesseract (eng+hin)
- Frontend: React + TypeScript (Vite) in `frontend/`, built into Docker image multi-stage; static `index.html` fallback
- Deploy: Docker Compose (`db` + `backend` always; `vllm` via `--profile llm`); Nginx reverse proxy with SSE support

## Run

### Docker (recommended)

```bash
# Full stack: DB + backend (with frontend built-in) + nginx
docker compose up --build -d

# With LLM server (needs NVIDIA GPU + nvidia-container-toolkit)
docker compose --profile llm up -d

# Rebuild after code changes
docker compose up --build -d --force-recreate backend
```

Open http://localhost (nginx) or http://localhost:8000 (direct backend)

### Local dev (no Docker)

```powershell
cd backend
copy .env.example .env        # edit DATABASE_URL to point at your Postgres
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\uvicorn app.main:app --reload
```

Frontend dev server:
```bash
cd frontend
npm install
npm run dev     # Vite dev server on :5173, proxies /api to backend
npm run build   # production build -> backend/app/static/
```

OCR on Windows: install [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) and add to PATH.

### Demo data seeding

```bash
# With database running:
DATABASE_URL=postgresql://user:pass@localhost:5432/cmpdi python backend/scripts/seed_demo_data.py

# Without database (JSON export):
python backend/scripts/seed_demo_data.py
# -> backend/scripts/demo_seed_data.json
```

### Verification

```bash
python backend/scripts/verify_demo_pipeline.py
```

## Batch ingestion (historical archives)

```powershell
.venv\Scripts\python scripts\batch_ingest.py D:\archive\ECL ECL
```

Walks folder recursively, extracts year from filename, ingests all supported files.

## Job worker

```powershell
.venv\Scripts\python scripts\worker.py            # processes ingest + extraction jobs
.venv\Scripts\python scripts\worker.py --once     # drain queue and exit
```

Uploads are queued jobs; the worker processes them. Safe to run multiple workers (SKIP LOCKED claim).

## Auth

- First boot creates admin user; password printed once to console (or set `ADMIN_PASSWORD`/`ADMIN_USER` env)
- `POST /auth/login {username, password}` -> `{token}`; send token as `X-API-Token` header
- Roles: viewer < analyst < admin; non-admin users locked to their `subsidiary` on every query
- Create users: `POST /auth/users {username, password, role, subsidiary}` (admin only)
- Set `AUTH_SECRET` env in production (tokens are signed with it)

## Extraction + review queue

- `POST /extractions/run {document_id, doc_type}` - doc types: `production_report`, `geological`, `parliamentary_q`, `daily_shift_report`, `stoppage_report`, `administrative_memo` (schema registry in `app/extraction_schemas.py`)
- LLM extracts -> JSON validated against schema -> per-field confidence stored with doc + run traceability
- Unit normalization applied at extraction time: lakh tonnes for quarterly, metric tonnes for daily shifts, MT for reserves, m³ for overburden
- Stoppage reports expand per-machine rows + individual stoppages (`machine_id`, `stoppage_duration_h` with reason in the item label) for Pareto/utilization analytics
- Figure questions are period-aware: quarterly fields aggregate per subsidiary/year; daily fields return the latest day (or the exact date asked), never a bogus average across days
- Low-confidence (< threshold), out-of-range, or anomalous fields (|z|>3 vs subsidiary history) land in the review queue - never silent-fail
- Review: `GET /extractions/review` + `POST /extractions/fields/{id}/review {action: confirm|reject, value?}`
- Totals cross-check (CIL total vs sum of subsidiaries): `GET /extractions/validation/totals?field_name=production_lt&year=2024`

## Eval harness

```powershell
.venv\Scripts\python scripts\eval_harness.py --gold evals\gold_set.jsonl
```

Field-level precision/recall/F1 vs gold set (numbers within 1%, strings case-insensitive). Add hand-verified entries to the JSONL and run after every model or schema change - this is where the 95%+ accuracy target is tracked.

## Daily operations reports (NLC Mine-I style)

Filenames carry the date and kind, so batch ingestion just works:

- `08-09-2026-B1 RELAY- 1st SHIFT -LBS-M1.pdf` -> `daily_shift_report`, date 2026-09-08 (BWE shift output, lignite tonnes, OB m3, supply to power units)
- `M-1 STOPPAGE on 07.09.2026.pdf` -> `stoppage_report`, date 2026-09-07 (per-machine TWH/EWH/output/rate + timestamped stoppages with reasons)

Analytics over extracted stoppages: `GET /analytics/stoppage_pareto?date_from=...&date_to=...` (reason categories: maintenance, planned_shifting, awaiting_infrastructure, standby, electrical_trip, repositioning, other) and `GET /analytics/machine_utilization` (EWH/TWH %). Ask "what was the total lignite production on 08.09.2026" on the Query page for an exact, sourced answer.

## Config (backend/.env or compose environment)

| Var | Default | Notes |
|---|---|---|
| `DATABASE_URL` | localhost pg | use `db` host in compose; on Windows with App Control policy blocking psycopg2, use `postgresql+pg8000://` |
| `AUTH_SECRET` | random | set in production for stable token signing |
| `LLM_BASE_URL` / `LLM_MODEL` | local llama-server (Qwen3-8B) | any OpenAI-compatible endpoint (llama.cpp/vLLM/Ollama) |
| `EMBEDDING_MODEL` | multilingual-e5-small | must be 384-dim (matches `Vector(384)`) |
| `RERANKER_ENABLED` | true | set false to skip cross-encoder reranking |
| `OCR_LANG` | eng+hin | Tesseract languages |
| `DEMO_MODE` | false | set true for demo (relaxed auth, sample data) |

## Tests

```powershell
cd backend
.venv\Scripts\python -m pytest tests -v
```

## Repo layout

```
backend/app/
├── main.py            # FastAPI app, static frontend mount
├── config.py db.py models.py schemas.py deps.py
├── routers/           # documents, reports, analytics, query, auth, admin
├── services/          # ingest, embeddings, llm, rag, text_to_sql, analytics, report_gen, extraction
├── static/index.html  # built frontend
└── templates/         # custom docxtpl report template (optional)
backend/scripts/
├── verify_demo_pipeline.py   # end-to-end objective verification
├── seed_demo_data.py         # demo data generator (DB or JSON)
├── batch_ingest.py           # bulk folder ingestion
├── worker.py                 # background job processor
├── eval_harness.py           # extraction accuracy eval
└── backup.py                 # pg_dump + file backup
frontend/
├── src/               # React + TypeScript source (Vite)
└── index.html         # dev entry point
nginx.conf             # reverse proxy + SSE config
docker-compose.yml     # db + backend + optional vllm
```

## Deliberate simplifications (upgrade when needed)

- pgvector instead of Qdrant, filesystem instead of MinIO — one service; add when multi-node scale demands
- MiniBatchKMeans topics instead of KeyBERT/BERTopic — swap in when topic quality matters
- In-memory per-IP rate bucket — Redis-backed if multi-node
- Lexical faithfulness check — LLM-judge if precision matters
- HMAC tokens instead of full JWT/pyjwt — same guarantees (signed payload + expiry), stdlib only; swap if SSO integration arrives
- Report figures rendered as JSON strings — style the docxtpl template once extraction schema is stable
