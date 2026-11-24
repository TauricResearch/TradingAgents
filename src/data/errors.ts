// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
import type { DataErrorKind } from "../contracts/index.js";

/**
 * Why a data source could not answer, one kind per way its caller reacts:
 *
 * - not_configured: no credential, or (code capability_unavailable) no source in this setup offers the
 *   data; try the next source without a request.
 * - rejected: the credential is refused or lacks access; try the next source.
 * - quota: the daily pool is spent until `resetsAt`; try the next source.
 * - rate_limited: too many requests now, for `retryAfterMs`; try the next source.
 * - unavailable: the source failed or answered in a form we do not read; try the next source.
 * - unsupported: this source cannot serve this instrument, listing, period or date (another may); try the next.
 * - no_data: the source has no answer for this request, which is an answer about the market; stop.
 * - invalid: the request itself must change (an ambiguous symbol, a bad range); tell the model.
 * - conflict: a session append started past the stored end; resend from `size`.
 * - diverged: another writer continued the session differently; fork a new one from `size`.
 * - full: the account's storage allowance is spent (`remainingBytes` left); stop writing.
 *
 * A failure of the source or its transport is never reported as a fact about the market.
 */
export type { DataErrorKind };

export type DataErrorDetails = {
  source: string;
  status?: number;
  code?: string;
  retryAfterMs?: number;
  resetsAt?: string;
  size?: number;
  /** The storage still free when the allowance is full. */
  remainingBytes?: number;
  /** The source's own advice: ask again later, never, or with a changed request. */
  retry?: "later" | "never" | "change_request";
  /** What an ambiguous symbol could mean, for the caller to choose from. */
  candidates?: { symbol: string; name: string }[];
};

/** Codes whose message tells the state of a listing now (a delisting, the end of coverage). */
export const LISTING_STATE_CODES: ReadonlySet<string> = new Set(["delisted"]);

export class DataError extends Error {
  override readonly name = "DataError";

  constructor(
    readonly kind: DataErrorKind,
    message: string,
    readonly details: DataErrorDetails,
  ) {
    super(message);
  }
}
