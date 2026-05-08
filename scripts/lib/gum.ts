/**
 * Gum — Charm Gum CLI styling helper
 *
 * Thin wrapper around `gum style` via Bun.spawn.
 * Handles the stdin piping so callers do not need to.
 *
 * Usage:
 *   import { gum } from "./lib/gum.ts"
 *   console.log(await gum("Hello", ["--bold", "--foreground", "212"]))
 */

export async function gum(text: string, args: string[]): Promise<string> {
  const proc = Bun.spawn({
    cmd: ["gum", "style", ...args],
    stdin: "pipe",
    stdout: "pipe",
    stderr: "pipe",
  })

  await proc.stdin.write(text)
  await proc.stdin.end()

  return new Response(proc.stdout).text().then((s) => s.trimEnd())
}
