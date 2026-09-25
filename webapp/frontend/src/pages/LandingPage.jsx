import { useApp } from "../context/AppContext";
import { Reveal } from "../components/Reveal";

const STEPS = [
  {
    num: "01",
    title: "Analysts read the tape",
    body: "Fundamentals, sentiment, news and technicals — four analysts build the evidence base for a ticker, independently.",
  },
  {
    num: "02",
    title: "Bull and bear researchers argue",
    body: "A structured debate stress-tests the case in both directions before anyone commits to a position.",
  },
  {
    num: "03",
    title: "A trader proposes a call",
    body: "Timing and sizing get weighed against the debate, not just the raw analyst output.",
  },
  {
    num: "04",
    title: "Risk management stamps it",
    body: "A final risk pass approves, adjusts or rejects the call — what prints is what survived scrutiny.",
  },
];

const FEATURES = [
  {
    icon: PrintIcon,
    title: "A real verdict, not a wall of text",
    body: "BUY, SELL or HOLD prints like an actual market ticket — ticker id and timestamp — with the full report underneath it.",
  },
  {
    icon: ChartIcon,
    title: "Free live price chart",
    body: "See price action for any ticker the moment you type it — no LLM cost, no quota spent, before you run anything.",
  },
  {
    icon: BoltIcon,
    title: "Instant on popular tickers",
    body: "A completed call is reused across everyone for a while. Ask for a hot ticker right after someone else and get it instantly, free.",
  },
  {
    icon: BookmarkIcon,
    title: "Watchlist",
    body: "Save the tickers you check often. One click from there straight into a fresh analysis.",
  },
  {
    icon: ClockIcon,
    title: "Full history, filterable",
    body: "Every call you've ever run, searchable by ticker or status — not just the last handful.",
  },
  {
    icon: KeyIcon,
    title: "Key rotation, self-service",
    body: "Think your API key leaked? Rotate it yourself from Profile — the old one stops working immediately.",
  },
];

