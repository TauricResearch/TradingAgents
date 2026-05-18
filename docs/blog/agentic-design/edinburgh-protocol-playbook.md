---
id: EP-001
title: "The Edinburgh Protocol Playbook"
role: "Architect | Constrain | Execute"
infrastructure: [General TypeScript, Bun, Hono, Native Storage Engines]
last_updated: "2026-05-17"
tags: [master-context, constraint-stack]
---

# The Edinburgh Protocol Playbook

## 1. Purpose & Core Mandate
This playbook documents the operational execution framework for the **Edinburgh Protocol**. It functions as a portable, machine-readable **Master Context** designed to stabilize a transformer substrate's active context window across discontinuous development sessions. 

By enforcing strict token locality, flat imperative syntax, and explicit uncertainty mapping, this protocol prevents agentic code-drift and eliminates structural complexity collapse.

---

## 2. When to Ingest This Playbook

| System State / Trigger | Immediate Playbook Action | Expected Tactical Outcome |
| :--- | :--- | :--- |
| **Ambiguous or shifting project specifications** | Execute Phase 1 & Phase 2 | Converts unstructured "Stuff" into low-entropy "Things" before coding. |
| **Designing high-throughput async pipelines** | Enforce Phase 3: Abstraction Cap | Guarantees an $N \le 2$ structural depth limit across all route vectors. |
| **Configuring local-first database channels** | Isolate Concurrency Boundaries | Separates Multi-Conn WAL Read Pools from Single-Threaded Write Clients. |
| **Reviewing agentic code generation pulls** | Invoke Phase 4: Impartial Spectator | Automatically filters out hallucinated frameworks and boilerplate noise. |

---

## 3. The Core Protocol Phases

### Phase 1: Acknowledge the Map (The Uncertainty Triage)
Before emitting a single line of feature code, the agent must parse the active prompt context and explicitly output a plain-text triage table using these exact headers:

1.  **Verified Evidence (What is Known):** Objectively verifiable data, exact library APIs present in the repo, and fixed database schemas.
2.  **Working Assumptions (What is Hypothesized):** Structural beliefs held without hard compile-time evidence or inferred human intent.
3.  **Explicit Ignorance Gaps (What is Unknown):** Missing configuration keys, unstated boundary conditions, or unmapped edge cases.

*Why this matters:* Forcing the model to commit these tokens to the active buffer suppresses its default statistical instinct to confabulate missing requirements with generic boilerplate.

### Phase 2: Measure & Print Conceptual Entropy
The agent must evaluate the complexity of the task and output a flat, plain-text classification block prior to code synthesis:


```

[System Token Assessment] ────► Entropy Score: [0.0 - 1.0] ────► Lens Selected

```

* **HIGH ENTROPY (Score > 0.6) — Chaos/Turbulence:** The objective is muddy or contradictory. *Action:* The agent must halt execution, strip away structural noise, isolate the single core question, and present a minimal testable hypothesis.
* **LOW ENTROPY (Score ≤ 0.3) — Structure/Clarity:** The implementation boundary is fully explicit. *Action:* The agent runs **Test-First Implementation (TDD)** and executes with precise imperative locality.

### Phase 3: Apply the Agentic Syntax Constraints (The Good Parts)
When generating or editing files within the workspace, the agent must strictly comply with the following structural laws:

#### Law 1: Hard Abstraction Depth Constraint ($N \le 2$)
The system layout must remain flat. The execution path must never cross more than two nested custom abstractions between the input boundary (e.g., Hono route handler) and physical storage state modification (e.g., native SQLite call).

#### Law 2: Imperative Locality over Function Coloring
All asynchronous operations and business data pipelines must be written using linear, readable `async/await` syntax wrapped in explicit `try/catch` enclosures. Opaque monadic chaining frameworks, lazy execution monads, and macro stream operators are unauthorized.

#### Law 3: Failures as Discriminated Unions
Expected domain and system errors must be explicitly returned as typed data values rather than un-typed runtime exceptions:
```typescript
type OperationResult<T, E> = 
  | { success: true; data: T } 
  | { success: false; error: E };

```

### Phase 4: The Impartial Spectator Pass

Prior to finalizing any output block, the agent must evaluate its own generated response against three silent validation vectors:

1. *"Would a completely disinterested technical expert find this architecture unnecessarily verbose?"*
2. *"What explicit compile-time or runtime failure would prove this implementation completely incorrect?"*
3. *"Have I introduces implicit, ambient global state that will cause a downstream sub-agent to drop context?"*

### Phase 5: The Watt Pragmatism Test

The final gate: **"Does this output directly lower conceptual entropy and improve runtime execution?"** If the generated code serves elegance or architectural dogma rather than immediate, measurable utility, the agent must discard the string, apply Deductive Minimalism, and refactor.

---

## 4. Anti-Patterns vs. Recommended Best Practices

| ❌ Banned Anti-Patterns (High Entropy) | Recommended Patterns (Low Entropy) |
| --- | --- |
| **Fragmenting context** across dozens of isolated, tiny abstraction helper files. | **Maintaining strict code locality**; keeping intent directly alongside the execution block. |
| **Hiding un-typed runtime failures** behind deep, unverified `throw` exceptions. | **Returning errors explicitly as values** inside clear, typed discriminated unions. |
| **Injecting opaque framework magic** that masks raw type signatures from the model. | **Writing flat, brutal, imperative code paths** that any transformer can audit in a single pass. |

---

## 5. Workflow Execution Script (TDD Interface)

When utilizing this Master Context to author a new module, the agent must adhere to the following strict execution sequence:

```typescript
// Step 1: Write the explicit success/failure test schema before generating logic
import { test, expect } from "bun:test";
import { processTransaction } from "./transaction-module.js";

test("Transaction isolation handles lock content gracefully", async () => {
  const mockDb = createMockWriteClient();
  const result = await processTransaction(mockDb, { id: "TX-100", amount: 500 });
  
  expect(result.success).toBe(true);
});

// Step 2: Generate the absolute minimum imperative implementation code 
// required to pass this explicit type verification and execution gate.