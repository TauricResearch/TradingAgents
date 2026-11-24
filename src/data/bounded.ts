// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * A bound on how much of an answer is read: past it, reading the body (as text, JSON or bytes) fails
 * with the caller's error and the rest is not downloaded.
 */

/** `response` with a body that fails with `overrun()` once it passes `maxBytes`. */
export function bounded(response: Response, maxBytes: number, overrun: () => Error): Response {
  if (!response.body) return response;
  let seen = 0;
  const body = response.body.pipeThrough(
    new TransformStream<Uint8Array, Uint8Array>({
      transform(chunk, controller) {
        seen += chunk.byteLength;
        if (seen > maxBytes) controller.error(overrun());
        else controller.enqueue(chunk);
      },
    }),
  );
  return new Response(body, {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers,
  });
}
