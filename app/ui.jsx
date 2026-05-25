// Shared UI primitives across all artboard variations.
// Aesthetic: modern fintech — light, clean, generous whitespace, tabular monospace numerals.

const COLORS = {
  buy:    { fg: "oklch(0.42 0.13 150)", bg: "oklch(0.96 0.05 150)", line: "oklch(0.55 0.16 150)" },
  sell:   { fg: "oklch(0.46 0.18 25)",  bg: "oklch(0.96 0.04 25)",  line: "oklch(0.58 0.22 25)"  },
  hold:   { fg: "oklch(0.48 0.10 75)",  bg: "oklch(0.97 0.05 80)",  line: "oklch(0.62 0.14 75)"  },
  ink:    "oklch(0.18 0.015 250)",
  ink2:   "oklch(0.36 0.015 250)",
  muted:  "oklch(0.52 0.012 250)",
  faint:  "oklch(0.70 0.008 250)",
  surface: "#FFFFFF",
  paper:  "oklch(0.985 0.004 250)",
  rule:   "oklch(0.92 0.006 250)",
  rule2:  "oklch(0.96 0.005 250)",
  accent: "oklch(0.50 0.16 260)",
  accentBg: "oklch(0.96 0.03 260)",
};

function verdictColor(kind) {
  if (kind === "BUY") return COLORS.buy;
  if (kind === "SELL") return COLORS.sell;
  return COLORS.hold;
}

// Pill / badge
function Pill({ children, kind = "neutral", size = "md", style }) {
  const c = kind === "BUY" ? COLORS.buy : kind === "SELL" ? COLORS.sell : kind === "HOLD" ? COLORS.hold : null;
  const bg = c ? c.bg : COLORS.rule2;
  const fg = c ? c.fg : COLORS.ink2;
  const fs = size === "sm" ? 11 : size === "lg" ? 14 : 12;
  const py = size === "sm" ? 2 : size === "lg" ? 5 : 3;
  const px = size === "sm" ? 7 : size === "lg" ? 12 : 9;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 6,
      fontSize: fs, fontWeight: 600, letterSpacing: 0.2,
      color: fg, background: bg, padding: `${py}px ${px}px`,
      borderRadius: 999, lineHeight: 1, fontFamily: "Geist, system-ui, sans-serif",
      ...style,
    }}>{children}</span>
  );
}

// Big verdict badge — like a stamp
function VerdictStamp({ kind, label, size = 64 }) {
  const c = verdictColor(kind);
  return (
    <div style={{
      display: "inline-flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
      width: size * 2.4, height: size,
      background: c.bg, color: c.fg,
      borderRadius: 12, border: `1px solid ${c.line}`, borderLeft: `4px solid ${c.line}`,
      fontFamily: "Geist, system-ui, sans-serif",
    }}>
      <div style={{ fontSize: size * 0.36, fontWeight: 700, letterSpacing: -0.5, lineHeight: 1 }}>{kind}</div>
      <div style={{ fontSize: size * 0.16, fontWeight: 500, opacity: 0.85, marginTop: 4, letterSpacing: 0.4, textTransform: "uppercase" }}>{label}</div>
    </div>
  );
}

// Confidence meter — half-arc gauge
function ConfidenceGauge({ value, size = 120, label = "Confidence" }) {
  // value 0..1
  const r = size / 2 - 8;
  const cx = size / 2, cy = size / 2 + 4;
  const sweep = Math.PI; // 180°
  // arc from -π to 0
  const arcPath = (frac) => {
    const a0 = Math.PI;
    const a1 = Math.PI - sweep * frac;
    const x0 = cx + r * Math.cos(a0), y0 = cy - r * Math.sin(a0);
    const x1 = cx + r * Math.cos(a1), y1 = cy - r * Math.sin(a1);
    const large = frac > 0.5 ? 1 : 0;
    return `M ${x0} ${y0} A ${r} ${r} 0 ${large} 1 ${x1} ${y1}`;
  };
  return (
    <div style={{ display: "inline-flex", flexDirection: "column", alignItems: "center" }}>
      <svg width={size} height={size / 2 + 16} style={{ overflow: "visible" }}>
        <path d={arcPath(1)} stroke={COLORS.rule} strokeWidth={8} fill="none" strokeLinecap="round" />
        <path d={arcPath(value)} stroke={COLORS.accent} strokeWidth={8} fill="none" strokeLinecap="round" />
        <text x={cx} y={cy - 4} textAnchor="middle" style={{ fontFamily: "Geist Mono, monospace", fontSize: size * 0.22, fontWeight: 600, fill: COLORS.ink }}>{Math.round(value * 100)}</text>
        <text x={cx} y={cy + 12} textAnchor="middle" style={{ fontFamily: "Geist, sans-serif", fontSize: 10, fill: COLORS.muted, letterSpacing: 0.5, textTransform: "uppercase" }}>{label}</text>
      </svg>
    </div>
  );
}

