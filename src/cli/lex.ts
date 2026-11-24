// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * An answer's Markdown as tokens, read the same for the transcript (markdown.ts) and the report
 * (report/layout.ts): GitHub-flavored, with definition lines read as their term's value.
 */
import { lexer, type TokensList } from "marked";

export function lexAnswer(source: string): TokensList {
  return lexer(joinDefinitions(source), { gfm: true });
}

/** A definition line, as some models write one under its term: ": $180.12, down 3.1%". */
const DEFINITION = /^ {0,3}:[ \t]+(\S.*)$/;
const FENCE = /^ {0,3}(`{3,}|~{3,})/;

/**
 * `source` with each definition line joined to its term ("Nov. 20 close: $180.12, down 3.1%"), a second
 * definition of the same term after a semicolon. GitHub-flavored Markdown has no definition lists, so the
 * lines would show with their colons as written. A blank line between a term and its definition is
 * dropped; code is left as it is.
 */
function joinDefinitions(source: string): string {
  if (!source.includes(":")) return source;
  const out: string[] = [];
  let fence: string | undefined;
  // Whether the last line out is a term that has a definition already.
  let defined = false;
  for (const line of source.split("\n")) {
    const opens = FENCE.exec(line)?.[1];
    if (fence) {
      if (opens?.startsWith(fence)) fence = undefined;
      out.push(line);
      continue;
    }
    if (opens) {
      fence = opens;
      defined = false;
      out.push(line);
      continue;
    }
    const definition = DEFINITION.exec(line)?.[1];
    const blank = out.at(-1)?.trim() === "" && out.length > 1;
    const term = blank ? out.at(-2) : out.at(-1);
    if (definition && term?.trim() && !FENCE.test(term) && !/^\s*[|>#]/.test(term)) {
      if (blank) out.pop();
      out[out.length - 1] = `${term.trimEnd()}${defined ? ";" : ":"} ${definition}`;
      defined = true;
      continue;
    }
    defined = false;
    out.push(line);
  }
  return out.join("\n");
}
