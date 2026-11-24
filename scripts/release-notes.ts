// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/** Print version `argv[2]`'s notes from CHANGELOG.md; fail when it has none. Run with Bun. */
import { readFileSync } from "node:fs";
import { releaseNotes } from "./changelog-source.ts";

const version = (process.argv[2] ?? "").replace(/^v/, "");
const notes = releaseNotes(readFileSync("CHANGELOG.md", "utf8"), version);
if (!notes) {
  console.error(`CHANGELOG.md has no notes for ${version}`);
  process.exit(1);
}
console.log(notes);
