// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Private files: a directory only its owner can enter, and files only its owner can read or write.
 * On POSIX the checks are enforced; on Windows, where modes mean little, they are skipped.
 *
 * The file itself is opened without following a symlink and checked through the open descriptor,
 * so it cannot be swapped between the check and the read. The directories above it are not checked.
 * Writes replace the file atomically through a private temporary file in the same directory, made
 * durable before and after the rename; two writers at once may lose one update (callers that can
 * race hold a lock).
 */

import { randomBytes } from "node:crypto";
import { constants, promises as fs } from "node:fs";
import { dirname, join } from "node:path";
import { message } from "../contracts/index.js";

const POSIX = process.platform !== "win32";

/** What opening or syncing a directory gives on a file system that does not support it (Linux, macOS). */
const UNSYNCABLE_DIRECTORY = new Set(["EINVAL", "ENOTSUP", "EOPNOTSUPP", "EISDIR", "EPERM", "EACCES"]);

export class UnsafeFileError extends Error {
  override readonly name = "UnsafeFileError";
}

/** The file's text, or undefined if it does not exist. Refuses a file others could read or change. */
export async function readPrivate(path: string): Promise<string | undefined> {
  let handle: fs.FileHandle;
  try {
    handle = await fs.open(path, constants.O_RDONLY | (POSIX ? constants.O_NOFOLLOW : 0));
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return undefined;
    if ((error as NodeJS.ErrnoException).code === "ELOOP")
      throw new UnsafeFileError(message("file.symlink", { path }));
    throw error;
  }
  try {
    const stat = await handle.stat();
    if (!stat.isFile()) throw new UnsafeFileError(message("file.notRegular", { path }));
    if (POSIX) {
      if (stat.uid !== process.getuid?.()) throw new UnsafeFileError(message("file.otherOwner", { path }));
      if (stat.mode & 0o077) throw new UnsafeFileError(message("file.tooOpen", { path }));
    }
    return await handle.readFile("utf8");
  } finally {
    await handle.close();
  }
}

/** Replace the file with `text`, readable and writable by its owner only. */
export async function writePrivate(path: string, text: string): Promise<void> {
  const dir = dirname(path);
  await fs.mkdir(dir, { recursive: true, mode: 0o700 });
  if (POSIX) {
    const stat = await fs.lstat(dir);
    if (!stat.isDirectory()) throw new UnsafeFileError(message("file.notDirectory", { path: dir }));
    if (stat.uid !== process.getuid?.()) throw new UnsafeFileError(message("file.otherOwner", { path: dir }));
    // A directory that already existed with wider rights is narrowed: it holds the keys.
    if (stat.mode & 0o077) await fs.chmod(dir, 0o700);
  }
  await writeAtomic(path, text, { mode: 0o600 });
  if (POSIX) {
    // The file is replaced by now; a directory some file systems will not sync leaves the rename to them.
    try {
      const folder = await fs.open(dir, constants.O_RDONLY);
      await folder.sync().finally(() => folder.close());
    } catch (error) {
      if (!UNSYNCABLE_DIRECTORY.has((error as NodeJS.ErrnoException).code ?? "")) throw error;
    }
  }
}

/**
 * Replace the file at `path` with `data` in one step: written to a new file beside it (`mode`, 0o600 to keep
 * it to its owner), made durable, then renamed over it, so an existing file or link is replaced whole and
 * never written through. Nothing is left behind when it fails.
 */
export async function writeAtomic(
  path: string,
  data: string | Uint8Array,
  { mode = 0o644 }: { mode?: number } = {},
): Promise<void> {
  const temporary = join(dirname(path), `.${randomBytes(8).toString("hex")}.tmp`);
  const handle = await fs.open(temporary, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL, mode);
  try {
    await handle.writeFile(data);
    // On disk before it replaces the old file: a crash leaves one or the other.
    await handle.sync();
    await handle.close();
    await fs.rename(temporary, path);
  } catch (error) {
    await handle.close().catch(() => {});
    await fs.rm(temporary, { force: true });
    throw error;
  }
}
