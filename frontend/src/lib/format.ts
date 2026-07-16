/** Display formatting only — the backend computes every trading number
 * (Constraint 2); these helpers never derive new quantities. */

export function fmtPrice(value: number | null | undefined, digits = 2): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function fmtPnl(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${fmtPrice(value)}`;
}

export function fmtPct(fraction: number | null | undefined, digits = 1): string {
  if (fraction == null || Number.isNaN(fraction)) return "—";
  return `${(fraction * 100).toFixed(digits)}%`;
}

/** Metric-aware display: funding rates as %/8h with the annualized figure,
 * tiny fractions as plain decimals — never scientific notation (trader
 * review: "FUNDING RATE 8.57e-5" is a formatting fail, not a reading). */
export function fmtMetricValue(
  name: string,
  value: number | null | undefined,
): string {
  if (value == null || Number.isNaN(value)) return "—";
  if (/FUNDING/i.test(name)) {
    // per-8h fraction (Binance convention: 3 windows/day)
    const pct = value * 100;
    return `${pct.toFixed(4)}%/8h · ${(pct * 3 * 365).toFixed(1)}% ann.`;
  }
  const abs = Math.abs(value);
  if (abs !== 0 && abs < 0.01) {
    const decimals = Math.min(8, Math.ceil(-Math.log10(abs)) + 2);
    return value.toFixed(decimals);
  }
  return fmtPrice(value, 2);
}

/** Short local timezone label ("IST", "GMT+5:30", ...) — every clock in a
 * cross-session product must say WHICH 22:41 it is (trader review G10). */
export const TZ_LABEL: string =
  new Intl.DateTimeFormat(undefined, { timeZoneName: "short" })
    .formatToParts(new Date())
    .find((part) => part.type === "timeZoneName")?.value ?? "";

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return `${date.toLocaleTimeString()}${TZ_LABEL ? ` ${TZ_LABEL}` : ""}`;
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return `${date.toLocaleDateString()} ${date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  })}${TZ_LABEL ? ` ${TZ_LABEL}` : ""}`;
}

/** Compact "MM/DD HH:MM" for dense lists like the run rail (mockup parity)
 * — no year, no timezone; the precise, TZ-qualified stamp lives in the
 * verdict header where there's room for it. */
export function fmtDateCompact(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  const md = date.toLocaleDateString([], { month: "2-digit", day: "2-digit" });
  const hm = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return `${md} ${hm}`;
}

export function relativeAge(iso: string | null | undefined): string {
  if (!iso) return "—";
  const ms = Date.now() - new Date(iso).getTime();
  if (Number.isNaN(ms)) return "—";
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export type Direction = "bull" | "bear" | "neutral";

/** Canonical direction mapping — glyph + word + color travel together
 * (A11Y-01: never color alone). */
export function directionOf(value: string | null | undefined): Direction {
  const v = (value ?? "").toLowerCase();
  if (["bull", "bullish", "buy", "long"].includes(v)) return "bull";
  if (["bear", "bearish", "sell", "short"].includes(v)) return "bear";
  return "neutral";
}

export const DIRECTION_GLYPH: Record<Direction, string> = {
  bull: "▲",
  bear: "▼",
  neutral: "–",
};
