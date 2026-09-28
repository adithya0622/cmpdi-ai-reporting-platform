# CMPDI AI Reporting Platform — User Guide

Quick-start guide for analysts, viewers, and administrators.

## Logging In

1. Open `http://localhost:8000` in your browser.
2. Enter the username and password provided by your administrator.
3. Your role determines what you can do:

| Role | Can do |
|---|---|
| **Viewer** | Query the AI, view analytics, download reports |
| **Analyst** | + Upload documents, run extractions, review flagged values, generate reports |
| **Admin** | + Manage users, retry failed jobs, view audit log |

## Uploading Documents

1. Go to **Documents**.
2. Click **Upload** and fill in: Title, Subsidiary (e.g. ECL, BCCL), Year, and select your file.
3. Supported formats: PDF, DOCX, XLSX, XLS, TXT, CSV, PNG, JPG, TIFF.
4. The system automatically extracts text (with OCR for scanned PDFs and images), chunks it, and indexes it for search.
5. Once processed, the document status changes from `pending` to `indexed`.

**Tip:** For bulk ingestion of historical archives, ask your admin to run the batch ingest script.

## Extracting Figures

After uploading a document:

1. On the **Documents** page, click **Extract** next to the document.
2. Choose the document type:
   - `production_report` — coal production, dispatch, offtake figures
   - `geological` — borehole depth, seam thickness, reserves, grade
   - `parliamentary_q` — ministry, year, subsidiary from Q&A records
   - `daily_shift_report` — date, shift production (lignite/OB tonnage)
   - `stoppage_report` — per-machine working hours and stoppages
3. The AI extracts structured fields and assigns a confidence score to each.
4. High-confidence values are auto-accepted. Low-confidence values are flagged for human review.

## Reviewing Flagged Extractions

1. Go to **Review**.
2. Each flagged field shows: the field name, extracted value, confidence %, and source document.
3. For each field:
   - If the value is correct, click **Confirm**.
   - If the value is wrong, type the correct value in the correction box and click **Confirm** (it saves your corrected value).
   - If the extraction is nonsensical, click **Reject**.
4. Your corrections improve the platform's accuracy metrics and feed back into the eval harness.

## Querying the AI

1. Go to **Query**.
2. Type your question in natural language, or click one of the preset inquiry buttons.
3. Optionally filter by subsidiary.

**What you can ask:**
- Production figures: "What was the coal production of BCCL in 2024?"
- Geological data: "Borehole depth and reserves at Suliyari block"
- Shift operations: "Show the shift report for 08.09.2026"
- Stoppages: "What were the stoppages at Mine-I on 12.09.2026?"
- Parliamentary: "What did the Minister of Coal say about Deucha Pachami?"
- Inventory: "Total coal resources in the national inventory"
- Hindi: "भारत की कुल कोयला भंडार संख्या क्या है?"

**How answers work:**
- **Deterministic SQL** (lightning bolt badge): Production/dispatch/reserves figures are retrieved directly from the database — zero hallucination.
- **Sovereign Hybrid RAG** (brain badge): Other questions use retrieval-augmented generation, grounding the AI's answer in your indexed documents.
- **Grounding %** shows what fraction of the answer is verifiably backed by cited source documents.
- Every answer includes source citations with document name and page number.

**Tips:**
- Answers stream in real-time — you see tokens as they arrive.
- The conversation remembers context — you can ask follow-up questions.
- If the AI says "documents do not contain information," try rephrasing or check that the relevant document has been uploaded.

## Generating Reports

1. Go to **Reports**.
2. Fill in: Report title, subsidiary (leave blank for all), year range.
3. Click **Generate**. The system creates a Word (.docx) report with:
   - Executive summary (AI-generated from extracted data)
   - Production benchmarks table
   - Subsidiary-wise statistics
   - Geological/borehole reserves
   - Operations and stoppage logs
4. Click **Download** to get the .docx file.
5. Click **Quick Preview** to view the report in-browser.

## Analytics Dashboard

Go to **Analytics** to see:

- **Word Cloud**: Most frequent terms across the corpus. Filter by subsidiary and year range.
- **Top Topics**: Key themes identified via TF-IDF analysis, with optional AI-generated summary.
- **Topic Trends**: How topics evolve year over year.
- **Production Trends**: Line chart of any extraction field (production, dispatch, reserves, etc.) over time.
- **Daily Operations** (when daily shift/stoppage data is present):
  - Stoppage Pareto chart: downtime by category (maintenance, planned shifting, etc.)
  - Machine utilization table: EWH/TWH % per machine
- **PS Metrics**: Platform KPIs — automation %, extraction accuracy, report prep-time reduction.

## Admin Panel

Admins see additional controls at **Admin**:

- **System KPIs**: Users, documents, pending/failed jobs, LLM status.
- **Data Quality Monitor**: Fields awaiting review, corrupt values caught, flagged anomalies.
- **Create User**: Add new users with role and subsidiary assignment.
- **Jobs**: View processing jobs, retry failures.
- **Query Log**: Monitor answer quality — faithfulness % per answer, mode, latency.
- **Audit Log**: Full trail of uploads, extractions, reviews, approvals, and report generation.

## Approving Shift Documents

For daily shift and stoppage reports that require officer sign-off:

1. On the **Documents** page, click **Approve Shift** next to the document.
2. Enter the approving officer's name.
3. The document status changes to `approved` and the approver is recorded.
4. Use **Approve All** for bulk approval of verified documents.

## Keyboard Shortcuts

- `Enter` — Send query (in Query page)
- Click any preset button to instantly fill and send that question

## Troubleshooting

| Problem | Solution |
|---|---|
| "LLM unavailable" in answers | The local AI model server is not running. Contact your admin. Answers still work in extractive mode (showing source passages). |
| Document stuck in "indexing" | The background worker may not be running. Contact your admin. |
| 401 / session expired | Log in again — sessions last 12 hours. |
| 403 on upload/generate | Your role doesn't have permission. Ask your admin to upgrade you to analyst. |
| Answer seems wrong | Check the grounding % and source citations. If data is missing, the relevant document may not be uploaded yet. |

## Data Security

- All processing runs on-premises — no data leaves your network.
- The AI model runs locally on GPU — no cloud API calls.
- Every action is logged in the audit trail.
- Documents and answers are scoped to your assigned subsidiary (non-admin users).
