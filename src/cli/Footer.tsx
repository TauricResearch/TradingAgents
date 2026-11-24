// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The footer: one dim row under the input, always there, so the layout never jumps. On the left, the mode
 * questions are asked in and the key that switches it; on the right, the model that answers and the
 * version. What a turn is doing is the status row's, and what it took is written at its end. In a narrow
 * window the key's hint goes first, then the model is cut and then goes; the mode and the version stay.
 */
import { Text } from "ink";
import stringWidth from "string-width";
import { APP_TITLE, type Mode, message } from "../contracts/index.js";
import { cut, oneLine, SEPARATOR } from "./rows.js";
import { useRoles } from "./theme-context.js";
import type { TranscriptState } from "./transcript-state.js";

/** Cells before the footer's text, as under the input's prompt. */
const INDENT = 2;
/** The fewest cells between the left side and the right. */
const GAP = 2;
/** A model name is cut no shorter than this; below it, it goes. */
const MODEL_MIN = 8;

/** `mode` absent (a replay takes no questions): the right side alone, from the left. */
export type FooterFacts = { mode?: Mode; model?: string; version?: string };

/** The footer's sides fitted to `width` cells: the mode (and its hint), the spaces, then the rest. */
type FooterLine = { mode: string; hint: string; gap: number; right: string };

/** What the footer shows in `width` cells (its indent included), dropping items in the order above. */
export function footerLine({ mode, model, version }: FooterFacts, width: number): FooterLine {
  const room = Math.max(0, width - INDENT);
  const label = mode ? message("app.mode", { mode }) : "";
  const name = model ? oneLine(model) : "";
  const release = version ? `${APP_TITLE} ${oneLine(version)}` : "";
  const fits = (left: string, right: string) =>
    stringWidth(left) + (left && right ? GAP : 0) + stringWidth(right) <= room;
  const line = (hint: string, right: string): FooterLine => {
    const used = stringWidth(label + hint) + stringWidth(right);
    return { mode: label, hint, gap: label && right ? room - used : 0, right };
  };
  const both = [name, release].filter(Boolean).join(SEPARATOR);
  const hint = mode ? ` (${message("app.modeSwitch")})` : "";
  if (fits(label + hint, both)) return line(hint, both);
  if (fits(label, both)) return line("", both);
  // The model cut to what is left beside the version, while enough of it is left to tell; else it goes.
  const tail = release ? `${SEPARATOR}${release}` : "";
  const left = room - stringWidth(label) - (label ? GAP : 0) - stringWidth(tail);
  if (name && left >= MODEL_MIN) return line("", `${cut(name, left)}${tail}`);
  if (fits(label, release)) return line("", release);
  // Too narrow for both: the mode, then the version, each cut to the room.
  if (label) return { mode: cut(label, Math.max(1, room)), hint: "", gap: 0, right: "" };
  return { mode: "", hint: "", gap: 0, right: release ? cut(release, Math.max(1, room)) : "" };
}

/**
 * The footer for `state` in `columns`: `model` the configured one, which a replayed session's own does not
 * replace.
 */
export function Footer({
  state,
  columns,
  mode,
  model,
  version,
}: {
  state: TranscriptState;
  columns: number;
  mode?: Mode | undefined;
  model?: string | undefined;
  version?: string | undefined;
}) {
  const roles = useRoles();
  const shownModel = model || state.status.model;
  const line = footerLine(
    {
      ...(mode ? { mode } : {}),
      ...(shownModel ? { model: shownModel } : {}),
      ...(version ? { version } : {}),
    },
    columns,
  );
  // The mode in its own role: auto in the accent, plan in its amber.
  const modeRole = mode === "plan" ? roles.plan : roles.accent;
  return (
    <Text wrap="truncate">
      {" ".repeat(INDENT)}
      <Text {...modeRole}>{line.mode}</Text>
      <Text {...roles.detail}>
        {line.hint}
        {" ".repeat(line.gap)}
        {line.right}
      </Text>
    </Text>
  );
}
