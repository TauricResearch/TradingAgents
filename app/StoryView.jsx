// Production Story Detail view — the hardened V3 with all the features the user wanted:
//   * sticky stage rail on the left (jump 01→05)
//   * each agent card expands inline to reveal the full markdown
//   * search within the report
//   * floating "Ask the report" assistant (claude-powered)

const COMPANY_BY_TICKER = Object.fromEntries(REPORT_MANIFEST.map((m) => [m.ticker, m.company]));

function StoryView({ folder, report, onBack, allRuns = [] }) {
  const tweaks = React.useContext(window.TweaksContext);
  const verdict = normalizeVerdict(report.decision.Rating, report.trader.__final);
  const conf = confidenceFromReport(report);
  const current = report.meta?.current_price ?? num(report.trader["Entry Price"]);
  const stop = num(report.trader["Stop Loss"]);
  const target = num(report.decision["Price Target"]);
  const ticker = folder.split("_")[0];
  const company = COMPANY_BY_TICKER[ticker] || "";
  const horizon = report.decision["Time Horizon"] || "";
  const dateStr = folder.replace(/^[A-Z]+_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/, "$1-$2-$3 · $4:$5");

  const realBullWeight = parseFloat(report.research?.["Bull Weight"]);
  let bullWeight = !isNaN(realBullWeight)
    ? Math.max(0, Math.min(1, realBullWeight))
    : (verdict.kind === "BUY" ? 0.72 : verdict.kind === "SELL" ? 0.28 : 0.5);

  // Search state
  const [searchOpen, setSearchOpen] = React.useState(false);
  const [searchQ, setSearchQ] = React.useState("");

  // Active stage for sticky-rail highlight
  const [activeStage, setActiveStage] = React.useState("01");

  React.useEffect(() => {
    const onScroll = () => {
      const stages = ["01", "02", "03", "04", "05"];
      let current = "01";
      for (const s of stages) {
        const el = document.getElementById(`stage-${s}`);
        if (!el) continue;
        const top = el.getBoundingClientRect().top;
        if (top < 200) current = s;
      }
      setActiveStage(current);
    };
    const scroller = document.getElementById("story-scroller");
    if (scroller) scroller.addEventListener("scroll", onScroll);
    return () => scroller && scroller.removeEventListener("scroll", onScroll);
  }, []);

  const jumpTo = (id) => {
    const el = document.getElementById(id);
    const scroller = document.getElementById("story-scroller");
    if (el && scroller) {
      scroller.scrollTo({ top: el.offsetTop - 80, behavior: "smooth" });
    }
  };

  return (
    <div style={{
      position: "fixed", inset: 0, background: COLORS.paper,
      fontFamily: "Geist, system-ui, sans-serif", color: COLORS.ink,
      display: "flex", flexDirection: "column"
    }}>
      {/* Top chrome */}
      <div style={{
        height: 56, flexShrink: 0, padding: "0 24px",
        background: "white", borderBottom: `1px solid ${COLORS.rule}`,
        display: "flex", alignItems: "center", justifyContent: "space-between", gap: 18
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <button onClick={onBack} style={{
            display: "inline-flex", alignItems: "center", gap: 6,
            background: "transparent", border: "none", color: COLORS.ink2,
            fontSize: 13, cursor: "pointer", padding: "6px 8px", borderRadius: 6,
            fontFamily: "Geist, sans-serif"
          }}>← Hub</button>
          <span style={{ width: 1, height: 18, background: COLORS.rule }} />
          <div style={{
            fontSize: 18, fontWeight: 700, letterSpacing: -0.4,
            fontFamily: "Geist Mono, monospace"
          }}>{ticker}</div>
          <span style={{ fontSize: 12.5, color: COLORS.ink2 }}>{company}</span>
          <Pill kind={verdict.kind} size="md">{verdict.label}</Pill>
          <span style={{ fontSize: 11, color: COLORS.muted, fontFamily: "Geist Mono, monospace" }}>{dateStr}</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <button data-find-btn onClick={() => setSearchOpen(true)}
          style={{
            padding: "6px 12px 6px 30px", fontSize: 12, background: "white",
            border: `1px solid ${COLORS.rule}`, borderRadius: 7, color: COLORS.muted,
            cursor: "pointer", position: "relative", minWidth: 200, textAlign: "left",
            fontFamily: "Geist, sans-serif"
          }}>
            <span style={{ position: "absolute", left: 10, top: 6 }}>⌕</span>
            Find in report
            <span style={{ position: "absolute", right: 10, top: 6, color: COLORS.faint, fontSize: 10, fontFamily: "Geist Mono, monospace" }}>⌘F</span>
          </button>
          {allRuns.length > 1 && <RunSwitcher ticker={ticker} runs={allRuns} current={folder} />}
          <button style={{
            padding: "6px 12px", fontSize: 12, fontWeight: 500,
            background: "white", color: COLORS.ink2,
            border: `1px solid ${COLORS.rule}`, borderRadius: 7, cursor: "pointer",
            fontFamily: "Geist, sans-serif"
          }}>Share</button>
        </div>
      </div>

      {/* Body: rail + scrolling story */}
      <div style={{ flex: 1, minHeight: 0, display: "flex" }}>
        {/* Sticky stage rail */}
        <StageRail active={activeStage} onJump={jumpTo} />

        {/* Scrolling content */}
        <div id="story-scroller" style={{ flex: 1, overflow: "auto" }}>
          <StoryContent
            report={report} folder={folder} verdict={verdict} conf={conf}
            current={current} stop={stop} target={target}
            ticker={ticker} company={company} horizon={horizon}
            bullWeight={bullWeight}
            searchQ={searchQ} />
          
        </div>

        {/* Floating AI assistant */}
        <AskPanel report={report} ticker={ticker} verdict={verdict} />
      </div>

      {/* Search overlay */}
      {searchOpen &&
      <SearchOverlay
        q={searchQ} setQ={setSearchQ}
        onClose={() => {setSearchOpen(false);setSearchQ("");}} />
      }
    </div>);

}

// === Sticky stage rail ===
function StageRail({ active, onJump }) {
  const items = [
  { num: "01", label: "AI Agents" },
  { num: "02", label: "Bull vs Bear" },
  { num: "03", label: "Trader" },
  { num: "04", label: "Risk" },
  { num: "05", label: "Decision" }];

  return (
    <div style={{
      width: 72, flexShrink: 0, background: "white",
      borderRight: `1px solid ${COLORS.rule}`,
      padding: "20px 0",
      display: "flex", flexDirection: "column", alignItems: "center"
    }} data-comment-anchor="d86218ff2e-div-150-5">
      {/* Inner container so the connecting line is scoped to the items, not the full rail height */}
      <div style={{
        position: "relative",
        display: "flex", flexDirection: "column", alignItems: "center", gap: 4,
        width: "100%"
      }}>
        {/* Vertical line connecting numbers — sits behind the circles and stops at the last one */}
        <div style={{
          position: "absolute", left: "50%", top: 23, bottom: 35,
          width: 1, marginLeft: -0.5,
          background: COLORS.rule
        }} />
        {items.map((it, i) => {
        const isActive = active === it.num;
        return (
          <button key={it.num} onClick={() => onJump(`stage-${it.num}`)}
          style={{
            position: "relative", zIndex: 1,
            display: "flex", flexDirection: "column", alignItems: "center", gap: 4,
            padding: "10px 4px", width: "100%",
            background: "transparent", border: "none", cursor: "pointer",
            fontFamily: "Geist, sans-serif"
          }}>
            <div style={{
              width: 26, height: 26, borderRadius: 13,
              border: `1px solid ${isActive ? COLORS.ink : COLORS.rule}`,
              background: isActive ? COLORS.ink : "white",
              color: isActive ? "white" : COLORS.ink2,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 11, fontWeight: 600, fontFamily: "Geist Mono, monospace",
              transition: "all 120ms"
            }}>{it.num}</div>
            <div style={{
              fontSize: 9.5, color: isActive ? COLORS.ink : COLORS.muted,
              fontWeight: isActive ? 600 : 500, textAlign: "center", lineHeight: 1.1,
              maxWidth: 60
            }}>{it.label}</div>
          </button>);

      })}
      </div>
    </div>);

}

// === The actual scrolling content ===
function StoryContent({ report, folder, verdict, conf, current, stop, target, ticker, company, horizon, bullWeight, searchQ }) {
  const tweaks = React.useContext(window.TweaksContext);
  const [drawerKey, setDrawerKey] = React.useState(null);

  // Flat ordered list of all agents that can open in the drawer.
  // Keep in sync with the cards below so prev/next walks the same order.
  const agentList = React.useMemo(() => [
    { key: "1/market",       title: "Market Analyst",       role: "Technical analysis",     glyph: "📈", tone: null,   stage: "AI Agents",   text: report.docs["1_analysts"]?.market },
    { key: "1/sentiment",    title: "Sentiment Analyst",    role: "Social & Reddit",        glyph: "💬", tone: null,   stage: "AI Agents",   text: report.docs["1_analysts"]?.sentiment },
    { key: "1/news",         title: "News Analyst",         role: "Catalysts & events",     glyph: "📰", tone: null,   stage: "AI Agents",   text: report.docs["1_analysts"]?.news },
    { key: "1/fundamentals", title: "Fundamentals Analyst", role: "Financials & valuation", glyph: "📊", tone: null,   stage: "AI Agents",   text: report.docs["1_analysts"]?.fundamentals },
    { key: "2/bull",         title: "Bull Researcher",      role: "Argues for upside",      glyph: "↑",  tone: "buy",  stage: "Bull vs Bear",   text: report.docs["2_research"]?.bull },
    { key: "2/bear",         title: "Bear Researcher",      role: "Argues against",         glyph: "↓",  tone: "sell", stage: "Bull vs Bear",   text: report.docs["2_research"]?.bear },
    { key: "2/manager",      title: "Research Manager",     role: "Synthesizes both sides", glyph: "◆",  tone: null,   stage: "Bull vs Bear",   text: report.docs["2_research"]?.manager },
    { key: "4/aggressive",   title: "Aggressive Analyst",   role: "Pro-risk perspective",   glyph: "▲",  tone: "buy",  stage: "Risk Committee", text: report.docs["4_risk"]?.aggressive },
    { key: "4/neutral",      title: "Neutral Analyst",      role: "Balanced view",          glyph: "◆",  tone: "hold", stage: "Risk Committee", text: report.docs["4_risk"]?.neutral },
    { key: "4/conservative", title: "Conservative Analyst", role: "Capital protection",     glyph: "▼",  tone: "sell", stage: "Risk Committee", text: report.docs["4_risk"]?.conservative },
  ], [report]);

  const openDrawer = (key) => setDrawerKey(key);
  const closeDrawer = () => setDrawerKey(null);
  const currentIdx = agentList.findIndex(a => a.key === drawerKey);
  const prevAgent = currentIdx > 0 ? agentList[currentIdx - 1] : null;
  const nextAgent = currentIdx >= 0 && currentIdx < agentList.length - 1 ? agentList[currentIdx + 1] : null;

  // ESC to close
  React.useEffect(() => {
    if (!drawerKey) return;
    const onKey = (e) => { if (e.key === "Escape") closeDrawer(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawerKey]);

  return (
    <>
    <div style={{ paddingBottom: 80 }}>
      {/* Hero cover */}
      <Hero report={report} verdict={verdict} conf={conf}
      current={current} stop={stop} target={target}
      ticker={ticker} company={company} horizon={horizon}
      folder={folder} />

      <div style={{ padding: "48px 60px 0", maxWidth: 1080, margin: "0 auto" }}>
        {/* Intro */}
        <div style={{ marginBottom: 36 }}>
          <div style={{ fontSize: 11, color: COLORS.muted, textTransform: "uppercase", letterSpacing: 0.6, fontWeight: 600, marginBottom: 8 }}>
            How we got here
          </div>
          <h2 style={{ margin: 0, fontSize: 32, fontWeight: 700, letterSpacing: -0.8 }}>
            Twelve agents. One decision.
          </h2>
          <p style={{ fontSize: 15.5, color: COLORS.ink2, marginTop: 12, maxWidth: 720, lineHeight: 1.65 }}>
            Each run walks through five stages, with specialist agents handing off to the next.
            Click any agent card below to read their full report.
          </p>
        </div>

        {/* Bull/Bear weighting bar */}
        {tweaks.showBullBear && (
        <div style={{ marginBottom: 36, padding: 20, background: "white", borderRadius: 12, border: `1px solid ${COLORS.rule}` }}>
          <BullBearBar bull={bullWeight} height={32} />
          <div style={{ fontSize: 12, color: COLORS.muted, marginTop: 10, lineHeight: 1.5 }}>
            Estimated weight given to each side of the debate, inferred from the portfolio manager's synthesis.
          </div>
        </div>
        )}

        {/* Stage 1 */}
        <Stage id="stage-01" step="01" label="AI Agents"
        caption="Four specialists scan the market, news, sentiment, and fundamentals.">
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 14 }}>
            {[
            { id: "market", name: "Market Analyst", role: "Technical analysis", glyph: "📈", key: "1/market" },
            { id: "sentiment", name: "Sentiment Analyst", role: "Social & Reddit", glyph: "💬", key: "1/sentiment" },
            { id: "news", name: "News Analyst", role: "Catalysts & events", glyph: "📰", key: "1/news" },
            { id: "fundamentals", name: "Fundamentals Analyst", role: "Financials & valuation", glyph: "📊", key: "1/fundamentals" }].
            map((a) =>
            <ExpandableAgent key={a.id}
            title={a.name} role={a.role} glyph={a.glyph}
            text={report.docs["1_analysts"]?.[a.id]}
            agentKey={a.key} onOpenDrawer={openDrawer} />
            )}
          </div>
        </Stage>

        <FlowArrow />

        {/* Stage 2 */}
        <Stage id="stage-02" step="02" label="Bull vs Bear"
        caption="Two researchers argue both sides; a manager renders judgment.">
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 14 }}>
            <ExpandableAgent
              title="Bull Researcher" role="Argues for upside"
              tone="buy" glyph="↑"
              text={report.docs["2_research"]?.bull}
              agentKey="2/bull" onOpenDrawer={openDrawer} />
            <ExpandableAgent
              title="Bear Researcher" role="Argues against"
              tone="sell" glyph="↓"
              text={report.docs["2_research"]?.bear}
              agentKey="2/bear" onOpenDrawer={openDrawer} />
          </div>
          <ExpandableAgent
            title="Research Manager" role="Synthesizes both sides"
            accent={COLORS.accent} glyph="◆"
            text={report.docs["2_research"]?.manager}
            agentKey="2/manager" onOpenDrawer={openDrawer} />
        </Stage>

        <FlowArrow />

        {/* Stage 3 — Trader */}
        <Stage id="stage-03" step="03" label="Trader"
        caption="The trader turns research into a concrete execution plan.">
          <TraderCard report={report} verdict={verdict}
          current={current} stop={stop} target={target} />
        </Stage>

        <FlowArrow />

        {/* Stage 4 — Risk */}
        <Stage id="stage-04" step="04" label="Risk Committee"
        caption="Three analysts stress-test from different risk appetites.">
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
            <ExpandableAgent title="Aggressive" role="Pro-risk perspective"
            tone="buy" glyph="▲" text={report.docs["4_risk"]?.aggressive}
            agentKey="4/aggressive" onOpenDrawer={openDrawer} />
            <ExpandableAgent title="Neutral" role="Balanced view"
            tone="hold" glyph="◆" text={report.docs["4_risk"]?.neutral}
            agentKey="4/neutral" onOpenDrawer={openDrawer} />
            <ExpandableAgent title="Conservative" role="Capital protection"
            tone="sell" glyph="▼" text={report.docs["4_risk"]?.conservative}
            agentKey="4/conservative" onOpenDrawer={openDrawer} />
          </div>
        </Stage>

        <FlowArrow final />

        {/* Stage 5 — Decision */}
        <Stage id="stage-05" step="05" label="Portfolio Manager"
        caption="The final verdict and rationale.">
          <FinalDecision report={report} verdict={verdict} />
        </Stage>
      </div>
    </div>
    {drawerKey && (
      <AgentDrawer
        agent={agentList[currentIdx]}
        prev={prevAgent} next={nextAgent}
        onClose={closeDrawer}
        onNavigate={(k) => setDrawerKey(k)} />
    )}
    </>);

}

