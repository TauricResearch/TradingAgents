# The Silo: Containment as Product, Not Constraint

## The Problem Being Solved

Corporate buyers have a problem: AI coding agents are now sophisticated enough to be genuinely useful, but also sophisticated enough to be genuinely dangerous. The danger isn't hypothetical — it's the same class of risk as any privileged software: uncontrolled access to systems, data, and credentials.

The traditional response is: don't use agents. This is increasingly untenable. The productivity gains are real and the opportunity cost of refusing the technology accumulates daily.

The next response is: use agents, but trust them. Hope they don't do something unintended. This is the default position for most developers — they trust their agent because they trust their own prompting. This is not a security posture. This is optimism applied to software.

The corporate buyer's actual question is: *can I give this thing access and sleep at night?*

The silo is the answer.

---

## What the Silo Is

A silo is a working directory — a folder and its subfolders — that defines the complete operational boundary of an agent.

Bash operations are restricted to the silo. Network access is controlled separately. The agent's world is this directory and nothing else. Period.

The mechanism can be bubblewrap on Linux, sandbox-exec on Mac, or any equivalent OS-level sandbox primitive. The implementation doesn't matter much — what matters is that the boundary is enforced, auditable, and portable across environments.

### The Silo Is the Context

The silo is not just a boundary — it is the agent's **context**. Every silo is self-describing. It boots from a conventions file (conventions.md at minimum, with additional docs as needed) that tells any visiting agent:

- **What this silo is** — its purpose, domain, and scope
- **How to orient** — boot sequence, entry points, conventions
- **What the command surface looks like** — a `justfile` facade exposes the silo\'s capabilities without requiring bash. Agents interact with the silo through structured commands, not raw shell access
- **Soft prohibitions** — norms against acting outside the silo, made legible to any agent that boots in

This means: any agent, regardless of its native capabilities, can land in any silo and orient itself. It reads the conventions, understands the command surface, grasps the scope. The silo is self-documenting and self-enforcing. It does not require a human to explain the environment to each new agent — the silo does that itself.

Bash is not always necessary in a silo. When the command surface is well-designed, the agent operates through structured invocations: `just <task>`, not `find . -name '*.ts' | xargs ...`. The facade makes the silo executable by any agent that can read a justfile. Bash is available when needed — but it is not the primary interface.

---

## The Irony, Stated Plainly

The thing being sold is: *an agent that can only operate inside a defined folder.*

The irony is that the means of demonstrating the product IS the product. You prove the value by showing an agent doing useful work — inside a box. The customer watches the agent work and simultaneously sees the constraint. The constraint is what makes the work credible.

This is not an obstacle to the pitch. It is the pitch.

---

## The Corporate Value Proposition

### 1. Blast Radius Contained

The worst case, without the silo: the agent exfiltrates source code, reads `.env` files, pivots to internal systems, pushes to production without review.

The worst case, with the silo: the agent deletes the wrong directory. That's it.

This is not a minor difference. It changes the insurance calculus entirely. Blast radius containment means you can deploy the agent without a human overhead hovering over every action.

### 2. Cost is Bounded

An agent that can only work in one directory has a finite problem space. You can estimate compute. You can measure throughput. You can compare cost-to-output across different agents and different tasks.

An unbounded agent is an unbounded budget. The silo is the unit of economic control.

### 3. Reliability via Constraint

Fewer failure modes. The agent can't accidentally touch something it shouldn't. The failure modes are all inside the box — which means they're auditable, recoverable, and bounded.

This is counterintuitive: restriction enables autonomy. Because the blast radius is defined, you can give the agent more rope. You can say "go refactor this module" without a human in the loop, because the worst case is known.

### 4. Auditability

The sandbox boundary is the audit surface. You can log every file touched, every call made. The silo makes the agent's behavior legible to someone who doesn't want to read code — they just want to know what the agent did and what it accessed.

Corporate buyers understand audit trails. They understand compliance reports. The silo makes the agent legible to that world.

### 5. Portability

Works on Linux (bubblewrap), works on Mac (sandbox-exec or equivalent). Works in CI. Works in a container. Works in a Kubernetes pod.

Cross-platform credibility matters. A proof of concept that only works on one OS looks like a one-off. Portability is the proof of generality.

---

## The Four Properties

A corporate buyer evaluating an agent solution should ask:

1. **Where can it go?** (filesystem boundary)
2. **What can it send?** (network boundary)
3. **What can it read?** (credential and secret exposure)
4. **What happens when it fails?** (failure mode analysis)

The silo answers (1) definitively. Network control answers (2) separately. Credential hygiene answers (3) at the deployment level. Failure mode analysis is a conversation — but the silo makes the conversation tractable.

Without the silo, questions (1) through (4) are unanswerable with confidence.

---

## The Argument Against "Just Trust It"

The trust model has an asymmetry: the developer who trusts the agent bears none of the risk when it does something unintended. The corporation bears all of it.

This is the same reason we don't give contractors admin access to production systems, even if they're trustworthy. Trust is not a control. It's a feeling. Controls are verifiable, auditable, and enforceable.

The silo is a control. It says: this agent cannot go here. That's not trust — that's engineering.

---

## The Harder Question (Which Should Be Asked)

The silo handles the filesystem boundary. The harder question is data egress.

Even with a sandbox, if the agent calls an external LLM API, the prompt context leaves the building. Corporate buyers should be asking about:

- API routing (does the call go through a proxy that logs everything?)
- Data residency (where does the provider store the prompt?)
- Audit logging (can you reconstruct exactly what the agent saw and did?)
- Model selection (open-source models runnable in-house vs. proprietary APIs)

The filesystem sandbox is necessary but not sufficient for a complete answer. It answers the first question. The rest are follow-on conversations that the silo enables — because once the filesystem boundary is settled, you can focus on the network and data boundary.

---

## Conclusion

The silo is not a restriction on the agent. It's the definition of the agent's scope. Scope is what makes it deployable. Scope is what makes it auditable. Scope is what makes it cost-measurable.

The irony — that the means of demonstrating value IS the value — is not a problem to solve. It's a design insight. The customer watches the agent work inside a box and sees both the capability and the containment. The containment is what makes the capability credible.

**This is what a bounded economic unit looks like.** Cost controlled. Blast radius contained. Does X amount of work for Y cost at Z reliability.

That description fits a contractor. It fits a software component. It fits an agent.

The corporate buyer who wants a reliable, auditable, deployable AI coding agent is not looking for the most capable agent. They're looking for the most controllable one.

The silo is the answer.

---

*Auto-generated: 2026-05-11*
*Tags: agent-silo, corporate-security, product-argument, blast-radius*