// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The status row: one row directly above the input while a turn runs, saying what it is doing, for how long,
 * and how to stop it: `⠋ Thinking… (52s | deep in thought | esc to stop)`. When the window is narrow, the
 * long-think phrase goes first, then the time; the stop hint stays longest.
 */
import { Text, useWindowSize } from "ink";
import { useEffect, useState } from "react";
import stringWidth from "string-width";
import { message } from "../contracts/index.js";
import { runningDuration, SEPARATOR, SPINNER_MS, spinnerFrame } from "./rows.js";
import { useRoles, useTheme } from "./theme-context.js";
import { phaseOf, type TranscriptState } from "./transcript-state.js";

const PHASE = {
  stopping: "app.stopping",
  summarizing: "app.phaseSummarizing",
  fetching: "app.phaseFetching",
  thinking: "app.phaseThinking",
  writing: "app.phaseWriting",
  working: "app.phaseWorking",
  reconnecting: "app.phaseReconnecting",
} as const;

/** A think this long earns a word on the status row. */
const LONG_THINK_S = 10;

/** The status row's text after the spinner, fitted to `width` cells. */
export function statusText(
  state: TranscriptState,
  {
    now,
    stopping,
    width,
    stoppable = true,
  }: { now: number; stopping: boolean; width: number; stoppable?: boolean },
): string {
  const phase = phaseOf(state, stopping);
  const label = message(PHASE[phase]);
  const since = state.status.since;
  const elapsed = since !== undefined && now - since >= 1_000 ? runningDuration(now - since) : "";
  const thought =
    state.live.thinkingSince !== undefined ? Math.floor((now - state.live.thinkingSince) / 1_000) : 0;
  const long =
    phase === "thinking" && thought >= LONG_THINK_S ? message("app.thinkingLong", { seconds: thought }) : "";
  const hint = phase === "stopping" || !stoppable ? "" : message("app.escToStop");
  const retrying = state.live.retrying;
  const retry =
    phase === "reconnecting" && retrying?.attempt !== undefined && retrying.of !== undefined
      ? message("app.retryOf", { attempt: retrying.attempt, of: retrying.of })
      : "";
  // Fuller first; each next form drops what matters least.
  const forms = [[retry, elapsed, long, hint], [retry, elapsed, hint], [retry, hint], [hint], []].map(
    (details) => {
      const shown = details.filter(Boolean);
      return shown.length ? `${label} (${shown.join(SEPARATOR)})` : label;
    },
  );
  return forms.find((form) => stringWidth(form) <= width) ?? label;
}

/** `stoppable`: whether Esc stops the turn here (a replay cannot be stopped). */
export function StatusRow({
  state,
  stopping,
  stoppable = true,
}: {
  state: TranscriptState;
  stopping: boolean;
  stoppable?: boolean;
}) {
  const { columns } = useWindowSize();
  const { unicode } = useTheme();
  const roles = useRoles();
  // The spinner moves and the time goes up while the row is shown.
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), SPINNER_MS); // not a limit: the spinner's pace
    return () => clearInterval(timer);
  }, []);
  return (
    <Text wrap="truncate">
      <Text {...roles.accent}>{spinnerFrame(now, unicode)}</Text>{" "}
      <Text {...roles.detail}>
        {statusText(state, { now, stopping, stoppable, width: Math.max(1, columns - 2) })}
      </Text>
    </Text>
  );
}