// === Hero cover ===
function Hero({ report, verdict, conf, current, stop, target, ticker, company, horizon, folder }) {
  const tweaks = React.useContext(window.TweaksContext);
  const c = verdictColor(verdict.kind);
  const verbMap = { BUY: "buy", SELL: "sell", HOLD: "hold" };
  return (
    <div style={{
      padding: tweaks.heroSize === "compact" ? "24px 60px 22px" : "44px 60px 36px",
      background: "white",
      borderBottom: `1px solid ${COLORS.rule}`,
      position: "relative", overflow: "hidden"
    }}>
      {/* Subtle accent shape */}
      <div style={{
        position: "absolute", right: -180, top: -180, width: 540, height: 540,
        background: c.bg, borderRadius: "50%", opacity: 0.5, pointerEvents: "none"
      }} />

      <div style={{ position: "relative", zIndex: 1, display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 40, alignItems: "start" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
            <span style={{ fontSize: 11, color: COLORS.muted, textTransform: "uppercase", letterSpacing: 0.6, fontWeight: 600 }}>Trading Analysis</span>
            <span style={{ width: 18, height: 1, background: COLORS.rule }} />
            <span style={{ fontSize: 11, color: COLORS.muted, fontFamily: "Geist Mono, monospace" }}>{folder}</span>
          </div>

          <h1 style={{
            margin: 0,
            fontSize: tweaks.heroSize === "compact" ? 52 : 84,
            fontWeight: 700,
            letterSpacing: tweaks.heroSize === "compact" ? -1.5 : -3,
            lineHeight: 0.95,
            fontFamily: "Geist, sans-serif"
          }}>{ticker}</h1>
          <div style={{ fontSize: 16, color: COLORS.muted, marginTop: 8, fontWeight: 500 }}>{company}</div>

          <div style={{
            fontSize: tweaks.heroSize === "compact" ? 18 : 26,
            color: COLORS.ink2, fontWeight: 500,
            letterSpacing: tweaks.heroSize === "compact" ? -0.3 : -0.6,
            marginTop: tweaks.heroSize === "compact" ? 16 : 28,
            lineHeight: 1.3
          }}>
            The case to{" "}
            <span style={{
              color: c.fg, background: c.bg,
              padding: "2px 12px", borderRadius: 8, fontWeight: 600
            }}>{verbMap[verdict.kind]}</span>
          </div>

          <p style={{
            maxWidth: 600,
            fontSize: tweaks.heroSize === "compact" ? 14 : 16,
            lineHeight: 1.65, color: COLORS.ink2,
            marginTop: tweaks.heroSize === "compact" ? 12 : 18,
            fontFamily: "Geist, sans-serif"
          }}>
            {firstSentence(report.decision["Executive Summary"]) || ""}
          </p>
        </div>

        <Card padding={22} style={{ background: "white", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
            <div style={{ fontSize: 11, color: COLORS.muted, textTransform: "uppercase", letterSpacing: 0.6, fontWeight: 600 }}>The Decision</div>
            <VerdictStamp kind={verdict.kind} label={verdict.label} size={52} />
          </div>
          <PriceScale current={current} stop={stop} target={target} />
          <div style={{ display: "grid", gridTemplateColumns: tweaks.showConfidence ? "1fr 1fr" : "1fr", gap: 12, marginTop: 18, paddingTop: 16, borderTop: `1px solid ${COLORS.rule2}` }}>
            <Stat label="Time Horizon" value={horizon.split(" ").slice(0, 2).join(" ") || "—"} mono={false} />
            {tweaks.showConfidence && <Stat label="Confidence" value={`${Math.round(conf * 100)}%`} align="right" />}
          </div>
        </Card>
      </div>
    </div>);

}

// === Stage wrapper ===
function Stage({ id, step, label, caption, children }) {
  return (
    <div id={id} style={{ scrollMarginTop: 80 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 16 }}>
        <span style={{
          fontFamily: "Geist Mono, monospace", fontSize: 13,
          color: "white", background: COLORS.ink, fontWeight: 600,
          padding: "4px 11px", borderRadius: 6, letterSpacing: 0.4
        }}>{step}</span>
        <div>
          <div style={{ fontSize: 22, fontWeight: 600, color: COLORS.ink, letterSpacing: -0.5 }}>{label}</div>
          <div style={{ fontSize: 13, color: COLORS.muted, marginTop: 2 }}>{caption}</div>
        </div>
      </div>
      {children}
    </div>);

}

function FlowArrow({ final = false }) {
  return (
    <div style={{
      height: 48, display: "flex", alignItems: "center", justifyContent: "center",
      margin: "8px 0"
    }}>
      <svg width="22" height="48" viewBox="0 0 22 48" fill="none">
        <path d="M 11 4 L 11 36" stroke={COLORS.rule} strokeWidth="1.5" strokeDasharray="3 3" />
        <path d="M 4 32 L 11 42 L 18 32" stroke={final ? COLORS.accent : COLORS.faint} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" fill="none" />
      </svg>
    </div>);

}

// === Agent Drawer — slides in from the right with the full markdown ===
function AgentDrawer({ agent, prev, next, onClose, onNavigate }) {
  // Subscribe to tweaks so the drawer re-renders when highlightMetrics etc. toggles.
  React.useContext(window.TweaksContext);
  if (!agent) return null;
  const col = agent.tone === "buy" ? COLORS.buy : agent.tone === "sell" ? COLORS.sell : agent.tone === "hold" ? COLORS.hold : null;
  const glyphBg = col?.bg || COLORS.accentBg;
  const glyphFg = col?.fg || COLORS.accent;
  const accentColor = col?.line || COLORS.accent;
  return (
    <>
      {/* Scrim */}
      <div onClick={onClose} style={{
        position: "fixed", inset: 0, background: "rgba(15, 17, 22, 0.32)",
        zIndex: 90, backdropFilter: "blur(2px)",
        animation: "fadeIn 180ms ease-out",
      }} />
      {/* Drawer */}
      <div style={{
        position: "fixed", top: 0, right: 0, bottom: 0, width: "min(720px, 92vw)",
        background: "white", zIndex: 91,
        display: "flex", flexDirection: "column",
        boxShadow: "-10px 0 40px rgba(0,0,0,0.10)",
        animation: "slideInRight 240ms cubic-bezier(0.2, 0.8, 0.2, 1)",
      }}>
        {/* Drawer header */}
        <div style={{
          padding: "16px 24px",
          borderBottom: `1px solid ${COLORS.rule}`,
          display: "flex", alignItems: "center", justifyContent: "space-between", gap: 14,
          flexShrink: 0,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
            <span style={{
              width: 36, height: 36, borderRadius: 18,
              background: glyphBg, color: glyphFg,
              display: "inline-flex", alignItems: "center", justifyContent: "center",
              fontSize: 16, fontWeight: 700, flexShrink: 0,
            }}>{agent.glyph}</span>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 10, color: COLORS.muted, textTransform: "uppercase", letterSpacing: 0.6, fontWeight: 600 }}>{agent.stage}</div>
              <div style={{ fontSize: 15, fontWeight: 600, color: COLORS.ink, letterSpacing: -0.2 }}>{agent.title}</div>
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <button onClick={() => prev && onNavigate(prev.key)} disabled={!prev}
              title={prev ? `← ${prev.title}` : ""}
              style={drawerNavBtn(!!prev)}>‹</button>
            <button onClick={() => next && onNavigate(next.key)} disabled={!next}
              title={next ? `${next.title} →` : ""}
              style={drawerNavBtn(!!next)}>›</button>
            <div style={{ width: 1, height: 20, background: COLORS.rule, margin: "0 4px" }} />
            <button onClick={onClose} title="Close (Esc)" style={drawerNavBtn(true)}>×</button>
          </div>
        </div>

        {/* Drawer body */}
        <div style={{
          flex: 1, overflow: "auto",
          padding: "24px 40px 60px",
          borderTop: `3px solid ${accentColor}`,
          background: COLORS.paper,
        }}>
          <div className="md prose"
            style={{ fontSize: 14, lineHeight: 1.7, color: COLORS.ink2, maxWidth: 680 }}
            dangerouslySetInnerHTML={{ __html: highlightMD(agent.text || "") }} />
        </div>

        {/* Drawer footer — quick jump to other agents */}
        <div style={{
          padding: "12px 18px",
          borderTop: `1px solid ${COLORS.rule}`,
          display: "flex", alignItems: "center", justifyContent: "space-between",
          background: "white", flexShrink: 0, gap: 12,
        }}>
          {prev ? (
            <button onClick={() => onNavigate(prev.key)} style={drawerFooterBtn}>
              <div style={{ fontSize: 10, color: COLORS.muted, textTransform: "uppercase", letterSpacing: 0.5 }}>← Previous</div>
              <div style={{ fontSize: 13, fontWeight: 500, color: COLORS.ink2 }}>{prev.title}</div>
            </button>
          ) : <div />}
          {next ? (
            <button onClick={() => onNavigate(next.key)} style={{ ...drawerFooterBtn, textAlign: "right" }}>
              <div style={{ fontSize: 10, color: COLORS.muted, textTransform: "uppercase", letterSpacing: 0.5 }}>Next →</div>
              <div style={{ fontSize: 13, fontWeight: 500, color: COLORS.ink2 }}>{next.title}</div>
            </button>
          ) : <div />}
        </div>
      </div>
      <style>{`
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes slideInRight { from { transform: translateX(20px); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
      `}</style>
    </>
  );
}

function drawerNavBtn(enabled) {
  return {
    width: 30, height: 30, borderRadius: 7,
    border: `1px solid ${COLORS.rule}`,
    background: "white", color: enabled ? COLORS.ink2 : COLORS.faint,
    cursor: enabled ? "pointer" : "not-allowed",
    display: "inline-flex", alignItems: "center", justifyContent: "center",
    fontSize: 16, lineHeight: 1, fontFamily: "Geist, sans-serif",
    opacity: enabled ? 1 : 0.5,
  };
}

const drawerFooterBtn = {
  background: "transparent", border: "none", cursor: "pointer",
  padding: "6px 8px", textAlign: "left", fontFamily: "Geist, sans-serif",
  display: "flex", flexDirection: "column", gap: 2,
  minWidth: 0, maxWidth: "48%",
};

// === Expandable agent card ===
function ExpandableAgent({ title, role, glyph, tone, accent, text, agentKey, onOpenDrawer }) {
  const tweaks = React.useContext(window.TweaksContext);
  const col = tone === "buy" ? COLORS.buy : tone === "sell" ? COLORS.sell : tone === "hold" ? COLORS.hold : null;
  const accentColor = accent || col?.line || COLORS.faint;
  const glyphBg = col?.bg || COLORS.accentBg;
  const glyphFg = col?.fg || tweaks.accent;

  const takeaway = extractTakeawayProd(text);
  const finalTransaction = text?.match(/FINAL TRANSACTION PROPOSAL:\s*\*\*([A-Z]+)\*\*/)?.[1];

  return (
    <div style={{
      background: "white", border: `1px solid ${COLORS.rule}`, borderRadius: 12,
      borderLeft: `3px solid ${accentColor}`,
      overflow: "hidden", transition: "border-color 150ms",
      display: "flex", flexDirection: "column", height: "100%"
    }}>
      <div style={{ padding: 18, display: "flex", flexDirection: "column", flex: 1 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, flex: 1, minWidth: 0 }}>
            <span style={{
              width: 32, height: 32, borderRadius: 16,
              background: glyphBg, color: glyphFg,
              display: "inline-flex", alignItems: "center", justifyContent: "center",
              fontSize: 15, fontWeight: 700, flexShrink: 0
            }}>{glyph}</span>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: COLORS.ink }}>{title}</div>
              {role && <div style={{ fontSize: 11, color: COLORS.muted, marginTop: 1 }}>{role}</div>}
            </div>
          </div>
          {finalTransaction &&
          <Pill kind={finalTransaction === "BUY" ? "BUY" : finalTransaction === "SELL" ? "SELL" : "HOLD"} size="sm">
              {finalTransaction.charAt(0) + finalTransaction.slice(1).toLowerCase()}
            </Pill>
          }
        </div>
        <div style={{
          fontSize: 13, color: COLORS.ink2, lineHeight: 1.55, marginBottom: 12,
          flex: 1,
          display: "-webkit-box", WebkitBoxOrient: "vertical", WebkitLineClamp: 5,
          overflow: "hidden", textOverflow: "ellipsis"
        }}>
          {takeaway || "—"}
        </div>
        {text && onOpenDrawer &&
        <button onClick={() => onOpenDrawer(agentKey)}
        style={{
          fontSize: 12, fontWeight: 500, color: tweaks.accent,
          background: "transparent", border: "none", cursor: "pointer",
          padding: 0, fontFamily: "Geist, sans-serif",
          display: "inline-flex", alignItems: "center", gap: 4,
          alignSelf: "flex-start"
        }}>
            Read full report
            <span>→</span>
          </button>
        }
      </div>
    </div>);

}

// === Trader card ===
function TraderCard({ report, verdict, current, stop, target }) {
  const [open, setOpen] = React.useState(false);
  const c = verdictColor(verdict.kind);
  return (
    <div style={{ background: "white", border: `1px solid ${COLORS.rule}`, borderLeft: `3px solid ${c.line}`, borderRadius: 12, overflow: "hidden" }}>
      <div style={{ padding: 22 }}>
        <div style={{ display: "grid", gridTemplateColumns: "240px 1fr", gap: 22 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
              <span style={{
                width: 32, height: 32, borderRadius: 16,
                background: c.bg, color: c.fg,
                display: "inline-flex", alignItems: "center", justifyContent: "center",
                fontSize: 15, fontWeight: 700
              }}>T</span>
              <div>
                <div style={{ fontSize: 14, fontWeight: 600 }}>Trader</div>
                <div style={{ fontSize: 11, color: COLORS.muted }}>Stage 3 · execution plan</div>
              </div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              <MiniStat label="Action" value={report.trader["Action"] || verdict.label} color={c.fg} />
              <MiniStat label="Entry" value={current ? `$${current.toFixed(0)}` : "—"} />
              <MiniStat label="Stop" value={stop ? `$${stop.toFixed(0)}` : "—"} color={COLORS.sell.fg} />
              <MiniStat label="Target" value={target ? `$${target.toFixed(0)}` : "—"}
              color={target && current && target > current ? COLORS.buy.fg : COLORS.sell.fg} />
            </div>
          </div>
          <div style={{ borderLeft: `1px solid ${COLORS.rule}`, paddingLeft: 22 }}>
            <div style={{ fontSize: 11, color: COLORS.muted, textTransform: "uppercase", letterSpacing: 0.5, fontWeight: 600, marginBottom: 6 }}>Reasoning</div>
            <div style={{ fontSize: 14, color: COLORS.ink2, lineHeight: 1.6 }}>
              {firstSentence(report.trader["Reasoning"]) || "—"}
            </div>
            {report.trader["Position Sizing"] &&
            <>
                <div style={{ fontSize: 11, color: COLORS.muted, textTransform: "uppercase", letterSpacing: 0.5, fontWeight: 600, marginTop: 14, marginBottom: 6 }}>Position Sizing</div>
                <div style={{ fontSize: 13, color: COLORS.ink2, lineHeight: 1.55 }}>{firstSentence(report.trader["Position Sizing"])}</div>
              </>
            }
            <button onClick={() => setOpen(!open)}
            style={{
              fontSize: 12, fontWeight: 500, color: COLORS.accent,
              background: "transparent", border: "none", cursor: "pointer",
              padding: 0, marginTop: 14, fontFamily: "Geist, sans-serif",
              display: "inline-flex", alignItems: "center", gap: 4
            }}>
              {open ? "Hide full plan" : "Read full plan"}
              <span style={{ transform: open ? "rotate(90deg)" : "none", transition: "transform 120ms" }}>›</span>
            </button>
          </div>
        </div>
      </div>
      {open &&
      <div style={{ padding: "18px 22px 22px", borderTop: `1px solid ${COLORS.rule2}`, background: COLORS.paper }}>
          <div className="md prose"
        style={{ fontSize: 13.5, lineHeight: 1.65, color: COLORS.ink2 }}
        dangerouslySetInnerHTML={{ __html: highlightMD(report.docs["3_trading"]?.trader || "") }} />
        </div>
      }
    </div>);

}

// === Final decision ===
function FinalDecision({ report, verdict }) {
  const [openThesis, setOpenThesis] = React.useState(false);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <Card padding={26} style={{ background: "white" }}>
        <div style={{ display: "flex", alignItems: "flex-start", gap: 24, marginBottom: 18 }}>
          <VerdictStamp kind={verdict.kind} label={verdict.label} size={80} />
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 11, color: COLORS.muted, textTransform: "uppercase", letterSpacing: 0.6, fontWeight: 600, marginBottom: 8 }}>Executive Summary</div>
            <div style={{ fontSize: 15, color: COLORS.ink2, lineHeight: 1.65 }}
            dangerouslySetInnerHTML={{ __html: highlightInline(report.decision["Executive Summary"] || "—") }} />
          </div>
        </div>
        <button onClick={() => setOpenThesis(!openThesis)}
        style={{
          padding: "10px 18px", fontSize: 13, fontWeight: 500,
          background: openThesis ? COLORS.ink : "white",
          color: openThesis ? "white" : COLORS.ink2,
          border: `1px solid ${openThesis ? COLORS.ink : COLORS.rule}`,
          borderRadius: 8, cursor: "pointer", fontFamily: "Geist, sans-serif"
        }}>
          {openThesis ? "Hide" : "Read"} full investment thesis →
        </button>
      </Card>
      {openThesis &&
      <Card padding={26} style={{ background: "white" }}>
          <div style={{ fontSize: 11, color: COLORS.muted, textTransform: "uppercase", letterSpacing: 0.6, fontWeight: 600, marginBottom: 12 }}>Investment Thesis</div>
          <div className="md prose"
        style={{ fontSize: 14.5, lineHeight: 1.7, color: COLORS.ink2 }}
        dangerouslySetInnerHTML={{ __html: highlightInline(report.decision["Investment Thesis"] || "") }} />
        </Card>
      }
    </div>);

}

// === Run switcher (only shown when ticker has multiple runs) ===
function RunSwitcher({ ticker, runs, current }) {
  const [open, setOpen] = React.useState(false);
  return (
    <div style={{ position: "relative" }}>
      <button onClick={() => setOpen(!open)}
      style={{
        padding: "6px 12px", fontSize: 12, fontWeight: 500,
        background: "white", color: COLORS.ink2,
        border: `1px solid ${COLORS.rule}`, borderRadius: 7, cursor: "pointer",
        fontFamily: "Geist, sans-serif"
      }}>
        {runs.length} runs ▾
      </button>
      {open &&
      <div style={{
        position: "absolute", top: "calc(100% + 6px)", right: 0, width: 280, zIndex: 10,
        background: "white", border: `1px solid ${COLORS.rule}`, borderRadius: 10,
        boxShadow: "0 6px 18px rgba(0,0,0,0.08)", overflow: "hidden"
      }}>
          {runs.map((r) =>
        <a key={r.folder} href={`#/r/${r.folder}`} onClick={() => setOpen(false)} style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "10px 14px", textDecoration: "none",
          background: r.folder === current ? COLORS.accentBg : "white",
          borderBottom: `1px solid ${COLORS.rule2}`
        }}>
              <span style={{ fontSize: 12, color: COLORS.ink2, fontFamily: "Geist Mono, monospace" }}>{r.ts}</span>
              {r.verdict && <Pill kind={r.verdict.kind} size="sm">{r.verdict.label}</Pill>}
            </a>
        )}
        </div>
      }
    </div>);

}

