"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api } from "../../lib/api";
import ActivityCard from "../../components/ActivityCard";

type Run = { id: string; ticker: string; date: string; provider: string; status: string; awaiting_input: boolean };

function Quote({ ticker }: { ticker: string }) {
  const [q, setQ] = useState<any>(null);
  useEffect(() => {
    if (!ticker) return;
    let alive = true;
    async function poll() {
      try {
        const r = await api.quote(ticker);
        if (alive && r.ok) setQ(r);
      } catch { /* keep last */ }
    }
    poll();
    const t = setInterval(poll, 30000);
    return () => { alive = false; clearInterval(t); };
  }, [ticker]);
  if (!q) return null;
  const color = q.up ? "#3fb950" : "#f85149";
  return (
    <span className="chip">
      <b>{q.symbol}</b> <span style={{ color }}>{q.price?.toFixed(2)} {q.up ? "▲" : "▼"} {q.pct?.toFixed(2)}%</span>
    </span>
  );
}

function fmtElapsed(s: number) {
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

export default function Live() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [runId, setRunId] = useState("");
  const [state, setState] = useState<any>(null);
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState("");
  const [followMsg, setFollowMsg] = useState(true);
  const [followRep, setFollowRep] = useState(true);
  const msgRef = useRef<HTMLDivElement>(null);
  const repRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("run");
    if (q) setRunId(q);
    api.runs().then((r) => {
      setRuns(r.runs);
      if (!q && r.runs.length) setRunId(r.runs[0].id);
    }).catch((e) => setError(String(e.message || e)));
  }, []);

  useEffect(() => {
    if (!runId) return;
    let alive = true;
    async function tick() {
      try {
        const s = await api.runState(runId);
        if (alive) {
          setState(s);
          if (!s.pending_prompt?.question) setAnswer("");
          else if (!answer && s.pending_prompt.default) setAnswer(s.pending_prompt.default);
        }
      } catch (e: any) {
        if (alive) setError(String(e.message || e));
      }
    }
    tick();
    const t = setInterval(tick, 1500);
    return () => { alive = false; clearInterval(t); };
  }, [runId]);

  useEffect(() => {
    if (followMsg && msgRef.current) msgRef.current.scrollTop = msgRef.current.scrollHeight;
  }, [state?.messages?.length, followMsg]);

  useEffect(() => {
    if (followRep && repRef.current) repRef.current.scrollTop = repRef.current.scrollHeight;
  }, [state?.current_report, followRep]);

  async function send() {
    try {
      await api.answerRun(runId, answer);
      setAnswer("");
    } catch (e: any) {
      setError(e.data?.error || String(e.message || e));
    }
  }

  const pending = state?.pending_prompt?.question ? state.pending_prompt : null;
  const st = state?.stats || {};
  const meta = state?.meta || {};
  const status = state?.status || "unknown";
  const live = state?.active && status === "running" && !pending;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>
          Live{" "}
          {live && <span className="pill pill-in_progress">live</span>}
          {pending && <span className="pill pill-pending">awaiting input</span>}
          {status === "done" && <span className="pill pill-completed">done</span>}
          {status === "error" && <span className="pill pill-error">error</span>}
        </h1>
        {meta.ticker && <Quote ticker={meta.ticker} />}
      </div>
      {error && <p className="err">{error}</p>}
      <label className="field" style={{ maxWidth: 460 }}>
        Run
        <select value={runId} onChange={(e) => setRunId(e.target.value)}>
          {runs.map((r) => (
            <option key={r.id} value={r.id}>
              {r.ticker} {r.date} — {r.status}
            </option>
          ))}
        </select>
      </label>
      {!state && <p className="dim">No run selected. Start one from Dashboard, or run the CLI.</p>}
      {state && (
        <>
          <div className="stats">
            <span className="chip">Agents <b>{state.agents_completed}/{state.agents_total}</b></span>
            <span className="chip">LLM <b>{st.llm_calls ?? "–"}</b></span>
            <span className="chip">Tools <b>{st.tool_calls ?? "–"}</b></span>
            <span className="chip">Reports <b>{state.reports_completed}/{state.reports_total}</b></span>
            <span className="chip">⏱ <b>{fmtElapsed(state.elapsed_seconds || 0)}</b></span>
            <span className="chip">
              ● <b>{state.current_agent || "idle"}</b> {state.last_activity_age ?? 0}s ago
            </span>
            {meta.llm_provider && <span className="chip">{meta.llm_provider}</span>}
            {state.status === "error" && <span className="chip err">error: {state.error}</span>}
          </div>
          {pending && (
            <div className="promptbar">
              <b style={{ color: "#d29922" }}>Input needed:</b> {pending.question}{" "}
              {pending.default && <span className="dim">[{pending.default}]</span>}
              <div style={{ marginTop: 6 }}>
                <input
                  type="text"
                  value={answer}
                  onChange={(e) => setAnswer(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") send(); }}
                  style={{ width: "40%" }}
                />{" "}
                <button className="primary" onClick={send}>Send</button>
              </div>
            </div>
          )}
          <div className="row">
            <div className="panel col">
              <h2>Progress</h2>
              <div className="scroll" style={{ maxHeight: "42vh" }}>
                {state.teams?.map((t: any) => (
                  <div key={t.team}>
                    <div className="teamhead">{t.team}</div>
                    <table className="grid">
                      <tbody>
                        {t.agents.map((a: string) => {
                          const s = state.statuses?.[a] || "pending";
                          return (
                            <tr key={a}>
                              <td>{a}</td>
                              <td style={{ textAlign: "right" }}>
                                <span className={`pill pill-${s}`}>{s.replace("_", " ")}</span>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                ))}
              </div>
            </div>
            <div className="panel col">
              <h2>
                Messages &amp; Tools{" "}
                <label className="dim" style={{ fontSize: 11 }}>
                  <input type="checkbox" checked={followMsg} onChange={(e) => setFollowMsg(e.target.checked)} /> follow
                </label>
              </h2>
              <div className="scroll" ref={msgRef} style={{ maxHeight: "42vh" }}>
                {state.messages?.map((m: any, i: number) => (
                  <div key={i} style={{ borderBottom: "1px solid #f0f0f0", padding: "6px 0" }}>
                    <span className="dim">{m.time} · </span>
                    <span className="ok">{m.type}</span>
                    <pre style={{ whiteSpace: "pre-wrap", wordBreak: "break-word", margin: "4px 0 0" }}>{m.content}</pre>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <ActivityCard messages={state.messages || []} />
          <div className="panel">
            <h2>
              Current report{" "}
              <label className="dim" style={{ fontSize: 11 }}>
                <input type="checkbox" checked={followRep} onChange={(e) => setFollowRep(e.target.checked)} /> follow
              </label>
            </h2>
            <div className="md scroll" ref={repRef} style={{ maxHeight: "50vh" }}>
              {state.current_report
                ? <ReactMarkdown>{state.current_report}</ReactMarkdown>
                : <span className="dim">Waiting for analysis report…</span>}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
