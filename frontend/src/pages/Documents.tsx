import { useEffect, useState } from "react";
import { api } from "../api";

export default function Documents() {
  const [docs, setDocs] = useState<any[]>([]);
  const [title, setTitle] = useState("");
  const [subsidiary, setSubsidiary] = useState("");
  const [year, setYear] = useState("");
  const [date, setDate] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [filterSub, setFilterSub] = useState("");

  async function load() {
    try {
      const q = filterSub ? `?subsidiary=${encodeURIComponent(filterSub)}` : "";
      setDocs(await api("/documents" + q));
    } catch (e: any) {
      setErr(e.message);
    }
  }
  useEffect(() => { load(); }, [filterSub]);

  async function upload() {
    if (!file) return;
    setBusy(true);
    setMsg("");
    setErr("");
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("title", title);
      fd.append("subsidiary", subsidiary);
      if (year) fd.append("doc_year", year);
      if (date) fd.append("doc_date", date);
      const j = await api("/documents/upload", { method: "POST", body: fd });
      setMsg(`Queued: ${j.job_id} - worker will OCR + index it`);
      load();
    } catch (e: any) {
      setErr(e.message);
    }
    setBusy(false);
  }

  async function extract(id: string) {
    const t = prompt(
      "Doc type (production_report / geological / parliamentary_q / daily_shift_report / stoppage_report):",
      "production_report",
    );
    if (!t) return;
    try {
      const j = await api("/extractions/run", { method: "POST", body: { document_id: id, doc_type: t } });
      setMsg(`Extraction queued: ${j.run_id}`);
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function approveShift(id: string, currentTitle: string, existingApprover?: string) {
    const approver = prompt(
      `Enter Approver Name (Mining Officer / Shift In-Charge) for "${currentTitle}":`,
      existingApprover || "Er. Rajesh Kumar Verma (Shift In-Charge, Mine-1)"
    );
    if (!approver) return;
    try {
      await api(`/documents/${id}/approve`, {
        method: "POST",
        body: { approved_by: approver, notes: "Verified and signed off via Dashboard" },
      });
      setMsg(`Document approved by: ${approver}`);
      load();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  return (
    <div className="page-inner">
      <div className="card">
        <h3>Upload document</h3>
        <label>Title</label>
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Monthly Production Report" />
        <label>Subsidiary (ECL / BCCL / CCL / NCL / WCL / SECL / MCL / CMPDIL)</label>
        <input value={subsidiary} onChange={(e) => setSubsidiary(e.target.value)} />
        <label>Year</label>
        <input type="number" value={year} onChange={(e) => setYear(e.target.value)} />
        <label>Report date (for daily ops reports; blank = auto-detect from filename)</label>
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        <label>File (PDF / DOCX / XLSX / TXT / CSV / image)</label>
        <input type="file" onChange={(e) => setFile(e.target.files?.[0] || null)} />
        <button className="primary" disabled={busy || !file} onClick={upload}>Upload</button>
        {msg && <span className="msg src">{msg}</span>}
        {err && <span className="msg err">{err}</span>}
      </div>
      <div className="card">
        <h3>Indexed documents</h3>
        <label>Filter by subsidiary</label>
        <input value={filterSub} onChange={(e) => setFilterSub(e.target.value)} />
        <table style={{ marginTop: 8 }}>
          <thead>
            <tr>
              <th>Title</th>
              <th>Subsidiary</th>
              <th>Year</th>
              <th>Date</th>
              <th>Approved By</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {docs.map((d) => (
              <tr key={d.id}>
                <td>{d.title}</td>
                <td>{d.subsidiary}</td>
                <td>{d.doc_year ?? ""}</td>
                <td>{d.doc_date ?? ""}</td>
                <td>
                  {d.approved_by ? (
                    <span
                      style={{
                        display: "inline-block",
                        background: "rgba(16, 185, 129, 0.12)",
                        color: "#10b981",
                        border: "1px solid rgba(16, 185, 129, 0.3)",
                        padding: "2px 8px",
                        borderRadius: 4,
                        fontSize: "0.8rem",
                        fontWeight: 600,
                        cursor: "pointer",
                      }}
                      title="Click to edit approver"
                      onClick={() => approveShift(d.id, d.title, d.approved_by)}
                    >
                      ✓ {d.approved_by}
                    </span>
                  ) : (
                    <button
                      className="small"
                      style={{ borderColor: "#6366f1", color: "#818cf8" }}
                      onClick={() => approveShift(d.id, d.title)}
                    >
                      Approve Shift
                    </button>
                  )}
                </td>
                <td>{d.status}</td>
                <td style={{ display: "flex", gap: 6 }}>
                  <button className="small" onClick={() => extract(d.id)}>Extract</button>
                  {!d.approved_by && (
                    <button className="small" onClick={() => approveShift(d.id, d.title)}>Approve</button>
                  )}
                </td>
              </tr>
            ))}
            {!docs.length && <tr><td colSpan={7}>No documents yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