// === Search overlay ===
function SearchOverlay({ q, setQ, onClose }) {
  React.useEffect(() => {
    const onKey = (e) => {if (e.key === "Escape") onClose();};
    window.addEventListener("keydown", onKey);
    // Highlight in DOM
    const scroller = document.getElementById("story-scroller");
    if (scroller && q && q.length >= 2) {
      highlightMatches(scroller, q);
    } else if (scroller) {
      clearHighlights(scroller);
    }
    return () => {
      window.removeEventListener("keydown", onKey);
      const s = document.getElementById("story-scroller");
      if (s) clearHighlights(s);
    };
  }, [q]);

  return (
    <div style={{
      position: "fixed", top: 20, left: "50%", transform: "translateX(-50%)",
      background: "white", border: `1px solid ${COLORS.rule}`, borderRadius: 12,
      boxShadow: "0 10px 30px rgba(0,0,0,0.12)", zIndex: 100,
      padding: "10px 14px", display: "flex", alignItems: "center", gap: 10,
      minWidth: 480
    }}>
      <span style={{ color: COLORS.muted }}>⌕</span>
      <input
        autoFocus value={q} onChange={(e) => setQ(e.target.value)}
        placeholder="Find in report…"
        style={{
          flex: 1, border: "none", outline: "none", fontSize: 14,
          fontFamily: "Geist, sans-serif", color: COLORS.ink
        }} />
      <span style={{ fontSize: 11, color: COLORS.faint, fontFamily: "Geist Mono, monospace" }}>esc</span>
      <button onClick={onClose} style={{
        background: "transparent", border: "none", cursor: "pointer",
        color: COLORS.muted, fontSize: 16, padding: 0
      }}>×</button>
    </div>);

}

