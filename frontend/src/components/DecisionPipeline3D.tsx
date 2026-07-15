/** Decision pipeline — isometric (2.5D) flow board for one run, matching
 * the Accops mockup: glass-slab stations on a projected floor grid, curved
 * edges with traveling pulse dots, per-stage outcome tints, hover decision
 * tooltips, click-to-inspect detail bar, replay, and live SSE mode.
 *
 * All numbers come from real run data (node_sequence, node_times, debate
 * entries, evidence, rejection, execution_status); personas are display
 * labels for the fixed agent roster. LLMs never compute anything here.
 */
import { Play } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import type {
  EvidencePanels,
  Recommendation,
  Timeline,
} from "@/lib/api/types";
import { cn } from "@/lib/utils";
import type { PipelineProgress } from "@/stores/ui";

/* ---------------------------------------------------------------- geometry */

// isometric projection: sx = CX + (x−y)·KX, sy = CY + (x+y)·KY − z
const KX = 83;
const KY = 35.5;
const CX = 302;
const CY = 62;

function px(x: number, y: number): number {
  return CX + (x - y) * KX;
}
function py(x: number, y: number, z = 0): number {
  return CY + (x + y) * KY - z;
}

/** Screen-space half extents of a grid-square diamond of half-size `a`.
 * Corners are (x±k, y∓k)/(x±k, y±k) with k = a·0.62 — grid-square corners,
 * NOT (x±a, y): those project to axis-aligned rectangles and kill the 3D. */
function halfExtents(a: number): { dx: number; dy: number } {
  const k = a * 0.62;
  return { dx: 2 * k * KX, dy: 2 * k * KY };
}

/* ------------------------------------------------------------------ tables */

const BUCKETS = [
  "prepare", "teams", "join", "debate", "risk_gate",
  "review", "judge", "sizing", "approval", "execution",
] as const;

/** LangGraph node name → progress bucket. */
function bucketOf(node: string): string {
  if (node.startsWith("team_")) return "teams";
  if (/^(technical|macro)_(bull|bear)$/.test(node) || node === "sentiment")
    return "debate";
  if (node === "critic" || node === "reflection") return "review";
  if (node === "portfolio_manager") return "sizing";
  if (node === "human_approval") return "approval";
  return node; // prepare, join, risk_gate, judge, execution, rejected
}

type LabelPos = "below" | "above" | "left";

interface Station {
  id: string;
  label: string;
  persona: string;
  role: string;
  nodes: string[]; // real LangGraph nodes that make up this station
  speakers?: string[]; // debate-entry speakers whose output belongs here
  team?: string; // evidence panel key
  x: number;
  y: number;
  a: number;
  h: number;
  labelPos: LabelPos;
  gate?: boolean;
  small?: boolean; // pods/teams: 10px label
  sink?: boolean;
}

