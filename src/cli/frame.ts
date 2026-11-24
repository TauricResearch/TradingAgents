// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * One row budget for the whole live frame. Ink redraws only what is still on screen, so the frame stays
 * within `rows - 1` (the last row is where the cursor waits). Rows go first to the input (it holds the
 * cursor), then the status row, then the footer or the menu under the input, then a row for the answer
 * being written, then the queue, then one blank row that sets the transcript apart from everything under
 * it (the queue or a hint, the status row, the input or a step), so exactly one blank row is above them; the
 * transcript's live rows get what is left. A short window drops the blank row before anything else.
 */
type FrameWants = {
  rows: number;
  /** The input's rows, rules included. */
  input: number;
  /** Whether a turn is under way (the status row is kept from send until it settles). */
  status: boolean;
  /**
   * Whether the blank row above the bottom area is wanted: always, unless what is above it ends in a blank
   * row of its own (a question's band, the welcome). The default is true.
   */
  gap?: boolean;
  /** The footer's row, or the menu's rows while it is open. */
  below: number;
  /** Whether an answer is being written: its newest row comes before the queue. */
  answer?: boolean;
  queue: number;
};

type FrameRows = {
  input: number;
  status: number;
  below: number;
  queue: number;
  /** The blank row above the queue and status row, while a turn runs. */
  gap: number;
  live: number;
};

export function frameRows({
  rows,
  input,
  status,
  gap = true,
  below,
  answer = false,
  queue,
}: FrameWants): FrameRows {
  let free = Math.max(0, rows - 1);
  const take = (wanted: number) => {
    const granted = Math.max(0, Math.min(wanted, free));
    free -= granted;
    return granted;
  };
  const granted = { input: take(input), status: take(status ? 1 : 0), below: take(below) };
  const kept = take(answer ? 1 : 0);
  const queued = take(queue);
  return { ...granted, queue: queued, gap: take(gap ? 1 : 0), live: free + kept };
}
