/**
 * Shared Python subprocess utilities.
 *
 * Provides consistent venv Python path resolution and a simple Promise-based
 * runner for non-streaming Python script invocations.
 *
 * Usage:
 *   import { venvPython, runPython } from "@lib/subprocess"
 *
 *   // Get the venv Python path
 *   const python = venvPython()
 *   spawn(python, [script, ...], opts)
 *
 *   // Run a script and get stdout as string
 *   const stdout = await runPython("scripts/py/get_price.py", ["AAPL"])
 */

import { spawn } from "node:child_process"
import { existsSync } from "node:fs"
import { dirname, join } from "node:path"

// ── Path resolution ───────────────────────────────────────────────────────────

/**
 * Resolve the .venv Python path for the TradingAgents project.
 * Uses TA_ROOT env var if set, otherwise walks up from this file's location.
 */
export function venvPython(): string {
  if (process.env.TA_ROOT) return join(process.env.TA_ROOT, ".venv", "bin", "python3")

  // Walk up from this file to find the project root
  let dir = dirname(import.meta.filename)
  while (dir !== "/" && dir !== "") {
    const venv = join(dir, ".venv", "bin", "python3")
    if (existsSync(venv)) return venv
    const parent = dirname(dir)
    if (parent === dir) break
    dir = parent
  }

  // Fallback: assume project root is two levels up from lib/
  const projectRoot = dirname(dirname(import.meta.filename))
  return join(projectRoot, ".venv", "bin", "python3")
}

/**
 * Resolve the TradingAgents project root directory.
 * Uses TA_ROOT env var if set, otherwise walks up from this file's location.
 */
export function projectRoot(): string {
  if (process.env.TA_ROOT) return process.env.TA_ROOT

  // Walk up from this file's location to find project root
  const python = venvPython()
  // python is <root>/.venv/bin/python3, so root is python's great-grandparent
  return dirname(dirname(dirname(python)))
}

// ── Simple runner ─────────────────────────────────────────────────────────────

export interface RunPythonOptions {
  /** Timeout in ms (default: 30_000) */
  timeout?: number
  /** Environment variables (merged with process.env) */
  env?: Record<string, string>
  /** Working directory (default: project root) */
  cwd?: string
}

export interface RunPythonResult {
  stdout: string
  stderr: string
  exitCode: number
}

/**
 * Run a Python script and return stdout/stderr/exitCode.
 * Times out after `opts.timeout` ms (default 30s).
 * Times out with SIGTERM on the JS side as defence-in-depth.
 *
 * Does NOT stream — use this for scripts that complete quickly and return
 * all output at once (e.g. get_price.py). For streaming output (analyze_stream.py),
 * use a custom streaming handler in the route.
 */
export function runPython(
  scriptPath: string,
  args: string[] = [],
  opts: RunPythonOptions = {},
): Promise<RunPythonResult> {
  const timeout = opts.timeout ?? 30_000
  const python = venvPython()
  // import.meta.filename = .../src/server/lib/subprocess.ts
  // dirname 3x: lib → server → src → project-root
  const projectRoot = dirname(dirname(dirname(import.meta.filename)))

  return new Promise((resolve) => {
    const child = spawn(python, [scriptPath, ...args], {
      cwd: opts.cwd ?? projectRoot,
      env: {
        ...process.env,
        PYTHONUNBUFFERED: "1",
        ...opts.env,
      },
    })

    let stdout = ""
    let stderr = ""
    let timedOut = false

    const timer = setTimeout(() => {
      timedOut = true
      child.kill("SIGTERM")
    }, timeout)

    child.stdout?.on("data", (d: Buffer) => {
      stdout += d.toString()
    })

    child.stderr?.on("data", (d: Buffer) => {
      stderr += d.toString()
    })

    child.on("close", (code) => {
      clearTimeout(timer)
      resolve({
        stdout,
        stderr,
        exitCode: timedOut ? 124 : (code ?? -1),
      })
    })

    child.on("error", () => {
      clearTimeout(timer)
      resolve({ stdout, stderr, exitCode: -1 })
    })
  })
}

/**
 * Run a Python script and return the parsed JSON stdout, or null on error.
 */
export async function runPythonJson<T = unknown>(
  scriptPath: string,
  args: string[] = [],
  opts?: RunPythonOptions,
): Promise<T | null> {
  const result = await runPython(scriptPath, args, opts)
  if (result.exitCode !== 0) return null
  try {
    return JSON.parse(result.stdout.trim()) as T
  } catch {
    return null
  }
}

/**
 * Run a Python script that reads a JSON payload from stdin and emits one JSON
 * object on stdout (request/response, not streaming). Used by bridges like
 * scripts/py/markov_hmm.py. Returns the parsed JSON, or null on error.
 *
 * Mirrors runPython's timeout/SIGTERM behaviour but additionally writes
 * `payload` (JSON-stringified) to the child's stdin and closes it.
 */
export function runPythonStdinJson<T = unknown>(
  scriptPath: string,
  payload: unknown,
  opts: RunPythonOptions = {},
): Promise<T | null> {
  const timeout = opts.timeout ?? 30_000
  const python = venvPython()
  const projectRoot = dirname(dirname(dirname(import.meta.filename)))

  return new Promise((resolve) => {
    const child = spawn(python, [scriptPath], {
      cwd: opts.cwd ?? projectRoot,
      env: {
        ...process.env,
        PYTHONUNBUFFERED: "1",
        ...opts.env,
      },
    })

    let stdout = ""
    let timedOut = false

    const timer = setTimeout(() => {
      timedOut = true
      child.kill("SIGTERM")
    }, timeout)

    child.stdout?.on("data", (d: Buffer) => {
      stdout += d.toString()
    })
    child.on("close", (code) => {
      clearTimeout(timer)
      const exitCode = timedOut ? 124 : (code ?? -1)
      if (exitCode !== 0) {
        resolve(null)
        return
      }
      try {
        resolve(JSON.parse(stdout.trim()) as T)
      } catch {
        resolve(null)
      }
    })
    child.on("error", () => {
      clearTimeout(timer)
      resolve(null)
    })

    // Write the request payload and signal EOF so the script can respond.
    child.stdin?.write(JSON.stringify(payload))
    child.stdin?.end()
  })
}
