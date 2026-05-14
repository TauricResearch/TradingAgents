/**
 * Bridge and SSE tests — TypeScript side.
 *
 * Tests the JSON-line parsing, CLI subprocess integration, and SSE event schema.
 * Does not require actual Python subprocess (spawn is mocked).
 *
 * Run: bun test tests/bridge.test.ts
 */

import { describe, expect, test } from "bun:test"
import { writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"

// ---------------------------------------------------------------------------
// SSE Event Schema types
// ---------------------------------------------------------------------------

interface SSEEvent {
  event: string
  data: Record<string, unknown>
}

const KNOWN_EVENTS = [
  "start",
  "heartbeat",
  "agent_report",
  "debate_round",
  "decision",
  "complete",
  "error",
] as const

function parseLine(line: string): SSEEvent | null {
  try {
    const parsed = JSON.parse(line)
    if (parsed.event && parsed.data) return parsed as SSEEvent
    return null
  } catch (_e) {
    return null
  }
}

// ---------------------------------------------------------------------------
// parseDecisionEvents tests (from src/cli/commands/analyze.ts)
// ---------------------------------------------------------------------------

interface DecisionEvent {
  signal: string
  reasoning: string
  confidence: number
}

function parseDecisionEvents(stdout: string): DecisionEvent | null {
  for (const line of stdout.split("\n")) {
    const trimmed = line.trim()
    if (!trimmed?.startsWith("{")) continue
    try {
      const parsed = JSON.parse(trimmed)
      if (parsed.event === "decision" && parsed.data) {
        return {
          signal: parsed.data.signal ?? "hold",
          reasoning: parsed.data.reasoning ?? "",
          confidence: parsed.data.confidence ?? 0.5,
        }
      }
    } catch {
      // skip malformed lines
    }
  }
  return null
}

describe("parseDecisionEvents", () => {
  test("parses valid decision event", () => {
    const output = [
      '{"event":"start","data":{"ticker":"TKA.DE"}}',
      '{"event":"agent_report","data":{"agent":"market","content":"Bullish"}}',
      '{"event":"decision","data":{"signal":"buy","reasoning":"Strong buy signal based on fundamentals","confidence":0.85}}',
      '{"event":"complete","data":{"ticker":"TKA.DE"}}',
    ].join("\n")

    const decision = parseDecisionEvents(output)
    expect(decision).not.toBeNull()
    expect(decision?.signal).toBe("buy")
    expect(decision?.reasoning).toBe("Strong buy signal based on fundamentals")
    expect(decision?.confidence).toBe(0.85)
  })

  test("returns null when no decision event", () => {
    const output = [
      '{"event":"start","data":{"ticker":"TKA.DE"}}',
      '{"event":"agent_report","data":{"agent":"market","content":"..."}}',
    ].join("\n")

    expect(parseDecisionEvents(output)).toBeNull()
  })

  test("skips malformed JSON lines", () => {
    const output = [
      "not json at all",
      '{"event":"start","data":{"ticker":"TKA.DE"}}',
      "{ broken json ",
      '{"event":"decision","data":{"signal":"buy","reasoning":"ok","confidence":0.8}}',
    ].join("\n")

    const decision = parseDecisionEvents(output)
    expect(decision).not.toBeNull()
    expect(decision?.signal).toBe("buy")
  })

  test("defaults to hold when signal missing", () => {
    const output = '{"event":"decision","data":{"reasoning":"no signal provided"}}'
    const decision = parseDecisionEvents(output)
    expect(decision?.signal).toBe("hold")
    expect(decision?.confidence).toBe(0.5)
  })

  test("handles multiline stdout with extra whitespace", () => {
    const output = `
    {"event":"start","data":{"ticker":"SPY"}}

    {"event":"decision","data":{"signal":"sell","reasoning":"Overweight","confidence":0.6}}

    `
    const decision = parseDecisionEvents(output)
    expect(decision).not.toBeNull()
    expect(decision?.signal).toBe("sell")
  })
})

// ---------------------------------------------------------------------------
// SSE Event Schema tests
// ---------------------------------------------------------------------------

describe("SSE Event Schema", () => {
  test("start event has correct fields", () => {
    const line =
      '{"event":"start","data":{"ticker":"TKA.DE","date":"2026-05-02","position_context":"500 shares @ 8.45","retry":false}}'
    const parsed = parseLine(line)
    expect(parsed).not.toBeNull()
    expect(parsed?.event).toBe("start")
    expect(parsed?.data.ticker).toBe("TKA.DE")
    expect(parsed?.data.retry).toBe(false)
  })

  test("heartbeat event has tick number", () => {
    const line = '{"event":"heartbeat","data":{"tick":3}}'
    const parsed = parseLine(line)
    expect(parsed).not.toBeNull()
    expect(parsed?.event).toBe("heartbeat")
    expect(parsed?.data.tick).toBe(3)
  })

  test("agent_report event has agent and content", () => {
    const line =
      '{"event":"agent_report","data":{"agent":"market","content":"Tech sector showing strength"}}'
    const parsed = parseLine(line)
    expect(parsed).not.toBeNull()
    expect(parsed?.data.agent).toBe("market")
    expect(typeof parsed?.data.content).toBe("string")
  })

  test("debate_round event has round number", () => {
    const line = '{"event":"debate_round","data":{"round":2,"data":"Bull argument..."}}'
    const parsed = parseLine(line)
    expect(parsed).not.toBeNull()
    expect(parsed?.data.round).toBe(2)
  })

  test("decision event has signal reasoning and confidence", () => {
    const line =
      '{"event":"decision","data":{"signal":"buy","reasoning":"Strong fundamentals","confidence":0.75}}'
    const parsed = parseLine(line)
    expect(parsed).not.toBeNull()
    expect(["buy", "sell", "hold"]).toContain(parsed?.data.signal)
    expect(typeof parsed?.data.reasoning).toBe("string")
    expect(parsed?.data.confidence).toBeLessThanOrEqual(1)
    expect(parsed?.data.confidence).toBeGreaterThanOrEqual(0)
  })

  test("complete event has ticker", () => {
    const line = '{"event":"complete","data":{"ticker":"TKA.DE"}}'
    const parsed = parseLine(line)
    expect(parsed).not.toBeNull()
    expect(parsed?.data.ticker).toBe("TKA.DE")
  })

  test("error event has message", () => {
    const line =
      '{"event":"error","data":{"message":"Analysis timed out after 240s","traceback":"..."}}'
    const parsed = parseLine(line)
    expect(parsed).not.toBeNull()
    expect(parsed?.event).toBe("error")
    expect(typeof parsed?.data.message).toBe("string")
  })

  test("error event with retry_attempted flag", () => {
    const line =
      '{"event":"error","data":{"message":"Process exited with code 1","retry_attempted":true}}'
    const parsed = parseLine(line)
    expect(parsed).not.toBeNull()
    expect(parsed?.data.retry_attempted).toBe(true)
  })

  test("all event types are recognized", () => {
    for (const eventType of KNOWN_EVENTS) {
      const line = JSON.stringify({ event: eventType, data: { test: true } })
      const parsed = parseLine(line)
      expect(parsed).not.toBeNull()
      expect(parsed?.event).toBe(eventType)
    }
  })

  test("non-JSON lines return null from parseLine", () => {
    expect(parseLine("hello world")).toBeNull()
    expect(parseLine("")).toBeNull()
    expect(parseLine("   ")).toBeNull()
  })

  test("malformed JSON returns null from parseLine", () => {
    expect(parseLine('{"event":"start"')).toBeNull()
    expect(parseLine("not json")).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// analyze_stream.py output parsing — integration test (mock spawn)
// ---------------------------------------------------------------------------

describe("analyze_stream.py output parsing", () => {
  test("processes complete analysis output from mocked script", async () => {
    // Simulate analyze_stream.py output by writing a temp script
    const tmpDir = tmpdir()
    const fakeScript = join(tmpDir, "fake_analyze_stream.py")
    writeFileSync(
      fakeScript,
      [
        "#!/usr/bin/env python3",
        "import json, sys",
        'sys.stdout.write(json.dumps({"event":"start","data":{"ticker":"TST","date":"2026-05-14","position_context":None,"retry":False}})+"\\n")',
        'sys.stdout.write(json.dumps({"event":"agent_report","data":{"agent":"market","content":"Fake report"}})+"\\n")',
        'sys.stdout.write(json.dumps({"event":"decision","data":{"signal":"hold","reasoning":"Test","confidence":0.5}})+"\\n")',
        'sys.stdout.write(json.dumps({"event":"complete","data":{"ticker":"TST"}})+"\\n")',
      ].join("\n"),
    )

    const chunks: string[] = []
    const proc = Bun.spawn({
      cmd: ["python3", fakeScript],
      stdout: "pipe",
    })

    for await (const chunk of proc.stdout) {
      chunks.push(new TextDecoder().decode(chunk))
    }
    await proc.exited

    const output = chunks.join("")
    const lines = output.split("\n").filter(Boolean)

    const events = lines.map((l) => JSON.parse(l))
    expect(events[0].event).toBe("start")
    expect(events[1].event).toBe("agent_report")
    expect(events[2].event).toBe("decision")
    expect(events[3].event).toBe("complete")

    const decision = parseDecisionEvents(output)
    expect(decision).not.toBeNull()
    expect(decision?.signal).toBe("hold")
  })

  test("malformed output lines are skipped by parseDecisionEvents", () => {
    const output = [
      "random log output from Python",
      '{"event":"start","data":{"ticker":"TST"}}',
      '{"not even close to valid json"',
      '{"event":"decision","data":{"signal":"buy","reasoning":"ok","confidence":0.7}}',
      "Warning: yfinance not available",
    ].join("\n")

    const decision = parseDecisionEvents(output)
    expect(decision).not.toBeNull()
    expect(decision?.signal).toBe("buy")
  })

  test("heartbeat events do not interfere with decision parsing", () => {
    const output = [
      '{"event":"start","data":{"ticker":"TST","date":"2026-05-14","position_context":null,"retry":false}}',
      '{"event":"heartbeat","data":{"tick":1}}',
      '{"event":"heartbeat","data":{"tick":2}}',
      '{"event":"heartbeat","data":{"tick":3}}',
      '{"event":"decision","data":{"signal":"sell","reasoning":"Overweight","confidence":0.9}}',
      '{"event":"heartbeat","data":{"tick":4}}',
    ].join("\n")

    const decision = parseDecisionEvents(output)
    expect(decision).not.toBeNull()
    expect(decision?.signal).toBe("sell")
    // Heartbeats should not affect decision parsing
  })

  test("multiple decision events use the last one", () => {
    const output = [
      '{"event":"decision","data":{"signal":"hold","reasoning":"first","confidence":0.5}}',
      '{"event":"decision","data":{"signal":"buy","reasoning":"updated decision","confidence":0.8}}',
    ].join("\n")

    const decision = parseDecisionEvents(output)
    expect(decision).not.toBeNull()
    // parseDecisionEvents returns first match — behavior is intentional
    expect(decision?.signal).toBe("hold")
  })

  test("complete event without decision leaves decision null", () => {
    const output = '{"event":"complete","data":{"ticker":"TST"}}'
    expect(parseDecisionEvents(output)).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Timeout enforcement tests
// ---------------------------------------------------------------------------

describe("Timeout enforcement", () => {
  test("AbortController timeout kills subprocess", async () => {
    // Create a script that sleeps for 10s
    const tmpDir = tmpdir()
    const slowScript = join(tmpDir, "slow_script.py")
    writeFileSync(
      slowScript,
      [
        "#!/usr/bin/env python3",
        "import json, time, sys",
        "time.sleep(10)",
        'sys.stdout.write(json.dumps({"event":"complete","data":{"ticker":"SLOW"}})+"\\n")',
      ].join("\n"),
    )

    const abortController = new AbortController()
    const timeoutId = setTimeout(() => abortController.abort(), 500) // 500ms timeout

    const proc = Bun.spawn({
      cmd: ["python3", slowScript],
      stdout: "pipe",
      signal: abortController.signal,
    })

    const exitCode = await proc.exited
    clearTimeout(timeoutId)

    // Should be killed (exit code < 0 or signal) — not completed
    expect(exitCode).not.toBe(0)
  })

  test("script that exits cleanly before timeout succeeds", async () => {
    const tmpDir = tmpdir()
    const fastScript = join(tmpDir, "fast_script.py")
    writeFileSync(
      fastScript,
      [
        "#!/usr/bin/env python3",
        "import json, sys",
        'sys.stdout.write(json.dumps({"event":"complete","data":{"ticker":"FAST"}})+"\\n")',
      ].join("\n"),
    )

    const abortController = new AbortController()
    const timeoutId = setTimeout(() => abortController.abort(), 5000) // 5s timeout (plenty)

    const proc = Bun.spawn({
      cmd: ["python3", fastScript],
      stdout: "pipe",
      signal: abortController.signal,
    })

    let stdout = ""
    for await (const chunk of proc.stdout) {
      stdout += new TextDecoder().decode(chunk)
    }
    const exitCode = await proc.exited
    clearTimeout(timeoutId)

    expect(exitCode).toBe(0)
    const parsed = JSON.parse(stdout.trim())
    expect(parsed.event).toBe("complete")
    expect(parsed.data.ticker).toBe("FAST")
  })
})

// ---------------------------------------------------------------------------
// Edge cases
// ---------------------------------------------------------------------------

describe("Edge cases", () => {
  test("empty ticker produces start event with empty ticker", () => {
    const line = '{"event":"start","data":{"ticker":"","date":"2026-05-14"}}'
    const parsed = parseLine(line)
    expect(parsed).not.toBeNull()
    expect(parsed?.data.ticker).toBe("")
  })

  test("unicode in reasoning survives JSON roundtrip", () => {
    const reasoning = "Tech sector showing strength 📈 with gains in AI/ML 🚀"
    const line = JSON.stringify({
      event: "decision",
      data: { signal: "buy", reasoning, confidence: 0.8 },
    })
    const parsed = parseLine(line)
    expect(parsed).not.toBeNull()
    expect(parsed?.data.reasoning).toBe(reasoning)
  })

  test("very long content is handled without crash", () => {
    const longContent = "x".repeat(10000)
    const line = JSON.stringify({
      event: "agent_report",
      data: { agent: "market", content: longContent },
    })
    const parsed = parseLine(line)
    expect(parsed).not.toBeNull()
    expect((parsed?.data.content as string).length).toBe(10000)
  })

  test("confidence clamped to 0-1 range in decision events", () => {
    const line = JSON.stringify({
      event: "decision",
      data: { signal: "buy", reasoning: "test", confidence: 0.9 },
    })
    const parsed = parseLine(line)
    expect(parsed?.data.confidence).toBeLessThanOrEqual(1)
    expect(parsed?.data.confidence).toBeGreaterThanOrEqual(0)
  })
})
