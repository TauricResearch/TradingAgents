/**
 * Defuddle Extension — Fetch any webpage as clean Markdown.
 *
 * Uses the hosted defuddle.md API: GET https://defuddle.md/<url>
 * Strips ads, navigation, cookies — returns only article content.
 */

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { Type } from "typebox";

const DEFUDDLE_BASE = "https://defuddle.md";
const FETCH_TIMEOUT_MS = 15_000;
const MAX_CONTENT_LEN = 100_000;

// Block private/internal URLs to prevent SSRF
const BLOCKED_PATTERNS = [
  /^https?:\/\/(localhost|127\.|0\.0\.0\.0)/i,
  /^https?:\/\/10\./i,
  /^https?:\/\/192\.168\./i,
  /^https?:\/\/172\.(1[6-9]|2\d|3[01])\./i,
  /^https?:\/\/169\.254\./i,
  /^(file|ftp|gopher|data):/i,
];

function isBlocked(url: string): boolean {
  return BLOCKED_PATTERNS.some((p) => p.test(url));
}

/**
 * Core fetch logic — shared between the tool and the command.
 */
async function fetchDefuddle(
  url: string,
  signal?: AbortSignal,
): Promise<{
  ok: boolean;
  text?: string;
  wordCount?: number;
  truncated?: boolean;
  error?: string;
  status?: number;
}> {
  if (!url || (!url.startsWith("http://") && !url.startsWith("https://"))) {
    return { ok: false, error: `Invalid URL: ${url}. Must start with http:// or https://` };
  }

  if (isBlocked(url)) {
    return { ok: false, error: `Blocked: ${url} is a private/internal URL.` };
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  signal?.addEventListener("abort", () => controller.abort());

  try {
    const resp = await fetch(`${DEFUDDLE_BASE}/${url}`, {
      signal: controller.signal,
      headers: { Accept: "text/plain" },
    });

    if (!resp.ok) {
      return { ok: false, error: `HTTP ${resp.status}`, status: resp.status };
    }

    let text = await resp.text();
    const truncated = text.length > MAX_CONTENT_LEN;
    if (truncated) text = text.slice(0, MAX_CONTENT_LEN) + "\n\n[Content truncated]";

    if (text.trim().length < 50) {
      return {
        ok: false,
        error: "Minimal content returned — page may be JS-rendered or not an article.",
        truncated,
      };
    }

    return { ok: true, text, wordCount: text.split(/\s+/).length, truncated };
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return { ok: false, error: `Fetch failed: ${message}` };
  } finally {
    clearTimeout(timeout);
  }
}

export default function (pi: ExtensionAPI) {
  pi.registerTool({
    name: "defuddle",
    label: "Defuddle",
    description:
      "Fetch a webpage URL and return its main content as clean Markdown. Strips ads, navigation, and sidebar clutter.",
    parameters: Type.Object({
      url: Type.String({
        description:
          "Full HTTP(S) URL of the webpage to fetch and convert to Markdown",
      }),
    }),
    promptSnippet: "Fetch webpage content as clean Markdown",
    promptGuidelines: [
      "Use defuddle to read full article content from URLs found in search results, news feeds, or documentation pages.",
      "Prefer defuddle over read or web_fetch when you need cleaned article content rather than raw HTML.",
    ],

    async execute(_toolCallId, params, signal) {
      const result = await fetchDefuddle(params.url, signal);

      if (!result.ok) {
        return {
          content: [{ type: "text", text: result.error! }],
          details: { error: result.error, status: result.status },
          isError: true,
        };
      }

      return {
        content: [{ type: "text", text: result.text! }],
        details: {
          url: params.url,
          wordCount: result.wordCount,
          truncated: result.truncated,
        },
      };
    },
  });

  pi.registerCommand("defuddle", {
    description: "Fetch a webpage URL and display its main content as clean Markdown",
    handler: async (args, ctx) => {
      const url = args?.trim();
      if (!url) {
        ctx.ui.notify("Usage: /defuddle <url>", "error");
        return;
      }

      ctx.ui.setStatus("defuddle", "Fetching…");
      const result = await fetchDefuddle(url);
      ctx.ui.setStatus("defuddle", undefined);

      if (!result.ok) {
        ctx.ui.notify(`Defuddle failed: ${result.error}`, "error");
        return;
      }

      const summary = `${result.wordCount} words` + (result.truncated ? " (truncated)" : "");
      ctx.ui.notify(`defuddle ${url} — ${summary}`, "success");

      // Inject the content as a steer message so the agent can see it
      pi.sendUserMessage(`Here is the content of ${url}:\n\n${result.text}`, {
        deliverAs: "followUp",
      });
    },
  });
}
