// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * What the terminal can show, decided once at startup so rows already written never change colour: how
 * many colours, whether the background is dark or light, the accent that reads on it (and plan mode's
 * amber beside it), and the shade that sets a question off. The accent marks chrome only (the prompt, the spinner, a finished row's mark);
 * text keeps the terminal's own foreground.
 */

import type { ChalkInstance } from "chalk";
import { agentHue, HUE_ANGLES, type HueName } from "../contracts/agent-hues.js";

type ColourLevel = "none" | "16" | "256" | "truecolor";
type Background = "dark" | "light" | "unknown";

export type Theme = {
  colours: ColourLevel;
  background: Background;
  /** An Ink colour for the accent, or undefined when colour is off. */
  accent: string | undefined;
  /** An Ink colour for plan mode, or undefined when colour is off. */
  plan: string | undefined;
  /** The question's background, a little off the terminal's own; undefined when that is not known. */
  shade?: string;
  /** Whether the terminal takes UTF-8 glyphs (the spinner and checks), else ASCII stand-ins. */
  unicode: boolean;
};

/** The accent per background: the brand green on dark, a deeper green on light, one between when unknown. */
const ACCENT: Record<Background, string> = { dark: "#14c290", light: "#0b8a66", unknown: "#0f9e75" };
/** Plan mode's amber per background: the accent's lightness and strength at the amber hue (OKLCH 75). */
const PLAN: Record<Background, string> = { dark: "#db9618", light: "#9c6a0f", unknown: "#b27a13" };

/** The terminal's colours and background from the environment it was started in. */
export function themeFrom(env: NodeJS.ProcessEnv): Theme {
  const colours = colourLevel(env);
  const index = backgroundIndex(env.COLORFGBG);
  const background = classify(index);
  const accent = colours === "none" ? undefined : colours === "16" ? "green" : ACCENT[background];
  const plan = colours === "none" ? undefined : colours === "16" ? "yellow" : PLAN[background];
  // The first locale variable set decides, as the C library reads them.
  const locale = [env.LC_ALL, env.LC_CTYPE, env.LANG].find((value) => value) ?? "";
  const unicode = env.TERM !== "linux" && (locale === "" || /utf-?8/i.test(locale));
  const shade = colours === "256" || colours === "truecolor" ? shadeOf(index) : undefined;
  return { colours, background, accent, plan, ...(shade ? { shade } : {}), unicode };
}

function colourLevel(env: NodeJS.ProcessEnv): ColourLevel {
  if (env.NO_COLOR !== undefined && env.NO_COLOR !== "") return "none";
  if (env.TERM === "dumb") return "none";
  if (env.COLORTERM === "truecolor" || env.COLORTERM === "24bit") return "truecolor";
  if (/256/.test(env.TERM ?? "")) return "256";
  return "16";
}

/** The background's palette index from `COLORFGBG` ("fg;bg", or "fg;x;bg"): the last field, 0-255. */
function backgroundIndex(colorfgbg: string | undefined): number | undefined {
  const last = colorfgbg?.split(";").at(-1);
  if (last === undefined || !/^\d+$/.test(last)) return undefined;
  const index = Number(last);
  return index <= 255 ? index : undefined;
}

/**
 * The palette colour as RGB, where it can be trusted: black, the greys and white of the 16 named colours
 * (the coloured ones are themed too freely to guess), and the fixed cube and grey ramp above them.
 */
function rgbOf(index: number): [number, number, number] | undefined {
  const named: Record<number, number> = { 0: 0, 7: 229, 8: 127, 15: 255 };
  if (index < 16) return named[index] === undefined ? undefined : [named[index], named[index], named[index]];
  if (index >= 232) {
    const level = 8 + 10 * (index - 232);
    return [level, level, level];
  }
  const steps = [0, 95, 135, 175, 215, 255];
  const cube = index - 16;
  return [steps[Math.floor(cube / 36)] ?? 0, steps[Math.floor(cube / 6) % 6] ?? 0, steps[cube % 6] ?? 0];
}

/** Dark or light: 7 and 9-15 are light among the 16 (the convention terminals follow), else by brightness. */
function classify(index: number | undefined): Background {
  if (index === undefined) return "unknown";
  if (index < 16) return index === 7 || index >= 9 ? "light" : "dark";
  const [r, g, b] = rgbOf(index) ?? [0, 0, 0];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 127.5 ? "light" : "dark";
}

/** The background blended 12% toward white when dark, 4% toward black when light. */
function shadeOf(index: number | undefined): string | undefined {
  const rgb = index === undefined ? undefined : rgbOf(index);
  if (!rgb || index === undefined) return undefined;
  const light = classify(index) === "light";
  const blend = (channel: number) => Math.round(light ? channel * 0.96 : channel + (255 - channel) * 0.12);
  return `#${rgb.map((channel) => blend(channel).toString(16).padStart(2, "0")).join("")}`;
}

/** The plain theme: no colour, Unicode glyphs; for tests and anything that sets its own. */
export const plainTheme: Theme = {
  colours: "none",
  background: "unknown",
  accent: undefined,
  plan: undefined,
  unicode: true,
};

/**
 * What a piece of text is, and so how it looks: components ask for a role, never a colour (the gate checks).
 * - `title`: a step's or list's heading, the question asked; `name`: an item's name; `selected`: the row the
 *   cursor is on.
 * - `detail`: everything that is not the thing itself (descriptions, sources, times, previews, hints).
 * - `success`, `warning`, `error`: a state; `accent`: the brand (the prompt, the spinner, matched letters);
 *   `plan`: plan mode; `code`: code in an answer.
 * Bold is for `title` and `selected` only; colour carries state; without colour every role still reads
 * through its glyph and its words.
 */
type RoleName =
  | "title"
  | "name"
  | "selected"
  | "detail"
  | "success"
  | "warning"
  | "error"
  | "accent"
  | "plan"
  | "code";

/** A role's look, as Ink's Text takes it. */
type Style = { color?: string; bold?: true; dimColor?: true; italic?: true };

export type Roles = Record<RoleName, Style>;

const roleCache = new WeakMap<Theme, Roles>();

/** The roles of `theme`, from its colour level, accent and plan colour. */
export function rolesOf(theme: Theme): Roles {
  const known = roleCache.get(theme);
  if (known) return known;
  const coloured = theme.colours !== "none";
  const tint = (color: string | undefined): Style => (coloured && color ? { color } : {});
  const roles: Roles = {
    title: { bold: true },
    name: {},
    selected: { ...tint(theme.accent), bold: true },
    detail: { dimColor: true },
    success: tint(theme.accent),
    warning: tint("yellow"),
    error: tint("red"),
    accent: tint(theme.accent),
    plan: tint(theme.plan),
    code: tint("cyan"),
  };
  roleCache.set(theme, roles);
  return roles;
}

/** The roles for text written through chalk without a theme at hand (an answer's Markdown): its level decides. */
export const TEXT_ROLES = {
  detail: { dimColor: true },
  code: { color: "cyan" },
} as const satisfies Partial<Roles>;

/** `text` in `role`'s look, through `style` (chalk at the terminal's level). */
export function paint(style: ChalkInstance, role: Style, text: string): string {
  let chain = style;
  if (role.color) chain = role.color.startsWith("#") ? chain.hex(role.color) : chain[role.color as "red"];
  if (role.bold) chain = chain.bold;
  if (role.dimColor) chain = chain.dim;
  if (role.italic) chain = chain.italic;
  return chain(text);
}

/** The hues' nearest of the 16 named colours, for a terminal with no more. */
const NAMED: Record<HueName, string> = {
  red: "red",
  amber: "yellow",
  green: "green",
  teal: "cyan",
  blue: "blue",
  rose: "magenta",
};

/**
 * The colour agent `name` is shown in: its hue (src/contracts/agent-hues.ts, the figure's too) at the accent's lightness
 * and strength on this background, so it reads like the accent; the accent for an agent of the user's own;
 * none without colour.
 */
export function agentColour(theme: Theme, name: string): string | undefined {
  if (theme.colours === "none") return undefined;
  const hue = agentHue(name);
  if (!hue) return theme.accent;
  if (theme.colours === "16") return NAMED[hue];
  const [lightness, chroma] = oklchOf(ACCENT[theme.background]);
  return inGamut(lightness, chroma, HUE_ANGLES[hue]);
}

// OKLCH, for colours derived from the accent (https://bottosson.github.io/posts/oklab/).
const linear = (channel: number) =>
  channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
const encoded = (value: number) =>
  Math.round(
    Math.min(1, Math.max(0, value <= 0.0031308 ? 12.92 * value : 1.055 * value ** (1 / 2.4) - 0.055)) * 255,
  );

/** A hex colour's OKLCH lightness and chroma. */
function oklchOf(hex: string): [number, number] {
  const [r, g, b] = [1, 3, 5].map((at) => linear(Number.parseInt(hex.slice(at, at + 2), 16) / 255)) as [
    number,
    number,
    number,
  ];
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  const a = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s;
  const bb = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s;
  return [0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s, Math.hypot(a, bb)];
}

/** The colour of OKLCH `lightness`, `chroma` and `hue`, its chroma lowered until it is in sRGB. */
function inGamut(lightness: number, chroma: number, hue: number): string {
  for (let c = chroma; ; c = Math.max(0, c - 0.002)) {
    const a = c * Math.cos((hue * Math.PI) / 180);
    const b = c * Math.sin((hue * Math.PI) / 180);
    const l = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3;
    const m = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3;
    const s = (lightness - 0.0894841775 * a - 1.291485548 * b) ** 3;
    const rgb = [
      4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
      -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
      -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
    ];
    if (c === 0 || rgb.every((value) => value >= -1e-4 && value <= 1 + 1e-4))
      return `#${rgb.map((value) => encoded(value).toString(16).padStart(2, "0")).join("")}`;
  }
}
