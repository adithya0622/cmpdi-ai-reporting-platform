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

type Preset = { tag: string; label: string; q: string; sub: string };

const PRESETS: Preset[] = [
  {
    tag: "Shift sign-off",
    label: "Who approved the shift on 08.09.2026?",
    q: "Who approved the shift on 08.09.2026 and what were the production figures?",
    sub: "",
  },
  {
    tag: "Production",
    label: "BCCL quarterly production in 2024",
    q: "What was the quarterly coal production of BCCL in 2024?",
    sub: "BCCL",
  },
  {
    tag: "Reserves",
    label: "India's total coal reserves",
    q: "What is India total coal reserve according to the National Inventory 2025?",
    sub: "",
  },
  {
    tag: "Approvers",
    label: "Who approved shifts in the past 4 years?",
    q: "give m the names of all the people who have approved the shifts in the past 4 years",
    sub: "",
  },
  {
    tag: "Borehole",
    label: "Borehole BH-21 reserves & depth",
    q: "What are the estimated coal reserves, seams, and depths for borehole BH-21?",
    sub: "CMPDI",
  },
  {
    tag: "हिंदी",
    label: "भारत की कुल कोयला भंडार संख्या?",
    q: "भारत की कुल कोयला भंडार संख्या क्या है?",
    sub: "",
  },
  {
    tag: "Stoppage",
    label: "Mine-1 stoppage report approver (07.09.2026)",
    q: "Who approved the stoppage report on 07.09.2026 for Mine-1?",
    sub: "",
  },
  {
    tag: "Parliament",
    label: "Coal production trend in Odisha (AU5084)",
    q: "What was the coal production trend in Odisha according to Lok Sabha question 5084?",
    sub: "",
  },
  {
    tag: "Equipment",
    label: "BWE-1029 stoppage causes & downtime",
    q: "What were the primary stoppage reasons and downtime hours for excavator BWE-1029?",
    sub: "NLC",
  },
  {
    tag: "हिंदी",
    label: "2024 में BCCL का उत्पादन?",
    q: "2024 में BCCL का कोयला उत्पादन कितना था?",
    sub: "BCCL",
  },
];

const VISIBLE_PRESETS = 6;

export default function Query() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [question, setQuestion] = useState("");
  const [subsidiary, setSubsidiary] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [showAllPresets, setShowAllPresets] = useState(false);

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

  function handlePreset(p: Preset) {
    setQuestion(p.q);
    setSubsidiary(p.sub);
    ask(p.q, p.sub);
  }

  const presets = showAllPresets ? PRESETS : PRESETS.slice(0, VISIBLE_PRESETS);

  return (
    <div className="page-inner">
      {/* ── Ask panel ─────────────────────────────────────────── */}
      <div className="card query-ask">
        <h3>Ask the AI</h3>
        <p className="src">
          Every answer comes from your indexed documents — figures are pulled from verified
          data tables, and citations are always shown.
        </p>

        <div className="ask-row">
          <input
            id="query-q"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && ask()}
            placeholder="Ask about production, reserves, shifts, approvals…"
            aria-label="Question"
          />
          <input
            id="query-sub"
            className="ask-subsidiary"
            value={subsidiary}
            onChange={(e) => setSubsidiary(e.target.value)}
            placeholder="Subsidiary (optional)"
            aria-label="Subsidiary filter"
          />
          <button className="primary" disabled={busy || !question.trim()} onClick={() => ask()}>
            {busy ? "Thinking…" : "Ask"}
          </button>
        </div>

        <div className="preset-group">
          {presets.map((p, idx) => (
            <button
              key={idx}
              type="button"
              className="preset-chip"
              onClick={() => handlePreset(p)}
              disabled={busy}
              title={p.tag}
            >
              {p.label}
            </button>
          ))}
          <button
            type="button"
            className="preset-chip preset-more"
            onClick={() => setShowAllPresets(!showAllPresets)}
          >
            {showAllPresets ? "− Fewer examples" : `+ ${PRESETS.length - VISIBLE_PRESETS} more examples`}
          </button>
        </div>

        {err && <p className="err" role="alert">{err}</p>}
      </div>

      {/* ── Conversation ──────────────────────────────────────── */}
      <div className="chat" role="log" aria-live="polite">
        {messages.map((m, i) => (
          <div key={i} className={`bubble ${m.role}`}>
            <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.55 }}>{m.content}</div>

            {m.role === "bot" && (m.mode || m.latency_ms != null || m.query_log_id) && (
              <div className="msg-meta">
                <span className="meta-mode">{m.mode === "figures" ? "Verified data" : "AI answer"}</span>
                {m.latency_ms != null && <span>{(m.latency_ms / 1000).toFixed(1)} s</span>}
                {m.grounded_pct != null && <span>{(m.grounded_pct * 100).toFixed(0)}% grounded</span>}
                {m.query_log_id && (
                  <span className="meta-feedback">
                    <button
                      className={`thumb${m.rating === 1 ? " thumb-up" : ""}`}
                      aria-label="Rate as helpful"
                      onClick={() => submitFeedback(i, 1)}
                      disabled={m.rating !== undefined}
                    >
                      <span aria-hidden="true">👍</span>
                    </button>
                    <button
                      className={`thumb${m.rating === -1 ? " thumb-down" : ""}`}
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
              <div className="meta cites">
                {m.sources.slice(0, 5).map((s: any, idx: number) => (
                  <span key={idx} className="cite-chip" title={s.title}>
                    📄 {s.title} (p.{s.page})
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}

        {busy && (
          <div className="bubble bot" role="status" style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span>Searching documents and data tables…</span>
          </div>
        )}

        {!messages.length && !busy && (
          <div className="chat-empty">
            <div style={{ fontSize: 30, marginBottom: 8 }} aria-hidden="true">💬</div>
            <p style={{ margin: 0 }}>
              Try an example above, or type your own question — in English or Hindi.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
