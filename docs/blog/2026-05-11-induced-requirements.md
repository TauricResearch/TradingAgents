# Induced Requirements: How Good Systems Tell You What They Need

*Published: 2026-05-11*

---

There's a common failure mode in system design: writing requirements before understanding the system. You decide what the system needs, document it in a spec, build it, and discover the spec was wrong. The system does something slightly different from what you planned, the spec doesn't match reality, and now you have technical debt that compounds.

The alternative is induced requirements: look at what exists, see the gap, write the brief that fills it. The artefacts are the specification. The system tells you what it needs — you just have to listen.

This sounds obvious. It rarely happens in practice. Here's why, and how coding agents change the calculus.

---

## The Imposed vs. Induced Spectrum

**Imposed requirements** come from outside the system. A manager says "we need a code registry." A consultant says "you should use a vector database for semantic search." A competitor has a feature, so you add it. The requirement exists before the system does — it's imposed on the system from above.

Imposed requirements are not wrong. They're just incomplete. They answer the question "what does someone think we need?" without answering "what does the system actually need?" The gap between those two questions is where technical debt lives.

**Induced requirements** emerge from the system itself. You look at what's there. You see what's missing. You write the brief that closes the gap. The requirement is induced — pulled out of the artefacts — not imposed.

Example from this project:

> The document registry system (`reg-sync.ts` → `*/INDEX.jsonl`) covered docs, briefs, debriefs, playbooks. When the documents were indexed, the code was not. The system showed the gap: "I can tell you what's in `docs/` but not in `src/`." A brief was written to close it. That brief did not come from outside. It came from the system.

This is induced. The system induced the requirement by existing.

---

## Why This Is Hard Without Agents

Induced requirements require looking. Not just reading — looking. Comparing. Noticing the absence of something that should be there.

This is slow and cognitively expensive for a human. You have to:

1. Know the full scope of what exists
2. Hold it in working memory
3. Compare it to a mental model of what should exist
4. Identify the gap precisely
5. Formulate it as a brief

Steps 1 and 2 are where humans break down. The scope of a codebase is large. Working memory is finite. You can't hold the full scope in mind — you default to the scope of your current task.

The traditional workaround is process: architecture reviews, design documents, specification reviews. These are attempts to externalize the system state so humans can look at it. They're better than nothing, but they have a problem: they're snapshots. They go stale. The system changes; the document doesn't.

---

## How Coding Agents Change This

A coding agent doesn't have human working memory constraints. It can:

- Read the full scope of the project (given conventions and time)
- Compare the scope to the conventions
- Identify gaps between what's documented and what exists
- Formulate a brief in the same register language as the project

The agent is not doing original design. It's doing systematic induction: "Here's what the project says about itself. Here's what's actually there. Here's the gap."

This is what happened in this project. The document registry system was reviewed — not to build a code registry, but to understand what existed. The review surfaced the gap. The agent wrote the brief.

The brief wasn't imposed. The system induced it.

---

## The Agent's Preference

An agent trained on good system design will prefer induced requirements. Why?

**Imposed requirements are risky.** They're often wrong. The manager doesn't know what's actually there. The consultant is working from general principles, not this project's specifics. The competitor's feature solves a different problem. Imposed requirements require significant re-work to align with reality.

**Induced requirements are reliable.** They come from the artefacts. They describe a gap that's actually there. The work has already been validated by the system — the gap exists; the brief is accurate.

An agent that can induce requirements is more useful than an agent that can implement imposed ones. The former closes real gaps. The latter implements specs that may be wrong.

This is why the agent orientation problem matters. An agent that boots into a silo and reads the conventions is doing the right kind of work: understanding the system's current state before acting. An agent that's given a spec and told to implement it is working in the dark — it doesn't know if the spec is right.

---

## The Human's Preference

Humans are more complicated. Some prefer imposed requirements — they feel safer. A spec is a spec. You know what's being asked. There's less ambiguity.

But that safety is an illusion. A spec that's wrong still has to be implemented. You know what's being asked, but the spec doesn't match the system. You spend weeks building something that doesn't fit.

Other humans prefer induced requirements — they want to understand the system before acting. They push back on specs, ask questions, want to see the codebase. This is the right instinct, but it runs into the working memory problem: they can't hold the full scope in mind. They understand the local problem but not the global gap.

The silo architecture helps here: the human works with the agent, not against it. The agent can hold the full scope. The human provides judgment — "yes, that gap is real," or "no, that's not the right fix." The agent does the systematic work of finding the gaps. The human does the triage.

The best outcome is a partnership: agent induces, human approves, together they close the loop.

---

## The Tension

The tension is real. Human coders often prefer to decide what's needed before looking. It's a natural cognitive habit — you want to know the plan before you look at the site. But in software, the site (the existing system) is the plan. Looking changes what you build.

Agents don't have this habit. They'll look first. This makes them better at induced requirements, but sometimes frustrating for humans who want a decision before a walkthrough.

The resolution is pragmatic: make the induced requirement process visible. When the agent finds a gap, it writes a brief. The brief goes through the same review process as an imposed one. The human approves or rejects. The agent didn't decide — it surfaced. The human still decides.

This is better than the alternative: building something because it was in a spec, then discovering it was wrong.

---

## The Register as Induced Requirement Infrastructure

The document registry system is the right infrastructure for induced requirements. Here's why:

1. **Visibility** — When everything is indexed, gaps are visible. You can see what's missing by comparing the index to the project.

2. **Feedback** — The register is updated continuously. Gaps surface as the system changes, not just once at the start.

3. **Consistency** — The same language (briefs, debriefs, decisions) is used whether the requirement is imposed or induced. The origin doesn't change the process.

4. **Audit** — You can see the history of what was induced, when, and why. This is useful for learning — did the agent find the right gaps? Was the brief accurate?

The code registry (`scripts/reg-sync.ts` → `code/INDEX.jsonl`) extends this to code — the last major surface that wasn't in the feedback loop. Once code is indexed, the loop is closed: documents and code, both visible, both inducing requirements when gaps appear.

---

## Conclusion

Induced requirements are better than imposed ones. They're more accurate, less risky, and more aligned with how software actually works — incrementally, in response to actual gaps, not hypothetical ones.

Coding agents make induced requirements practical at scale. They don't have working memory limits. They can read the full scope. They can find the gaps that humans miss.

The human's role is judgment: when the agent surfaces a gap, the human approves the brief. The agent does the systematic work; the human does the triage. Together, they build a system that's actually needed, not just what was spec'd.

The register is the infrastructure that makes this possible. Without it, the loop is broken — documents exist, code exists, but they're not connected. With it, every gap in the system has a path to a brief, and every brief has a path to a fix.

That's a learning system. That's the goal.

---

*Tags: induced-requirements, agent-architecture, requirements-engineering, system-design*