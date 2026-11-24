// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/** Technical indicators of one instrument with daily bars at its latest completed session. */
import { z } from "zod";
import { message } from "../contracts/index.js";
import type { Technicals, TechnicalsAnswer } from "../data/capabilities.js";
import { defineTool } from "./tool.js";
import { fieldNotes, instrument, instrumentLine, provenanceOf } from "./tool-text.js";

const num = (value: number | null | undefined, digits = 2) =>
  typeof value === "number" && Number.isFinite(value)
    ? (Math.round(value * 10 ** digits) / 10 ** digits).toString()
    : "n/a";

/** Dates listed up to a few, the rest counted, so a long list cannot crowd out the indicators. */
const LISTED = 10;
function dates(list: readonly string[]): string {
  return list.length > LISTED
    ? `${list.slice(0, LISTED).join(", ")} and ${list.length - LISTED} more`
    : list.join(", ");
}

/** The indicators as the source gives them, the instrument named in words. */
type Payload = Omit<TechnicalsAnswer, "instrument"> & { symbol: string; instrument: string };
const OUT = z.looseObject({ symbol: z.string(), instrument: z.string(), through: z.string().nullish() });

export function technicalsTool(technicals: Technicals) {
  return defineTool({
    name: "technicals",
    description:
      "Technical indicators of one US-listed security, futures contract or price series at its latest completed session: RSI, MACD, moving averages, " +
      "Bollinger bands, ATR, stochastics, ADX and others, each with its definition. Latest session only.",
    kind: "data",
    parallelSafe: true,
    input: z.object({ symbol: instrument }),
    output: OUT,
    async run({ symbol }, { signal }) {
      const sourced = await technicals.latest(symbol, { signal });
      const { instrument: described, ...indicators } = sourced.data;
      const payload: Payload = { symbol, instrument: instrumentLine(described), ...indicators };
      return {
        payload,
        provenance: provenanceOf(sourced, {
          subject: symbol,
          as_of: payload.through,
        }),
        summary: message("tool.technicals", { through: payload.through ?? "?" }),
      };
    },
    render(payload) {
      const t = payload as Payload;
      const window = t.window;
      const lines = [
        `${t.instrument}: technical indicators through ${t.through ?? "?"} (close ${num(t.last_value?.value)} on ${t.last_value?.date ?? "?"}), from ${window?.bars ?? "?"} daily bars, ${t.price_basis ?? "basis not stated"}`,
        `- RSI(14, Wilder): ${num(t.rsi)} (0-100; 30 and 70 are the customary thresholds)`,
        `- MACD(12, 26): line ${num(t.macd)}, signal (9-period EMA of the line) ${num(t.macd_signal)}, histogram ${num(t.macd_histogram)} (price units)`,
        `- moving averages: SMA 50 ${num(t.sma_50)}, SMA 200 ${num(t.sma_200)}, EMA 10 ${num(t.ema_10)}, EMA 50 ${num(t.ema_50)}; the close is ${t.price_vs_sma50 ?? "?"} SMA 50 and ${t.price_vs_sma200 ?? "?"} SMA 200; SMA 50 is ${t.sma50_vs_sma200 ?? "?"} SMA 200`,
        `- Bollinger (20, 2 standard deviations): upper ${num(t.bb_upper)}, middle ${num(t.bb_middle)}, lower ${num(t.bb_lower)}`,
        `- average true range: ATR(14) ${num(t.atr)}, ATR(5) ${num(t.atr_5)}`,
        `- stochastic (KDJ, 9-period): %K ${num(t.stochastic_k)}, %D ${num(t.stochastic_d)}; CCI(14) ${num(t.cci)}; ADX(14) ${num(t.adx)}`,
        `- z-score of the close against 75 sessions: ${num(t.z_score_75)}; one-session change ${num(t.roc)}%`,
        t.volume_available === true
          ? `- volume: MFI(14) ${num(t.mfi)}, VWMA(20) ${num(t.vwma)}, PVO(12, 26) ${num(t.pvo)}%`
          : t.volume_available === false
            ? "- volume-based indicators (MFI, VWMA, PVO): not given, volume is not available for this instrument"
            : "- volume-based indicators (MFI, VWMA, PVO): not given, the source does not say whether volume is available",
      ];
      if (window?.settled_through && t.through && window.settled_through < t.through) {
        lines.push(`sessions after ${window.settled_through} are not settled yet (values may still change)`);
      }
      if (window?.missing?.length)
        lines.push(
          `sessions left out of the computation: ${dates(window.missing.map((m) => `${m.date}${m.reason ? ` (${m.reason})` : ""}`))}`,
        );
      const notes = fieldNotes(t.field_states);
      if (notes && t.history_rows !== null && t.history_rows !== undefined) {
        lines.push(
          `not enough history: ${t.history_rows} daily rows, ${t.rows_needed ?? "?"} needed (${notes})`,
        );
      }
      return lines;
    },
  });
}
