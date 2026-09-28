import { useEffect, useState } from "react";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { api } from "../api";

const FIELDS = [
  "production_lt",
  "dispatch_lt",
  "offtake_lt",
  "rom_lt",
  "washery_output_lt",
  "reserves_mt",
  "total_lignite_mt",
  "total_ob_m3",
  "power_generation_mw",
  "output_mt",
  "ewh_h",
];

export default function Analytics() {
  const [subsidiary, setSubsidiary] = useState("");
  const [yf, setYf] = useState("");
  const [yt, setYt] = useState("");
  const [kpis, setKpis] = useState<any | null>(null);
  const [cloud, setCloud] = useState<any[]>([]);
  const [topics, setTopics] = useState<any[]>([]);
  const [summary, setSummary] = useState("");
  const [trendField, setTrendField] = useState("production_lt");
  const [trends, setTrends] = useState<any[]>([]);
  const [topicTrends, setTopicTrends] = useState<any[]>([]);
  const [err, setErr] = useState("");

  // recommendations state
  const [recs, setRecs] = useState<any | null>(null);
  const [recsLoading, setRecsLoading] = useState(false);
  const [recsErr, setRecsErr] = useState("");

  // daily operations state
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [pareto, setPareto] = useState<any | null>(null);
  const [util, setUtil] = useState<any[]>([]);
  const [opsErr, setOpsErr] = useState("");
  const [opsBusy, setOpsBusy] = useState(false);

  function qs(extra: Record<string, string> = {}) {
    const p = new URLSearchParams();
    if (subsidiary) p.set("subsidiary", subsidiary);
    if (yf) p.set("year_from", yf);
    if (yt) p.set("year_to", yt);
    Object.entries(extra).forEach(([k, v]) => p.set(k, v));
    const s = p.toString();
    return s ? `?${s}` : "";
  }

  async function run() {
    setErr("");
    try {
      const wc = await api("/analytics/wordcloud" + qs());
      setCloud(wc);
      const tp = await api("/analytics/topics" + qs());
      setTopics(tp.topics);
      setSummary(tp.summary || "");
      const tr = await api("/analytics/trends" + qs({ field_name: trendField }));
      setTrends(tr);
      const tt = await api("/analytics/topic_trends" + qs());
      setTopicTrends(tt);
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function runDailyOps() {
    setOpsErr("");
    setOpsBusy(true);
    try {
      const p = new URLSearchParams();
      if (subsidiary) p.set("subsidiary", subsidiary);
      if (dateFrom) p.set("date_from", dateFrom);
      if (dateTo) p.set("date_to", dateTo);
      const s = p.toString() ? `?${p.toString()}` : "";
      const [pt, ut] = await Promise.all([
        api("/analytics/stoppage_pareto" + s),
        api("/analytics/machine_utilization" + s),
      ]);
      setPareto(pt);
      setUtil(ut);
    } catch (e: any) {
      setOpsErr(e.message);
    }
    setOpsBusy(false);
  }

  async function loadRecs() {
    setRecsErr("");
    setRecsLoading(true);
    try {
      const s = subsidiary ? `?subsidiary=${subsidiary}` : "";
      setRecs(await api("/analytics/recommendations" + s));
    } catch (e: any) {
      setRecsErr(e.message);
    }
    setRecsLoading(false);
  }

  useEffect(() => {
    api("/analytics/kpis").then(setKpis).catch(() => {});
  }, []);

  useEffect(() => {
    api(`/analytics/trends?field_name=${trendField}`).then(setTrends).catch(() => {});
  }, [trendField]);

  const max = cloud.length ? cloud[0].count : 1;

  return (
    <div className="page-inner">
      <div className="card">
        <h3>PS Metrics</h3>
        {!kpis && <p className="src">Loading metrics…</p>}
        {kpis && (
          <div className="kpis" style={{ marginBottom: 0 }}>
            <div className="kpi"><div className="n">{kpis.automation_pct}%</div><div className="l">automation — {kpis.fields_auto}/{kpis.fields_total} fields auto-extracted</div></div>
            <div className="kpi"><div className="n">{kpis.automation_strong_pct}%</div><div className="l">automation (high-confidence)</div></div>
            <div className="kpi">
              <div className="n">{kpis.eval ? `${(kpis.eval.precision * 100).toFixed(1)}%` : "—"}</div>
              <div className="l">extraction accuracy (precision{kpis.eval ? `, ${kpis.eval.entries} gold entries` : " — run eval harness"})</div>
            </div>
            <div className="kpi">
              <div className="n">{kpis.report_prep_seconds != null ? (kpis.report_prep_seconds < 90 ? `${kpis.report_prep_seconds.toFixed(1)} s` : `${(kpis.report_prep_seconds / 3600).toFixed(2)} h`) : "—"}</div>
              <div className="l">report build time{kpis.report_prep_time_reduction_pct != null ? ` — ${kpis.report_prep_time_reduction_pct}% vs manual` : " — baseline not measured"}</div>
            </div>
            {kpis.human_triage_agreement_pct != null && (
              <div className="kpi"><div className="n">{kpis.human_triage_agreement_pct}%</div><div className="l">human–AI agreement ({kpis.fields_confirmed + kpis.fields_rejected} triaged)</div></div>
            )}
            <div className="kpi"><div className="n">{kpis.corpus.documents}</div><div className="l">documents indexed ({kpis.corpus.vector_chunks}/{kpis.corpus.chunks} chunks vectorized)</div></div>
          </div>
        )}
      </div>

      <div className="card">
        <h3>AI Recommendations</h3>
        <p className="src" style={{ marginTop: -4, marginBottom: 8 }}>
          AI-generated actionable insights based on production trends, equipment utilization, stoppage patterns, and query quality.
        </p>
        <button className="primary" onClick={loadRecs} disabled={recsLoading}>
          {recsLoading ? "Analyzing..." : "Generate Recommendations"}
        </button>
        {recsErr && <span className="msg err">{recsErr}</span>}
        {recs && recs.recommendations && (
          <div style={{ marginTop: 12 }}>
            {recs.recommendations.map((r: any, idx: number) => {
              const color = r.priority === "high" ? "#e74c3c" : r.priority === "medium" ? "#f39c12" : "#2980b9";
              return (
                <div key={idx} style={{ borderLeft: `4px solid ${color}`, padding: "8px 12px", marginBottom: 10, background: "var(--card-bg)", borderRadius: 4 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                    <span className="badge" style={{ background: color, color: "#fff", padding: "2px 8px", fontSize: 10, borderRadius: 3 }}>
                      {(r.priority || "medium").toUpperCase()}
                    </span>
                    <b>{r.title}</b>
                  </div>
                  <div style={{ fontSize: 13, lineHeight: 1.5 }}>{r.recommendation}</div>
                  {r.impact && <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>Impact: {r.impact}</div>}
                </div>
              );
            })}
            {recs.recommendations.length === 0 && <p className="src">No actionable recommendations at this time — all metrics within healthy ranges.</p>}
          </div>
        )}
      </div>

      <div className="card">
        <h3>Filters</h3>
        <label>Subsidiary (blank = all)</label>
        <input value={subsidiary} onChange={(e) => setSubsidiary(e.target.value)} />
        <label>Year from / to</label>
        <div style={{ display: "flex", gap: 8 }}>
          <input type="number" value={yf} onChange={(e) => setYf(e.target.value)} />
          <input type="number" value={yt} onChange={(e) => setYt(e.target.value)} />
        </div>
        <button className="primary" onClick={run}>Run analysis</button>
        {err && <span className="msg err">{err}</span>}
      </div>

      <div className="card">
        <h3>Daily operations — stoppages &amp; machine utilization</h3>
        <label>Date from / to (YYYY-MM-DD, blank = all)</label>
        <div style={{ display: "flex", gap: 8 }}>
          <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        </div>
        <button className="primary" onClick={runDailyOps} disabled={opsBusy}>
          {opsBusy ? "Loading…" : "Load daily operations"}
        </button>
        {opsErr && <span className="msg err">{opsErr}</span>}
        {pareto && (
          <>
            <p className="src">
              Total downtime <b>{pareto.total_stoppage_h} h</b> across {pareto.stoppage_events} stoppage events.
            </p>

            {/* Interactive Bar Chart for Pareto */}
            {pareto.categories && pareto.categories.length > 0 && (
              <div style={{ marginTop: 16, marginBottom: 16 }}>
                <h4 style={{ margin: "0 0 10px 0" }}>HEMM Downtime Hours by Stoppage Reason</h4>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={pareto.categories} margin={{ top: 10, right: 20, left: 0, bottom: 25 }}>
                    <XAxis
                      dataKey="category"
                      angle={-20}
                      textAnchor="end"
                      interval={0}
                      tick={{ fontSize: 11 }}
                    />
                    <YAxis label={{ value: 'Hours', angle: -90, position: 'insideLeft', fontSize: 12 }} />
                    <Tooltip
                      formatter={(val: any) => [`${val} hrs`, "Downtime"]}
                      labelFormatter={(label) => `Category: ${label}`}
                    />
                    <Bar dataKey="hours" radius={[4, 4, 0, 0]}>
                      {pareto.categories.map((_: any, index: number) => {
                        const colors = ["#e74c3c", "#e67e22", "#f39c12", "#2980b9", "#8e44ad", "#16a085", "#7f8c8d"];
                        return <Cell key={`cell-${index}`} fill={colors[index % colors.length]} />;
                      })}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}

            <table style={{ marginTop: 8 }}>
              <thead><tr><th>Stoppage category</th><th>Hours</th><th>Share</th><th>Cumulative</th></tr></thead>
              <tbody>
                {pareto.categories.map((c: any) => (
                  <tr key={c.category}>
                    <td style={{ fontWeight: 600 }}>{c.category}</td>
                    <td>{c.hours} hrs</td>
                    <td>{c.share_pct}%</td>
                    <td><b>{c.cumulative_pct}%</b></td>
                  </tr>
                ))}
                {!pareto.categories.length && <tr><td>No stoppage data extracted yet.</td></tr>}
              </tbody>
            </table>

            <h4 style={{ marginTop: 24, marginBottom: 8 }}>Heavy Equipment Utilization (EWH / TWH)</h4>
            <table>
              <thead><tr><th>Machine ID</th><th>TWH (h)</th><th>EWH (h)</th><th>Util %</th><th>Output (t)</th><th>Days Reported</th><th>Status</th></tr></thead>
              <tbody>
                {util.map((m) => {
                  const u = m.utilization_pct;
                  const badgeClass = u == null ? "" : u >= 70 ? "badge-green" : u >= 50 ? "badge-amber" : "badge-red";
                  const statusText = u == null ? "N/A" : u >= 70 ? "Optimal" : u >= 50 ? "Moderate" : "Underutilized";
                  return (
                    <tr key={m.machine_id}>
                      <td style={{ fontWeight: 600 }}>{m.machine_id}</td>
                      <td>{m.twh_h}</td>
                      <td>{m.ewh_h}</td>
                      <td><b>{m.utilization_pct != null ? `${m.utilization_pct}%` : "-"}</b></td>
                      <td>{m.output_mt?.toLocaleString()}</td>
                      <td>{m.days_reported}</td>
                      <td><span className={`badge ${badgeClass}`}>{statusText}</span></td>
                    </tr>
                  );
                })}
                {!util.length && <tr><td colSpan={7}>No utilization data extracted yet.</td></tr>}
              </tbody>
            </table>
          </>
        )}
        {!pareto && <p className="src">Run extractions on stoppage reports first, then load here.</p>}
      </div>

      <div className="card">
        <h3>Production trend (extracted figures)</h3>
        <label>Field</label>
        <select value={trendField} onChange={(e) => setTrendField(e.target.value)}>
          {FIELDS.map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
        <div style={{ marginTop: 12 }}>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={trends}>
              <XAxis dataKey="year" />
              <YAxis />
              <Tooltip />
              <Line type="monotone" dataKey="value" stroke="#f5a623" strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
          {!trends.length && <p className="src">No extracted figures yet - run extractions first.</p>}
        </div>
      </div>

      <div className="card">
        <h3>Word cloud</h3>
        <div className="cloud">
          {cloud.map((w) => (
            <span key={w.term} style={{ fontSize: `${(12 + 24 * (w.count / max)).toFixed(0)}px` }}>{w.term}</span>
          ))}
          {!cloud.length && <span className="src">Run analysis to generate.</span>}
        </div>
      </div>

      <div className="card">
        <h3>Top topics</h3>
        <table>
          <thead><tr><th>Term</th><th>Count</th></tr></thead>
          <tbody>
            {topics.map((t) => (
              <tr key={t.term}><td>{t.term}</td><td>{t.count}</td></tr>
            ))}
            {!topics.length && <tr><td>-</td></tr>}
          </tbody>
        </table>
        {summary && <pre>{summary}</pre>}
      </div>

      <div className="card">
        <h3>Topic trends over years</h3>
        {topicTrends.map((t) => (
          <p key={t.year} className="src">
            <b>{t.year || "unyeared"}:</b> {t.topics.map((x: any) => `${x.term} (${x.count})`).join(", ") || "-"}
          </p>
        ))}
        {!topicTrends.length && <p className="src">Run analysis to generate.</p>}
      </div>
    </div>
  );
}
