/** Pure oscillator-pane helpers (G1): conventional reference levels and
 * the MACD line/signal cross state. Both render the sign/threshold of
 * server-provided values against fixed conventional constants — no
 * indicator math (Constraint 2). Kept out of PriceChart so they're
 * unit-testable without pulling in lightweight-charts. */

/** Conventional reference levels per oscillator. `mid` renders fainter. */
export function oscillatorLevels(
  name: string,
): { price: number; mid?: boolean }[] {
  if (name.startsWith("RSI_"))
    return [{ price: 70 }, { price: 50, mid: true }, { price: 30 }];
  if (name === "MACD") return [{ price: 0, mid: true }];
  if (name === "STOCH") return [{ price: 80 }, { price: 20 }];
  if (name.startsWith("CCI_")) return [{ price: 100 }, { price: -100 }];
  if (name.startsWith("WILLR_")) return [{ price: -20 }, { price: -80 }];
  if (name === "ADX") return [{ price: 25, mid: true }];
  return [];
}

/** "bull cross" / "bear cross" when the served MACD and signal lines swap
 * order on the last bar; else "bullish"/"bearish" by their last ordering;
 * null when there isn't enough aligned data. A comparison of two server
 * values at their shared last timestamp — no indicator math. */
export function macdCrossLabel(
  macd: { time: number; value: number }[],
  signal: { time: number; value: number }[],
): string | null {
  if (macd.length < 2 || signal.length < 2) return null;
  const sig = new Map(signal.map((p) => [p.time, p.value]));
  const m1 = macd[macd.length - 1]!;
  const m0 = macd[macd.length - 2]!;
  const s1 = sig.get(m1.time);
  const s0 = sig.get(m0.time);
  if (s0 == null || s1 == null) return null;
  if (m0.value <= s0 && m1.value > s1) return "bull cross";
  if (m0.value >= s0 && m1.value < s1) return "bear cross";
  return m1.value >= s1 ? "bullish" : "bearish";
}
