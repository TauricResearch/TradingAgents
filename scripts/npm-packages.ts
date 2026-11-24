// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The npm packages of a release, written from its executables: one package per platform under the @tauric
 * scope, carrying that platform's executable, and @tauric/tradingagents, whose `tradingagents` command runs
 * the one npm installed for the platform it is on. Every package has the release's version.
 *
 *   bun scripts/npm-packages.ts <version> <directory with tradingagents-<os>-<arch>> <output directory>
 *
 * It writes <output>/tradingagents and <output>/tradingagents-<os>-<arch>, each ready for `npm publish`.
 */
import { chmodSync, copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import {
  NPM_PACKAGE,
  NPM_PLATFORM_PREFIX,
  NPM_UPDATE_COMMAND,
  REPOSITORY_URL,
} from "../src/config/release.js";

const ROOT = resolve(import.meta.dirname, "..");
/** The licenses of the fonts the executable embeds for PDF reports. */
const FONT_DIR = join(ROOT, "licenses");
const FONT_LICENSES = ["OFL-EncodeSansExpanded.txt", "OFL-JetBrainsMono.txt"] as const;

/** The platforms a release is built for, as npm names their os and cpu. */
export const TARGETS = [
  { os: "darwin", cpu: "arm64" },
  { os: "darwin", cpu: "x64" },
  { os: "linux", cpu: "arm64" },
  { os: "linux", cpu: "x64" },
] as const;

const COMMON = {
  license: "Apache-2.0",
  homepage: REPOSITORY_URL,
  repository: { type: "git", url: `git+${REPOSITORY_URL}.git` },
  bugs: `${REPOSITORY_URL}/issues`,
};

/** The platform package's name for a target. */
export function platformPackage(target: { os: string; cpu: string }): string {
  return `${NPM_PLATFORM_PREFIX}${target.os}-${target.cpu}`;
}

/** Write the packages for `version` from the executables in `from` into `out`; gives their directories. */
export function stagePackages(version: string, from: string, out: string): string[] {
  if (!/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(-[0-9A-Za-z.-]+)?$/.test(version)) {
    throw new Error(`${version} is not a version`);
  }
  const license = readFileSync(join(ROOT, "LICENSE"));
  // The executable carries the PDF report's fonts (scripts/gen-report-fonts.ts); their licenses go with it.
  const fontLicenses = FONT_LICENSES.map((name) => ({
    name,
    text: readFileSync(join(FONT_DIR, name)),
  }));
  const written: string[] = [];
  for (const target of TARGETS) {
    const executable = join(from, `tradingagents-${target.os}-${target.cpu}`);
    if (!existsSync(executable)) throw new Error(`${executable} is missing`);
    const dir = join(out, `tradingagents-${target.os}-${target.cpu}`);
    mkdirSync(join(dir, "bin"), { recursive: true });
    copyFileSync(executable, join(dir, "bin", "tradingagents"));
    chmodSync(join(dir, "bin", "tradingagents"), 0o755);
    writeFileSync(join(dir, "LICENSE"), license);
    mkdirSync(join(dir, "licenses"), { recursive: true });
    for (const { name, text } of fontLicenses) writeFileSync(join(dir, "licenses", name), text);
    writeJson(join(dir, "package.json"), {
      name: platformPackage(target),
      version,
      description: `The TradingAgents executable for ${target.os === "darwin" ? "macOS" : "Linux"} on ${target.cpu}.`,
      ...COMMON,
      os: [target.os],
      cpu: [target.cpu],
      // The Linux executables are built for glibc.
      ...(target.os === "linux" ? { libc: ["glibc"] } : {}),
      files: ["bin", "licenses"],
      publishConfig: { access: "public" },
    });
    written.push(dir);
  }
  const dir = join(out, "tradingagents");
  mkdirSync(join(dir, "bin"), { recursive: true });
  copyFileSync(join(ROOT, "scripts", "npm", "launcher.js"), join(dir, "bin", "tradingagents.js"));
  chmodSync(join(dir, "bin", "tradingagents.js"), 0o755);
  writeFileSync(join(dir, "LICENSE"), license);
  writeFileSync(join(dir, "README.md"), README);
  writeJson(join(dir, "package.json"), {
    name: NPM_PACKAGE,
    version,
    description: "TradingAgents: Towards Agentic Finance Research",
    ...COMMON,
    type: "module",
    bin: { tradingagents: "bin/tradingagents.js" },
    files: ["bin"],
    engines: { node: ">=18" },
    os: ["darwin", "linux"],
    cpu: ["arm64", "x64"],
    optionalDependencies: Object.fromEntries(TARGETS.map((target) => [platformPackage(target), version])),
    publishConfig: { access: "public" },
  });
  return [...written, dir];
}

const README = `# TradingAgents: Towards Agentic Finance Research

\`\`\`bash
${NPM_UPDATE_COMMAND}
tradingagents
\`\`\`

Builds are for macOS and Linux (glibc), on x64 and arm64. See ${REPOSITORY_URL} for the documentation.
`;

function writeJson(path: string, value: unknown): void {
  writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`);
}

if (import.meta.main) {
  const [version, from, out] = process.argv.slice(2);
  if (!version || !from || !out) {
    process.stderr.write(
      "usage: bun scripts/npm-packages.ts <version> <executables directory> <output directory>\n",
    );
    process.exit(2);
  }
  for (const dir of stagePackages(version, from, out)) process.stdout.write(`${dir}\n`);
}
