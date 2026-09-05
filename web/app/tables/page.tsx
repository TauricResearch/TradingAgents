"use client";

import { useEffect, useState } from "react";
import { api, Provider } from "../../lib/api";

type Session = { id: string; kind: string; ticker: string; date: string };
type Table = { title: string; headers: string[]; rows: string[][] };

export default function Tables() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [sel, setSel] = useState("");
  const [tables, setTables] = useState<Record<string, Table[]>>({});
  const [status, setStatus] = useState("");
  const [statusDetail, setStatusDetail] = useState<any>(null);
  const [error, setError] = useState("");
  const [providers, setProviders] = useState<Provider[]>([]);
  const [provider, setProvider] = useState("opencode");
  const [models, setModels] = useState<{ name: string; id: string }[]>([]);
  const [model, setModel] = useState("");
  const [modelsLoading, setModelsLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);

  useEffect(() => {
    api.sessions().then((r) => {
      setSessions(r.sessions);
      if (r.sessions.length) open(r.sessions[0].id);
    }).catch((e) => setError(String(e.message || e)));
    api.options().then((o) => setProviders(o.providers)).catch(() => {});
  }, []);

  useEffect(() => {
    if (!provider) return;
    setModelsLoading(true);
    setModels([]);
    setModel("");
    api.models(provider, "quick")
      .then((r) => {
        const list = r.models.filter((m: any) => m.id !== "custom");
        setModels(r.models);
        const free = list.find((m: any) => /free/i.test(m.id));
        setModel(free?.id || list[0]?.id || "");
      })
      .catch(() => {})
      .finally(() => setModelsLoading(false));
  }, [provider]);

  async function open(id: string) {
    setSel(id);
    setError("");
    setStatusDetail(null);
    try {
      const r = await api.session(id);
      setTables(r.tables || {});
      const st = await api.tablesStatus(id);
      setStatus(st.status);
      setStatusDetail(st);
    } catch (e: any) {
      setError(e.data?.error || String(e.message || e));
    }
  }

  async function generate() {
    if (!model) return;
    setShowForm(false);
    try {
      await api.generateTables(sel, provider, model);
      poll();
    } catch (e: any) {
      setError(e.data?.error || String(e.message || e));
    }
  }

  async function poll() {
    try {
      const st = await api.tablesStatus(sel);
      setStatus(st.status);
      setStatusDetail(st);
      if (st.status === "generating") {
        setTimeout(poll, 3000);
      } else if (st.status === "done") {
        const r = await api.session(sel);
        setTables(r.tables || {});
      }
    } catch { /* keep polling next tick */ }
  }

  const agents = Object.keys(tables);
  const generating = status === "generating";

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Tables</h1>
        {sel && Object.keys(tables).length === 0 && status !== "generating" && (
          <button className="primary" onClick={() => setShowForm(!showForm)}>
            Generate tables for this session
          </button>
        )}
      </div>
      {error && <p className="err">{error}</p>}
      {showForm && sel && (
        <div className="panel" style={{ maxWidth: 640 }}>
          <h2>Generate with model</h2>
          <div className="row">
            <label className="field col">
              Provider
              <select value={provider} onChange={(e) => setProvider(e.target.value)}>
                {providers.map((p) => (
                  <option key={p.key} value={p.key}>
                    {p.display}{p.keySet ? " (configured)" : ""}
                  </option>
                ))}
              </select>
            </label>
            <label className="field col">
              Model
              <select value={model} onChange={(e) => setModel(e.target.value)} disabled={modelsLoading}>
                {modelsLoading && <option>Loading…</option>}
                {models.map((m) => (
                  <option key={m.id} value={m.id}>{m.name}</option>
                ))}
              </select>
            </label>
          </div>
          <button className="primary" disabled={!model || generating} onClick={generate}>
            {generating ? "Generating…" : "Generate"}
          </button>
        </div>
      )}
      <div className="row">
        <div className="panel col" style={{ maxWidth: 340 }}>
          <h2>Sessions</h2>
          <div className="scroll" style={{ maxHeight: "70vh" }}>
            {sessions.map((s) => (
              <div key={s.id} style={{ marginBottom: 6 }}>
                <button
                  className="ghost"
                  style={{ borderColor: s.id === sel ? "#ea580c" : undefined }}
                  onClick={() => open(s.id)}
                >
                  {s.ticker} · {s.date} <span className="dim">({s.kind})</span>
                </button>
              </div>
            ))}
            {!sessions.length && <div className="shimmer" style={{ height: 120 }} />}
          </div>
        </div>
        <div className="panel col" style={{ flex: 2 }}>
          <h2>{sel ? `Tables — ${sel}` : "Select a session"}</h2>
          {generating && (
            <>
              <p className="dim">
                Extracting tables{statusDetail?.agents ? ` — ${Object.entries(statusDetail.agents).map(([a, c]) => `${a} (${c})`).join(", ")}` : ""}…
              </p>
              <div className="shimmer" style={{ height: 90, marginBottom: 10 }} />
              <div className="shimmer" style={{ height: 150, marginBottom: 10 }} />
              <div className="shimmer" style={{ height: 120 }} />
            </>
          )}
          {statusDetail?.status === "error" && <p className="err">{statusDetail.error}</p>}
          {!generating && !agents.length && sel && (
            <p className="dim">No tables yet — use “Generate tables for this session”.</p>
          )}
          {agents.map((agent) => (
            <div key={agent}>
              <h3 style={{ color: "#ea580c" }}>{agent}</h3>
              {tables[agent].map((t, i) => (
                <div key={i}>
                  {t.title && <b>{t.title}</b>}
                  <table className="data">
                    <thead>
                      <tr>{t.headers.map((h, j) => <th key={j}>{h}</th>)}</tr>
                    </thead>
                    <tbody>
                      {t.rows.map((row, k) => (
                        <tr key={k}>{row.map((c, j) => <td key={j}>{c}</td>)}</tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
