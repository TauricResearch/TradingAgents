// HUB — landing page listing all report runs. Group by ticker so multi-run timeline shows up.
// Includes search, filter by verdict, and clickable rows that "navigate" to the detail view.

function HubArtboard({ index = {}, onOpen }) {
  // index: { folder -> { ticker, ts, verdict, target, current, stop, company } }
  const [q, setQ] = React.useState("");
  const [verdictFilter, setVerdictFilter] = React.useState("ALL");

  const rows = REPORT_MANIFEST.map(r => ({ ...r, ...(index[r.folder] || {}) }));

  // Group by ticker
  const byTicker = {};
  for (const r of rows) {
    (byTicker[r.ticker] ||= []).push(r);
  }
  // Filter
  const tickerOrder = Object.keys(byTicker).filter(t => {
    if (q && !t.toLowerCase().includes(q.toLowerCase()) && !byTicker[t].some(r => (r.company || "").toLowerCase().includes(q.toLowerCase()))) return false;
    if (verdictFilter !== "ALL" && !byTicker[t].some(r => r.verdict?.kind === verdictFilter)) return false;
    return true;
  });

  // Counts
  const counts = { BUY: 0, HOLD: 0, SELL: 0 };
  for (const r of rows) if (r.verdict) counts[r.verdict.kind]++;

  return (
    <div style={{
      width: 1280, minHeight: 1100, background: COLORS.paper,
      fontFamily: "Geist, system-ui, sans-serif", color: COLORS.ink,
      padding: "32px 44px 44px",
      display: "flex", flexDirection: "column", gap: 24,
    }}>
      {/* Top bar */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div style={{
            width: 32, height: 32, borderRadius: 9, background: COLORS.ink, color: "white",
            display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, fontSize: 15,
            letterSpacing: -0.5,
          }}>TA</div>
          <div>
            <div style={{ fontSize: 16, fontWeight: 600, letterSpacing: -0.3 }}>TradingAgents</div>
            <div style={{ fontSize: 11, color: COLORS.muted }}>Run archive · {rows.length} reports</div>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ position: "relative" }}>
            <input
              value={q} onChange={e => setQ(e.target.value)}
              placeholder="Search ticker or company…"
              style={{
                width: 260, padding: "8px 12px 8px 32px", fontSize: 13,
                border: `1px solid ${COLORS.rule}`, borderRadius: 9, background: "white",
                fontFamily: "Geist, sans-serif", outline: "none",
              }}
            />
            <span style={{ position: "absolute", left: 11, top: 9, color: COLORS.muted, fontSize: 13 }}>⌕</span>
          </div>
          <button style={{
            padding: "8px 14px", fontSize: 13, fontWeight: 500,
            background: COLORS.ink, color: "white", border: "none",
            borderRadius: 9, cursor: "pointer", fontFamily: "Geist, sans-serif",
          }}>+ New Run</button>
        </div>
      </div>

      {/* Summary strip */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14 }}>
        <Card padding={18}>
          <Stat label="Total Reports" value={rows.length} mono={true} />
        </Card>
        <Card padding={18}>
          <Stat label="Buy / Overweight" value={counts.BUY} color={COLORS.buy.fg} mono={true} />
        </Card>
        <Card padding={18}>
          <Stat label="Hold" value={counts.HOLD} color={COLORS.hold.fg} mono={true} />
        </Card>
        <Card padding={18}>
          <Stat label="Sell / Underweight" value={counts.SELL} color={COLORS.sell.fg} mono={true} />
        </Card>
      </div>

      {/* Filter chips */}
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <span style={{ fontSize: 11, color: COLORS.muted, textTransform: "uppercase", letterSpacing: 0.5, fontWeight: 500, marginRight: 4 }}>Filter</span>
        {["ALL", "BUY", "HOLD", "SELL"].map(k => (
          <button key={k} onClick={() => setVerdictFilter(k)}
            style={{
              padding: "5px 12px", fontSize: 12, fontWeight: 500, cursor: "pointer",
              border: `1px solid ${verdictFilter === k ? COLORS.ink : COLORS.rule}`,
              background: verdictFilter === k ? COLORS.ink : "white",
              color: verdictFilter === k ? "white" : COLORS.ink2,
              borderRadius: 999, fontFamily: "Geist, sans-serif",
            }}>{k === "ALL" ? "All" : k.charAt(0) + k.slice(1).toLowerCase()}</button>
        ))}
      </div>

      {/* Run list */}
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {tickerOrder.map(ticker => {
          const runs = byTicker[ticker];
          const latest = runs[0];
          return (
            <Card key={ticker} padding={0}>
              {/* Ticker header */}
              <div style={{
                display: "flex", alignItems: "center", justifyContent: "space-between",
                padding: "16px 22px", borderBottom: `1px solid ${COLORS.rule2}`,
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                  <div style={{
                    fontSize: 22, fontWeight: 700, letterSpacing: -0.5,
                    fontFamily: "Geist Mono, monospace", color: COLORS.ink,
                  }}>{ticker}</div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                    <div style={{ fontSize: 13, color: COLORS.ink2, fontWeight: 500 }}>{latest.company}</div>
                    <div style={{ fontSize: 11, color: COLORS.muted }}>{runs.length} run{runs.length > 1 ? "s" : ""}</div>
                  </div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                  {latest.target != null && latest.current != null && (
                    <div style={{ textAlign: "right" }}>
                      <div style={{ fontSize: 10, color: COLORS.muted, textTransform: "uppercase", letterSpacing: 0.5 }}>Target / Now</div>
                      <div style={{ fontFamily: "Geist Mono, monospace", fontSize: 13, fontWeight: 600 }}>
                        <span style={{ color: latest.target > latest.current ? COLORS.buy.fg : COLORS.sell.fg }}>${latest.target.toFixed(0)}</span>
                        <span style={{ color: COLORS.muted, margin: "0 6px" }}>/</span>
                        <span style={{ color: COLORS.ink }}>${latest.current.toFixed(0)}</span>
                      </div>
                    </div>
                  )}
                  {latest.verdict && <Pill kind={latest.verdict.kind} size="lg">{latest.verdict.label}</Pill>}
                </div>
              </div>
              {/* Run rows */}
              {runs.map((r, i) => (
                <div key={r.folder}
                  onClick={() => onOpen && onOpen(r.folder)}
                  style={{
                    display: "grid", gridTemplateColumns: "180px 1fr 120px 110px 90px",
                    alignItems: "center", gap: 16,
                    padding: "12px 22px", cursor: "pointer",
                    borderBottom: i < runs.length - 1 ? `1px solid ${COLORS.rule2}` : "none",
                    transition: "background 120ms",
                  }}
                  onMouseEnter={e => e.currentTarget.style.background = COLORS.rule2}
                  onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                >
                  <div style={{ fontSize: 12, color: COLORS.ink2, fontFamily: "Geist Mono, monospace" }}>
                    {r.ts.replace(" ", " · ")}
                  </div>
                  <div style={{ fontSize: 12, color: COLORS.muted, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", lineHeight: 1.5 }}>
                    {r.summary || "—"}
                  </div>
                  <div style={{ fontSize: 11, color: COLORS.muted, textAlign: "right" }}>
                    {r.horizon ? <><span style={{ color: COLORS.faint }}>Horizon</span> {r.horizon}</> : ""}
                  </div>
                  <div style={{ textAlign: "right" }}>
                    {r.verdict && <Pill kind={r.verdict.kind} size="sm">{r.verdict.label}</Pill>}
                  </div>
                  <div style={{ textAlign: "right", color: COLORS.accent, fontSize: 13, fontWeight: 500 }}>Open →</div>
                </div>
              ))}
            </Card>
          );
        })}
      </div>
    </div>
  );
}

window.HubArtboard = HubArtboard;
