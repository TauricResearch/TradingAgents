// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Build the single-file executable from the compiled JavaScript in dist/. Run with Bun:
 * `bun scripts/compile.ts [outfile] [target] [runtime]`, the target being one of Bun's (bun-darwin-arm64,
 * ...); without one, the executable is for this machine. A cross-compiled executable is built on
 * `runtime`, the target's Bun as scripts/runtime.ts checks it against package-lock.json; without one,
 * Bun downloads the target's runtime itself.
 *
 * The executable reads no .env or bunfig.toml from the directory it runs in: its settings come only from
 * its own environment and data directory.
 *
 * Ink imports react-devtools-core only when DEV=true and the package is installed, but the bundler hoists
 * the import, so it resolves here to an empty module.
 */

const outfile = process.argv[2] ?? "dist-bin/tradingagents";
const target = process.argv[3] as Bun.Build.CompileTarget | undefined;
const executablePath = process.argv[4];

const result = await Bun.build({
  entrypoints: ["dist/cli/main.js"],
  minify: true,
  // React's production build: its development build checks and warns as it renders.
  define: { "process.env.NODE_ENV": '"production"' },
  plugins: [
    {
      name: "no-react-devtools",
      setup(build) {
        build.onResolve({ filter: /^react-devtools-core$/ }, () => ({
          path: "react-devtools-core",
          namespace: "empty",
        }));
        build.onLoad({ filter: /.*/, namespace: "empty" }, () => ({
          contents: "export default {};",
          loader: "js",
        }));
      },
    },
  ],
  compile: {
    outfile,
    autoloadDotenv: false,
    autoloadBunfig: false,
    ...(target ? { target } : {}),
    ...(executablePath ? { executablePath } : {}),
  },
});
if (!result.success) {
  for (const log of result.logs) console.error(log);
  process.exit(1);
}
console.log(`compiled ${outfile}`);
