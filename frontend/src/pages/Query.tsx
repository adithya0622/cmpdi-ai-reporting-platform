import { useState } from "react";
import { api, apiStream } from "../api";

type Msg = {
  role: "user" | "bot";
  content: string;
  mode?: string;
  latency_ms?: number;
  grounded_pct?: number;
  sources?: any[];
  query_log_id?: number;
  rating?: number;
};

const PRESETS = [
  {
    tag: "Shift Sign-off & Approver",
    label: "Who approved shift on 08.09.2026? (Shift Sign-off)",
    q: "Who approved the shift on 08.09.2026 and what were the production figures?",
    sub: "",
  },
  {
    tag: "Stoppage Report Sign-off",
    label: "Mine-1 stoppage report approver (07.09.2026)",
    q: "Who approved the stoppage report on 07.09.2026 for Mine-1?",
    sub: "",
  },
  {
    tag: "Lok Sabha AU5084",
    label: "Coal production trends in Odisha (AU5084)",
    q: "What was the coal production trend in Odisha according to Lok Sabha question 5084?",
    sub: "",
  },
  {
    tag: "Borehole Exploration",
    label: "Borehole BH-21 reserves & depth (CMPDI)",
    q: "What are the estimated coal reserves, seams, and depths for borehole BH-21?",
    sub: "CMPDI",
  },
  {
    tag: "Production Figures",
    label: "BCCL 2024 quarterly production (Deterministic SQL)",
    q: "What was the quarterly coal production of BCCL in 2024?",
    sub: "BCCL",
  },
  {
    tag: "Equipment Downtime",
    label: "BWE-1029 equipment stoppage causes (HEMM)",
    q: "What were the primary stoppage reasons and downtime hours for excavator BWE-1029?",
    sub: "NLC",
  },
  {
    tag: "National Inventory",
    label: "National Coal Inventory & Reserve Estimates 2025",
    q: "What are the total confirmed and indicated coal reserves reported in the National Inventory 2025?",
    sub: "",
  },
  {
    tag: "Rajya Sabha 2668",
    label: "Critical mineral exploration (Rajya Sabha 2668)",
    q: "What are the exploration replies regarding critical mineral and coal blocks in Rajya Sabha question 2668?",
    sub: "",
  },
  {
    tag: "Hindi Query",
    label: "भारत की कुल कोयला भंडार संख्या क्या है? (Hindi)",
    q: "भारत की कुल कोयला भंडार संख्या क्या है?",
    sub: "",
  },
  {
    tag: "Hindi Query",
    label: "2024 में BCCL का कोयला उत्पादन कितना था? (Hindi)",
    q: "2024 में BCCL का कोयला उत्पादन कितना था?",
    sub: "BCCL",
  },
];

