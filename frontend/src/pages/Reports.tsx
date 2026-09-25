import { useEffect, useState } from "react";
import { api, downloadReport } from "../api";

export default function Reports() {
  const [reports, setReports] = useState<any[]>([]);
  const [title, setTitle] = useState("");
  const [subsidiary, setSubsidiary] = useState("");
  const [yf, setYf] = useState("");
  const [yt, setYt] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  // Preview Modal state
  const [previewData, setPreviewData] = useState<any | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [activeTableTab, setActiveTableTab] = useState(0);

  async function load() {
    try {
      setReports(await api("/reports"));
    } catch (e: any) {
      setErr(e.message);
    }
  }
  useEffect(() => { load(); }, []);

  async function generate() {
    setBusy(true);
    setMsg("");
    setErr("");
    try {
      const res = await api("/reports/generate", {
        method: "POST",
        body: {
          title: title || "Coal India Report",
          subsidiary: subsidiary,
          year_from: yf ? +yf : null,
          year_to: yt ? +yt : null,
        },
      });
      setMsg(`Report generated successfully!`);
      load();
      if (res && res.id) {
        openPreview(res.id);
      }
    } catch (e: any) {
      setErr(e.message);
    }
    setBusy(false);
  }

  async function openPreview(id: string) {
    setPreviewLoading(true);
    setErr("");
    try {
      const data = await api(`/reports/${id}/preview`);
      setPreviewData(data);
      setActiveTableTab(0);
    } catch (e: any) {
      setErr(`Preview failed: ${e.message}`);
    }
    setPreviewLoading(false);
  }

  function closePreview() {
    setPreviewData(null);
  }

  return (
    <div className="page-inner">
      <div className="card">
        <h3>Generate Official Review Report (Ministry of Coal / CMPDI)</h3>
        <p className="src" style={{ marginTop: -4 }}>
          Compiles structured borehole logs, chronological quarterly production, national macro benchmarks, and an AI analytical executive summary into publication-ready Word (.docx).
        </p>

        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr", gap: 12 }}>
          <div>
            <label>Report Title</label>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. CMPDI / CIL Consolidated Operations & Geological Review"
            />
          </div>
          <div>
            <label>Subsidiary Filter (Blank = All)</label>
            <input
              value={subsidiary}
              onChange={(e) => setSubsidiary(e.target.value)}
              placeholder="e.g. BCCL, ECL, CMPDI"
            />
          </div>
          <div>
            <label>Years (From / To)</label>
            <div style={{ display: "flex", gap: 6 }}>
              <input type="number" placeholder="2022" value={yf} onChange={(e) => setYf(e.target.value)} />
              <input type="number" placeholder="2024" value={yt} onChange={(e) => setYt(e.target.value)} />
            </div>
          </div>
        </div>

        <button className="primary" disabled={busy} onClick={generate}>
          {busy ? "Compiling Report & Qwen AI Summary..." : "⚡ Generate Official Report"}
        </button>
        {msg && <span className="msg src" style={{ color: "#2e7d32", fontWeight: 600 }}>{msg}</span>}
        {err && <span className="msg err">{err}</span>}
      </div>

      <div className="card">
        <h3>Generated Report Archive</h3>
        <table>
          <thead>
            <tr>
              <th>Report Title</th>
              <th>Scope &amp; Filters</th>
              <th>Generated At</th>
              <th style={{ textAlign: "right" }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {reports.map((r) => (
              <tr key={r.id}>
                <td style={{ fontWeight: 600 }}>{r.title}</td>
                <td className="src">
                  {r.params?.subsidiary ? `Sub: ${r.params.subsidiary}` : "All subsidiaries"} |{" "}
                  {r.params?.year_from || r.params?.year_to
                    ? `${r.params?.year_from || "..."} - ${r.params?.year_to || "..."}`
                    : "All periods"}
                </td>
                <td className="src">{new Date(r.created_at).toLocaleString()}</td>
                <td style={{ textAlign: "right" }}>
                  <button
                    className="small"
                    style={{ background: "var(--indigo)", color: "#fff", border: "none", cursor: "pointer", borderRadius: 4, marginRight: 6 }}
                    disabled={previewLoading}
                    onClick={() => openPreview(r.id)}
                  >
                    {previewLoading ? "Loading..." : "👁️ Quick Preview"}
                  </button>
                  <button
                    className="small"
                    style={{ background: "var(--gold)", color: "#221a63", border: "none", cursor: "pointer", borderRadius: 4, fontWeight: 700 }}
                    onClick={() => downloadReport(r.id).catch((e2) => setErr(e2.message))}
                  >
                    ⬇️ .docx
                  </button>
                </td>
              </tr>
            ))}
            {!reports.length && <tr><td colSpan={4}>No reports generated yet. Click generate above.</td></tr>}
          </tbody>
        </table>
      </div>

      {/* Interactive In-Browser Report Preview Modal */}
      {previewData && (
        <div className="modal-overlay" onClick={closePreview}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div>
                <h3>{previewData.title}</h3>
                <div style={{ fontSize: 12, opacity: 0.85, marginTop: 2 }}>
                  Generated on {previewData.created_at ? new Date(previewData.created_at).toLocaleDateString() : "Today"} | Official CMPDI / CIL Format
                </div>
              </div>
              <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                <button
                  className="primary"
                  style={{ marginTop: 0, padding: "6px 14px", fontSize: 12 }}
                  onClick={() => downloadReport(previewData.id)}
                >
                  ⬇️ Download Official .docx
                </button>
                <button className="modal-close-btn" onClick={closePreview}>&times;</button>
              </div>
            </div>

            <div className="modal-body">
              {/* Executive Summary */}
              {previewData.paragraphs && previewData.paragraphs.length > 2 && (
                <div>
                  <h4 style={{ margin: "0 0 8px 0", color: "var(--indigo)" }}>
                    🤖 Executive Summary (AI Synthesized &amp; Verified)
                  </h4>
                  <div className="preview-summary-box">
                    {previewData.paragraphs.slice(2, 6).map((p: string, idx: number) => (
                      <p key={idx}>{p}</p>
                    ))}
                  </div>
                </div>
              )}

              {/* Table Tabs */}
              {previewData.tables && previewData.tables.length > 0 && (
                <div>
                  <div className="preview-tabs">
                    {previewData.tables.map((t: any, idx: number) => (
                      <button
                        key={idx}
                        className={`preview-tab-btn ${activeTableTab === idx ? "active" : ""}`}
                        onClick={() => setActiveTableTab(idx)}
                      >
                        {t.title} ({t.rows.length} rows)
                      </button>
                    ))}
                  </div>

                  {/* Active Table Content */}
                  {previewData.tables[activeTableTab] && (
                    <div>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8, alignItems: "center" }}>
                        <h4 style={{ margin: 0 }}>{previewData.tables[activeTableTab].title}</h4>
                        <span className="src">Total Records: {previewData.tables[activeTableTab].rows.length}</span>
                      </div>
                      <div className="table-scroll">
                        <table>
                          <thead style={{ background: "var(--bg)" }}>
                            <tr>
                              {previewData.tables[activeTableTab].headers.map((h: string, hidx: number) => (
                                <th key={hidx} style={{ whiteSpace: "nowrap" }}>{h}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {previewData.tables[activeTableTab].rows.slice(0, 50).map((row: string[], ridx: number) => (
                              <tr key={ridx}>
                                {row.map((cell: string, cidx: number) => (
                                  <td key={cidx}>{cell}</td>
                                ))}
                              </tr>
                            ))}
                            {previewData.tables[activeTableTab].rows.length > 50 && (
                              <tr>
                                <td colSpan={previewData.tables[activeTableTab].headers.length} style={{ textAlign: "center", color: "var(--text-muted)" }}>
                                  ... showing first 50 of {previewData.tables[activeTableTab].rows.length} rows (full table in Word document)
                                </td>
                              </tr>
                            )}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

