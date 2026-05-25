// Production app router — Hub ↔ Story Detail via hash.
//   #/         → Hub
//   #/r/<folder> → Story detail for that report

const { useState, useEffect } = React;

function getHashRoute() {
  const h = window.location.hash.replace(/^#\/?/, "");
  if (h.startsWith("r/")) {
    return { name: "detail", folder: decodeURIComponent(h.slice(2)) };
  }
  return { name: "hub" };
}

function App() {
  const [t, setTweak] = useTweaks(window.TWEAK_DEFAULTS);
  // Drive imperative globals from tweaks (used by non-React render paths like highlightMD)
  React.useEffect(() => { window.__noHighlightMetrics = !t.highlightMetrics; }, [t.highlightMetrics]);
  return (
    <TweaksContext.Provider value={t}>
      <style>{`:root { --accent: ${t.accent}; }`}</style>
      <AppShell />
      <ReportTweaks t={t} setTweak={setTweak} />
    </TweaksContext.Provider>
  );
}

function ReportTweaks({ t, setTweak }) {
  return (
    <TweaksPanel>
      <TweakSection label="Appearance" />
      <TweakColor label="Accent" value={t.accent}
        options={["#4F5AE6", "#0B7A6E", "#7A4FB5", "#B66431", "#1F8A5B", "#475569"]}
        onChange={(v) => setTweak("accent", v)} />
      <TweakRadio label="Density" value={t.density}
        options={["compact", "cozy"]}
        onChange={(v) => setTweak("density", v)} />
      <TweakRadio label="Hero" value={t.heroSize}
        options={["large", "compact"]}
        onChange={(v) => setTweak("heroSize", v)} />

      <TweakSection label="Show / hide" />
      <TweakToggle label="Confidence gauge" value={t.showConfidence}
        onChange={(v) => setTweak("showConfidence", v)} />
      <TweakToggle label="Bull / bear bar" value={t.showBullBear}
        onChange={(v) => setTweak("showBullBear", v)} />
      <TweakToggle label="Highlight $ / % / x metrics" value={t.highlightMetrics}
        onChange={(v) => setTweak("highlightMetrics", v)} />
    </TweaksPanel>
  );
}

function AppShell() {
  const [route, setRoute] = useState(getHashRoute());
  const [reportsIndex, setReportsIndex] = useState({});
  const [activeReport, setActiveReport] = useState(null);
  const [indexLoading, setIndexLoading] = useState(true);
  const [reportLoading, setReportLoading] = useState(false);

  // Listen for hash changes
  useEffect(() => {
    const onHash = () => setRoute(getHashRoute());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  // Load hub index once
  useEffect(() => {
    (async () => {
      const idx = {};
      await Promise.all(REPORT_MANIFEST.map(async (m) => {
        const decisionTxt = await fetchText(`reports/${m.folder}/5_portfolio/decision.md`);
        const traderTxt   = await fetchText(`reports/${m.folder}/3_trading/trader.md`);
        const metaTxt     = await fetchText(`reports/${m.folder}/meta.json`);
        const decision = parseFieldedMarkdown(decisionTxt || "");
        const trader = parseFieldedMarkdown(traderTxt || "");
        const meta = metaTxt ? (() => { try { return JSON.parse(metaTxt); } catch(e) { return {}; } })() : {};
        const verdict = normalizeVerdict(decision.Rating, trader.__final);
        idx[m.folder] = {
          ticker: m.ticker, ts: m.ts, company: m.company, verdict,
          target: num(decision["Price Target"]),
          stop: num(trader["Stop Loss"]),
          current: meta.current_price ?? num(trader["Entry Price"]),
          horizon: decision["Time Horizon"],
          summary: firstSentenceShort(decision["Executive Summary"]),
          confidence: confidenceFromReport({ decision, trader, docs: {} }),
        };
      }));
      setReportsIndex(idx);
      setIndexLoading(false);
    })();
  }, []);

  // Load active full report when navigating to detail
  useEffect(() => {
    if (route.name !== "detail" || !route.folder) {
      setActiveReport(null);
      return;
    }
    setReportLoading(true);
    setActiveReport(null);
    (async () => {
      const r = await loadReport(route.folder);
      setActiveReport(r);
      setReportLoading(false);
    })();
  }, [route]);

  // === Render ===
  if (route.name === "detail") {
    if (reportLoading || !activeReport) return <FullScreenLoading label="Loading report…" />;
    // Find sibling runs of same ticker for the version switcher
    const ticker = route.folder.split("_")[0];
    const sameTicker = REPORT_MANIFEST.filter(m => m.ticker === ticker).map(m => ({
      ...m, verdict: reportsIndex[m.folder]?.verdict,
    }));
    return (
      <StoryView
        folder={route.folder}
        report={activeReport}
        allRuns={sameTicker}
        onBack={() => { window.location.hash = "/"; }} />
    );
  }

  if (indexLoading) return <FullScreenLoading label="Indexing reports…" />;

  return (
    <div style={{ minHeight: "100vh", background: COLORS.paper, padding: "32px 0", display: "flex", justifyContent: "center" }}>
      <div style={{ width: "100%", maxWidth: 1280 }}>
        <HubArtboard index={reportsIndex} onOpen={(folder) => { window.location.hash = `/r/${encodeURIComponent(folder)}`; }} />
      </div>
    </div>
  );
}

function FullScreenLoading({ label }) {
  return (
    <div style={{
      position: "fixed", inset: 0, display: "flex", alignItems: "center", justifyContent: "center",
      background: COLORS.paper, color: COLORS.muted,
      fontFamily: "Geist, system-ui, sans-serif", fontSize: 13,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{
          width: 12, height: 12, borderRadius: 6,
          border: `2px solid ${COLORS.rule}`, borderTopColor: COLORS.accent,
          animation: "spin 0.7s linear infinite",
        }} />
        {label}
      </div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

function firstSentenceShort(text) {
  if (!text) return null;
  const s = text.replace(/\*\*([^*]+)\*\*/g, "$1").replace(/[*_`]/g, "");
  const m = s.match(/^([^.!?]{20,200}[.!?])/);
  return m ? m[1].trim() : s.slice(0, 180).trim();
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