export function LandingPage() {
  const { openAuthModal } = useApp();

  return (
    <>
      <section className="hero">
        <div className="hero__copy">
          <p className="hero__eyebrow">multi-agent equity research</p>
          <h1 className="hero__headline">
            Agents debate the ticker.
            <br />
            You get the print.
          </h1>
          <p className="hero__sub">
            Analyst, researcher, trader and risk agents work a stock the way a real desk would —
            then stamp a BUY, SELL or HOLD call with the full case behind it. Free tier, no card.
          </p>
          <div className="hero__actions">
            <button type="button" className="btn btn--primary btn--lg" onClick={() => openAuthModal("signup")}>
              Get started free
            </button>
            <button type="button" className="btn btn--lg" onClick={() => openAuthModal("signin")}>
              Sign in
            </button>
          </div>
          <p className="hero__disclaimer">Research output only. Not financial advice.</p>
          <div className="hero__trust">
            <span className="hero__trust-item">
              <CheckDotIcon /> Free tier, no card
            </span>
            <span className="hero__trust-item">
              <CheckDotIcon /> 4-agent debate per call
            </span>
            <span className="hero__trust-item">
              <CheckDotIcon /> Key rotation, self-service
            </span>
          </div>
        </div>

        <div className="hero__visual" aria-hidden="true">
          <div className="hero__grid-texture" />

          <div className="hero__chip hero__chip--agents">
            <div className="hero__chip-avatars">
              <span style={{ background: "var(--brand)" }}>A</span>
              <span style={{ background: "var(--buy)" }}>R</span>
              <span style={{ background: "var(--hold)" }}>T</span>
              <span style={{ background: "var(--sell)" }}>K</span>
            </div>
            <div>
              <strong>4 agents</strong>
              <span>debating NVDA…</span>
            </div>
          </div>

          <div className="hero__mockup">
            <div className="hero__mockup-bar">
              <span />
              <span />
              <span />
            </div>
            <div className="hero__mockup-body">
              <div className="hero__mockup-chart">
                <svg viewBox="0 0 100 32" preserveAspectRatio="none">
                  <defs>
                    <linearGradient id="heroChartFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="var(--buy)" stopOpacity="0.28" />
                      <stop offset="100%" stopColor="var(--buy)" stopOpacity="0" />
                    </linearGradient>
                  </defs>
                  <path
                    d="M0,26 L6,24 L12,25 L18,20 L24,21 L30,16 L36,18 L42,13 L48,15 L54,10 L60,12 L66,7 L72,9 L78,5 L84,7 L90,3 L100,4 L100,32 L0,32 Z"
                    fill="url(#heroChartFill)"
                  />
                  <path
                    d="M0,26 L6,24 L12,25 L18,20 L24,21 L30,16 L36,18 L42,13 L48,15 L54,10 L60,12 L66,7 L72,9 L78,5 L84,7 L90,3 L100,4"
                    fill="none"
                  />
                </svg>
              </div>
              <div className="hero__mockup-stamp">BUY</div>
              <div className="hero__mockup-lines">
                <span />
                <span style={{ width: "70%" }} />
                <span style={{ width: "85%" }} />
              </div>
            </div>
          </div>

          <div className="hero__chip hero__chip--watchlist">
            <BookmarkIcon small />
            <span>Added to watchlist</span>
          </div>

          <div className="hero__blob hero__blob--one" />
          <div className="hero__blob hero__blob--two" />
        </div>
      </section>

      <section id="how-it-works" className="section">
        <Reveal as="div" className="section__head">
          <p className="section__eyebrow">how it works</p>
          <h2 className="section__title">Four agents, one accountable call</h2>
        </Reveal>
        <div className="steps">
          {STEPS.map((step, i) => (
            <Reveal as="div" key={step.num} delay={i * 90} className="step-card">
              <span className="step-card__num">{step.num}</span>
              <h3 className="step-card__title">{step.title}</h3>
              <p className="step-card__body">{step.body}</p>
            </Reveal>
          ))}
        </div>
      </section>

      <section id="features" className="section section--sunken">
        <Reveal as="div" className="section__head">
          <p className="section__eyebrow">features</p>
          <h2 className="section__title">Built like a desk, not a demo</h2>
        </Reveal>
        <div className="feature-grid">
          {FEATURES.map((feature, i) => (
            <Reveal as="div" key={feature.title} delay={i * 70} className="feature-card">
              <feature.icon />
              <h3 className="feature-card__title">{feature.title}</h3>
              <p className="feature-card__body">{feature.body}</p>
            </Reveal>
          ))}
        </div>
      </section>

      <Reveal as="section" className="cta-band">
        <h2 className="cta-band__title">Run your first call, free.</h2>
        <p className="cta-band__sub">5 analyses a month on the house — no card required.</p>
        <button type="button" className="btn btn--primary btn--lg" onClick={() => openAuthModal("signup")}>
          Get started free
        </button>
      </Reveal>
    </>
  );
}

// Duotone: a soft currentColor fill for the main shape plus a full-strength
// stroke for the defining line, so icons have depth without needing a
// second hardcoded color (they still inherit --brand/--buy/etc via CSS).
function PrintIcon() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" className="feature-card__icon">
      <rect x="3" y="3" width="18" height="18" rx="4" fill="currentColor" fillOpacity="0.12" stroke="currentColor" strokeWidth="1.7" />
      <path d="M8 12.5l2.3 2.3L16 9" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
function ChartIcon() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" className="feature-card__icon">
      <path d="M4 18l4.5-5 3.5 3 6-8 4 4" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M4 18l4.5-5 3.5 3 6-8 4 4V21H4Z" fill="currentColor" fillOpacity="0.12" stroke="none" />
      <path d="M4 21h16" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}
function BoltIcon() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" className="feature-card__icon">
      <path d="M13 2 4 14h6l-1 8 9-12h-6l1-8Z" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
    </svg>
  );
}
function BookmarkIcon({ small }) {
  const size = small ? 16 : 26;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={small ? undefined : "feature-card__icon"}>
      <path d="M6 3.5h12a1 1 0 0 1 1 1V21l-7-4-7 4V4.5a1 1 0 0 1 1-1Z" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
    </svg>
  );
}
function ClockIcon() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" className="feature-card__icon">
      <circle cx="12" cy="12" r="9" fill="currentColor" fillOpacity="0.12" stroke="currentColor" strokeWidth="1.7" />
      <path d="M12 7v5l3.5 2" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
function KeyIcon() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" className="feature-card__icon">
      <circle cx="8" cy="15" r="4" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.7" />
      <path d="M11 12l9-9M17 6l2.5 2.5M14 9l2 2" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
function CheckDotIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <circle cx="8" cy="8" r="8" fill="var(--buy)" fillOpacity="0.16" />
      <path d="M5 8.3l2 2 4-4.3" stroke="var(--buy)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
