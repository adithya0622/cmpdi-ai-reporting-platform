const TOKEN_KEY = "cmpdi_token";
const ROLE_KEY = "cmpdi_role";

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function getRole(): string {
  return localStorage.getItem(ROLE_KEY) || "";
}

export function isLoggedIn(): boolean {
  return !!getToken();
}

export function setToken(token: string, role: string): void {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(ROLE_KEY, role);
}

export function logout(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(ROLE_KEY);
}

type ApiOpts = Omit<RequestInit, "body"> & { body?: any };

export async function api(path: string, opts: ApiOpts = {}): Promise<any> {
  const headers: Record<string, string> = Object.assign(
    { "X-API-Token": getToken() },
    (opts.headers as Record<string, string>) || {}
  );
  if (opts.body && typeof opts.body !== "string" && !(opts.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
    opts = { ...opts, body: JSON.stringify(opts.body) };
  }
  const r = await fetch(path, { ...opts, headers });
  if (r.status === 401) {
    logout();
    throw new Error("session expired - login again");
  }
  if (!r.ok) throw new Error((await r.text()).slice(0, 300));
  return r.json();
}

export async function login(username: string, password: string): Promise<any> {
  const r = await fetch("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!r.ok) throw new Error("login failed: check username/password");
  const j = await r.json();
  setToken(j.token, j.role);
  return j;
}

export async function downloadReport(id: string): Promise<void> {
  const r = await fetch(`/reports/${id}/download`, { headers: { "X-API-Token": getToken() } });
  if (!r.ok) throw new Error("download failed");
  const b = await r.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(b);
  a.download = "report.docx";
  a.click();
}

export function esc(s: unknown): string {
  return String(s ?? "");
}
