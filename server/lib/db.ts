import { Database } from "bun:sqlite";

/**
 * DatabaseFactory — singleton SQLite connection with hardened pragmas.
 *
 * Per playbooks/sqlite-playbook.md:
 *   - WAL mode mandatory (concurrent reads during analysis writes)
 *   - ReadWrite mandatory (WAL readers need -shm write access)
 *   - No raw new Database() in routes or services
 *   - Graceful close with PRAGMA optimize before disconnect
 */

let _instance: Database | null = null;
let _path: string | null = null;

const PRAGMAS = [
  "PRAGMA journal_mode = WAL",
  "PRAGMA busy_timeout = 5000",
  "PRAGMA mmap_size = 0",
  "PRAGMA foreign_keys = ON",
  "PRAGMA synchronous = NORMAL",
] as const;

export const DatabaseFactory = {
  /**
   * Get or create the singleton database connection.
   * Enforces all required pragmas on first connect.
   * Throws if called with a different path after initialisation.
   */
  connect(path: string): Database {
    if (_instance) {
      // Normalize paths for comparison
      const resolved = path.replace(/^\.\//, process.cwd() + "/");
      const stored = (_path ?? "").replace(/^\.\//, process.cwd() + "/");
      if (resolved !== stored) {
        throw new Error(
          `Database already connected to "${_path}". "${path}" ignored.`,
        );
      }
      return _instance;
    }

    // Initialize with local var — only assign to singleton after all pragmas succeed
    const db = new Database(path, { readwrite: true, create: true });
    try {
      for (const pragma of PRAGMAS) {
        db.run(pragma);
      }
    } catch (e) {
      try { db.close(); } catch { /* best effort */ }
      _path = null;
      throw e;
    }

    _path = path;
    _instance = db;
    return _instance;
  },

  /**
   * Close the database gracefully.
   * Runs PRAGMA optimize (updates query-planner stats) before closing.
   * WAL checkpointing is handled automatically by SQLite on close.
   */
  close(): void {
    if (_instance) {
      try {
        _instance.run("PRAGMA optimize");
      } catch {
        // optimize may fail on empty DB — safe to ignore
      }
      _instance.close();
      _instance = null;
      _path = null;
    }
  },

  /**
   * Get the current database instance, or throw if not initialized.
   */
  get(): Database {
    if (!_instance) {
      throw new Error(
        "Database not initialized. Call DatabaseFactory.connect(path) first.",
      );
    }
    return _instance;
  },

  /**
   * Check if the database is currently connected.
   */
  isConnected(): boolean {
    return _instance !== null;
  },

  /**
   * Get the current database file path.
   */
  get path(): string | null {
    return _path;
  },
};
