/**
 * G1 - Presentation layer over ROLE_REGISTRY for the 13-role workflow map.
 *
 * Pure data + pure functions: groups the 13 roles into the 3-row V2 grid
 * layout, provides Chinese display labels, and maps each role to the CSS
 * color class used on its .node-icon. No React, no side effects.
 *
 * Layout matches .superpowers/brainstorm/20260717-tradingagents-web/
 * workbench-v2.html:
 *   Row 1: 4 analysts (1 col each) + evidence.steward (wide = 2 cols) = 6
 *   Row 2: researcher.bull + researcher.bear (1 col each) + manager.research
 *          (wide) + trader (wide) = 6
 *   Row 3: 3 risk roles (1 col each) + manager.portfolio (wide) = 5
 * The grid is repeat(6, 1fr); row 3 leaves one cell empty, matching the
 * approved mockup exactly.
 */

// ---------------------------------------------------------------------------
// Stages
// ---------------------------------------------------------------------------

export type StageId =
  | "analysts"
  | "evidence"
  | "research"
  | "trading"
  | "risk"
  | "portfolio";

export interface StageDef {
  id: StageId;
  title: string;
  actor_ids: string[];
}

/**
 * Ordered stage definitions. The 6 stages map 1:1 to team_id values in
 * tradingagents/observability/roles.py and group the 13 roles for V2
 * section headers / filter chips.
 */
export const STAGES: StageDef[] = [
  {
    id: "analysts",
    title: "分析师团队",
    actor_ids: [
      "analyst.market",
      "analyst.sentiment",
      "analyst.news",
      "analyst.fundamentals",
    ],
  },
  { id: "evidence", title: "证据管理", actor_ids: ["evidence.steward"] },
  {
    id: "research",
    title: "多空研究",
    actor_ids: ["researcher.bull", "researcher.bear", "manager.research"],
  },
  { id: "trading", title: "交易", actor_ids: ["trader"] },
  {
    id: "risk",
    title: "风险管理",
    actor_ids: ["risk.aggressive", "risk.neutral", "risk.conservative"],
  },
  { id: "portfolio", title: "组合管理", actor_ids: ["manager.portfolio"] },
];

// ---------------------------------------------------------------------------
// Per-role layout entries
// ---------------------------------------------------------------------------

export interface RoleLayoutEntry {
  actor_id: string;
  stage: StageId;
  /** When true, the node spans 2 grid columns (.node.wide). */
  wide: boolean;
}

/**
 * 13 entries ordered for the 3-row V2 grid. Wide entries span 2 columns
 * (.node.wide). Column demand per row: row1=6, row2=6, row3=5.
 */
export const ROLE_LAYOUT: RoleLayoutEntry[] = [
  // Row 1: analysts (4) + evidence (wide)
  { actor_id: "analyst.market", stage: "analysts", wide: false },
  { actor_id: "analyst.sentiment", stage: "analysts", wide: false },
  { actor_id: "analyst.news", stage: "analysts", wide: false },
  { actor_id: "analyst.fundamentals", stage: "analysts", wide: false },
  { actor_id: "evidence.steward", stage: "evidence", wide: true },
  // Row 2: bull + bear + manager.research (wide) + trader (wide)
  { actor_id: "researcher.bull", stage: "research", wide: false },
  { actor_id: "researcher.bear", stage: "research", wide: false },
  { actor_id: "manager.research", stage: "research", wide: true },
  { actor_id: "trader", stage: "trading", wide: true },
  // Row 3: risk (3) + portfolio (wide)
  { actor_id: "risk.aggressive", stage: "risk", wide: false },
  { actor_id: "risk.neutral", stage: "risk", wide: false },
  { actor_id: "risk.conservative", stage: "risk", wide: false },
  { actor_id: "manager.portfolio", stage: "portfolio", wide: true },
];

/**
 * Rows for the 3-row grid. Row 1 = first 5 entries, row 2 = next 4,
 * row 3 = last 4. Total = 13.
 */
export const ROWS: RoleLayoutEntry[][] = [
  ROLE_LAYOUT.slice(0, 5),
  ROLE_LAYOUT.slice(5, 9),
  ROLE_LAYOUT.slice(9, 13),
];

// ---------------------------------------------------------------------------
// Chinese display labels (actor_id -> display name)
// ---------------------------------------------------------------------------

export const ROLE_LABELS_ZH: Record<string, string> = {
  "analyst.market": "市场分析师",
  "analyst.sentiment": "情绪分析师",
  "analyst.news": "新闻分析师",
  "analyst.fundamentals": "基本面分析师",
  "evidence.steward": "证据管理员",
  "researcher.bull": "多方研究员",
  "researcher.bear": "空方研究员",
  "manager.research": "研究经理",
  trader: "交易员",
  "risk.aggressive": "激进风险分析师",
  "risk.neutral": "中性风险分析师",
  "risk.conservative": "保守风险分析师",
  "manager.portfolio": "组合经理",
};

// ---------------------------------------------------------------------------
// Icon color class
// ---------------------------------------------------------------------------

/**
 * Returns the CSS modifier class for the .node-icon background/color.
 * Drives .node.bull / .node.bear / .node.risk in workbench.css.
 *
 * Maps by actor_id (NOT by StageId) because the "research" stage contains
 * both bull ('bull' / green) and bear ('bear' / red) plus manager (''),
 * which need distinct classes that a stage-level lookup cannot distinguish.
 *
 *   researcher.bull -> 'bull'
 *   researcher.bear -> 'bear'
 *   risk.*          -> 'risk'
 *   (everything else) -> ''
 */
export function stageColorClass(actor_id: string): string {
  if (actor_id === "researcher.bull") return "bull";
  if (actor_id === "researcher.bear") return "bear";
  if (actor_id.startsWith("risk.")) return "risk";
  return "";
}
