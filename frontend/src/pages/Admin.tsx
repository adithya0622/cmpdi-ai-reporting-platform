import { useEffect, useState } from "react";
import { api } from "../api";

export default function Admin() {
  const [overview, setOverview] = useState<any>(null);
  const [dq, setDq] = useState<any>(null);
  const [users, setUsers] = useState<any[]>([]);
  const [jobs, setJobs] = useState<any[]>([]);
  const [audit, setAudit] = useState<any[]>([]);
  const [queries, setQueries] = useState<any[]>([]);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("viewer");
  const [subsidiary, setSubsidiary] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  async function load() {
    try {
      const [ov, d, u, j, a, q] = await Promise.all([
        api("/admin/overview"),
        api("/admin/data_quality"),
        api("/auth/users"),
        api("/admin/jobs?limit=50"),
        api("/admin/audit?limit=50"),
        api("/admin/queries?limit=30"),
      ]);
      setOverview(ov);
      setDq(d);
      setUsers(u);
      setJobs(j);
      setAudit(a);
      setQueries(q);
    } catch (e: any) {
      setErr(e.message);
    }
  }
  useEffect(() => { load(); }, []);

  async function createUser() {
    setMsg("");
    setErr("");
    try {
      await api("/auth/users", { method: "POST", body: { username, password, role, subsidiary } });
      setMsg(`user ${username} created`);
      setUsername("");
      setPassword("");
      load();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function retry(id: string) {
    try {
      await api(`/admin/jobs/${id}/retry`, { method: "POST" });
      load();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  return (
    <div className="page-inner">
      {err && <div className="card err" role="alert">{err}</div>}
      {msg && <div className="card src" role="status">{msg}</div>}
      {overview && (
        <div className="kpis" style={{ marginBottom: 16 }}>
          <div className="kpi"><div className="n">{overview.users}</div><div className="l">Users</div></div>
          <div className="kpi"><div className="n">{overview.documents}</div><div className="l">Documents</div></div>
          <div className="kpi"><div className="n">{overview.extraction_runs_pending}</div><div className="l">Runs pending</div></div>
          <div className="kpi"><div className="n">{overview.jobs?.failed || 0}</div><div className="l">Failed jobs</div></div>
          <div className="kpi"><div className="n">{overview.llm ? "up" : "down"}</div><div className="l">LLM</div></div>
          {overview.feedback && (
            <div className="kpi">
              <div className="n">{overview.feedback.positive} / {overview.feedback.negative}</div>
              <div className="l">Feedback +/- ({overview.feedback.total_queries} queries)</div>
            </div>
          )}
        </div>
      )}
      {dq && (
        <div className="card">
          <h3>Data Quality Monitor</h3>
          <div className="kpis" style={{ marginBottom: 12 }}>
            <div className="kpi"><div className="n">{dq.fields_awaiting_review}</div><div className="l">Fields awaiting review</div></div>
            <div className="kpi"><div className="n">{dq.junk_subsidiary_values}</div><div className="l">Corrupt values caught</div></div>
            <div className="kpi"><div className="n">{(dq.document_status || []).find((s: any) => s.status === "approved")?.n ?? 0}</div><div className="l">Approved docs</div></div>
          </div>
          {(dq.flagged_anomalies || []).length > 0 && (
            <table>
              <caption className="sr-only">Data quality anomalies flagged for review</caption>
              <thead>
                <tr><th scope="col">Document</th><th scope="col">Field</th><th scope="col">Value</th><th scope="col">Confidence</th></tr>
              </thead>
              <tbody>
                {dq.flagged_anomalies.slice(0, 8).map((a: any, i: number) => (
                  <tr key={i}>
                    <td>{a.title}</td>
                    <td>{a.field_name}</td>
                    <td>{a.value_num != null ? String(a.value_num) : "—"} {a.unit}</td>
                    <td>{(a.confidence * 100).toFixed(0)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
      <div className="card">
        <h3>Create user</h3>
        <label htmlFor="admin-username">Username</label>
        <input id="admin-username" value={username} onChange={(e) => setUsername(e.target.value)} />
        <label htmlFor="admin-password">Password</label>
        <input id="admin-password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        <label htmlFor="admin-role">Role</label>
        <select id="admin-role" value={role} onChange={(e) => setRole(e.target.value)}>
          <option value="viewer">viewer</option>
          <option value="analyst">analyst</option>
          <option value="admin">admin</option>
        </select>
        <label htmlFor="admin-subsidiary">Subsidiary (blank = all)</label>
        <input id="admin-subsidiary" value={subsidiary} onChange={(e) => setSubsidiary(e.target.value)} />
        <button className="primary" disabled={!username || !password} onClick={createUser}>Create</button>
      </div>
      <div className="card">
        <h3>Users</h3>
        <table>
          <caption className="sr-only">Registered platform users</caption>
          <thead><tr><th scope="col">Username</th><th scope="col">Role</th><th scope="col">Subsidiary</th></tr></thead>
          <tbody>{users.map((u) => <tr key={u.username}><td>{u.username}</td><td>{u.role}</td><td>{u.subsidiary}</td></tr>)}</tbody>
        </table>
      </div>
      <div className="card">
        <h3>Jobs</h3>
        <table>
          <caption className="sr-only">Background processing jobs</caption>
          <thead><tr><th scope="col">Kind</th><th scope="col">Status</th><th scope="col">Error</th><th scope="col">Created</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
          <tbody>
            {jobs.map((j) => (
              <tr key={j.id}>
                <td>{j.kind}</td>
                <td>{j.status}</td>
                <td className="err">{j.error ? String(j.error).slice(0, 80) : ""}</td>
                <td>{new Date(j.created_at).toLocaleString()}</td>
                <td>{j.status === "failed" && <button className="small" onClick={() => retry(j.id)} aria-label={`Retry ${j.kind} job`}>Retry</button>}</td>
              </tr>
            ))}
            {!jobs.length && <tr><td colSpan={5}>No jobs yet.</td></tr>}
          </tbody>
        </table>
      </div>
      <div className="card">
        <h3>Query log (faithfulness monitor)</h3>
        <table>
          <caption className="sr-only">Query log with faithfulness and feedback metrics</caption>
          <thead><tr><th scope="col">Question</th><th scope="col">User</th><th scope="col">Mode</th><th scope="col">Latency</th><th scope="col">Grounded</th><th scope="col">Feedback</th></tr></thead>
          <tbody>
            {queries.map((q) => (
              <tr key={q.id}>
                <td>{String(q.question).slice(0, 60)}</td>
                <td>{q.username}</td>
                <td>{q.mode}</td>
                <td>{q.latency_ms} ms</td>
                <td>{q.grounded_pct != null ? (q.grounded_pct * 100).toFixed(0) + "%" : "-"}</td>
                <td>{q.rating === 1 ? <span aria-label="Positive feedback">👍</span> : q.rating === -1 ? <span aria-label="Negative feedback">👎</span> : "-"}</td>
              </tr>
            ))}
            {!queries.length && <tr><td colSpan={6}>No queries yet.</td></tr>}
          </tbody>
        </table>
      </div>
      <div className="card">
        <h3>Audit log</h3>
        <table>
          <caption className="sr-only">System audit trail</caption>
          <thead><tr><th scope="col">When</th><th scope="col">User</th><th scope="col">Action</th><th scope="col">Detail</th></tr></thead>
          <tbody>
            {audit.map((a) => (
              <tr key={a.id}>
                <td>{new Date(a.ts).toLocaleString()}</td>
                <td>{a.username}</td>
                <td>{a.action}</td>
                <td className="src">{JSON.stringify(a.detail).slice(0, 100)}</td>
              </tr>
            ))}
            {!audit.length && <tr><td colSpan={4}>No audit entries yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