function highlightMatches(root, q) {
  clearHighlights(root);
  if (!q) return;
  const re = new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: (n) => {
      if (!n.nodeValue || !n.nodeValue.match(re)) return NodeFilter.FILTER_REJECT;
      if (n.parentElement?.closest("script,style,input,textarea")) return NodeFilter.FILTER_REJECT;
      if (n.parentElement?.classList.contains("__search-hit")) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    }
  });
  const nodes = [];
  let n;while (n = walker.nextNode()) nodes.push(n);
  let firstHit = null;
  nodes.forEach((textNode) => {
    const parts = textNode.nodeValue.split(re);
    const matches = textNode.nodeValue.match(re);
    if (!matches) return;
    const frag = document.createDocumentFragment();
    parts.forEach((part, i) => {
      frag.appendChild(document.createTextNode(part));
      if (i < matches.length) {
        const span = document.createElement("span");
        span.className = "__search-hit";
        span.style.background = "oklch(0.92 0.18 90)";
        span.style.color = "oklch(0.25 0.10 75)";
        span.style.borderRadius = "3px";
        span.style.padding = "0 2px";
        span.textContent = matches[i];
        if (!firstHit) firstHit = span;
        frag.appendChild(span);
      }
    });
    textNode.parentNode.replaceChild(frag, textNode);
  });
  if (firstHit) firstHit.scrollIntoView({ block: "center", behavior: "smooth" });
}

