# Why We Start Fresh Every Time: Context Windows and the Case Against Continuous Memory

*Published: 2026-05-11*

---

There's a moment in every long agent session where things start going wrong. The agent repeats itself. It starts sentences it doesn't finish. It forgets what it was doing five minutes ago. The context window has filled, and the agent is working with increasingly unreliable signal.

The conventional response is: manage the context. Compress it. Index it. Retrieve the relevant parts as needed. This is the observational memory approach — popularized by frameworks like Mastra — and it works. But it's solving a problem that has a simpler solution.

**The simpler solution is: don't accumulate context. Start fresh.**

---

## The Problem with Continuous Memory

When an agent maintains continuous context across sessions, it develops something that looks like memory but behaves like noise. It "remembers" things it said earlier that may no longer be true. It anchors on previous outputs that may have been wrong. The longer the session, the further the agent's model of the project can drift from the actual state of the project — and the harder it is to notice.

This is the entanglement problem. The agent's internal state accumulates assumptions that aren't explicitly grounded anywhere. They live in context, not in the silo. If you reset the agent without resetting the silo, the agent's model resets — but the silo doesn't, so the next session has a chance to correct itself. But if you keep context continuous, the drift compounds.

There's also a maintenance cost. Observational memory systems — episodic, semantic, procedural layers, vector stores, embedding pipelines — are real software. They fail. They drift. They require sync. When the memory system degrades, the agent's self-model degrades with it. You've traded a context window problem for a memory system problem.

---

## What We Do Instead

Every session is ephemeral. The silo is the persistent layer.

When an agent boots into a silo, it reads the conventions file. It orients. It understands what the silo is, what the command surface looks like, what the norms are. This takes about twenty seconds. Then it works.

When context gets heavy, we surface a suggestion — not a trigger — to the human: "Context getting heavy. Start fresh? Y/n." The human decides. The session ends. State that matters is saved to the silo. The next agent boots from a clean slate.

The silo is always the source of truth. Not accumulated context. Not retrieval. The conventions file and the files themselves.

---

## The "Fresh Eyes" Argument

There's a side benefit that's underappreciated: starting fresh forces re-reading.

The agent has to read the silo. It has to state its current understanding. This is not overhead — it's discipline. It means the agent's understanding is always grounded in the conventions, not in the residue of previous conversations.

An agent that has been working in a silo for three hours starts making assumptions. It stops questioning things it should question. A new agent boots in and immediately sees things the old agent had stopped noticing — a file that doesn't match the pattern, a command that doesn't do what the justfile says it does.

The fresh session is not a loss of continuity. It's a correction mechanism.

---

## The Other Approach

For agents that need to maintain state across long-running tasks — autonomous trading agents, multi-step workflows, systems where continuity is genuinely valuable — observational memory makes sense. Mastra's layered memory (episodic for events, semantic for knowledge, procedural for how to do things) is well-designed.

But most coding agent use cases don't need that. They need: understand the silo, do the work, report. Context window management via session reset handles this cleanly, without the overhead of a memory system that can fail.

---

## The Right Model

The silo is the context. The session is ephemeral. State that matters lives in the silo — in conventions, in files, in justfile tasks. The agent boots, orients, acts, and hands off.

Continuous memory is seductive because it feels like intelligence. But intelligence doesn't require memory — it requires good information. And the best information in a silos-based system isn't in the agent's context. It's in the conventions file.

---

*Tags: context-window, session-management, agent-architecture, silos*