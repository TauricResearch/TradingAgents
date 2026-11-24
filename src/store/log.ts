// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Append-only JSON-lines files: one value per line, written whole by one `write`, never edited. The
 * store reads and writes values; what they mean belongs to its callers.
 *
 * A crash can leave a last line without its newline. Opening for append cuts that torn tail first,
 * so the next line does not join it; reading skips it. Any other line that is not JSON
 * is damage the store will not guess around.
 */

import { constants, promises as fs } from "node:fs";
import { dirname } from "node:path";
import { message } from "../contracts/index.js";
import { SESSIONS } from "../contracts/limits.js";

const POSIX = process.platform !== "win32";

export class DamagedLogError extends Error {
  override readonly name = "DamagedLogError";
  constructor(
    readonly path: string,
    readonly line: number,
  ) {
    super(message("file.damaged", { path, line }));
  }
}

/**
 * Every value in the file, in order; a torn last line (bytes after the last newline) is not read.
 * Refuses a file with a broken line before its end.
 */
export async function readLog(path: string): Promise<unknown[]> {
  const text = await fs.readFile(path, "utf8");
  const end = text.lastIndexOf("\n") + 1;
  const values: unknown[] = [];
  const lines = text.slice(0, end).split("\n");
  lines.pop();
  for (const [index, line] of lines.entries()) {
    try {
      values.push(JSON.parse(line));
    } catch {
      throw new DamagedLogError(path, index + 1);
    }
  }
  return values;
}

/** The first values of a file, reading at most `bytes` of it: enough to list it without reading it all. */
export async function readLogHead(path: string, bytes: number = SESSIONS.headBytes): Promise<unknown[]> {
  const handle = await fs.open(path, "r");
  try {
    const buffer = Buffer.alloc(bytes);
    const { bytesRead } = await handle.read(buffer, 0, bytes, 0);
    const text = buffer.subarray(0, bytesRead).toString("utf8");
    const values: unknown[] = [];
    for (const line of text.slice(0, text.lastIndexOf("\n") + 1).split("\n")) {
      if (!line) continue;
      try {
        values.push(JSON.parse(line));
      } catch {
        break;
      }
    }
    return values;
  } finally {
    await handle.close();
  }
}

export class LogWriter {
  private constructor(
    private readonly handle: fs.FileHandle,
    readonly path: string,
    /** Bytes of a torn last line cut when the file was opened. */
    readonly repairedBytes: number,
  ) {}

  /**
   * Open `path` for appending, creating it (and its directory) private to the user. A new file
   * starts with `header`; an existing one is made private again and has a torn last line cut first.
   * A symbolic link is refused, and the repair and the appends go through the one descriptor opened.
   */
  static async open(path: string, header?: unknown): Promise<LogWriter> {
    const dir = dirname(path);
    await fs.mkdir(dir, { recursive: true, mode: 0o700 });
    if (POSIX && (await fs.lstat(dir)).mode & 0o077) await fs.chmod(dir, 0o700);
    const flags = constants.O_RDWR | constants.O_APPEND | (POSIX ? constants.O_NOFOLLOW : 0);
    let handle: fs.FileHandle;
    let created = false;
    try {
      handle = await fs.open(path, flags | constants.O_CREAT | constants.O_EXCL, 0o600);
      created = true;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
      handle = await fs.open(path, flags);
    }
    try {
      const stat = await handle.stat();
      if (!stat.isFile()) throw new Error(message("file.notRegular", { path }));
      if (POSIX && stat.mode & 0o077) await handle.chmod(0o600);
      if (created) {
        if (header !== undefined) await handle.appendFile(`${JSON.stringify(header)}\n`);
        return new LogWriter(handle, path, 0);
      }
      return new LogWriter(handle, path, await cutTornTail(handle));
    } catch (error) {
      await handle.close().catch(() => {});
      if (created) await fs.rm(path, { force: true });
      throw error;
    }
  }

  /** Append values, one line each, in a single write. */
  async append(...values: unknown[]): Promise<void> {
    if (!values.length) return;
    await this.handle.appendFile(values.map((value) => `${JSON.stringify(value)}\n`).join(""));
  }

  /** Make what was appended durable. */
  async sync(): Promise<void> {
    await this.handle.sync();
  }

  /** The file's size in bytes. */
  async size(): Promise<number> {
    return (await this.handle.stat()).size;
  }

  async close(): Promise<void> {
    await this.handle.close();
  }
}

/** Cut everything after the last newline; returns how many bytes were cut. */
async function cutTornTail(handle: fs.FileHandle): Promise<number> {
  const { size } = await handle.stat();
  if (size === 0) return 0;
  // Look back in blocks for the last newline; a line can be long.
  const block = 65_536;
  for (let end = size; end > 0; end -= block) {
    const start = Math.max(0, end - block);
    const buffer = Buffer.alloc(end - start);
    await handle.read(buffer, 0, buffer.length, start);
    const newline = buffer.lastIndexOf(0x0a);
    if (newline >= 0) {
      const keep = start + newline + 1;
      if (keep < size) await handle.truncate(keep);
      return size - keep;
    }
  }
  await handle.truncate(0);
  return size;
}
