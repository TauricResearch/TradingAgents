#!/usr/bin/env node
// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
// The tradingagents command as npm installs it: it runs this platform's executable, from the package npm
// installed beside it for this platform, with the same arguments, and ends as that ends.
import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";

const TARGETS = ["darwin-arm64", "darwin-x64", "linux-arm64", "linux-x64"];
const target = `${process.platform}-${process.arch}`;
const reinstall = "npm i -g @tauric/tradingagents";

function fail(text) {
  process.stderr.write(`tradingagents: ${text}\n`);
  process.exit(1);
}

if (!TARGETS.includes(target)) {
  fail(`there is no build for ${target}; builds are for macOS and Linux (glibc), on x64 and arm64.`);
}
const name = `@tauric/tradingagents-${target}`;
let executable;
try {
  executable = join(
    dirname(createRequire(import.meta.url).resolve(`${name}/package.json`)),
    "bin",
    "tradingagents",
  );
} catch {
  fail(
    `${name} is not installed. npm installs it with this package unless optional dependencies are turned off; ` +
      `on Linux it needs glibc. Reinstall with: ${reinstall}`,
  );
}

const child = spawn(executable, process.argv.slice(2), { stdio: "inherit" });
// Ctrl+C reaches the executable from the terminal itself (it is in the same process group), so it is not
// passed on again; a signal sent to this process alone is.
const passOn = Object.fromEntries(["SIGTERM", "SIGHUP"].map((signal) => [signal, () => child.kill(signal)]));
const ignore = () => {};
process.on("SIGINT", ignore);
for (const [signal, handler] of Object.entries(passOn)) process.on(signal, handler);

child.on("error", (error) => fail(`could not start ${executable}: ${error.message}`));
child.on("exit", (code, signal) => {
  process.off("SIGINT", ignore);
  for (const [name, handler] of Object.entries(passOn)) process.off(name, handler);
  // Ended by a signal: this process ends by the same one, so whoever waits on it sees how it ended.
  if (signal) process.kill(process.pid, signal);
  else process.exit(code ?? 1);
});