// Price scale — shows current price + stop loss + price target on a single horizontal line
function PriceScale({ current, stop, target, height = 80 }) {
  if (current == null) return <div style={{ color: COLORS.muted, fontSize: 12 }}>No price data</div>;
  const vals = [current, stop, target].filter(v => v != null);
  const lo = Math.min(...vals) * 0.92;
  const hi = Math.max(...vals) * 1.08;
  const span = hi - lo;
  const xOf = (v) => ((v - lo) / span) * 100;
  const targetUp = target != null && target > current;
  const targetCol = targetUp ? COLORS.buy : COLORS.sell;

  // Detect label collisions — if two labels are within 15% of each other, stagger them vertically.
  const points = [
    target != null && { key: "target", x: xOf(target), val: target, label: "Target", color: targetCol.fg, lineColor: targetCol.line },
    current != null && { key: "current", x: xOf(current), val: current, label: "Now", color: COLORS.ink, lineColor: COLORS.ink },
    stop != null    && { key: "stop", x: xOf(stop), val: stop, label: "Stop", color: COLORS.sell.fg, lineColor: COLORS.sell.line },
  ].filter(Boolean).sort((a, b) => a.x - b.x);

  // Assign each point a row (0 or 1) such that no two adjacent points within 18% horizontal share a row
  const rows = {};
  for (let i = 0; i < points.length; i++) {
    const p = points[i];
    let row = 0;
    for (let j = 0; j < i; j++) {
      if (Math.abs(points[j].x - p.x) < 18 && rows[points[j].key] === row) row = 1 - row;
    }
    rows[p.key] = row;
  }

  return (
    <div style={{ width: "100%", padding: "8px 0 0", fontFamily: "Geist, sans-serif" }}>
      {/* The track */}
      <div style={{ position: "relative", height: 8, background: COLORS.rule2, borderRadius: 4 }}>
        {points.map(p => p.key === "current" ? (
          <div key={p.key} style={{
            position: "absolute", left: `calc(${p.x}% - 7px)`, top: -5, width: 14, height: 18,
            background: "white", border: `2px solid ${COLORS.ink}`, borderRadius: 4,
            boxShadow: "0 1px 4px rgba(0,0,0,0.15)",
          }} />
        ) : (
          <div key={p.key} style={{
            position: "absolute", left: `calc(${p.x}% - 3px)`, top: -4, width: 6, height: 16,
            background: p.lineColor, borderRadius: 2,
          }} />
        ))}
      </div>
      {/* Labels — staggered into 2 rows if needed */}
      <div style={{ position: "relative", marginTop: 10, height: 70 }}>
        {points.map(p => {
          const row = rows[p.key];
          return (
            <div key={p.key} style={{
              position: "absolute", left: `${p.x}%`, top: row * 34,
              transform: "translateX(-50%)", textAlign: "center",
            }}>
              <div style={{ fontSize: 9.5, color: COLORS.muted, letterSpacing: 0.4, textTransform: "uppercase", lineHeight: 1.1 }}>{p.label}</div>
              <div style={{ fontFamily: "Geist Mono, monospace", fontSize: 12.5, color: p.color, fontWeight: p.key === "current" ? 700 : 600, marginTop: 2, lineHeight: 1 }}>${p.val.toFixed(2)}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// Bull-vs-bear weight bar — shows how much weight the manager gave each side
function BullBearBar({ bull = 0.5, height = 28 }) {
  return (
    <div style={{ fontFamily: "Geist, sans-serif" }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6, fontSize: 11, color: COLORS.muted, textTransform: "uppercase", letterSpacing: 0.5 }}>
        <span>Bull</span>
        <span style={{ color: COLORS.ink2 }}>Manager weighting</span>
        <span>Bear</span>
      </div>
      <div style={{ display: "flex", height, borderRadius: 6, overflow: "hidden", background: COLORS.rule2 }}>
        <div style={{ width: `${bull * 100}%`, background: COLORS.buy.bg, borderRight: `1px solid ${COLORS.rule}`, display: "flex", alignItems: "center", justifyContent: "flex-start", paddingLeft: 10, fontSize: 12, fontWeight: 600, color: COLORS.buy.fg, fontFamily: "Geist Mono, monospace" }}>{Math.round(bull * 100)}%</div>
        <div style={{ width: `${(1 - bull) * 100}%`, background: COLORS.sell.bg, display: "flex", alignItems: "center", justifyContent: "flex-end", paddingRight: 10, fontSize: 12, fontWeight: 600, color: COLORS.sell.fg, fontFamily: "Geist Mono, monospace" }}>{Math.round((1 - bull) * 100)}%</div>
      </div>
    </div>
  );
}

// Stat — label above value
function Stat({ label, value, sub, color, mono = true, align = "left" }) {
  return (
    <div style={{ textAlign: align, fontFamily: "Geist, sans-serif" }}>
      <div style={{ fontSize: 10, color: COLORS.muted, letterSpacing: 0.6, textTransform: "uppercase", fontWeight: 500 }}>{label}</div>
      <div style={{
        fontSize: 22, fontWeight: 600, color: color || COLORS.ink, marginTop: 2,
        fontFamily: mono ? "Geist Mono, monospace" : "Geist, sans-serif",
        letterSpacing: mono ? -0.3 : -0.4, lineHeight: 1.1,
      }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: COLORS.muted, marginTop: 3 }}>{sub}</div>}
    </div>
  );
}

// Compact card wrapper
function Card({ children, style, padding = 20 }) {
  return (
    <div style={{
      background: COLORS.surface, border: `1px solid ${COLORS.rule}`,
      borderRadius: 14, padding,
      ...style,
    }}>{children}</div>
  );
}

// Section header
function SectionHeader({ eyebrow, title, action }) {
  return (
    <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 14, fontFamily: "Geist, sans-serif" }}>
      <div>
        {eyebrow && <div style={{ fontSize: 10, color: COLORS.muted, letterSpacing: 0.6, textTransform: "uppercase", fontWeight: 500, marginBottom: 2 }}>{eyebrow}</div>}
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600, color: COLORS.ink, letterSpacing: -0.4 }}>{title}</h2>
      </div>
      {action}
    </div>
  );
}

// Render markdown to HTML using marked
function MD({ src, style }) {
  const html = React.useMemo(() => {
    if (!src) return "";
    if (typeof window.marked === "undefined") return src;
    return window.marked.parse(src);
  }, [src]);
  return (
    <div className="md" style={style} dangerouslySetInnerHTML={{ __html: html }} />
  );
}

// Auto-highlight key numbers in a text block: $123, 45%, 12.3x
function highlightMetrics(text) {
  if (!text) return "";
  return text.replace(
    /(\$\d[\d.,]*[BMK]?|\b\d+(?:\.\d+)?%|\b\d+(?:\.\d+)?x\b|\b\d{1,3}(?:,\d{3})+\b)/g,
    (m) => `<mark class="metric">${m}</mark>`
  );
}

Object.assign(window, {
  COLORS, verdictColor,
  Pill, VerdictStamp, ConfidenceGauge, PriceScale, BullBearBar,
  Stat, Card, SectionHeader, MD, highlightMetrics,
});
