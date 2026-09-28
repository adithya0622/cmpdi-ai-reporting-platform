# CMPDI AI Reporting Platform

AI-assisted document processing and reporting for CMPDI/CIL subsidiaries. On-prem, air-gapped capable.

## Modules

| Module | Endpoint | What it does |
|---|---|---|
| Report generation | `POST /reports/generate`, `GET /reports/{id}/download` | Filters corpus by subsidiary/year, LLM executive summary, Word report via docxtpl |
| Word cloud + topics | `GET /analytics/wordcloud`, `GET /analytics/topics` | Term frequency cloud, bigram topics, optional LLM topic summary |
| Trends | `GET /analytics/trends`, `GET /analytics/topic_trends` | Yearly averages of extracted fields (chart data), topics over time |
| Query & response (RAG) | `POST /query` | Hybrid search (FTS + pgvector HNSW, RRF) + cross-encoder reranker, figure-question routing to extracted data, multi-turn, cited answers, faithfulness score, extractive fallback when LLM down |
| Extraction + review | `POST /extractions/run`, `GET /extractions/review` | Schema-validated LLM extraction, per-field confidence, human review queue, anomaly flags |
| Daily operations analytics | `GET /analytics/stoppage_pareto`, `GET /analytics/machine_utilization` | Downtime Pareto by stoppage-reason category, per-machine EWH/TWH utilization % |
| Admin | `GET /admin/overview|jobs|audit|queries`, `POST /admin/jobs/{id}/retry` | KPIs, job monitor with retry, audit trail, faithfulness monitor |
| Auth / RBAC | `POST /auth/login`, `POST /auth/users` | HMAC tokens, roles (viewer/analyst/admin), subsidiary scoping, rate limiting |
| Ingestion | `POST /documents/upload` | PDF (digital + OCR fallback, table-aware), DOCX, XLSX, TXT/CSV, images (OCR eng+hin), chunking + embeddings; doc-type + report-date auto-inference from filename |

## Stack

- Backend: FastAPI, SQLAlchemy 2, PostgreSQL + pgvector (structured data, full-text, vectors — one DB, three jobs)
- LLM: any OpenAI-compatible server - llama.cpp `llama-server` with Qwen3-8B (Q4_K_M) locally, or vLLM; works without LLM (graceful degradation)
- Embeddings: `intfloat/multilingual-e5-base` (Hindi + English)
- OCR: Tesseract (eng+hin)
- Frontend: static HTML/JS served by backend at `/` (no npm build step — air-gapped friendly)
- Deploy: Docker Compose (`db` + `backend` always; `vllm` via `--profile llm`)

## Run

```powershell
docker compose up --build -d            # db + backend
docker compose --profile llm up -d      # + LLM server (needs NVIDIA GPU)
```

Open http://localhost:8000

Local dev (no Docker):

```powershell
cd backend
copy .env.example .env        # edit DATABASE_URL to point at your Postgres
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\uvicorn app.main:app --reload
```

OCR on Windows: install [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) and add to PATH.

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

- `POST /extractions/run {document_id, doc_type}` - doc types: `production_report`, `geological`, `parliamentary_q`, `daily_shift_report`, `stoppage_report` (schema registry in `app/extraction_schemas.py`)
- LLM extracts -> JSON validated against schema -> per-field confidence stored with doc + run traceability
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

## Full build (Phases B-D)

- **Reranker**: `BAAI/bge-reranker-v2-m3` cross-encoder on top-20 hybrid hits (disable with `RERANKER_ENABLED=false`)
- **Figure-question routing**: production/dispatch/reserves questions query extracted data first - exact answers, no hallucination; everything else RAG
- **Multi-turn**: frontend chat sends history; backend resolves follow-ups
- **Faithfulness score**: every answer gets % of sentences grounded in cited chunks; monitored in `GET /admin/queries`
- **Rate limiting**: per-IP token bucket, `RATE_LIMIT_PER_MIN` (default 120)
- **Frontend**: React + TS (Vite) in `frontend/`, served by backend; `npm install && npm run build` in frontend/ (or built into the Docker image multi-stage). Static `index.html` fallback if no dist.
- **Backups**: `python scripts/backup.py` (pg_dump + report files) - schedule daily via cron/Task Scheduler
- **Load test**: `python scripts/load_test.py --users 50 --concurrency 10 --token <token>`
- **Fine-tuning (Phase D)**: `python scripts/finetune_lora.py --build-only` builds training JSONL from confirmed extractions (needs >= 50); LoRA training runs on the GPU server (torch/peft)
- **CI**: `.github/workflows/ci.yml` - ruff lint, pytest (with pgvector service), frontend build

## Air-gap deployment

Pre-download on a connected machine, then copy into `./data` (mounted at `/data` in container):

- Models: `Qwen/Qwen3-8B-GGUF` (Q4_K_M), `intfloat/multilingual-e5-base`
- pip wheels: `pip download -r backend/requirements.txt -d wheels/`
- vLLM image: `docker pull vllm/vllm-openai:v0.6.6` + `docker save`

## Config (backend/.env or compose environment)

| Var | Default | Notes |
|---|---|---|
| `DATABASE_URL` | localhost pg | use `db` host in compose; on Windows with App Control policy blocking psycopg2, use `postgresql+pg8000://` |
| `API_TOKEN` | empty = auth off | set a token to require `X-API-Token` header |
| `LLM_BASE_URL` / `LLM_MODEL` | local llama-server (Qwen3-8B) | any OpenAI-compatible endpoint (llama.cpp/vLLM/Ollama) |
| `EMBEDDING_MODEL` | multilingual-e5-base | must be 384-dim (matches `Vector(384)`) |
| `OCR_LANG` | eng+hin | Tesseract languages |

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
├── routers/           # documents, reports, analytics, query
├── services/          # ingest (OCR+chunk), embeddings, llm, rag, analytics, report_gen
├── static/index.html  # UI
└── templates/         # custom docxtpl report template (optional)
```

## Deliberate simplifications (upgrade when needed)

- pgvector instead of Qdrant, filesystem instead of MinIO — one service; add when multi-node scale demands
- Bigram topics instead of KeyBERT/BERTopic — swap in when topic quality matters
- In-memory per-IP rate bucket — Redis-backed if multi-node
- Lexical faithfulness check — LLM-judge if precision matters
- HMAC tokens instead of full JWT/pyjwt — same guarantees (signed payload + expiry), stdlib only; swap if SSO integration arrives
- Report figures rendered as JSON strings — style the docxtpl template once extraction schema is stable
