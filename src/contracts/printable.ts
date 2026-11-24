// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Text from the model or a data source, made safe to print: control characters (escape sequences
 * that restyle, hide text, set titles or links) and invisible format characters (bidirectional
 * overrides, zero-width spaces) are removed; line breaks, tabs and the joiners emoji and some
 * scripts are written with stay.
 */
export function printable(text: string): string {
  let out = "";
  for (const character of text) {
    const code = character.codePointAt(0) ?? 0;
    const control = code < 0x20 || (code >= 0x7f && code <= 0x9f);
    const format = FORMAT.test(character) && code !== 0x200c && code !== 0x200d;
    if ((!control && !format) || character === "\n" || character === "\t") out += character;
  }
  return out;
}

const FORMAT = /^\p{Cf}$/u;
