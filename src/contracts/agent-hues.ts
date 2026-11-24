// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Each built-in agent's colour, by hue: one source for the README's figure (its fills) and the terminal (its
 * names), so the two agree. A hue is an OKLCH hue angle; each surface sets its own lightness and chroma.
 * Risk is rose rather than red: in the terminal, red says something failed.
 */

/** The hues colours are drawn from, by name, as OKLCH hue angles. */
export const HUE_ANGLES = {
  red: 25,
  amber: 75,
  green: 145,
  teal: 195,
  blue: 250,
  rose: 350,
} as const;
export type HueName = keyof typeof HUE_ANGLES;

/** A built-in agent's hue; an agent of the user's own has none and takes the accent. */
export const AGENT_HUES = {
  equity: "blue",
  macro: "teal",
  quant: "green",
  risk: "rose",
} as const satisfies Record<string, HueName>;

/** The hue of agent `name` (its name as the catalog has it, "equity"), if it is a built-in one. */
export function agentHue(name: string): HueName | undefined {
  return (AGENT_HUES as Record<string, HueName>)[name];
}