const STATIONS: Station[] = [
  { id: "prepare", label: "Prepare", persona: "Atlas", role: "snapshot · regime",
    nodes: ["prepare"], x: 0.1, y: 2, a: 0.44, h: 13, labelPos: "above" },
  { id: "team_technical", label: "Technical", persona: "Kenji",
    role: "technical analysis", nodes: ["team_technical"], team: "technical",
    x: 1.4, y: 0.4, a: 0.3, h: 9, labelPos: "left", small: true },
  { id: "team_macro", label: "Macro", persona: "Margaux",
    role: "macro analysis", nodes: ["team_macro"], team: "macro",
    x: 1.4, y: 1.2, a: 0.3, h: 9, labelPos: "left", small: true },
  { id: "team_news_sentiment", label: "News & Sentiment", persona: "Priya",
    role: "news & sentiment", nodes: ["team_news_sentiment"],
    team: "news_sentiment",
    x: 1.4, y: 2, a: 0.3, h: 9, labelPos: "left", small: true },
  { id: "team_quant", label: "Quant", persona: "Viktor",
    role: "quant metrics", nodes: ["team_quant"], team: "quant",
    x: 1.4, y: 2.8, a: 0.3, h: 9, labelPos: "left", small: true },
  { id: "team_risk", label: "Risk", persona: "Nadia",
    role: "risk assessment", nodes: ["team_risk"], team: "risk",
    x: 1.4, y: 3.6, a: 0.3, h: 9, labelPos: "left", small: true },
  { id: "join", label: "Join", persona: "Atlas", role: "evidence merge",
    nodes: ["join"], x: 2.6, y: 2, a: 0.4, h: 13, labelPos: "below" },
  { id: "debate_technical", label: "Technical", persona: "Tomas ⇄ Freya",
    role: "bull ⇄ bear",
    nodes: ["technical_bull", "technical_bear"],
    speakers: ["technical_bull", "technical_bear"],
    x: 3.68, y: 1.35, a: 0.3, h: 9, labelPos: "above", small: true },
  { id: "debate_macro", label: "Macro", persona: "Elif ⇄ Bruno",
    role: "bull ⇄ bear",
    nodes: ["macro_bull", "macro_bear"], speakers: ["macro_bull", "macro_bear"],
    x: 3.68, y: 2.65, a: 0.3, h: 9, labelPos: "below", small: true },
  { id: "debate_sentiment", label: "Sentiment", persona: "Noa",
    role: "rapporteur", nodes: ["sentiment"], speakers: ["sentiment"],
    x: 4.5, y: 2, a: 0.3, h: 9, labelPos: "below", small: true },
  { id: "risk_gate", label: "Risk gate", persona: "Imara", role: "hard limits",
    nodes: ["risk_gate"], x: 5.7, y: 2, a: 0.42, h: 13,
    labelPos: "below", gate: true },
  { id: "review", label: "Critic · Reflection", persona: "Cass + Miro",
    role: "audit + memory",
    nodes: ["critic", "reflection"], speakers: ["critic", "reflection"],
    x: 6.55, y: 1.3, a: 0.38, h: 13, labelPos: "above" },
  { id: "judge", label: "Judge", persona: "Aldous", role: "final verdict",
    nodes: ["judge"], speakers: ["judge"],
    x: 7.45, y: 2.05, a: 0.48, h: 20, labelPos: "below" },
  { id: "sizing", label: "Portfolio mgr", persona: "Ingrid", role: "sizing gate",
    nodes: ["portfolio_manager"], x: 8.3, y: 1.3, a: 0.38, h: 13,
    labelPos: "above", gate: true },
  { id: "approval", label: "Human approval", persona: "operator (you)",
    role: "live only", nodes: ["human_approval"],
    x: 9.1, y: 2.05, a: 0.38, h: 13, labelPos: "below", gate: true },
  { id: "execution", label: "Execution", persona: "Otto", role: "paper venue",
    nodes: ["execution"], x: 9.95, y: 1.3, a: 0.44, h: 13, labelPos: "below" },
  { id: "rejected", label: "Rejected", persona: "—", role: "terminal sink",
    nodes: ["rejected"], x: 7.7, y: 3.9, a: 0.46, h: 6,
    labelPos: "below", sink: true },
];

const STATION_BY_ID = new Map(STATIONS.map((s) => [s.id, s]));

interface Edge {
  from: string;
  to: string;
  reject?: boolean;
}

const EDGES: Edge[] = [
  // fan-out / fan-in
  ...["team_technical", "team_macro", "team_news_sentiment", "team_quant",
      "team_risk"].flatMap((t) => [
    { from: "prepare", to: t },
    { from: t, to: "join" },
  ]),
  // arena flow
  { from: "join", to: "debate_technical" },
  { from: "debate_technical", to: "debate_macro" },
  { from: "debate_macro", to: "debate_sentiment" },
  { from: "debate_sentiment", to: "risk_gate" },
  // gauntlet
  { from: "risk_gate", to: "review" },
  { from: "review", to: "judge" },
  { from: "judge", to: "sizing" },
  { from: "sizing", to: "approval" },
  { from: "approval", to: "execution" },
  // rejection rails (all 4 gates)
  { from: "risk_gate", to: "rejected", reject: true },
  { from: "review", to: "rejected", reject: true },
  { from: "sizing", to: "rejected", reject: true },
  { from: "approval", to: "rejected", reject: true },
];

/* ----------------------------------------------------------------- status */

type Status = "queued" | "active" | "done";
type Tint = "brand" | "bull" | "bear";

const TINT_VAR: Record<Tint, string> = {
  brand: "var(--brand)",
  bull: "var(--bull)",
  bear: "var(--bear)",
};

function stanceTint(s: string | null | undefined): Tint {
  if (!s) return "brand";
  if (/bull|long|buy/i.test(s)) return "bull";
  if (/bear|short|sell/i.test(s)) return "bear";
  return "brand";
}

function firstSentence(text: string, max = 160): string {
  const cut = text.split(/(?<=[.!?])\s/)[0] ?? text;
  return cut.length > max ? `${cut.slice(0, max - 1)}…` : cut;
}

interface StationView {
  status: Status;
  tint: Tint;
  decision: string; // short tooltip text
  output: string | null; // detail-bar sentence
  latency: number | null; // seconds, null when not recorded
}

