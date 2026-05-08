/**
 * Shared OpenRouter LLM substrate.
 *
 * Usage:
 *   import { llm } from "./lib/llm.ts";
 *
 *   const content = await llm([
 *     { role: "system", content: SYSTEM_PROMPT },
 *     { role: "user",   content: userText },
 *   ]);
 *
 * Options:
 *   temperature  (default: 0.2)
 *   maxTokens    (default: 4000)
 *   model        (default: google/gemini-2.5-flash-lite-preview-09-2025)
 *   title        (X-Title header for OpenRouter)
 *   referer      (HTTP-Referer header for OpenRouter)
 */

import { existsSync, readFileSync } from "node:fs"
import { join } from "node:path"

const API_URL = "https://openrouter.ai/api/v1/chat/completions"
const DEFAULT_MODEL = "google/gemini-2.5-flash-lite-preview-09-2025"

interface LlmMessage {
  role: "system" | "user"
  content: string
}

interface LlmOptions {
  temperature?: number
  maxTokens?: number
  model?: string
  title?: string
  referer?: string
}

function loadEnvOnce(): void {
  const envPath = join(process.cwd(), ".env")
  if (!existsSync(envPath)) return

  const text = readFileSync(envPath, "utf8")
  for (const line of text.split("\n")) {
    const idx = line.indexOf("=")
    if (idx === -1 || line.startsWith("#")) continue
    const key = line.slice(0, idx).trim()
    const val = line.slice(idx + 1).trim()
    if (key && !process.env[key]) process.env[key] = val
  }
}

loadEnvOnce()

const REQUEST_TIMEOUT_MS = 60_000

export async function llm(messages: LlmMessage[], opts: LlmOptions = {}): Promise<string> {
  const apiKey = process.env.OPENROUTER_API_KEY ?? ""
  if (!apiKey) throw new Error("OPENROUTER_API_KEY not set (checked .env and env)")

  const headers: Record<string, string> = {
    Authorization: `Bearer ${apiKey}`,
    "Content-Type": "application/json",
  }
  if (opts.title) headers["X-Title"] = opts.title
  if (opts.referer) headers["HTTP-Referer"] = opts.referer

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)

  try {
    const res = await fetch(API_URL, {
      method: "POST",
      headers,
      signal: controller.signal,
      body: JSON.stringify({
        model: opts.model ?? DEFAULT_MODEL,
        messages,
        temperature: opts.temperature ?? 0.2,
        max_tokens: opts.maxTokens ?? 4000,
      }),
    })

    if (!res.ok) {
      const err = await res.text()
      throw new Error(`OpenRouter ${res.status}: ${err.slice(0, 500)}`)
    }

    const data = (await res.json()) as {
      choices?: Array<{ message?: { content?: string } }>
    }

    const content = data?.choices?.[0]?.message?.content
    if (!content) throw new Error("LLM response missing content")
    return content
  } catch (e) {
    if (e instanceof Error && e.name === "AbortError") {
      throw new Error(`OpenRouter request timed out after ${REQUEST_TIMEOUT_MS}ms`)
    }
    throw e
  } finally {
    clearTimeout(timer)
  }
}
