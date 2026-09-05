"use client";

import { useEffect, useState } from "react";
import { api, Provider } from "../../lib/api";

export default function Settings() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [results, setResults] = useState<Record<string, { ok: boolean; message: string }>>({});
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const [error, setError] = useState("");
  const [opencodeUrl, setOpencodeUrl] = useState("");
  const [opencodeOpts, setOpencodeOpts] = useState<any>(null);
  const [apiBase, setApiBase] = useState("");

  function load() {
    api.keys()
      .then((r) => setProviders(r.keys))
      .catch((e) => setError(String(e.message || e)));
    api.options().then(setOpencodeOpts).catch(() => {});
  }

  useEffect(load, []);

  useEffect(() => {
    setApiBase(window.localStorage.getItem("ta_api_base") || "");
  }, []);

  useEffect(() => {
    if (opencodeOpts?.opencode) setOpencodeUrl(opencodeOpts.opencode.current);
  }, [opencodeOpts]);

  async function save(p: Provider) {
    const value = (drafts[p.key] || "").trim();
    if (!p.keyEnv || !value) return;
    setBusy((b) => ({ ...b, [p.key]: true }));
    try {
      await api.saveKey(p.keyEnv, value);
      setDrafts((d) => ({ ...d, [p.key]: "" }));
      load();
    } catch (e: any) {
      setResults((r) => ({ ...r, [p.key]: { ok: false, message: e.data?.error || String(e.message || e) } }));
    } finally {
      setBusy((b) => ({ ...b, [p.key]: false }));
    }
  }

  async function test(p: Provider) {
    setBusy((b) => ({ ...b, [p.key + ":test"]: true }));
    try {
      const key = (drafts[p.key] || "").trim() || undefined;
      const r = await api.testKey(p.key, key);
      setResults((prev) => ({ ...prev, [p.key]: { ok: r.ok, message: r.message } }));
    } catch (e: any) {
      setResults((prev) => ({ ...prev, [p.key]: { ok: false, message: e.data?.error || String(e.message || e) } }));
    } finally {
      setBusy((b) => ({ ...b, [p.key + ":test"]: false }));
    }
  }

  async function saveCatalog() {
    try {
      await api.saveKey("OPENCODE_BASE_URL", opencodeUrl);
      setResults((r) => ({ ...r, catalog: { ok: true, message: `Catalog endpoint saved: ${opencodeUrl}` } }));
    } catch (e: any) {
      setResults((r) => ({ ...r, catalog: { ok: false, message: e.data?.error || String(e.message || e) } }));
    }
  }

  return (
    <div>
      <h1>Settings</h1>
      {error && <p className="err">{error}</p>}
      <p className="dim">
        Keys save straight to <code>.env</code> and take effect immediately — no restart needed.
        Values are never displayed back.
      </p>
      <div className="panel">
        <h2>Provider API keys</h2>
        <table className="grid">
          <thead>
            <tr><th>Provider</th><th>Status</th><th>New key</th><th></th></tr>
          </thead>
          <tbody>
            {providers.filter((p) => p.keyEnv).map((p) => (
              <tr key={p.key}>
                <td>{p.display}<br /><span className="dim">{p.keyEnv}</span></td>
                <td>{p.keySet ? <span className="ok">● set</span> : <span className="warn">○ missing</span>}</td>
                <td>
                  <input
                    type="password"
                    placeholder={p.keyOptional ? "optional" : "paste key…"}
                    value={drafts[p.key] || ""}
                    onChange={(e) => setDrafts((d) => ({ ...d, [p.key]: e.target.value }))}
                    style={{ width: "100%" }}
                  />
                  {results[p.key] && (
                    <div className={results[p.key].ok ? "ok" : "err"} style={{ marginTop: 4 }}>
                      {results[p.key].ok ? "✓ " : ""}{results[p.key].message}
                    </div>
                  )}
                </td>
                <td style={{ whiteSpace: "nowrap" }}>
                  <button className="ghost" disabled={busy[p.key]} onClick={() => save(p)}>Save</button>{" "}
                  <button className="ghost" disabled={busy[p.key + ":test"]} onClick={() => test(p)}>Test</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="panel">
        <h2>Connection</h2>
        <label className="field" style={{ maxWidth: 520 }}>
          API server (where `tradingagents web` or browser mode listens)
          <input
            type="text"
            placeholder="http://127.0.0.1:8787"
            value={apiBase}
            onChange={(e) => setApiBase(e.target.value)}
          />
        </label>
        <button
          className="ghost"
          onClick={() => {
            window.localStorage.setItem("ta_api_base", apiBase.trim());
            window.location.reload();
          }}
        >
          Save &amp; reconnect
        </button>{" "}
        <button
          className="ghost"
          onClick={() => {
            window.localStorage.removeItem("ta_api_base");
            window.location.reload();
          }}
        >
          Reset to default
        </button>
      </div>
      <div className="panel">
        <h2>Opencode catalog</h2>
        <label className="field" style={{ maxWidth: 520 }}>
          Endpoint
          <select value={opencodeUrl} onChange={(e) => setOpencodeUrl(e.target.value)}>
            <option value={opencodeOpts?.opencode?.fullUrl}>Full — zen/v1 (free + paid, recommended)</option>
            <option value={opencodeOpts?.opencode?.legacyUrl}>Legacy — zen/go/v1 (older catalog)</option>
          </select>
        </label>
        <button className="ghost" onClick={saveCatalog}>Save endpoint</button>{" "}
        {results.catalog && (
          <span className={results.catalog.ok ? "ok" : "err"}>{results.catalog.ok ? "✓ " : ""}{results.catalog.message}</span>
        )}
      </div>
    </div>
  );
}
