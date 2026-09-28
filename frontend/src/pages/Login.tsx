import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "../api";

export default function Login({ onLogin }: { onLogin: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const nav = useNavigate();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      await login(username, password);
      onLogin();
      nav("/dashboard");
    } catch (ex: any) {
      setErr(ex.message);
    }
    setBusy(false);
  }

  return (
    <main className="login-wrap">
      <div className="card">
        <h1 style={{ fontSize: 22, marginTop: 0 }}>CMPDI AI Reporting Platform</h1>
        <form onSubmit={submit}>
          <label htmlFor="login-user">Username</label>
          <input id="login-user" value={username} onChange={(e) => setUsername(e.target.value)} autoFocus required autoComplete="username" />
          <label htmlFor="login-pass">Password</label>
          <input id="login-pass" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" />
          <button className="primary" disabled={busy || !username || !password}>
            {busy ? "Logging in..." : "Login"}
          </button>
          {err && <p className="err" role="alert">{err}</p>}
        </form>
      </div>
    </main>
  );
}
