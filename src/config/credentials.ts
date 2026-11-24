// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The stored keys: `credentials.json` in the home directory, owner-only. It is read more strictly than
 * the settings: a file that is not the user's own is not used. Problems name the field, never a value.
 */
import { z } from "zod";
import { HOSTED_PROVIDERS, type HostedProvider, message } from "../contracts/index.js";
import { KEYS } from "../contracts/limits.js";
import { readPrivate, UnsafeFileError, writePrivate } from "../store/index.js";
import { isRecord, parseJson, pick } from "./json.js";

/** A key as stored and as used: trimmed, one line, long enough to be one. */
export const credentialKey = z
  .string()
  .trim()
  .min(KEYS.minChars)
  .refine((value) => !/[\r\n]/.test(value));
/** The keys credentials.json keeps: the compatible server's (`model`) and each hosted provider's, Tauric's among them. */
export type CredentialName = "model" | HostedProvider;
export const CREDENTIAL_NAMES: readonly CredentialName[] = [
  "tauric",
  "model",
  ...HOSTED_PROVIDERS.filter((provider) => provider !== "tauric"),
];
const credentialFields = Object.fromEntries(CREDENTIAL_NAMES.map((name) => [name, credentialKey]));
type FileCredentials = { [N in CredentialName]?: string };

/** The stored keys, and the server the compatible server's key was stored for. */
export async function readCredentials(
  path: string,
  problems: string[],
): Promise<FileCredentials & { modelEndpoint?: string }> {
  let text: string | undefined;
  try {
    text = await readPrivate(path);
  } catch (error) {
    problems.push(
      error instanceof UnsafeFileError
        ? message("config.keysUnused", { reason: error.message })
        : message("config.unreadable", { path }),
    );
    return {};
  }
  if (text === undefined) return {};
  const json = parseJson(text);
  if (!isRecord(json)) {
    problems.push(message("config.credentialsNotObject", { path }));
    return {};
  }
  const keys = pick(
    json,
    credentialFields,
    (field) => message("config.unusableKey", { path, field }),
    problems,
  ) as FileCredentials;
  return typeof json.modelEndpoint === "string" ? { ...keys, modelEndpoint: json.modelEndpoint } : keys;
}

/** Write `entries` into the credentials file at `path`, keeping its others. Refuses to overwrite a file it cannot read. */
export async function writeCredentials(path: string, entries: Record<string, string>): Promise<void> {
  const text = await readPrivate(path);
  let current: Record<string, unknown> = {};
  if (text !== undefined) {
    const parsed = parseJson(text);
    if (!isRecord(parsed)) throw new Error(message("config.fixFirst", { path }));
    current = parsed;
  }
  await writePrivate(path, `${JSON.stringify({ ...current, ...entries }, null, 2)}\n`);
}