function computeViews(
  timeline: Timeline | undefined,
  evidence: EvidencePanels | undefined,
  rec: Recommendation | null | undefined,
  activeNode: string | null,
  visibleNodes: Set<string> | null, // replay: only nodes revealed so far
): Map<string, StationView> {
  const seq = timeline?.node_sequence ?? [];
  const nodeTimes = timeline?.node_times ?? [];
  const rejection = timeline?.rejection ?? null;
  const executionStatus = timeline?.execution_status ?? null;
  const entries = timeline?.entries ?? [];
  const done = new Set(
    seq.filter((n) => visibleNodes == null || visibleNodes.has(n)),
  );
  const activeBucket = activeNode ? bucketOf(activeNode) : null;

  const views = new Map<string, StationView>();
  for (const st of STATIONS) {
    const stDone = st.nodes.some((n) => done.has(n));
    const isActive =
      activeNode != null &&
      (st.nodes.includes(activeNode) ||
        (activeBucket === "teams" && st.team != null && stDone === false &&
          st.nodes.some((n) => bucketOf(n) === "teams")));
    const status: Status = isActive ? "active" : stDone ? "done" : "queued";

    // latency: sum of recorded elapsed_s for this station's nodes
    let latency: number | null = null;
    if (nodeTimes.length > 0) {
      const sum = nodeTimes
        .filter((t) => st.nodes.includes(t.node) && done.has(t.node))
        .reduce((acc, t) => acc + t.elapsed_s, 0);
      latency = stDone ? sum : null;
    }

    // outcome tint + decision + output, from real run data only
    let tint: Tint = "brand";
    let decision = status === "active" ? "running…" : "queued";
    let output: string | null = null;

    if (st.sink) {
      tint = "bear";
      decision = rejection?.stage
        ? `rejected @ ${String(rejection.stage)}`
        : "not hit this run";
      const reasons = (rejection?.reasons as string[] | undefined) ?? [];
      output = reasons.length > 0 ? firstSentence(reasons.join("; ")) : null;
    } else if (status === "done") {
      const rejectedHere =
        rejection?.stage != null && st.nodes.includes(String(rejection.stage));
      if (st.team) {
        const items = evidence?.[st.team] ?? [];
        const longs = items.filter((e) => /long|bull|buy/i.test(e.direction)).length;
        const shorts = items.filter((e) => /short|bear|sell/i.test(e.direction)).length;
        tint = longs > shorts ? "bull" : shorts > longs ? "bear" : "brand";
        decision =
          items.length === 0
            ? "no evidence"
            : `lean ${longs > shorts ? "bullish" : shorts > longs ? "bearish" : "mixed"}`;
        output = items[0] ? firstSentence(items[0].claim) : null;
      } else if (st.id === "review") {
        // critic is a gate; reflection supplies the falsifiability prose
        const critic = entries.filter((e) => e.speaker === "critic").pop();
        const refl = entries.filter((e) => e.speaker === "reflection").pop();
        const arg = critic?.argument ?? refl?.argument;
        if (rejectedHere) {
          tint = "bear";
          decision = "REJECT";
          const reasons = (rejection?.reasons as string[] | undefined) ?? [];
          output =
            reasons.length > 0
              ? firstSentence(reasons.join("; "))
              : arg
                ? firstSentence(arg)
                : null;
        } else {
          tint = "bull";
          decision = critic?.stance ? critic.stance.toUpperCase() : "PASS";
          output = arg ? firstSentence(arg) : null;
        }
      } else if (st.speakers && st.id !== "judge") {
        const own = entries.filter((e) => st.speakers?.includes(e.speaker));
        const last = own[own.length - 1];
        tint = stanceTint(last?.stance);
        decision = last
          ? `${last.stance ?? "done"}${last.confidence != null ? ` · conf ${last.confidence}` : ""}`
          : "done";
        output = last ? firstSentence(last.argument) : null;
      } else if (st.id === "judge") {
        const judgeEntry = entries.find((e) => e.speaker === "judge");
        const action = rec?.action ?? judgeEntry?.stance ?? null;
        tint = stanceTint(action);
        decision = action
          ? `${action}${rec?.confidence != null ? ` · conf ${rec.confidence}` : ""}`
          : "done";
        output = judgeEntry ? firstSentence(judgeEntry.argument) : null;
      } else if (st.gate) {
        if (rejectedHere) {
          tint = "bear";
          const reasons = (rejection?.reasons as string[] | undefined) ?? [];
          decision = "REJECT";
          output = reasons.length > 0 ? firstSentence(reasons.join("; ")) : null;
        } else {
          tint = "bull";
          decision =
            st.id === "approval" && executionStatus?.includes("paper")
              ? "auto-approved (paper)"
              : "PASS";
          if (st.id === "approval" && executionStatus?.includes("paper"))
            output =
              "Auto-approved — paper mode. The human interrupt arms only in live trading (fail closed).";
        }
      } else if (st.id === "execution") {
        tint = executionStatus?.startsWith("accepted")
          ? "bull"
          : executionStatus?.startsWith("rejected")
            ? "bear"
            : "brand";
        decision = executionStatus ?? "done";
        output = executionStatus;
      } else if (st.id === "join") {
        tint = "brand";
        // merge tally straight from the evidence panels
        const all = Object.values(evidence ?? {}).flat();
        const up = all.filter((e) => /long|bull|buy/i.test(e.direction)).length;
        const dn = all.filter((e) => /short|bear|sell/i.test(e.direction)).length;
        const flat = all.length - up - dn;
        decision =
          all.length > 0 ? `merged ${up}▲ ${dn}▼ ${flat}–` : "done";
      } else {
        // prepare: neutral infrastructure stage
        tint = "brand";
        decision = rec?.market_regime
          ? `snapshot ready · ${rec.market_regime}`
          : "snapshot ready";
      }
    }
    views.set(st.id, { status, tint, decision, output, latency });
  }
  return views;
}

