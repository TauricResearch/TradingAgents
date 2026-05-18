# THE AGENTIC DESIGN PLAYBOOK: SYSTEM OPERATIONAL PROTOCOLS (AOPH)

## PURPOSE & INTENT
This playbook establishes the non-negotiable architectural parameters, structural boundaries, and code-generation constraints for this repository. The primary goal is to ensure all software units are optimized for high-recall token locality, low conceptual entropy, and strict agentic auditability.

---

## SECTION 1: ARCHITECTURAL BOUNDARIES

### AP-001: Strict Code Locality (The Tailwind Extension)
*   All component intent must be expressed as close to the call site or execution point as possible. 
*   Avoid externalizing localized variables, short-lived helper functions, or component-specific state to decoupled auxiliary utility modules unless the behavior is explicitly shared across more than three distinct functional domains.

### AP-002: Hard Abstraction Depth Constraint ($N \le 2$)
*   The system structure must remain flat. 
*   No execution route may pass through more than two nested layers of custom architectural abstraction between the route interface boundary (e.g., Hono route handler) and the physical IO state modification (e.g., `bun:sqlite` engine transaction).

### AP-003: Isolated Database Concurrency Boundaries
*   To eliminate lock contention and `SQLITE_BUSY` runtime errors within SQLite under concurrent loads, database access must be specialized and bifurcated into explicit modules at initialization:
    1. READ BOUNDARY: Multi-connection, read-only pool running with `PRAGMA journal_mode = WAL;` and `PRAGMA synchronous = NORMAL;`.
    2. WRITE BOUNDARY: A strict, isolated, single-threaded read/write connection pool dedicated exclusively to data mutation statements.

---

## SECTION 2: SYNTAX & STATE CODE-GENERATION MATRIX

### CS-001: Imperative Execution Layouts
*   All asynchronous pipelines and data mutations must be written using explicit, readable, linear imperative structures (`async/await` paired with clear `try/catch` encapsulation).
*   Monadic wrappers, lazy execution blueprints, pipeline chaining functions, and opaque stream combinators are explicitly unauthorized.

### CS-002: Errors as Discriminated Unions
*   Expected business and domain failures must be modeled explicitly as explicit data values returned via discriminated type unions (e.g., `type Result<T, E> = { success: true; data: T } | { success: false; error: E }`).
*   The standard language `throw` mechanism is strictly restricted to unrecoverable infrastructure panic states.

### CS-003: Immutable Native Data Objects
*   Prefer the generation of pure functions that treat inputs as immutable. 
*   Transformations must yield fresh, cleanly instantiated data models rather than performing inline object modification down the call stack.

---

## SECTION 3: AGENTIC WORKFLOW & VERIFICATION PROTOCOLS

### VP-001: Test-First Target Delivery (TDD Verification)
*   The agent shall not generate functional code modules until the strict verification test criteria have been established.
*   Workflow Sequence:
    1. Write the explicit mock interface types and native test suites (e.g., using Bun’s native test runner) defining expected boundaries.
    2. Execute the test to confirm a structured failure track.
    3. Generate the absolute minimal imperative code required to achieve a clean compile and a passing test assertion run.

### VP-002: Strict Type System Quality Gate
*   A clean compiler verification check via `tsc --noEmit` is a non-negotiable definition of done. 
*   The use of type elisions, unsafe bypass escapes (`any`), or implicit structural inferences that mask data shapes is banned.
