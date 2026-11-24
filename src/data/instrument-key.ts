// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Instrument keys: a listed security by its ticker ("AAPL", "XNAS:AAPL") or a typed key naming its kind
 * ("security:AAPL", "future:XNYM:CL", "fx:EURUSD", "crypto:BTC-USDT", "series:us.equity_index.sp500").
 * Capabilities take either; providers route by the kind and answer only the kinds they serve.
 */

export const INSTRUMENT_KINDS = ["security", "future", "fx", "crypto", "series"] as const;
type InstrumentKind = (typeof INSTRUMENT_KINDS)[number];

/** A key read into its kind and the identifier within that kind. */
type ParsedInstrument = { kind: InstrumentKind; id: string };

/**
 * The kind and identifier a key names: a bare ticker is a security; a future's continuous series and
 * its family name the same contract root ("future:XNYM:CL/continuous" and "future:XNYM:CL").
 */
export function parseInstrument(key: string): ParsedInstrument {
  const typed = /^([a-z]+):(.+)$/i.exec(key.trim());
  const kind = typed?.[1]?.toLowerCase() as InstrumentKind | undefined;
  if (!typed || !kind || !INSTRUMENT_KINDS.includes(kind))
    return { kind: "security", id: key.trim().toUpperCase() };
  const id = typed[2] as string;
  if (kind === "series") return { kind, id: id.toLowerCase() };
  if (kind === "future") return { kind, id: id.replace(/\/continuous$/i, "").toUpperCase() };
  return { kind, id: id.toUpperCase() };
}

/** What each kind's identifier looks like, as the API spells it once parsed. */
const IDENTIFIERS: Record<InstrumentKind, RegExp> = {
  security: /^([A-Z0-9]{2,6}:)?[A-Z0-9][A-Z0-9.-]{0,14}$/,
  future: /^([A-Z0-9]{2,6}:)?[A-Z0-9]{1,6}$/,
  fx: /^[A-Z]{6}$/,
  crypto: /^[A-Z0-9]{1,15}-[A-Z0-9]{2,10}$/,
  series: /^[a-z0-9_]+(\.[a-z0-9_]+)+$/,
};

/** Whether `key` names an instrument as its kind spells one; a recognized prefix is never read as a ticker. */
export function isInstrumentKey(key: string): boolean {
  const prefixed = new RegExp(`^(${INSTRUMENT_KINDS.join("|")}):`, "i").test(key.trim());
  const parsed = parseInstrument(key);
  if (prefixed && parsed.kind === "security" && !/^security:/i.test(key.trim())) return false;
  if (parsed.kind === "future" && /\/(?!continuous$)/i.test(key)) return false;
  return IDENTIFIERS[parsed.kind].test(parsed.id);
}

/** The key written whole, in the form answers name it. */
export function instrumentKey({ kind, id }: ParsedInstrument): string {
  return `${kind}:${id}`;
}
