import { useEffect, useState } from "react";
import { api } from "../api";

export default function Admin() {
  const [overview, setOverview] = useState<any>(null);
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
      const [ov, u, j, a, q] = await Promise.all([
        api("/admin/overview"),
        api("/auth/users"),
        api("/admin/jobs?limit=50"),
        api("/admin/audit?limit=50"),
        api("/admin/queries?limit=30"),
      ]);
      setOverview(ov);
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
      {err && <div className="card err">{err}</div>}
      {msg && <div className="card src">{msg}</div>}
      {overview && (
        <div className="kpis" style={{ marginBottom: 16 }}>
          <div className="kpi"><div className="n">{overview.users}</div><div className="l">Users</div></div>
          <div className="kpi"><div className="n">{overview.documents}</div><div className="l">Documents</div></div>
          <div className="kpi"><div className="n">{overview.extraction_runs_pending}</div><div className="l">Runs pending</div></div>
          <div className="kpi"><div className="n">{overview.jobs?.failed || 0}</div><div className="l">Failed jobs</div></div>
          <div className="kpi"><div className="n">{overview.llm ? "up" : "down"}</div><div className="l">LLM</div></div>
        </div>
      )}
      <div className="card">
        <h3>Create user</h3>
        <label>Username / Password</label>
        <div style={{ display: "flex", gap: 8 }}>
          <input value={username} onChange={(e) => setUsername(e.target.value)} />
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
        <label>Role / Subsidiary (blank = all)</label>
        <div style={{ display: "flex", gap: 8 }}>
          <select value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="viewer">viewer</option>
            <option value="analyst">analyst</option>
            <option value="admin">admin</option>
          </select>
          <input value={subsidiary} onChange={(e) => setSubsidiary(e.target.value)} />
        </div>
        <button className="primary" disabled={!username || !password} onClick={createUser}>Create</button>
      </div>
      <div className="card">
        <h3>Users</h3>
        <table>
          <thead><tr><th>Username</th><th>Role</th><th>Subsidiary</th></tr></thead>
          <tbody>{users.map((u) => <tr key={u.username}><td>{u.username}</td><td>{u.role}</td><td>{u.subsidiary}</td></tr>)}</tbody>
        </table>
      </div>
      <div className="card">
        <h3>Jobs</h3>
        <table>
          <thead><tr><th>Kind</th><th>Status</th><th>Error</th><th>Created</th><th></th></tr></thead>
          <tbody>
            {jobs.map((j) => (
              <tr key={j.id}>
                <td>{j.kind}</td>
                <td>{j.status}</td>
                <td className="err">{j.error ? String(j.error).slice(0, 80) : ""}</td>
                <td>{new Date(j.created_at).toLocaleString()}</td>
                <td>{j.status === "failed" && <button className="small" onClick={() => retry(j.id)}>Retry</button>}</td>
              </tr>
            ))}
            {!jobs.length && <tr><td>No jobs yet.</td></tr>}
          </tbody>
        </table>
      </div>
      <div className="card">
        <h3>Query log (faithfulness monitor)</h3>
        <table>
          <thead><tr><th>Question</th><th>User</th><th>Mode</th><th>Latency</th><th>Grounded</th></tr></thead>
          <tbody>
            {queries.map((q) => (
              <tr key={q.id}>
                <td>{String(q.question).slice(0, 60)}</td>
                <td>{q.username}</td>
                <td>{q.mode}</td>
                <td>{q.latency_ms} ms</td>
                <td>{q.grounded_pct != null ? (q.grounded_pct * 100).toFixed(0) + "%" : "-"}</td>
              </tr>
            ))}
            {!queries.length && <tr><td>No queries yet.</td></tr>}
          </tbody>
        </table>
      </div>
      <div className="card">
        <h3>Audit log</h3>
        <table>
          <thead><tr><th>When</th><th>User</th><th>Action</th><th>Detail</th></tr></thead>
          <tbody>
            {audit.map((a) => (
              <tr key={a.id}>
                <td>{new Date(a.ts).toLocaleString()}</td>
                <td>{a.username}</td>
                <td>{a.action}</td>
                <td className="src">{JSON.stringify(a.detail).slice(0, 100)}</td>
              </tr>
            ))}
            {!audit.length && <tr><td>No audit entries yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
