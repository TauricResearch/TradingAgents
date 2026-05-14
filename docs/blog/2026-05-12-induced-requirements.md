## The System Already Knows What It Needs — You Just Have to Listen

*Published June 2026 · 6 min read*

---

Here's a mistake I see over and over in software teams:

Someone writes a spec. The team builds it. It ships. And then everyone realizes the spec was wrong. Not dramatically wrong — just *slightly* wrong. The system does something the spec didn't account for. A gap opens up. Technical debt starts compounding.

The fix isn't a better spec. It's a different way of writing specs entirely.

## Imposed vs. Induced

Most requirements are **imposed**. A manager says "we need a code registry." A consultant says "use a vector database for semantic search." A competitor launches a feature, so you add one too. The requirement exists *before* the system does. It's dropped on top of the codebase like a blueprint for a building that's already been built.

Imposed requirements aren't evil. They're just incomplete. They answer *"what does someone think we need?"* — not *"what does the system actually need?"*

That gap between those two questions? That's where all your technical debt lives.

**Induced requirements** are different. They come from *inside* the system. You look at what exists. You notice what's missing. You write the brief that closes the gap.

Here's a real example from a recent project:

> The document registry (`reg-sync.ts` → `*/INDEX.jsonl`) tracked docs, briefs, debriefs, playbooks. When it indexed everything, it covered `docs/` — but not `src/`. The system literally told us: *"I can tell you what's in your docs, but I have no idea what's in your code."* A brief was written to close that gap. It didn't come from a manager. It came from the system itself.

That's induced. The system *induced* the requirement by existing.

## Why Nobody Does This (Until Now)

Induced requirements require **looking**. Not just reading — *looking*. Comparing. Noticing the absence of something that should be there.

For a human, this is brutally hard. You have to:

1. Know the full scope of what exists
2. Hold it all in working memory
3. Compare it to a mental model of what *should* exist
4. Identify the gap precisely
5. Formulate it as a brief

Steps 1 and 2 are where humans break down. Codebases are large. Working memory is not. You default to the scope of your current task — not the whole system.

The traditional fix? Architecture reviews, design docs, spec reviews. These try to externalize system state so humans can look at it. They help. But they're **snapshots**. They go stale the moment the system changes.

## Enter the Coding Agent

A coding agent doesn't have working memory limits. It can:

- Read the full scope of the project
- Compare that scope to the project's own conventions
- Identify gaps between what's documented and what actually exists
- Write a brief in the same register and language as the project

The agent isn't doing original design. It's doing **systematic induction**: *"Here's what the project says about itself. Here's what's actually there. Here's the gap."*

This is what happened in that project. The document registry wasn't reviewed to build a code registry. It was reviewed to *understand what existed*. The gap surfaced. The agent wrote the brief. The brief wasn't imposed. The system induced it.

## Why Agents Prefer Induced Requirements

Here's something interesting: an agent trained on good system design will *prefer* induced requirements over imposed ones. Why?

**Imposed requirements are risky.** The manager doesn't know what's actually in the codebase. The consultant is working from general principles, not this project's specifics. The competitor's feature solves a different problem. Imposed requirements require massive rework to align with reality.

**Induced requirements are reliable.** They come from the artefacts. They describe a gap that *actually exists*. The work is already validated — the gap is real, the brief is accurate.

An agent that induces requirements closes real gaps. An agent that implements imposed ones might just build the wrong thing, faster.

This is why **agent orientation matters so much**. An agent that boots into a silo, reads the conventions, and understands the system's current state *before* acting — that's the right kind of agent. One that's handed a spec and told to implement it is working in the dark.

## The Human's Role (It's Still Judgment)

Humans are more complicated. Some prefer imposed requirements — they feel safer. A spec is a spec. You know what's being asked. Less ambiguity.

But that safety is an illusion. A spec that's wrong still has to be built. You know what's being asked — but it doesn't match the system. You spend weeks building something that doesn't fit.

Others prefer induced requirements — they want to understand the system before acting. That's the right instinct. But they hit the working memory wall: they understand the local problem, not the global gap.

The best setup? **A partnership.**

The agent induces. The human approves. The agent does the systematic work of finding gaps. The human does the triage — *"yes, that gap is real"* or *"no, that's not the right fix."*

The agent surfaces. The human decides. Together, they close the loop.

## The Infrastructure That Makes This Work

The document registry system turned out to be the right infrastructure for induced requirements. Here's why:

| Property | Why It Matters |
|---|---|
| **Visibility** | When everything is indexed, gaps are visible. You see what's missing by comparing the index to the project. |
| **Feedback** | The register updates continuously. Gaps surface as the system changes, not just once at kickoff. |
| **Consistency** | The same language — briefs, debriefs, decisions — is used whether the requirement is imposed or induced. Origin doesn't change the process. |
| **Audit** | You can see the history of what was induced, when, and why. Did the agent find the right gaps? Was the brief accurate? |

The code registry (`scripts/reg-sync.ts` → `code/INDEX.jsonl`) extends this to the last major surface that wasn't in the feedback loop: the code itself. Once code is indexed, the loop closes. Documents and code — both visible, both inducing requirements when gaps appear.

## The Bottom Line

Induced requirements are better than imposed ones. More accurate. Less risky. More aligned with how software actually works — incrementally, in response to *actual* gaps, not hypothetical ones.

Coding agents make induced requirements practical at scale. They don't have working memory limits. They can read the full scope. They find the gaps humans miss.

The human's role is **judgment**. When the agent surfaces a gap, the human approves the brief. The agent does the systematic work. The human does the triage. Together, you build a system that's *actually needed* — not just what was spec'd.

The register is the infrastructure that makes this possible. Without it, the loop is broken — documents exist, code exists, but they're not connected. With it, every gap has a path to a brief, and every brief has a path to a fix.

That's a learning system. That's the goal.

---

*Tags: #systemdesign #requirements #codingagents #inducedrequirements #softwareengineering*