export default function Query() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [question, setQuestion] = useState("");
  const [subsidiary, setSubsidiary] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function ask(customQ?: string, customSub?: string) {
    const q = customQ || question;
    const sub = customSub !== undefined ? customSub : subsidiary;
    if (!q || busy) return;
    setQuestion("");
    setErr("");
    const history = messages.map((m) => ({
      role: m.role === "bot" ? "assistant" : "user",
      content: m.content,
    }));
    setMessages((m) => [...m, { role: "user", content: q }]);
    setBusy(true);
    try {
      let msg = { role: "bot" as const, content: "" };
      setMessages((m) => [...m, msg]);
      const patch = (p: Partial<Msg>) =>
        setMessages((all) => all.map((x, i) => (i === all.length - 1 ? { ...x, ...p } : x)));
      await apiStream(
        "/query/stream",
        { method: "POST", body: { question: q, subsidiary: sub, history } },
        (ev) => {
          if (ev.type === "sources") {
            patch({ sources: ev.sources });
          } else if (ev.type === "token") {
            msg = { ...msg, content: msg.content + ev.token };
            patch({ content: msg.content });
          } else if (ev.type === "done" && ev.result) {
            const j = ev.result;
            patch({
              content: j.answer,
              mode: j.mode,
              latency_ms: j.latency_ms,
              grounded_pct: j.grounded_pct,
              sources: j.sources,
              query_log_id: j.query_log_id,
            });
          } else if (ev.type === "query_log_id") {
            patch({ query_log_id: ev.id });
          }
        }
      );
    } catch (e: any) {
      setErr(e.message);
      setMessages((m) => [...m, { role: "bot", content: `Error: ${e.message}` }]);
    }
    setBusy(false);
  }

  async function submitFeedback(msgIdx: number, rating: number) {
    const m = messages[msgIdx];
    if (!m?.query_log_id) return;
    try {
      await api(`/query/${m.query_log_id}/feedback`, {
        method: "POST",
        body: { rating },
      });
      setMessages((all) =>
        all.map((x, i) => (i === msgIdx ? { ...x, rating } : x))
      );
    } catch {}
  }

  function handlePreset(p: (typeof PRESETS)[0]) {
    setQuestion(p.q);
    setSubsidiary(p.sub);
    ask(p.q, p.sub);
  }

  return (
    <div className="page-inner">
      <div className="card">
        <h3>Ask the Corpus (Parliamentary Inquiries, Geological & Operational Figures)</h3>
        <p className="src" style={{ marginTop: -4, marginBottom: 12 }}>
          Numerical inquiries automatically route to deterministic SQL tables (sub-10ms, zero hallucinations). Conceptual inquiries route to hybrid dense+sparse RAG with sentence-level citations.
        </p>

        <label style={{ fontWeight: 600 }}>1-Click Inquiry Presets (SIH Pitch Presets):</label>
        <div className="preset-group">
          {PRESETS.map((p, idx) => (
            <button
              key={idx}
              type="button"
              className="preset-chip"
              onClick={() => handlePreset(p)}
              disabled={busy}
            >
              <span className="tag">{p.tag}</span>
              <span>{p.label}</span>
            </button>
          ))}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 3fr", gap: 12, marginTop: 8 }}>
          <div>
            <label htmlFor="query-sub">Subsidiary Filter</label>
            <input
              id="query-sub"
              value={subsidiary}
              onChange={(e) => setSubsidiary(e.target.value)}
              placeholder="e.g. BCCL, ECL, CMPDI"
            />
          </div>
          <div>
            <label htmlFor="query-q">Question / Inquiry</label>
            <div style={{ display: "flex", gap: 8 }}>
              <input
                id="query-q"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && ask()}
                placeholder="Ask any question about production, reserves, or parliamentary queries..."
              />
              <button className="primary" style={{ marginTop: 2 }} disabled={busy} onClick={() => ask()}>
                {busy ? "Thinking..." : "Submit Inquiry"}
              </button>
            </div>
          </div>
        </div>

        {err && <p className="err" role="alert">{err}</p>}

        <div className="chat" style={{ marginTop: 24 }} role="log" aria-live="polite">
          {messages.map((m, i) => (
            <div key={i} className={`bubble ${m.role}`}>
              <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.5 }}>{m.content}</div>

              {m.role === "bot" && (
                <div style={{ marginTop: 10, display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                  {m.mode === "figures" ? (
                    <span className="badge badge-sql"><span aria-hidden="true">⚡</span> Deterministic SQL Query (Zero Hallucination)</span>
                  ) : (
                    <span className="badge badge-rag"><span aria-hidden="true">🧠</span> Sovereign Hybrid RAG (Local GPU · Qwen3-8B)</span>
                  )}

                  {m.latency_ms != null && (
                    <span className="badge badge-green"><span aria-hidden="true">⏱️</span> {m.latency_ms} ms</span>
                  )}

                  {m.grounded_pct != null && (
                    <span className="badge badge-amber">
                      <span aria-hidden="true">🎯</span> {(m.grounded_pct * 100).toFixed(0)}% Grounded
                    </span>
                  )}

                  {m.query_log_id && (
                    <span style={{ marginLeft: "auto", display: "flex", gap: 4 }}>
                      <button
                        className={`small${m.rating === 1 ? " badge-green" : ""}`}
                        style={{ padding: "2px 8px", fontSize: 14, cursor: "pointer" }}
                        aria-label="Rate as helpful"
                        onClick={() => submitFeedback(i, 1)}
                        disabled={m.rating !== undefined}
                      >
                        <span aria-hidden="true">👍</span>
                      </button>
                      <button
                        className={`small${m.rating === -1 ? " badge-red" : ""}`}
                        style={{ padding: "2px 8px", fontSize: 14, cursor: "pointer" }}
                        aria-label="Rate as not helpful"
                        onClick={() => submitFeedback(i, -1)}
                        disabled={m.rating !== undefined}
                      >
                        <span aria-hidden="true">👎</span>
                      </button>
                    </span>
                  )}
                </div>
              )}

              {m.sources && m.sources.length > 0 && (
                <div className="meta" style={{ marginTop: 8, borderTop: "1px dashed var(--border)", paddingTop: 6 }}>
                  <b>Verified Citations:</b>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 4 }}>
                    {m.sources.slice(0, 6).map((s: any, idx: number) => (
                      <span
                        key={idx}
                        style={{
                          background: "var(--card-bg)",
                          border: "1px solid var(--border)",
                          padding: "2px 8px",
                          borderRadius: 4,
                          fontSize: 11,
                        }}
                      >
                        <span aria-hidden="true">📄</span> {s.title} (p.{s.page})
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}

          {busy && (
            <div className="bubble bot" role="status" style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span>Searching verified vector chunks & SQL tables...</span>
            </div>
          )}

          {!messages.length && !busy && (
            <div style={{ textAlign: "center", padding: "32px 0", color: "var(--text-muted)" }}>
              <div style={{ fontSize: 32, marginBottom: 8 }} aria-hidden="true">🔍</div>
              <p style={{ margin: 0 }}>Click any of the inquiry presets above or type a custom question.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
