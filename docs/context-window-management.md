# Context Window Management: Session Reset as Architecture

*Decision record — 2026-05-11*

---

## The Problem

AI coding agents consume context. As a conversation progresses, the context window fills. At some threshold — terminator-adjacent — the session becomes unreliable. The agent starts losing recent context, truncating outputs, repeating itself. The question is: what do you do about it?

---

## The Options

### Option 1: Continuous Context with Observational Memory (Mastra)

Mastra's observational memory provides persistent state across sessions via episodic, semantic, and procedural memory layers. The agent retains what it has seen and done. Context is not discarded — it is indexed and retrieved.

**Pros:**
- Continuity. The agent doesn't forget.
- Useful for agents that need to maintain state across long-running tasks.

**Cons:**
- Adds a second state store that must stay in sync with the silo.
- Retrieval can surface stale information, anchoring the agent in outdated assumptions.
- The memory system can fail, drift, or degrade — the agent's self-model degrades with it.
- Embedding pipelines, vector store, retrieval logic: significant complexity for a problem that's better solved elsewhere.
- Observational memory is primarily about agent self-awareness, not context window management. These are different problems.

---

### Option 2: Session Reset (The Silos Model)

Each session is ephemeral. The silo is the persistent layer. The agent reads conventions on boot, orients, acts. When context gets heavy, save state to the silo and start a new session.

**Pros:**
- The silo is always the source of truth. No accumulated context that might have drifted.
- The agent's understanding is grounded in the conventions file, not in the residue of previous conversations.
- Fresh set of eyes. Accumulated context creates anchoring — the agent assumes things are true because it said them before. A new session starts from the conventions and the files.
- Lightweight. No vector store, no retrieval pipeline, no additional system to maintain.
- The conventions file is the persistent layer. A session reset + conventions read is ~20 seconds of orientation overhead — negligible against the cost of context entanglement.

**Cons:**
- The agent loses conversational continuity. It must re-orient each time.
- State that isn't persisted in the silo is lost.

---

### Option 3: Automated Threshold Reset

Token counting at 80% of context window. Trigger a save-and-reset automatically. No human decision required.

**Pros:**
- Proactive. Removes the human from the loop on a mechanical decision.

**Cons:**
- Automation without consent. The user loses their session without being asked.
- What was the agent in the middle of? The automation doesn't know — and can't ask.
- It's a one-way door. Once triggered, the session is gone.
- Creates a dependency on the token-counting mechanism being reliable.

---

## Decision

**Do not automate.** Keep the reset lightweight. The conventions file is the persistent layer.

If you want to be proactive, detect token pressure at 70-80% of window and surface a prompt to the user: "Context getting heavy — start fresh? Y/n." The human decides. The mechanism is a suggestion, not a trigger.

The silo is the context. The session is ephemeral. That's the right model.

---

## Rationale

The session reset is the mechanism, not the problem. The problem is: what persists across sessions?

In the silos model, the answer is: the silo. Conventions, justfile, AGENTS.md, project-level state. That's a clean, durable answer. It doesn't require continuous memory.

Observational memory adds complexity to solve a problem you're solving better with a conventions file and a session reset.

The "fresh set of eyes" point is underappreciated. Accumulated context creates anchoring. The agent's model of the project can diverge from the actual project — and that's harder to detect when context is continuous.

---

*Tags: context-window, session-management, observability, decision-record*
*Status: active*