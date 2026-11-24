// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Where a streaming answer can be cut so its head is final: written to the scrollback once, it renders
 * the same as it would within the whole answer. Two kinds of cut: at the last blank line outside a
 * code block (before a line that starts a new block, not an indented continuation), and inside an
 * open code block after its last finished line, since code renders line by line.
 */

/** A code fence line: up to three spaces, then three or more backticks or tildes. */
const FENCE = /^ {0,3}(`{3,}|~{3,})(.*)$/;

type Split = {
  /** The final head, as Markdown that renders on its own (a code block it is in reopened and closed). */
  head: string;
  /** What is still being written. */
  rest: string;
  /** The code fence `rest` is inside, which renders it (and is not part of it). */
  restFence?: string;
};

/** A list item's first line: a bullet or a number, then a space. */
const LIST_ITEM = /^ {0,3}(?:[-*+]|\d{1,9}[.)])[ \t]/;

/** Whether `fence` closes a code block opened by `opener`: the same character, as many or more, nothing else. */
function closes(line: string, opener: string): boolean {
  const marker = FENCE.exec(line);
  const open = FENCE.exec(opener);
  return (
    marker?.[1] !== undefined &&
    open?.[1] !== undefined &&
    marker[1][0] === open[1][0] &&
    marker[1].length >= open[1].length &&
    !marker[2]?.trim()
  );
}

type Scan = {
  /** The code fence open at the end of the finished lines, if any. */
  open?: string;
  /** The blank lines of the last cut outside code, and where the line after them starts. */
  blankCut?: { at: number; next: number };
  /** After the last finished line of a top-level code block that has a line of code. */
  codeCut?: number;
  /** Where a reopened code block closed with no code in this text, and the text after it starts. */
  emptyClose?: number;
};

/** Read `text`'s finished lines (its last line may still be being written), starting inside `fence`. */
function scan(text: string, fence?: string): Scan {
  let open = fence;
  let blankCut: Scan["blankCut"];
  let codeCut: number | undefined;
  let emptyClose: number | undefined;
  let code = false;
  // Where the blank lines before the current line began, outside code, and the last line before them.
  let blankAt: number | undefined;
  let before = "";
  let previous = "";
  for (let lineStart = 0; lineStart < text.length; ) {
    const end = text.indexOf("\n", lineStart);
    const line = text.slice(lineStart, end < 0 ? undefined : end);
    // A line after blank lines that has begun makes the blank lines a cut when it starts a block of its
    // own: not an indented continuation, and not a list item after a list (the list may go on, loose).
    if (blankAt !== undefined && line.trim()) {
      const indented = /^[ \t]/.test(line);
      const listGoesOn = LIST_ITEM.test(line) && (LIST_ITEM.test(before) || /^[ \t]/.test(before));
      if (!indented && !listGoesOn) blankCut = { at: blankAt, next: lineStart };
      blankAt = undefined;
    }
    // The last line is still being written: it cannot be judged yet.
    if (end < 0) break;
    const next = end + 1;
    if (open) {
      if (closes(line, open)) {
        if (!code && open === fence && emptyClose === undefined) emptyClose = next;
        open = undefined;
        codeCut = undefined;
      } else if (line.trim()) {
        code = true;
        // Only a top-level block is cut: one inside a list item would lose its indentation reopened.
        if (!/^\s/.test(open)) codeCut = next;
      }
    } else if (FENCE.test(line)) {
      open = line;
      code = false;
      codeCut = undefined;
    } else if (!line.trim()) {
      if (blankAt === undefined) before = previous;
      blankAt ??= lineStart;
    }
    if (line.trim()) previous = line;
    lineStart = next;
  }
  return {
    ...(open !== undefined ? { open } : {}),
    ...(blankCut ? { blankCut } : {}),
    ...(codeCut !== undefined ? { codeCut } : {}),
    ...(emptyClose !== undefined ? { emptyClose } : {}),
  };
}

/** The code fence open at the end of `text`'s finished lines, starting inside `fence`. */
export function openFence(text: string, fence?: string): string | undefined {
  return scan(text, fence).open;
}

/**
 * The cut nearest the end of `text`, or undefined when no part of it is final yet. `fence` is the
 * opening line of a code block `text` starts inside (its head was cut off earlier).
 */
export function stableSplit(text: string, fence?: string): Split | undefined {
  const { open, blankCut, codeCut, emptyClose } = scan(text, fence);
  // A reopened block that closed with no more code: nothing of it to show, and what follows is ordinary.
  if (emptyClose !== undefined) return { head: "", rest: text.slice(emptyClose) };
  const reopen = (head: string) => (fence ? `${fence}\n${head}` : head);
  if (open && codeCut !== undefined && codeCut > (blankCut?.next ?? 0)) {
    const close = FENCE.exec(open)?.[1]?.trim() ?? "```";
    return {
      head: `${reopen(text.slice(0, codeCut))}${close}`,
      rest: text.slice(codeCut),
      restFence: open,
    };
  }
  if (blankCut) {
    // The head ends with its last line, not the line break before the blank line.
    return { head: reopen(text.slice(0, blankCut.at).replace(/\n$/, "")), rest: text.slice(blankCut.next) };
  }
  return undefined;
}
