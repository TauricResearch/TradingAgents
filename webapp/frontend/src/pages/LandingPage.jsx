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
        </div>

        <div className="hero__visual" aria-hidden="true">
          <div className="hero__mockup">
            <div className="hero__mockup-bar">
              <span />
              <span />
              <span />
            </div>
            <div className="hero__mockup-body">
              <div className="hero__mockup-chart">
                <svg viewBox="0 0 100 32" preserveAspectRatio="none">
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

function PrintIcon() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" className="feature-card__icon">
      <rect x="3" y="3" width="18" height="18" rx="4" stroke="currentColor" strokeWidth="1.7" />
      <path d="M8 12.5l2.3 2.3L16 9" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
function ChartIcon() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" className="feature-card__icon">
      <path d="M4 18l4.5-5 3.5 3 6-8" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M4 21h16" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}
function BoltIcon() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" className="feature-card__icon">
      <path d="M13 2 4 14h6l-1 8 9-12h-6l1-8Z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
    </svg>
  );
}
function BookmarkIcon() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" className="feature-card__icon">
      <path d="M6 3.5h12a1 1 0 0 1 1 1V21l-7-4-7 4V4.5a1 1 0 0 1 1-1Z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
    </svg>
  );
}
function ClockIcon() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" className="feature-card__icon">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.7" />
      <path d="M12 7v5l3.5 2" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
function KeyIcon() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" className="feature-card__icon">
      <circle cx="8" cy="15" r="4" stroke="currentColor" strokeWidth="1.7" />
      <path d="M11 12l9-9M17 6l2.5 2.5M14 9l2 2" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
