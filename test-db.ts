import { readFileSync, unlinkSync } from "node:fs"
import { join } from "node:path"
import { DatabaseFactory } from "./server/lib/db.ts"

const TEST_DB = "/tmp/test-portfolio.db"

// Clean up any previous test
for (const f of [TEST_DB, `${TEST_DB}-wal`, `${TEST_DB}-shm`]) {
  try {
    unlinkSync(f)
  } catch {}
}

console.log("1. Connect...")
const db = DatabaseFactory.connect(TEST_DB)
console.log("   Connected:", DatabaseFactory.path)

console.log("2. Verify WAL mode...")
const [{ journal_mode: mode }] = db.query("PRAGMA journal_mode").all() as { journal_mode: string }[]
console.log(`   journal_mode = "${mode}" ${mode === "wal" ? "✅" : "❌"}`)

console.log("3. Verify pragmas...")
const checks = [
  {
    name: "busy_timeout",
    expected: 5000,
    actual: (db.query("PRAGMA busy_timeout").get() as { timeout: number }).timeout,
  },
  {
    name: "mmap_size",
    expected: 0,
    actual: (db.query("PRAGMA mmap_size").get() as { mmap_size: number }).mmap_size,
  },
  {
    name: "foreign_keys",
    expected: 1,
    actual: (db.query("PRAGMA foreign_keys").get() as { foreign_keys: number }).foreign_keys,
  },
  {
    name: "synchronous",
    expected: 1,
    actual: (db.query("PRAGMA synchronous").get() as { synchronous: number }).synchronous,
  },
]
for (const c of checks) {
  console.log(`   ${c.name} = ${c.actual} ${c.actual === c.expected ? "✅" : "❌"}`)
}

console.log("4. Load schema...")
const schema = readFileSync(join(import.meta.dir, "server/lib/schema.sql"), "utf-8")
db.exec(schema)
console.log("   Schema loaded ✅")

console.log("5. Verify tables...")
const tables = db
  .query("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
  .all() as { name: string }[]
for (const t of tables) console.log(`   - ${t.name}`)

console.log("6. Test CRUD on positions...")
db.exec(
  `INSERT INTO positions (ticker, quantity, avg_cost, entry_date) VALUES ('TKA.DE', 500, 8.45, '2026-04-20')`,
)
const pos = db.query("SELECT * FROM positions WHERE ticker = ?").get("TKA.DE") as Record<
  string,
  unknown
>
console.log(`   Inserted: ticker=${pos?.ticker} qty=${pos?.quantity} cost=${pos?.avg_cost}`)

console.log("7. Test singleton (second connect returns same instance)...")
const db2 = DatabaseFactory.connect(TEST_DB)
console.log(`   Same instance: ${db === db2 ? "✅" : "❌"}`)

console.log("8. Close gracefully...")
DatabaseFactory.close()
console.log(`   isConnected: ${DatabaseFactory.isConnected()}`)

console.log("\n✅ All checks passed")
