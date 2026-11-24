// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/** What a caught error says, as text. */

/** The message of `error`, or its text when it is not an Error. */
export function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