/* ------------------------------------------------------------ sub-renders */

function fmtLatency(s: number | null): string | null {
  if (s == null) return null;
  return s >= 10 ? `${s.toFixed(0)}s` : `${s.toFixed(1)}s`;
}

function Slab({
  st,
  view,
  reduced,
  selected,
  onSelect,
  onHover,
}: {
  st: Station;
  view: StationView;
  reduced: boolean;
  selected: boolean;
  onSelect: () => void;
  onHover: (hover: boolean) => void;
}) {
  const { dx, dy } = halfExtents(st.a);
  const cx = px(st.x, st.y);
  const cy = py(st.x, st.y);
  const h =
    st.h + (view.status === "active" ? 9 : view.status === "done" ? 3 : 0);
  const tintVar = TINT_VAR[view.tint];

  // faces
  const top = `${cx},${cy - dy - h} ${cx + dx},${cy - h} ${cx},${cy + dy - h} ${cx - dx},${cy - h}`;
  const right = `${cx + dx},${cy - h} ${cx},${cy + dy - h} ${cx},${cy + dy} ${cx + dx},${cy}`;
  const left = `${cx - dx},${cy - h} ${cx},${cy + dy - h} ${cx},${cy + dy} ${cx - dx},${cy}`;
  const silhouette = `${cx},${cy - dy - h} ${cx + dx},${cy - h} ${cx + dx},${cy} ${cx},${cy + dy} ${cx - dx},${cy} ${cx - dx},${cy - h}`;

  let topFill = "var(--surface-2)";
  let topFillOp = 1;
  let topStroke = "var(--border-strong)";
  let topStrokeOp = 1;
  let sideFill = "var(--fg-subtle)";
  let sideOpR = 0.14;
  let sideOpL = 0.24;
  if (view.status === "active") {
    topFill = "var(--brand)";
    topFillOp = 0.92;
    topStroke = "var(--brand)";
    sideFill = "var(--brand)";
    sideOpR = 0.45;
    sideOpL = 0.68;
  } else if (st.sink) {
    topFill = "var(--bear)";
    topFillOp = 0.07;
    topStroke = "var(--bear)";
    topStrokeOp = 0.5;
    sideFill = "var(--bear)";
    sideOpR = 0.1;
    sideOpL = 0.16;
  } else if (view.status === "done") {
    topFill = tintVar;
    topFillOp = 0.18;
    topStroke = tintVar;
    topStrokeOp = 0.55;
    sideFill = tintVar;
    sideOpR = 0.18;
    sideOpL = 0.3;
  }

  // labels
  const line1Size = st.small ? 10 : 11.5;
  let lx = cx;
  let anchor: "middle" | "end" = "middle";
  let l1y = cy + dy + 14;
  let l2y = cy + dy + 26;
  if (st.labelPos === "left") {
    anchor = "end";
    lx = cx - dx - 8;
    l1y = cy + 2;
    l2y = cy + 13;
  } else if (st.labelPos === "above") {
    l1y = cy - dy - h - 20;
    l2y = cy - dy - h - 9;
  }
  // teams/pods show persona only (spec §5); full stations add status/latency
  const statusLine =
    view.status === "active"
      ? `${st.persona} · running…`
      : !st.small && view.status === "done" && fmtLatency(view.latency) != null
        ? `${st.persona} · ${fmtLatency(view.latency)}`
        : st.persona;

  const halo = { paintOrder: "stroke" as const };

  return (
    <g
      data-testid={`pipeline-station-${st.id}`}
      role="button"
      tabIndex={0}
      aria-label={`${st.label} — ${st.persona}, ${view.status}`}
      aria-pressed={selected}
      style={{ cursor: "pointer", outline: "none" }}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect();
        }
      }}
      onMouseEnter={() => onHover(true)}
      onMouseLeave={() => onHover(false)}
      onFocus={() => onHover(true)}
      onBlur={() => onHover(false)}
    >
      {/* gate ground ring */}
      {st.gate && (
        <polygon
          points={`${cx},${cy - dy * 1.7} ${cx + dx * 1.7},${cy} ${cx},${cy + dy * 1.7} ${cx - dx * 1.7},${cy}`}
          fill="none"
          stroke="var(--neutral)"
          strokeOpacity={0.55}
          strokeWidth={1}
          strokeDasharray="4 4"
        />
      )}
      {/* active ground glow + pulse ring */}
      {view.status === "active" && (
        <>
          <ellipse
            cx={cx}
            cy={cy}
            rx={dx * 1.9}
            ry={dy * 1.9}
            fill="url(#pp-glow)"
          />
          {!reduced && (
            <g transform={`translate(${cx},${cy})`}>
              <polygon
                points={`0,${-dy} ${dx},0 0,${dy} ${-dx},0`}
                fill="none"
                stroke="var(--brand)"
                strokeWidth={1.4}
              >
                <animateTransform
                  attributeName="transform"
                  type="scale"
                  from="0.6"
                  to="1.7"
                  dur="1.5s"
                  repeatCount="indefinite"
                />
                <animate
                  attributeName="opacity"
                  from="0.8"
                  to="0"
                  dur="1.5s"
                  repeatCount="indefinite"
                />
              </polygon>
            </g>
          )}
        </>
      )}
      {/* opaque underlay so the floor grid never shows through */}
      <polygon points={silhouette} fill="var(--bg)" />
      <polygon
        points={left}
        fill={sideFill}
        fillOpacity={sideOpL}
        stroke={topStroke}
        strokeOpacity={0.25}
        strokeWidth={0.6}
      />
      <polygon
        points={right}
        fill={sideFill}
        fillOpacity={sideOpR}
        stroke={topStroke}
        strokeOpacity={0.25}
        strokeWidth={0.6}
      />
      <polygon
        points={top}
        fill={topFill}
        fillOpacity={topFillOp}
        stroke={topStroke}
        strokeOpacity={topStrokeOp}
        strokeWidth={selected ? 1.8 : 1.1}
        strokeDasharray={st.sink ? "4 3" : undefined}
      />
      <text
        x={lx}
        y={l1y}
        textAnchor={anchor}
        fontSize={line1Size}
        fontWeight={700}
        fill={view.status === "queued" ? "var(--fg-muted)" : "var(--fg)"}
        stroke="var(--bg)"
        strokeWidth={2.5}
        style={halo}
      >
        {st.label}
      </text>
      {!st.sink && (
        <text
          x={lx}
          y={l2y}
          textAnchor={anchor}
          fontSize={8.5}
          fontFamily="var(--font-mono)"
          fill="var(--fg-subtle)"
          stroke="var(--bg)"
          strokeWidth={2.5}
          style={halo}
        >
          {statusLine}
        </text>
      )}
    </g>
  );
}