function clearHighlights(root) {
  root.querySelectorAll(".__search-hit").forEach((el) => {
    const parent = el.parentNode;
    parent.replaceChild(document.createTextNode(el.textContent), el);
    parent.normalize();
  });
}

// === Ask the report panel ===
function AskPanel({ report, ticker, verdict }) {
  const [open, setOpen] = React.useState(false);
  const [history, setHistory] = React.useState([]);
  const [q, setQ] = React.useState("");
  const [pending, setPending] = React.useState(false);

  const suggested = [
  `Why ${verdict.kind.toLowerCase()}?`,
  "What's the biggest risk?",
  "What would change the verdict?"];


  const ask = async (question) => {
    if (!question?.trim()) return;
    const userMsg = { role: "user", content: question };
    setHistory((h) => [...h, userMsg]);
    setQ("");
    setPending(true);

    // Build context — keep it tight so we don't blow the token budget
    const ctx = [
    `Ticker: ${ticker}`,
    `Verdict: ${verdict.label} (${verdict.kind})`,
    `--- EXECUTIVE SUMMARY ---`,
    report.decision["Executive Summary"] || "",
    `--- INVESTMENT THESIS ---`,
    (report.decision["Investment Thesis"] || "").slice(0, 4000),
    `--- TRADER PLAN ---`,
    `Action: ${report.trader["Action"]}, Entry: ${report.trader["Entry Price"]}, Stop: ${report.trader["Stop Loss"]}`,
    `Reasoning: ${(report.trader["Reasoning"] || "").slice(0, 1500)}`].
    join("\n\n");

    const prompt = `You are a financial analyst reading a multi-agent trading research report. Answer the user's question using ONLY the report excerpt below. Be concise (3-4 sentences). If the report doesn't address it, say so.

REPORT EXCERPT:
${ctx}

USER QUESTION: ${question}`;

    try {
      const answer = await window.claude.complete(prompt);
      setHistory((h) => [...h, { role: "assistant", content: answer }]);
    } catch (e) {
      setHistory((h) => [...h, { role: "assistant", content: "Couldn't reach the model. Try again?" }]);
    }
    setPending(false);
  };

  if (!open) {
    return (
      <button onClick={() => setOpen(true)}
      style={{
        position: "fixed", bottom: 24, right: 24, zIndex: 50,
        padding: "12px 18px", background: COLORS.ink, color: "white",
        border: "none", borderRadius: 999, cursor: "pointer",
        fontSize: 13, fontWeight: 500, fontFamily: "Geist, sans-serif",
        display: "flex", alignItems: "center", gap: 8,
        boxShadow: "0 4px 14px rgba(0,0,0,0.16)"
      }}>
        <span style={{ fontSize: 14 }}>✦</span> Ask the report
      </button>);

  }

  return (
    <div style={{
      position: "fixed", bottom: 24, right: 24, width: 380, zIndex: 50,
      background: "white", border: `1px solid ${COLORS.rule}`, borderRadius: 14,
      boxShadow: "0 8px 32px rgba(0,0,0,0.12)",
      display: "flex", flexDirection: "column", maxHeight: "70vh"
    }}>
      <div style={{
        padding: "14px 16px", borderBottom: `1px solid ${COLORS.rule2}`,
        display: "flex", alignItems: "center", justifyContent: "space-between"
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ color: COLORS.accent }}>✦</span>
          <span style={{ fontSize: 13, fontWeight: 600 }}>Ask the report</span>
        </div>
        <button onClick={() => setOpen(false)} style={{ background: "transparent", border: "none", cursor: "pointer", color: COLORS.muted, fontSize: 18, padding: 0, lineHeight: 1 }}>×</button>
      </div>
      <div style={{ padding: 14, overflow: "auto", flex: 1, display: "flex", flexDirection: "column", gap: 10 }}>
        {history.length === 0 &&
        <>
            <div style={{ fontSize: 12, color: COLORS.muted, lineHeight: 1.5, marginBottom: 6 }}>
              Ask anything about the analysis. Try one of these:
            </div>
            {suggested.map((s) =>
          <button key={s} onClick={() => ask(s)} style={{
            padding: "8px 12px", textAlign: "left", fontSize: 12.5,
            background: COLORS.paper, color: COLORS.ink2,
            border: `1px solid ${COLORS.rule}`, borderRadius: 8, cursor: "pointer",
            fontFamily: "Geist, sans-serif"
          }}>{s}</button>
          )}
          </>
        }
        {history.map((m, i) =>
        <div key={i} style={{
          padding: "10px 12px", borderRadius: 8, maxWidth: "92%",
          background: m.role === "user" ? COLORS.ink : COLORS.paper,
          color: m.role === "user" ? "white" : COLORS.ink2,
          alignSelf: m.role === "user" ? "flex-end" : "flex-start",
          fontSize: 13, lineHeight: 1.55,
          border: m.role === "user" ? "none" : `1px solid ${COLORS.rule}`
        }}>{m.content}</div>
        )}
        {pending &&
        <div style={{ fontSize: 12, color: COLORS.muted, fontStyle: "italic", padding: "4px 6px" }}>Thinking…</div>
        }
      </div>
      <form onSubmit={(e) => {e.preventDefault();ask(q);}}
      style={{ padding: 12, borderTop: `1px solid ${COLORS.rule2}`, display: "flex", gap: 8 }}>
        <input
          value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask anything…"
          style={{
            flex: 1, padding: "8px 12px", fontSize: 13,
            border: `1px solid ${COLORS.rule}`, borderRadius: 8, outline: "none",
            fontFamily: "Geist, sans-serif"
          }} />
        <button type="submit" disabled={pending || !q.trim()} style={{
          padding: "8px 14px", fontSize: 13, fontWeight: 500,
          background: COLORS.ink, color: "white",
          border: "none", borderRadius: 8, cursor: pending || !q.trim() ? "not-allowed" : "pointer",
          opacity: pending || !q.trim() ? 0.5 : 1,
          fontFamily: "Geist, sans-serif"
        }}>Ask</button>
      </form>
    </div>);

}

