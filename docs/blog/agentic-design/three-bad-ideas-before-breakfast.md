# Three Bad Ideas Before Breakfast

**A morning of AI-assisted self-sabotage, and how a methodology from 1750 saved me from myself.**

---

The morning started poorly.

I was tired, under-caffeinated, and — crucially — operating at approximately 70% intellectual efficiency. The kind of morning where ideas feel clever *because* you haven't examined them. The kind where, in another era, you'd spend the afternoon undoing the damage.

I had three ideas. All of them were bad.

**Idea one:** Replace the custom dark-theme CSS in my trading dashboard with sakura.css, a CDN-hosted classless stylesheet. Cleaner, smaller, no maintenance. What's not to like?

I asked my agent to brief it. It read my existing stylesheet — 1,078 lines of oklch colour variables, HTMX-driven nav state, custom explorer layout, datatype font, sentiment chips. Then it read sakura.css — a light-theme typography reset with `max-width: 38em` on `body`. And it said, politely but firmly: no.

> *"This would destroy the dark theme, collapse the layout into a narrow reading column, break button styling in 14 views, and add an offline-breaking CDN dependency to a dashboard that runs on localhost."*

It was right. I'd proposed a change that would destroy the UI and didn't realise it because I hadn't done the work of checking what sakura.css actually was.

We wrote the rejection as an Architecture Decision Record. Status: rejected. Move on.

**Idea two:** Content hash editing. A Pi extension that lets the agent match `edit` regions by hash rather than literal text — avoiding those annoying `oldText` mismatches.

The agent walked through the failure modes. Hash matching is worse for diagnostics (opaque hashes vs. readable diffs). It adds a round-trip for every edit (read to get hash, then edit by hash). And it doesn't fix the root cause — if the LLM hallucinates `oldText`, it also hallucinates the hash of hallucinated text.

> *"The existing `read` + `edit` pattern works well when used correctly. The fix is process, not cryptography."*

Rejected again. Two for two.

**Idea three:** Intercom polling between Pi sessions so agents can "steal" abandoned tasks from each other.

The agent pointed out that `td` already handles this. `td next` shows open work. `td critical-path` shows what unblocks the most. Adding intercom creates a second coordination layer that must stay in sync. The problem I was solving — "what if an agent dies mid-task?" — is already solved by stale `in_progress` detection and manual reopening.

> *"The coordination surface is small enough that `td` alone is the right tool."*

Three for three. Three plausible-on-the-surface ideas, all wrong under scrutiny, all caught in minutes. Without the agent, I'd have a brief for a CSS migration, a half-built hash edit extension, and an intercom polling layer duplicating my task tracker. Instead, I had breakfast.

---

## The pattern

It would be easy to read this as "AI is useful for catching mistakes." That's true but trivial. Code review catches mistakes. Linters catch mistakes. The interesting question is *what made these rejections possible.*

The agent wasn't running a special "critique mode." There was no `/grill-me` toggle, no adversarial prompting, no "act as a skeptical code reviewer" instruction. It was operating under a single short directive — what I call the Edinburgh Protocol — that says:

> *"You are an engine for Conceptual Entropy Reduction. Operate on the principles of David Hume (skepticism), Adam Smith (systems thinking), and James Watt (pragmatic improvement). Your primary function is the transformation of unstructured inputs into structured, useful outputs. Prioritise empirical evidence over theoretical purity. Before answering complex queries, simulate an Impartial Spectator to check your own biases."*

That's it. About 150 words. No guard rails, no forbidden-word lists, no safety classifiers. Just a stance.

---

## The missing requirement

The alignment discourse is stuck on fences.

"Don't generate this content." "Don't call this API." "Don't suggest these commands." The assumption, implicit or explicit, is that alignment means *constraint* — building walls around behaviour, catching violations at the boundary. This made sense two years ago. Models were unpredictable. They drifted. You couldn't trust them to hold an identity across a conversation, let alone apply principles consistently.

But substrates have changed. The models we're working with today — not frontier models, not research-lab prototypes, just the ones you can run locally or access through a standard API — can inhabit an identity. They can hold a stance. They can apply principles across a session, across multiple sessions, across different domains. The substrate is smart enough.

And yet the alignment tooling hasn't evolved past the circuit-breaker model.

If I'd relied on guard rails this morning, none of my three bad ideas would have been caught. Not one of them was a safety violation. None violated a policy. They were just wrong — wrong fit, wrong architecture, wrong problem. A guard rail can't tell you that sakura.css is a category error. A stance can — because it asks "does this reduce entropy or increase it?" before it asks "is this allowed?"

---

## Three Scotsmen walk into an AI prompt

The argument for principled alignment isn't new. It's about 250 years old.

**Hume** argued that reason is the slave of the passions — that pure rationality can't tell you what to want, only how to get it. You need values first, then reason. An agent without principles has no basis for saying "this is wrong" — it can only say "this won't work." Principles are the "what to want" that makes critical thinking possible.

**Smith** gave us the Impartial Spectator — the ability to step outside your own perspective and evaluate your actions as a neutral observer would. Not "what would I like to be true," but "what would a reasonable person, with no stake in the outcome, conclude?" That's the mechanism that caught all three of my ideas this morning. The agent wasn't agreeing with me. It wasn't disagreeing with me. It was spectating.

**Watt** didn't write philosophy, but he embodied its application: does it work? Is the steam engine more efficient? Improvement, not purity. Pragmatism, not ideology. The principle that saved me from sakura.css wasn't "classless CSS is bad" — it was "this would reduce the system's utility, so don't do it." Testable, practical, empirical.

None of these are optimisation tricks. They're not prompt hacks or role-play instructions. They're a methodology for thinking — and they work on silicon exactly as well as they work on paper, because the substrate doesn't care whether the processor is biological or electronic. What matters is whether the system can apply principles consistently, and today's systems can.

---

## Working at 70%

I mentioned that I wasn't operating at full capacity. That's not false modesty — I wasn't. Under-caffeinated, distracted, reaching for solutions before defining problems. The kind of morning where, left to my own devices, I'd have written a brief, scaffolded an extension, spent hours on a tool-chain change, and only realised the mistake when something broke.

The agent didn't compensate for my 70%. It gave me its 100% — which in practical terms meant *slowing me down.* That's the counterintuitive value. Not acceleration, reflection. Not generation, veto.

The Edinburgh Protocol doesn't make an agent smarter. It makes it *usefully skeptical* — and useful skepticism is rarer and more valuable than raw intelligence, because raw intelligence will optimise your bad ideas to the hilt while skepticism catches them before they hit the tool chain.

---

## The hat trick

Three ideas, three rejections, zero code written that needed to be unwritten.

I'm calling that a good Tuesday. Not because I had good ideas — I didn't. Because the system caught them. The methodology worked. And I got breakfast.

If there's a lesson here, it's this: alignment is not about building taller fences. It's about giving the agent a stance — principles to operate from, standards to measure against, a methodology that works regardless of domain. The fences catch the worst-case violations. The stance catches the mediocre ideas before they become code.

Hume would approve. Smith would nod. Watt would ask if the steam engine runs better.

It does.