/* -------------------------------------------------------------- component */

function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return reduced;
}

const LEGEND: { label: string; style: React.CSSProperties }[] = [
  { label: "running", style: { background: "var(--brand)" } },
  {
    label: "bullish / pass",
    style: { background: "color-mix(in srgb, var(--bull) 40%, transparent)" },
  },
  {
    label: "bearish",
    style: { background: "color-mix(in srgb, var(--bear) 40%, transparent)" },
  },
  {
    label: "queued",
    style: {
      background: "var(--surface-2)",
      border: "1px solid var(--border-strong)",
    },
  },
  {
    label: "reject",
    style: { border: "1px dashed var(--bear)", background: "transparent" },
  },
];

export function DecisionPipeline3D({
  timeline,
  evidence,
  rec,
  live,
  runLabel,
}: {
  timeline: Timeline | undefined;
  evidence: EvidencePanels | undefined;
  rec: Recommendation | null | undefined;
  live: PipelineProgress | null;
  /** e.g. "last run · BTC-USD 1d · #61" */
  runLabel: string;
}) {
  const reduced = useReducedMotion();
  const [selected, setSelected] = useState("judge");
  const [hovered, setHovered] = useState<string | null>(null);
  const [replayIdx, setReplayIdx] = useState<number | null>(null);
  const replayTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const seq = useMemo(
    () => timeline?.node_sequence ?? [],
    [timeline?.node_sequence],
  );

  // replay stepper over the recorded sequence (client-side animation of
  // real recorded data; disabled while a genuine live run is in flight)
  useEffect(() => {
    if (replayIdx == null) return;
    replayTimer.current = setInterval(() => {
      setReplayIdx((i) => {
        if (i == null || i >= seq.length - 1) {
          if (replayTimer.current) clearInterval(replayTimer.current);
          return null; // replay finished → settle on the real final state
        }
        return i + 1;
      });
    }, 420);
    return () => {
      if (replayTimer.current) clearInterval(replayTimer.current);
    };
  }, [replayIdx == null, seq.length]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (live) setReplayIdx(null); // a real run preempts replay
  }, [live]);

  const replaying = replayIdx != null;
  const activeNode = live?.stage ?? (replaying ? seq[replayIdx] ?? null : null);
  const visibleNodes = replaying
    ? new Set(seq.slice(0, replayIdx))
    : null;

  const views = useMemo(
    () => computeViews(timeline, evidence, rec, activeNode, visibleNodes),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [timeline, evidence, rec, activeNode, replayIdx],
  );

  const liveBucketIdx = activeNode
    ? BUCKETS.indexOf(bucketOf(activeNode) as (typeof BUCKETS)[number])
    : -1;
  const subtitle = live
    ? `running ${live.symbol} · stage ${Math.max(liveBucketIdx + 1, 1)}/10`
    : replaying
      ? `replaying recorded run · stage ${Math.max(liveBucketIdx + 1, 1)}/10`
      : runLabel;

  const sel: Station =
    STATION_BY_ID.get(selected) ?? (STATIONS.find((s) => s.id === "judge") as Station);
  const selView = views.get(sel.id);

  const rejectedStage = timeline?.rejection?.stage ?? null;
  const finalMode = !live && !replaying;
  const verdict =
    finalMode && rec?.action && !rejectedStage
      ? {
          action: String(rec.action),
          confidence: rec.confidence as number | undefined,
          tint: stanceTint(String(rec.action)),
        }
      : null;

  /* edges: flowing when source is done and target done/active */
  const edgeState = (e: Edge) => {
    const from = views.get(e.from);
    const to = views.get(e.to);
    if (e.reject) {
      const fired =
        rejectedStage != null &&
        (STATION_BY_ID.get(e.from)?.nodes ?? []).includes(String(rejectedStage));
      return { flowing: fired, current: false, fired };
    }
    const flowing =
      from?.status === "done" &&
      (to?.status === "done" || to?.status === "active");
    return { flowing, current: flowing && to?.status === "active", fired: false };
  };

  const execTop = {
    x: px(9.95, 1.3),
    y: py(9.95, 1.3, 13 + 3),
  };
  const hoveredSt = hovered ? STATION_BY_ID.get(hovered) : null;
  const hoveredView = hovered ? views.get(hovered) : null;

  return (
    <div data-testid="decision-pipeline">
      {/* header row: subtitle + legend + replay */}
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <p className="text-[11.5px] text-fg-muted">
          <span className="font-mono">{subtitle}</span>
          <span className="text-fg-subtle"> — click any stage for its output</span>
        </p>
        <div className="flex items-center gap-4">
          <ul className="flex items-center gap-3 text-[10.5px] text-fg-subtle">
            {LEGEND.map((item) => (
              <li key={item.label} className="flex items-center gap-1.5">
                <span
                  aria-hidden
                  className="inline-block size-[7px] rotate-45"
                  style={item.style}
                />
                {item.label}
              </li>
            ))}
          </ul>
          <button
            onClick={() => seq.length > 0 && setReplayIdx(0)}
            disabled={live != null || seq.length === 0}
            data-testid="pipeline-replay"
            className={cn(
              "inline-flex h-7 items-center gap-1.5 rounded-[9px] border border-border-strong",
              "px-2.5 text-xs font-semibold text-fg hover:bg-surface-2",
              "disabled:cursor-not-allowed disabled:opacity-50",
            )}
          >
            <Play size={11} /> Replay run
          </button>
        </div>
      </div>

      {/* the isometric board */}
      <svg
        viewBox="0 0 1100 536"
        width="100%"
        role="img"
        aria-label="Isometric 3D view of the decision pipeline: prepare fans out to five agent teams, evidence joins into the debate arena, then passes risk gate, critic and reflection, judge, portfolio manager, human approval and execution; gates can reject."
        className="mt-1 block"
      >
        <defs>
          <radialGradient id="pp-glow">
            <stop offset="0%" stopColor="var(--brand)" stopOpacity={0.28} />
            <stop offset="100%" stopColor="var(--brand)" stopOpacity={0} />
          </radialGradient>
        </defs>

        {/* ground + floor grid */}
        <polygon
          points={`${px(-1, 0)},${py(-1, 0)} ${px(11, 0)},${py(11, 0)} ${px(11, 4)},${py(11, 4)} ${px(-1, 4)},${py(-1, 4)}`}
          fill="var(--fg-subtle)"
          fillOpacity={0.04}
        />
        <g stroke="var(--fg-subtle)" strokeOpacity={0.1} strokeWidth={0.7}>
          {Array.from({ length: 13 }, (_, i) => i - 1).map((x) => (
            <line
              key={`gx${x}`}
              x1={px(x, 0)}
              y1={py(x, 0)}
              x2={px(x, 4)}
              y2={py(x, 4)}
            />
          ))}
          {Array.from({ length: 5 }, (_, i) => i).map((y) => (
            <line
              key={`gy${y}`}
              x1={px(-1, y)}
              y1={py(-1, y)}
              x2={px(11, y)}
              y2={py(11, y)}
            />
          ))}
        </g>

        {/* debate arena platform (flat slab under the pods) */}
        {(() => {
          const { dx, dy } = halfExtents(1.14);
          const cx = px(4.02, 2);
          const cy = py(4.02, 2);
          const h = 5;
          return (
            <g aria-hidden>
              <polygon
                points={`${cx},${cy - dy - h} ${cx + dx},${cy - h} ${cx + dx},${cy} ${cx},${cy + dy} ${cx - dx},${cy} ${cx - dx},${cy - h}`}
                fill="var(--bg)"
              />
              <polygon
                points={`${cx + dx},${cy - h} ${cx},${cy + dy - h} ${cx},${cy + dy} ${cx + dx},${cy}`}
                fill="var(--brand)"
                fillOpacity={0.06}
              />
              <polygon
                points={`${cx - dx},${cy - h} ${cx},${cy + dy - h} ${cx},${cy + dy} ${cx - dx},${cy}`}
                fill="var(--brand)"
                fillOpacity={0.1}
              />
              <polygon
                points={`${cx},${cy - dy - h} ${cx + dx},${cy - h} ${cx},${cy + dy - h} ${cx - dx},${cy - h}`}
                fill="var(--brand)"
                fillOpacity={0.05}
                stroke="var(--border-strong)"
                strokeWidth={0.9}
              />
              <text
                x={cx}
                y={cy + dy - 12}
                textAnchor="middle"
                fontSize={9}
                fontWeight={700}
                letterSpacing="0.18em"
                fill="var(--fg-subtle)"
                stroke="var(--bg)"
                strokeWidth={2.5}
                style={{ paintOrder: "stroke" }}
              >
                DEBATE ARENA
              </text>
            </g>
          );
        })()}

        {/* edges */}
        {EDGES.map((e, i) => {
          const a = STATION_BY_ID.get(e.from);
          const b = STATION_BY_ID.get(e.to);
          if (!a || !b) return null;
          const x1 = px(a.x, a.y);
          const y1 = py(a.x, a.y);
          const x2 = px(b.x, b.y);
          const y2 = py(b.x, b.y);
          const d = `M ${x1} ${y1} Q ${(x1 + x2) / 2} ${(y1 + y2) / 2 - 9} ${x2} ${y2}`;
          const { flowing, current, fired } = edgeState(e);
          const len = Math.hypot(x2 - x1, y2 - y1);
          const id = `pp-edge-${i}`;
          return (
            <g key={id}>
              <path
                id={id}
                d={d}
                fill="none"
                stroke={
                  e.reject
                    ? "var(--bear)"
                    : flowing
                      ? "var(--brand)"
                      : "var(--fg-subtle)"
                }
                strokeOpacity={e.reject ? (fired ? 0.8 : 0.35) : flowing ? 0.85 : 0.45}
                strokeWidth={flowing || fired ? 1.7 : 1.1}
                strokeDasharray={
                  e.reject ? "5 4" : flowing ? (current ? "6 6" : undefined) : "2 4"
                }
              >
                {current && !reduced && (
                  <animate
                    attributeName="stroke-dashoffset"
                    from="24"
                    to="0"
                    dur="0.9s"
                    repeatCount="indefinite"
                  />
                )}
              </path>
              {flowing && !e.reject && !reduced && (
                <circle r={2.2} fill="var(--brand)">
                  <animateMotion
                    dur={`${Math.max(len / 90, 1.4).toFixed(2)}s`}
                    begin={`${(i % 7) * 0.35}s`}
                    repeatCount="indefinite"
                  >
                    <mpath href={`#${id}`} />
                  </animateMotion>
                </circle>
              )}
              {fired && !reduced && (
                <circle r={2.2} fill="var(--bear)">
                  <animateMotion dur="1.8s" repeatCount="indefinite">
                    <mpath href={`#${id}`} />
                  </animateMotion>
                </circle>
              )}
            </g>
          );
        })}

        {/* stations, painted back-to-front */}
        {[...STATIONS]
          .sort((s1, s2) => s1.x + s1.y - (s2.x + s2.y))
          .map((st) => (
            <Slab
              key={st.id}
              st={st}
              view={views.get(st.id)!}
              reduced={reduced}
              selected={selected === st.id}
              onSelect={() => setSelected(st.id)}
              onHover={(on) =>
                setHovered((h) => (on ? st.id : h === st.id ? null : h))
              }
            />
          ))}

        {/* verdict pill beaconed above execution (last-run mode) */}
        {verdict && (
          <g aria-hidden>
            <line
              x1={execTop.x}
              y1={execTop.y - 46}
              x2={execTop.x}
              y2={execTop.y - 8}
              stroke={TINT_VAR[verdict.tint]}
              strokeOpacity={0.5}
              strokeWidth={1}
              strokeDasharray="2 3"
            />
            <rect
              x={execTop.x - 46}
              y={execTop.y - 68}
              width={92}
              height={22}
              rx={11}
              fill="var(--surface-solid)"
              stroke={TINT_VAR[verdict.tint]}
              strokeWidth={1.2}
            />
            <text
              x={execTop.x}
              y={execTop.y - 53}
              textAnchor="middle"
              fontSize={11}
              fontWeight={700}
              fontFamily="var(--font-mono)"
              fill={TINT_VAR[verdict.tint]}
            >
              {verdict.action === "BUY" ? "▲" : verdict.action === "SELL" ? "▼" : "■"}{" "}
              {verdict.action}
              {verdict.confidence != null ? ` · ${verdict.confidence}` : ""}
            </text>
          </g>
        )}

        {/* hover tooltip — painted last, never captures the pointer */}
        {hoveredSt && hoveredView && (
          <g aria-hidden style={{ pointerEvents: "none" }}>
            {(() => {
              const cx = px(hoveredSt.x, hoveredSt.y);
              const { dy } = halfExtents(hoveredSt.a);
              const topY = py(hoveredSt.x, hoveredSt.y, hoveredSt.h) - dy;
              const text = hoveredView.decision;
              const w = Math.max(text.length * 6.2 + 18, 56);
              const tx = Math.min(Math.max(cx, w / 2 + 4), 1100 - w / 2 - 4);
              return (
                <>
                  <rect
                    x={tx - w / 2}
                    y={topY - 34}
                    width={w}
                    height={20}
                    rx={10}
                    fill="var(--surface-solid)"
                    stroke={
                      hoveredView.status === "queued"
                        ? "var(--border-strong)"
                        : TINT_VAR[hoveredView.tint]
                    }
                    strokeWidth={1.1}
                  />
                  <text
                    x={tx}
                    y={topY - 20}
                    textAnchor="middle"
                    fontSize={10}
                    fontFamily="var(--font-mono)"
                    fill="var(--fg)"
                  >
                    {text}
                  </text>
                </>
              );
            })()}
          </g>
        )}
      </svg>

      {/* detail bar: the selected stage's real output */}
      {selView && (
        <div
          data-testid="pipeline-detail"
          className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-[12px] border border-border bg-surface-2/60 px-3 py-2 text-xs"
        >
          <span
            className={cn(
              "rounded-full px-2 py-0.5 font-mono text-[10px] font-semibold",
              selView.status === "active"
                ? "bg-accent text-on-solid"
                : selView.status === "done"
                  ? sel.sink || selView.tint === "bear"
                    ? "bg-bear-muted text-bear"
                    : "bg-accent-muted text-accent"
                  : "bg-surface-2 text-fg-subtle",
            )}
          >
            {selView.status === "active"
              ? "running"
              : selView.status === "done"
                ? sel.sink
                  ? "terminal"
                  : "done"
                : "queued"}
          </span>
          <span className="font-semibold">
            {sel.label} — {sel.persona}
          </span>
          <span className="text-fg-subtle">
            {sel.role}
            {fmtLatency(selView.latency) != null && (
              <span className="font-mono"> · {fmtLatency(selView.latency)}</span>
            )}
          </span>
          {selView.output != null && selView.status !== "queued" && (
            <span className="min-w-0 flex-1 truncate text-fg-muted" title={selView.output}>
              {selView.decision !== "done" && (
                <span className="font-mono text-fg">
                  {selView.decision.replace(" · conf ", " · confidence ")}.{" "}
                </span>
              )}
              {selView.output}
            </span>
          )}
          {selView.output == null && selView.status !== "queued" && (
            <span className="font-mono text-fg-muted">{selView.decision}</span>
          )}
        </div>
      )}
    </div>
  );
}
