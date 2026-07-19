/**
 * G1 - 13 custom inline SVG icon path bundles, ported verbatim from the
 * approved V2 mockup (.superpowers/brainstorm/20260717-tradingagents-web/
 * workbench-v2.html). One coherent visual language: shared 24x24 viewBox,
 * stroke-based, no fill. The icon_id keys match RoleDefinition.icon_id in
 * state/model.ts (which mirrors tradingagents/observability/roles.py).
 *
 * Each bundle is the list of SVG child elements (<path>/<circle>) inside the
 * <symbol>. RoleIcon renders them with stroke=currentColor so the icon
 * inherits the team color (green/red for bull/bear, cyan for risk, gold for
 * evidence/portfolio, blue default).
 */
import type { ReactNode } from "react";

export interface IconBundle {
  /** SVG child elements rendered inside the 24x24 viewBox. */
  children: ReactNode;
}

/** icon_id -> SVG path bundle. Exactly 13 entries, one per role. */
export const ROLE_ICON_PATHS: Record<string, IconBundle> = {
  "chart-bars": {
    children: (
      <>
        <path d="M4 19V9m5 8V5m5 14v-7m5 5V3" />
        <path d="M2 19h20" />
      </>
    ),
  },
  "speech-pulse": {
    children: (
      <>
        <path d="M4 17h3l2-5 3 8 3-13 2 10h3" />
        <path d="M5 4h14a2 2 0 0 1 2 2v14H7l-4 3V6a2 2 0 0 1 2-2Z" />
      </>
    ),
  },
  newspaper: {
    children: (
      <>
        <path d="M4 5h13v15H4z" />
        <path d="M17 8h3v10a2 2 0 0 1-2 2M7 9h7M7 13h7M7 17h4" />
      </>
    ),
  },
  "institution-columns": {
    children: (
      <path d="M3 21h18M5 18V9m5 9V9m4 9V9m5 9V9M3 7l9-4 9 4z" />
    ),
  },
  "verified-magnifier": {
    children: (
      <>
        <circle cx="10" cy="10" r="6" />
        <path d="m14.5 14.5 5 5M7.5 10l1.7 1.7L13 8" />
      </>
    ),
  },
  "rising-horn": {
    children: (
      <>
        <path d="M4 18 9 13l3 3 7-8" />
        <path d="M14 8h5v5M5 8c1-3 4-4 7-2 3-2 6-1 7 2" />
      </>
    ),
  },
  "falling-paw": {
    children: (
      <>
        <path d="m4 6 5 5 3-3 7 8" />
        <path d="M14 16h5v-5M6 18l2-3m8 3-2-3" />
        <circle cx="7" cy="7" r="2" />
        <circle cx="17" cy="7" r="2" />
      </>
    ),
  },
  scales: {
    children: (
      <path d="M12 3v18M5 6h14M7 6l-4 7h8L7 6Zm10 0-4 7h8l-4-7ZM8 21h8" />
    ),
  },
  "opposing-arrows": {
    children: (
      <path d="M4 7h14M14 3l4 4-4 4M20 17H6m4-4-4 4 4 4" />
    ),
  },
  lightning: {
    children: <path d="m13 2-8 12h7l-1 8 8-12h-7z" />,
  },
  "centered-crosshair": {
    children: (
      <>
        <path d="M4 12h16M12 4v16" />
        <circle cx="12" cy="12" r="9" />
      </>
    ),
  },
  shield: {
    children: (
      <>
        <path d="M12 3 5 6v5c0 5 3 8 7 10 4-2 7-5 7-10V6z" />
        <path d="m9 12 2 2 4-5" />
      </>
    ),
  },
  "portfolio-compass": {
    children: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 3v9h9M12 12l-6 6" />
      </>
    ),
  },
};

/** Number of distinct icon bundles; must equal the 13-role registry. */
export const ICON_COUNT = Object.keys(ROLE_ICON_PATHS).length;
