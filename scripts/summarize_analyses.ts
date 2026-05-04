#!/usr/bin/env bun
/**
 * Generate LLM summaries for all analyses that don't have one yet.
 *
 * Usage:
 *   bun run scripts/summarize_analyses.ts           # Unsaved analyses only
 *   bun run scripts/summarize_analyses.ts --ticker TKA.DE   # One ticker
 *   bun run scripts/summarize_analyses.ts --all             # Regenerate all
 *
 * Pipeline:
 *   1. Scan $TRADINGAGENTS_RESULTS_DIR/ for full_states_log_*.json
 *   2. Skip if summary_*.json already exists (cached)
 *   3. Call OpenRouter API → structured summary
 *   4. Write summary_*.json alongside the log file
 */

import { readdirSync, readFileSync, writeFileSync, existsSync } from "fs";
import { join, basename } from "path";
import { homedir } from "os";

const LOGS_DIR =
  process.env.TRADINGAGENTS_RESULTS_DIR ??
  join(homedir(), ".tradingagents", "logs");

const OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions";
const MODEL = process.env.SUMMARY_MODEL ?? "openai/gpt-4.4-mini";

const SYSTEM_PROMPT = `You are a financial analyst explaining trading decisions in plain English.
Given an analysis decision, extract these fields as JSON:
- signal: the recommendation (Buy/Hold/Sell/Overweight/Underweight)
- confidence: 0-1 number
- position_size: recommended position sizing
- entry_strategy: how and when to enter the position
- risk_management: stop losses, invalidation levels, risk controls
- time_horizon: expected holding period
- catalysts: what events or conditions to monitor
- risks: key risk factors
- plain_english: a 2-3 sentence explanation of what this means for an investor

Respond with ONLY valid JSON. No markdown, no explanation.`;

// ─── File scanning ───────────────────────────────────────────────────────────

interface AnalysisFile {
  logFile: string;
  summaryFile: string;
  ticker: string;
  date: string;
}

function findAnalyses(tickerFilter?: string): AnalysisFile[] {
  if (!existsSync(LOGS_DIR)) {
    console.error(`Logs directory not found: ${LOGS_DIR}`);
    return [];
  }

  const results: AnalysisFile[] = [];
  for (const tickerDir of readdirSync(LOGS_DIR, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .sort((a, b) => a.name.localeCompare(b.name))) {
    if (tickerFilter && tickerDir.name !== tickerFilter) continue;

    const logDir = join(LOGS_DIR, tickerDir.name, "TradingAgentsStrategy_logs");
    if (!existsSync(logDir)) continue;

    for (const logFile of readdirSync(logDir).sort()) {
      if (!logFile.startsWith("full_states_log_") || !logFile.endsWith(".json")) continue;
      const stem = logFile
        .replace("full_states_log_", "")
        .replace(".json", "");
      const summaryFile = join(logDir, `summary_${stem}.json`);
      results.push({
        logFile: join(logDir, logFile),
        summaryFile,
        ticker: tickerDir.name,
        date: stem,
      });
    }
  }
  return results;
}

// ─── LLM call ────────────────────────────────────────────────────────────────

interface SummaryResult {
  signal?: string;
  confidence?: number;
  position_size?: string;
  entry_strategy?: string;
  risk_management?: string;
  time_horizon?: string;
  catalysts?: string;
  risks?: string;
  plain_english?: string;
}

async function generateSummary(
  decision: string,
  reports: Record<string, string>,
  ticker: string,
  date: string,
): Promise<SummaryResult> {
  const apiKey = process.env.OPENROUTER_API_KEY;
  if (!apiKey) throw new Error("OPENROUTER_API_KEY not set in .env");

  const userPrompt =
    `Analyse this trading decision for ${ticker} on ${date}.\n\n` +
    `Decision:\n${decision.slice(0, 2000)}\n\n` +
    `Agent reports:\n${JSON.stringify(reports, null, 2).slice(0, 2000)}`;

  const payload = {
    model: MODEL,
    messages: [
      { role: "system", content: SYSTEM_PROMPT },
      { role: "user", content: userPrompt },
    ],
    temperature: 0.3,
    max_tokens: 800,
  };

  const res = await fetch(OPENROUTER_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API error ${res.status}: ${body.slice(0, 200)}`);
  }

  const data = await res.json();
  const content = data?.choices?.[0]?.message?.content ?? "";

  if (!content) throw new Error("Empty response from LLM");

  try {
    return JSON.parse(content);
  } catch {
    return { plain_english: content };
  }
}

// ─── Main ────────────────────────────────────────────────────────────────────

const args = Bun.argv.slice(3); // skip bun, script path
const tickerFilter = args.includes("--ticker")
  ? args[args.indexOf("--ticker") + 1]
  : undefined;
const regenerateAll = args.includes("--all");

async function main() {
  const analyses = findAnalyses(tickerFilter);
  if (analyses.length === 0) {
    console.log("No analyses found.");
    return;
  }

  console.log(`Found ${analyses.length} analyses\n`);
  let done = 0, skipped = 0, errors = 0;

  for (const { logFile, summaryFile, ticker, date } of analyses) {
    if (!regenerateAll && existsSync(summaryFile)) {
      console.log(`  SKIP ${ticker} ${date} (cached)`);
      skipped++;
      continue;
    }

    process.stdout.write(`  PROCESS ${ticker} ${date} ... `);

    try {
      const state = JSON.parse(readFileSync(logFile, "utf8")) as Record<string, unknown>;

      const decision = String(state.final_trade_decision ?? "");

      const reports: Record<string, string> = {};
      for (const [key, value] of Object.entries(state)) {
        if (
          typeof value === "string" &&
          key.endsWith("_report") &&
          value.length > 0
        ) {
          reports[key.replace("_report", "")] = value.slice(0, 1000);
        }
      }

      const summary = await generateSummary(decision, reports, ticker, date);
      writeFileSync(summaryFile, JSON.stringify(summary, null, 2));

      console.log(
        `OK (${summary.signal ?? "?"}, conf ${summary.confidence ?? "?"})`,
      );
      done++;

      // Rate limit: sleep 1s between calls
      await new Promise((r) => setTimeout(r, 1000));
    } catch (e) {
      console.error(`ERROR: ${e}`);
      errors++;
    }
  }

  console.log(`\nDone: ${done} generated, ${skipped} cached, ${errors} errors`);
}

main();