// === Utilities ===
function firstSentence(text) {
  if (!text) return null;
  const stripped = text.replace(/\*\*([^*]+)\*\*/g, "$1").replace(/[*_`]/g, "");
  const m = stripped.match(/^([^.!?]{20,300}[.!?])/);
  return m ? m[1].trim() : stripped.slice(0, 240).trim();
}

function MiniStat({ label, value, color }) {
  return (
    <div style={{ padding: "10px 12px", background: COLORS.rule2, borderRadius: 8 }}>
      <div style={{ fontSize: 10, color: COLORS.muted, textTransform: "uppercase", letterSpacing: 0.5, fontWeight: 500 }}>{label}</div>
      <div style={{
        fontSize: 16, fontWeight: 600, color: color || COLORS.ink,
        fontFamily: "Geist Mono, monospace", marginTop: 2, lineHeight: 1.1
      }}>{value}</div>
    </div>);

}

function highlightMD(text) {
  if (!text) return "";
  const html = window.marked.parse(text);
  if (window.__noHighlightMetrics) return html;
  return html.replace(
    /(\$\d[\d.,]*[BMK]?|\b\d+(?:\.\d+)?%|\b\d+(?:\.\d+)?x\b|\b\d{1,3}(?:,\d{3})+\b)/g,
    (m) => `<mark class="metric">${m}</mark>`
  );
}

function extractTakeawayProd(text) {
  if (!text) return null;
  // Normalize: drop CRLF + strip bold/italic markers from headings so they don't break the section regex
  const norm = text
    .replace(/\r\n/g, "\n")
    .replace(/^(#{1,6}\s*)\*+([\s\S]*?)\*+\s*$/gm, "$1$2");

  // 1. Look for an "Executive Summary" or "Overall …" / "Bottom Line" section
  //    and pull the first paragraph after it.
  const sectionRe = /(?:^|\n)#{1,6}\s*(?:\d+\.\s*)?(?:executive\s+summary|overall\s+[a-z\s]+|summary|key\s+takeaway[s]?|top[\s-]?line|conclusion|bottom\s+line|tl;?dr)\b[^\n]*\n+([\s\S]*?)(?:\n#{1,6}\s|\n---|\Z)/i;
  const m = norm.match(sectionRe);
  if (m && m[1]) {
    const para = firstParagraph(m[1]);
    if (para) return trimToSentences(para, 3, 480);
  }

  // 2. "**Field:** value" at the top of the doc (sentiment uses **Direction:** etc.)
  const bold = norm.match(/^\s*\*\*([^*\n]{3,40})\*\*:?\s*\*?\*?([^*\n]{20,300})\*?\*?/m);
  if (bold) {
    const phrase = `${bold[1].trim()}: ${bold[2].trim().replace(/[*_]/g, "")}`;
    if (phrase.length > 40) return phrase;
  }

  // 3. First substantive paragraph (skip headings, lists, blockquotes)
  const blocks = norm
    .replace(/^#.*$/gm, "")
    .replace(/^---+$/gm, "")
    .split(/\n\s*\n/)
    .map(b => b.trim().replace(/\*\*([^*]+)\*\*/g, "$1").replace(/[*_`]/g, ""))
    .filter(b => b && b.length > 60 && !b.match(/^[-•|>]/) && !b.match(/^\d+\./));
  if (blocks[0]) return trimToSentences(blocks[0], 3, 480);

  // 4. Ultimate fallback
  const firstLine = norm.split("\n").map(l => l.trim()).find(l => l && !l.startsWith("#"));
  return firstLine ? firstLine.slice(0, 260) : null;
}

function firstParagraph(text) {
  return text
    .split(/\n\s*\n/)
    .map(b => b.trim().replace(/\*\*([^*]+)\*\*/g, "$1").replace(/[*_`]/g, ""))
    .find(b => b && b.length > 30 && !b.match(/^[-•|>]/) && !b.match(/^\d+\./));
}

function trimToSentences(text, maxSentences, maxChars) {
  const sentences = text.match(/[^.!?]+[.!?]+/g) || [text];
  let out = "";
  for (let i = 0; i < sentences.length && i < maxSentences; i++) {
    if ((out + sentences[i]).length > maxChars) break;
    out += sentences[i];
  }
  return out.trim() || text.slice(0, maxChars);
}

function highlightInline(text) {
  if (!text) return "";
  const html = window.marked.parseInline(text);
  if (window.__noHighlightMetrics) return html;
  return html.replace(
    /(\$\d[\d.,]*[BMK]?|\b\d+(?:\.\d+)?%|\b\d+(?:\.\d+)?x\b|\b\d{1,3}(?:,\d{3})+\b)/g,
    (m) => `<mark class="metric">${m}</mark>`
  );
}

Object.assign(window, { StoryView });