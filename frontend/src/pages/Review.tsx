import { useEffect, useState } from "react";
import { api } from "../api";

export default function Review() {
  const [items, setItems] = useState<any[]>([]);
  const [err, setErr] = useState("");
  const [values, setValues] = useState<Record<number, string>>({});
  const [approverName, setApproverName] = useState("Er. Rajesh Kumar Verma (Shift In-Charge)");

  async function load() {
    try {
      setItems(await api("/extractions/review"));
    } catch (e: any) {
      setErr(e.message);
    }
  }
  useEffect(() => { load(); }, []);

  async function act(id: number, action: "confirm" | "reject") {
    const body: any = { action, approved_by: approverName };
    const v = values[id];
    if (action === "confirm" && v !== undefined && v !== "") body.value = isNaN(+v) ? v : +v;
    try {
      await api(`/extractions/fields/${id}/review`, { method: "POST", body });
      load();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  return (
    <div className="page-inner">
      <div className="card">
        <h3>Fields needing review & approval</h3>
      <p className="src">Low-confidence, out-of-range or anomalous extracted values. Confirm or correct them - confirmed fields record the approver's sign-off.</p>
      
      <div style={{ margin: "14px 0", display: "flex", alignItems: "center", gap: 10, background: "rgba(99, 102, 241, 0.08)", padding: 10, borderRadius: 6 }}>
        <label style={{ margin: 0, fontWeight: 600, minWidth: 120 }}>Approving Officer:</label>
        <input
          style={{ maxWidth: 350, padding: "6px 10px" }}
          value={approverName}
          onChange={(e) => setApproverName(e.target.value)}
          placeholder="e.g. Er. Rajesh Kumar Verma (Shift In-Charge)"
        />
        <span style={{ fontSize: "0.8rem", color: "#64748b" }}>Recorded upon field confirmation</span>
      </div>

      {err && <p className="err">{err}</p>}
      <table>
        <thead><tr><th>Field</th><th>Value</th><th>Conf.</th><th>Document</th><th>Corrected value</th><th>Actions</th></tr></thead>
        <tbody>
          {items.map((f) => (
            <tr key={f.id}>
              <td>{f.field_name}</td>
              <td>{f.value_num ?? f.value_str}</td>
              <td>{(f.confidence * 100).toFixed(0)}%</td>
              <td>{f.title}</td>
              <td>
                <input
                  style={{ padding: 4, width: 130 }}
                  value={values[f.id] ?? ""}
                  onChange={(e) => setValues({ ...values, [f.id]: e.target.value })}
                />
              </td>
              <td>
                <button className="small" onClick={() => act(f.id, "confirm")}>Confirm</button>
                <button className="small" onClick={() => act(f.id, "reject")}>Reject</button>
              </td>
            </tr>
          ))}
          {!items.length && <tr><td>Nothing to review.</td></tr>}
        </tbody>
      </table>
      </div>
    </div>
  );
}
