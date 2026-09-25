# HANDOVER — CMPDI AI Reporting Platform

Operational handover: what runs, how to operate, how to troubleshoot.

## 1. What is running

```
[Documents] → [Worker: OCR + chunking + embeddings + LLM extraction]
    → [PostgreSQL + pgvector: full-text, vectors, structured figures]
    → [FastAPI: documents / reports / analytics / query / extractions / admin]
    → [React UI at /]  (+ static fallback)
[LLM server: vLLM Qwen2.5-7B on GPU]  (optional; extractive fallback without it)
```

Modules: report generation (docxtpl Word), word cloud + topic ID + trends, RAG query/response
with figure routing, schema-validated extraction with human review queue, RBAC, audit log.

## 2. First-time setup

1. **Servers**: app server (16 cores/64GB) + GPU server (1× A100 40GB or 2× 4090)
2. **Start**:
   ```powershell
   docker compose up --build -d                    # db + backend (+ React UI)
   docker compose --profile llm up -d              # + LLM (GPU host)
   ```
3. **Admin login**: first boot prints a one-time admin password to console — copy it.
   Or set `ADMIN_USER`/`ADMIN_PASSWORD` env before first boot.
4. **Set in production** (backend/.env or compose environment):
   - `AUTH_SECRET` (long random string — tokens are signed with it)
   - `ADMIN_PASSWORD` (avoid one-time-printed in shared environments)
5. **Create users**: Admin page → Create user. Roles:
   - `viewer` — read-only (query, analytics, reports download)
   - `analyst` — + upload, extraction, review, report generation
   - `admin` — + users, jobs, audit
   Non-admin users are locked to their `subsidiary` field on every query.
6. **Worker**: on the app server:
   ```powershell
   python scripts/worker.py            # long-running (ingest + extraction jobs)
   ```
   Safe to run multiple workers. Uploads/extractions are queued jobs.

## 3. Daily operations

| Task | How |
|---|---|
| Ingest historical archives | `python scripts/batch_ingest.py D:\archive\ECL ECL` (year from filename) |
| Ingest single doc | Documents page → Upload |
| Extract figures | Documents page → Extract (choose `production_report` / `geological` / `parliamentary_q` / `daily_shift_report` / `stoppage_report`) |
| Review flagged values | Review page → Confirm / Reject (corrections update the value, feed eval) |
| Daily ops analytics | Analytics page → Daily operations card: stoppage Pareto + machine utilization (filter by date range) |
| Generate report | Reports page → title/subsidiary/years → Download .docx |
| Ask questions | Query page — figure questions route to extracted data, rest to RAG |
| Word cloud / topics / trends | Analytics page (filter by subsidiary/year) |

## 4. Admin runbook

| Task | Command |
|---|---|
| System health | Admin page, or `GET /query/health` |
| Job failures + retry | Admin page → Jobs → Retry |
| Audit trail | Admin page → Audit log |
| Answer quality monitor | Admin page → Query log (faithfulness % per answer) |
| Backup | `python scripts/backup.py` — schedule daily (cron / Task Scheduler) |
| Load test | `python scripts/load_test.py --users 50 --concurrency 10 --token <token>` |
| Extraction accuracy eval | `python scripts/eval_harness.py --gold evals/gold_set.jsonl --show-misses --save` (LLM required; `--show-misses` prints each failed field, `--save` writes `evals/latest_eval.json` for the KPI endpoint) |
| Fine-tune prep | `python scripts/finetune_lora.py --build-only` (needs ≥50 confirmed extractions) |
| Ingest daily ops PDFs | Drop files named like `08-09-2026-B1 RELAY-....pdf` / `M-1 STOPPAGE on 07.09.2026.pdf` into a folder and batch-ingest; type + date auto-inferred from filename |

## 5. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Answers say "LLM unavailable" | LLM server down / not started | `docker compose --profile llm up -d`; check `GET /query/health` |
| Documents stuck in `indexing` | Worker not running | `python scripts/worker.py` |
| Status `indexed_no_embeddings` | Embedding model missing | Pre-download `intfloat/multilingual-e5-base` into `/data/models` (full-text search still works) |
| Garbage OCR on old scans | Scan quality below Tesseract floor | Low-confidence pages need manual review; consider rescan at 300+ dpi |
| 401 on every call | Not logged in / token expired | Login again (token lasts 12h) |
| 403 on upload/generate | Role too low | Admin page → upgrade to analyst |
| 429 responses | Rate limit (120 req/min/IP) | Raise `RATE_LIMIT_PER_MIN` |
| Login fails after restart | `AUTH_SECRET` unset → random per-process secret | Set `AUTH_SECRET` env |

## 6. Air-gap checklist

Pre-download on a connected machine, copy into `./data` (mounted at `/data`):

- [ ] HuggingFace models: `Qwen/Qwen2.5-7B-Instruct`, `intfloat/multilingual-e5-base`, `BAAI/bge-reranker-v2-m3`
- [ ] pip wheels: `pip download -r backend/requirements.txt -d wheels/`
- [ ] Docker images: `pgvector/pgvector:pg16`, `vllm/vllm-openai:v0.6.6`, `node:20-slim`, `python:3.11-slim` (`docker save` / `docker load`)
- [ ] npm packages: vendored `frontend/node_modules` or offline registry mirror
- [ ] Tesseract language packs (hin) — included in the Dockerfile apt install

## 7. Metrics tracking (RFP targets)

| Metric | Where |
|---|---|
| Report prep time ↓70-80% | `reports.created_at` vs Phase-1 baseline (measure before go-live) |
| Extraction accuracy 95%+ | ✅ **98.4% measured** (2026-09-25: 53 gold entries, Qwen2.5-3B via llama.cpp; stable across repeat runs). Re-run after any model/prompt/schema change; grow gold set to 100-200 entries |
| Automation 80% | Ingestion + extraction + report jobs vs manual touchpoints |
| MoC response time | `query_log.latency_ms` + answer turnaround |

## 8. Where things live

```
backend/app/            FastAPI app (routers/, services/, static/)
backend/app/extraction_schemas.py   schema registry (add doc types here; supports list-item expansion for stoppage machines)
backend/tests/          pytest (python -m pytest tests -v from backend/)
frontend/               React app (npm run build → dist, served by backend)
scripts/                batch_ingest, worker, eval_harness, backup, load_test, finetune_lora, make_demo_data
evals/gold_set.jsonl    gold-standard entries for the eval harness (incl. NLC Mine-I daily shift + stoppage samples)
data/                   runtime data: uploads/, reports/, models/, backups/
```

## 9. Demo (no real data needed)

```powershell
python scripts/make_demo_data.py --ingest     # 34 synthetic docs, ingested into running platform
```

Covers production reports (ECL/BCCL/CIL 2022-2024), geological, parliamentary questions —
populates figure routing, trends, totals cross-check and analytics immediately.
