---
title: "A Single CLAUDE.md File Went Viral. The Reason Is Embarrassingly Simple."
author: "Sumit Pandey"
site: "Towards Deep Learning"
published: 2026-05-08T08:32:29Z
source: "https://medium.com/towards-deep-learning/a-single-claude-md-file-went-viral-the-reason-is-embarrassingly-simple-5b515c9e4cca"
domain: "towardsdeeplearning.com"
language: "en"
description: "91,000 stars on GitHub. No code. Four rules from Andrej Karpathy that every coding agent should have been following from day one."
word_count: 184
---

## Relationship to the Edinburgh Protocol

Karpathy's four rules and the Edinburgh Protocol are two expressions of the same philosophical position. The mapping is nearly clean:

| Karpathy Rule | Edinburgh Principle |
|---|---|
| **Think Before Coding** — state assumptions, surface tradeoffs, stop when confused | Map vs. Territory + Mentational Humility |
| **Simplicity First** — nothing speculative, no over-abstraction | Anti-Dogma (theoretical purity is a cost, not a virtue) |
| **Surgical Changes** — touch only what you must, don't refactor what's not broken | Mentational Humility (don't cover unknowns with over-engineering) |
| **Goal-Driven Execution** — success criteria, test-first, loop until verified | Practicality (the Watt test: does it work?) |

**What's different:**

Karpathy's four rules are *mechanics* — observable, applicable, trainable behaviors. The Edinburgh Protocol is a *philosophical substrate* — the "why" beneath the rules.

Karpathy tells you *what to do*. Edinburgh tells you *what to be* when you're doing it.

**Where Edinburgh goes further:**

- The **Impartial Spectator** — a deliberate bias-checking step before responding — is not in Karpathy.
- **Systems over Villains** ("look for bad incentives, not bad people") is absent entirely. Karpathy is silent on failure attribution.

**The synthesis:**

Karpathy's four rules are what the Edinburgh Protocol looks like in a code editor. They're the operational surface of the same epistemological position: don't assume, don't bloat, don't drift, and measure success, not effort.

Use Edinburgh when you're uncertain about approach. Use Karpathy when you're mid-task and need a behavioral checklist. They reinforce each other.

---

## The Viral Article

## 91,000 stars on GitHub. No code. Four rules from Andrej Karpathy that every coding agent should have been following from day one.

I almost scrolled past it. A LinkedIn post about a markdown file going viral on GitHub. Sounded like hype. The kind of thing where someone screenshots a star count and pretends it is a revolution.

![](https://miro.medium.com/v2/resize:fit:1400/format:webp/1*wpOHldCy2O2itB-241M5rQ.png)

Generates using chatgpt

> **If you can't read this further because of paywall please click** [**here**](https://medium.com/@sumit.ai/5b515c9e4cca?sk=92fe9934f874bb1b8dabfc94ab7089a0)

Then I checked the repo. 91,000 stars. No dependencies. No build step. No model. Just one file called CLAUDE.md with four behavioral rules inside it. And the rules are not novel. That is what bothered me. They are things every senior engineer would tell a junior on day one. Yet the file is the number one trending repository on GitHub right now, and the curve is not flat. So I sat with it for a while. Here is what is actually going on.

## [GitHub - forrestchang/andrej-karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills)

A single CLAUDE.md file to improve Claude Code behavior, derived from [Andrej Karpathy's observations](https://x.com/karpathy/status/2015883857489522876) on LLM coding pitfalls.

---

## The Full CLAUDE.md (The Viral File Itself)

> Source: [forrestchang/andrej-karpathy-skills/CLAUDE.md](https://raw.githubusercontent.com/forrestchang/andrej-karpathy-skills/main/CLAUDE.md)

```markdown
# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
```

---

## The Problems Karpathy Diagnosed

From Karpathy's original post:

> "The models make wrong assumptions on your behalf and just run along with them without checking. They don't manage their confusion, don't seek clarifications, don't surface inconsistencies, don't present tradeoffs, don't push back when they should."

> "They really like to overcomplicate code and APIs, bloat abstractions, don't clean up dead code... implement a bloated construction over 1000 lines when 100 would do."

> "They still sometimes change/remove comments and code they don't sufficiently understand as side effects, even if orthogonal to the task."

## Key Insight

> "LLMs are exceptionally good at looping until they meet specific goals... Don't tell it what to do, give it success criteria and watch it go." — Karpathy

---

## Install

**Claude Code Plugin (recommended):**
```
/plugin marketplace add forrestchang/andrej-karpathy-skills
/plugin install andrej-karpathy-skills@karpathy-skills
```

**Per-project CLAUDE.md:**
```bash
curl -o CLAUDE.md https://raw.githubusercontent.com/forrestchang/andrej-karpathy-skills/main/CLAUDE.md
```