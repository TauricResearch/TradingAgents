---
tags:
  - metadata
  - vocabulary
  - agent-driven
  - extracted
---
# SQLite Configuration & Best Practices (Canon)

> [!IMPORTANT]
> This document is the **Single Source of Truth** for all SQLite operations in PolyVis.
> Deviating from these standards causes "Disk I/O Errors" and locking issues in our concurrent environment (Daemon + MCP).

## 1. The "Hardened" Standard

To ensure concurrency (1 Writer + N Readers) without `SQLITE_BUSY` or `disk I/O error`, we enforce the following configuration via `DatabaseFactory`.

### 1.1 The Golden Rules
1.  **WAL Mode is Mandatory**: `PRAGMA journal_mode = WAL`.
2.  **ReadWrite is Mandatory**: Even "Readers" must connect with `readonly: false` because WAL readers need to write to the `-shm` shared memory file.
3.  **Busy Timeout**: `PRAGMA busy_timeout = 5000;` (Wait 5s for locks).
4.  **No mmap**: `PRAGMA mmap_size = 0;` (Stability over speed).
5.  **Foreign Keys**: `PRAGMA foreign_keys = ON;` (Data integrity).
6.  **Synchronous**: `PRAGMA synchronous = NORMAL;` (Faster commits in WAL mode safely).

### 1.2 Implementation (`DatabaseFactory.ts`)
Do not instantiate `new Database()` directly. Always use the factory:

```typescript
import { DatabaseFactory } from "@src/resonance/DatabaseFactory";

// For raw access (enforces WAL, timeout, etc.)
const db = DatabaseFactory.connectToResonance(); 
// Factory will enforce Pragma settings automatically.
```

## 2. Architecture Patterns

### ✅ Protocol A: The `ResonanceDB` Class
Use the `ResonanceDB` class for all standard graph operations. It encapsulates the config above.

```typescript
// Correct: Uses Factory internally via init()
const db = ResonanceDB.init();
```

### ✅ Protocol B: Dependency Injection
Services (like `VectorEngine`) should NOT open their own connections. Pass the existing `ResonanceDB` instance or its raw connection.

```typescript
// Correct
const vectorEngine = new VectorEngine(db.getRawDb());
```

### ❌ Anti-Pattern: Raw Connections
Do not instantiate `new Database()` directly in business logic unless properly configured with ALL pragmas above.

## 3. Maintenance Protocols

### Vacuuming & Optimization
*   **Action**: Regularly reclaim unused space and optimize query plans.
*   **Command**: `VACUUM;` (Weekly) and `PRAGMA optimize;` (On Close).

### Bulk Operations
*   **Pattern**: Wrap multiple operations in a Transaction.
*   **Impact**: Performance increases from ~50 ops/sec to ~10,000 ops/sec.

```typescript
const insertMany = db.transaction((items) => {
  for (const item of items) stmt.run(item);
});
```

## 4. Connection Lifecycle
*   **Daoemons**: Singleton connection (long-lived).
*   **CLI Tools**: Ephemeral connection (open/close).
*   **Graceful Exit**: Always `db.close()` to checkpoint WAL.
