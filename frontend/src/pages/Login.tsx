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
    <div className="login-wrap">
      <div className="card">
        <h3>CMPDI AI Reporting Platform</h3>
        <form onSubmit={submit}>
          <label>Username</label>
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
          <label>Password</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
          <button className="primary" disabled={busy || !username || !password}>
            {busy ? "Logging in..." : "Login"}
          </button>
          {err && <p className="err">{err}</p>}
        </form>
      </div>
    </div>
  );
}
