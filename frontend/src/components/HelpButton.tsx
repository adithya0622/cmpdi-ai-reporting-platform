import { useState } from "react";
import { useLocation } from "react-router-dom";

const HELP: Record<string, { title: string; content: string }> = {
  "/": {
    title: "Home",
    content:
      "Welcome to the CMPDI AI Reporting Platform. Navigate using the top bar:\n\n" +
      "- Documents: Upload PDFs, spreadsheets, and images for processing\n" +
      "- Review: Confirm or correct AI-extracted figures\n" +
      "- Reports: Generate Word reports from extracted data\n" +
      "- Analytics: View KPIs, trends, stoppages, and AI recommendations\n" +
      "- Query: Ask questions about your data in English or Hindi\n" +
      "- Admin: Manage users, jobs, and system health",
  },
  "/documents": {
    title: "Document Management",
    content:
      "Upload documents for AI processing:\n\n" +
      "1. Click Upload and select a file (PDF, DOCX, XLSX, CSV, or image)\n" +
      "2. Set the subsidiary and document type\n" +
      "3. After upload, click Extract to run AI field extraction\n" +
      "4. Documents are automatically chunked and indexed for RAG queries\n\n" +
      "Tip: Parliamentary questions get priority processing.",
  },
  "/review": {
    title: "Extraction Review",
    content:
      "Review AI-extracted fields for accuracy:\n\n" +
      "- Fields marked 'review' need human verification\n" +
      "- Click Confirm if the value is correct\n" +
      "- Click Reject (and optionally correct) if wrong\n" +
      "- Your decisions train the accuracy metrics on the Analytics page\n\n" +
      "Tip: Focus on low-confidence fields first (shown with amber badges).",
  },
  "/reports": {
    title: "Report Generation",
    content:
      "Generate Word (.docx) reports from extracted data:\n\n" +
      "1. Enter a report title, subsidiary filter, and year range\n" +
      "2. Click Generate - the AI compiles figures and summaries\n" +
      "3. Download the .docx file when ready\n\n" +
      "Reports include production figures, trend analysis, and source citations.",
  },
  "/analytics": {
    title: "Analytics & AI Recommendations",
    content:
      "View platform metrics and get AI-powered insights:\n\n" +
      "- PS Metrics: Automation %, extraction accuracy, report build time\n" +
      "- AI Recommendations: Click 'Generate' for actionable insights based on trends, stoppages, and utilization\n" +
      "- Daily Operations: Stoppage Pareto charts and machine utilization tables\n" +
      "- Trends: Year-over-year production and field value charts\n" +
      "- Word Cloud & Topics: TF-IDF extracted keyphrases from your corpus",
  },
  "/query": {
    title: "Query System",
    content:
      "Ask questions about your data in English or Hindi:\n\n" +
      "- Numerical questions route to deterministic SQL (zero hallucination)\n" +
      "- Conceptual questions route to hybrid RAG with citations\n" +
      "- Use preset queries for common inquiry types\n" +
      "- Rate answers with thumbs up/down to help improve the system\n\n" +
      "Examples: 'BCCL 2024 production', 'compare ECL and BCCL', 'shift approver on 08.09.2026'",
  },
  "/admin": {
    title: "Administration",
    content:
      "System management (admin role required):\n\n" +
      "- Overview: System health, LLM status, feedback stats\n" +
      "- Data Quality: Fields awaiting review, anomaly detection\n" +
      "- Users: Create accounts with role-based access\n" +
      "- Jobs: Monitor background processing, retry failures\n" +
      "- Query Log: Monitor answer quality and user feedback\n" +
      "- Audit Log: Track all system actions",
  },
};

export default function HelpButton() {
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const page = HELP[location.pathname] || HELP["/"];

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        title="Help"
        style={{
          position: "fixed",
          bottom: 20,
          right: 20,
          width: 44,
          height: 44,
          borderRadius: "50%",
          border: "none",
          background: "var(--accent, #2980b9)",
          color: "#fff",
          fontSize: 20,
          cursor: "pointer",
          boxShadow: "0 2px 8px rgba(0,0,0,0.2)",
          zIndex: 1000,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        ?
      </button>
      {open && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.4)",
            zIndex: 1001,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
          onClick={() => setOpen(false)}
        >
          <div
            style={{
              background: "var(--card-bg, #fff)",
              borderRadius: 8,
              padding: "24px 28px",
              maxWidth: 520,
              width: "90%",
              maxHeight: "80vh",
              overflow: "auto",
              boxShadow: "0 4px 24px rgba(0,0,0,0.15)",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
              <h3 style={{ margin: 0 }}>{page.title}</h3>
              <button onClick={() => setOpen(false)} style={{ background: "none", border: "none", fontSize: 18, cursor: "pointer" }}>
                X
              </button>
            </div>
            <pre style={{ whiteSpace: "pre-wrap", lineHeight: 1.6, fontSize: 13, margin: 0 }}>{page.content}</pre>
          </div>
        </div>
      )}
    </>
  );
}
