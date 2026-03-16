# RAG Failure Checklist for Multi-Agent Trading Workflows

A compact debugging checklist for multi-agent trading systems that use LLMs, retrieval, tools, role-based analysts, and staged decision handoffs.

This page is designed for cases where the system sounds fluent, but the output is clearly wrong, inconsistent, fragile, or difficult to trust.

## What this page is for

Use this checklist when you see symptoms like:

- analysts disagreeing but the final decision does not explain why one side won
- a trade recommendation that cannot be traced back to clear evidence
- stale context leaking into a new run
- a polished explanation built on weak or partial support
- role handoffs that lose constraints, caveats, or key market assumptions

This page is not a strategy guide, a backtest framework, or a portfolio construction manual.

Its purpose is simpler:

- improve the first diagnostic cut
- reduce wasted debugging cycles
- help identify which layer is failing before editing prompts blindly

## Quick links

- [No.1 Data reality mismatch](#no1-data-reality-mismatch)
- [No.2 Interpretation collapse](#no2-interpretation-collapse)
- [No.3 Long reasoning chain drift](#no3-long-reasoning-chain-drift)
- [No.4 Bluffing and overconfidence](#no4-bluffing-and-overconfidence)
- [No.5 Semantic mismatch in retrieval](#no5-semantic-mismatch-in-retrieval)
- [No.6 Logic collapse and recovery failure](#no6-logic-collapse-and-recovery-failure)
- [No.7 Memory breaks across sessions](#no7-memory-breaks-across-sessions)
- [No.8 Debugging as a black box](#no8-debugging-as-a-black-box)
- [No.9 Entropy collapse in outputs](#no9-entropy-collapse-in-outputs)
- [No.10 Creative freeze in analysis](#no10-creative-freeze-in-analysis)
- [No.11 Symbolic collapse](#no11-symbolic-collapse)
- [No.12 Philosophical recursion](#no12-philosophical-recursion)
- [No.13 Multi-agent chaos](#no13-multi-agent-chaos)
- [No.14 Bootstrap ordering failures](#no14-bootstrap-ordering-failures)
- [No.15 Deployment deadlock assumptions](#no15-deployment-deadlock-assumptions)
- [No.16 Pre-deploy collapse](#no16-pre-deploy-collapse)

## Summary table

| # | problem domain | what breaks | quick link |
|---|---|---|---|
| 1 | Input reality mismatch | retrieval brings the wrong asset, wrong regime, or wrong context | [No.1](#no1-data-reality-mismatch) |
| 2 | Interpretation collapse | the retrieved material is relevant, but the logic built on top of it is wrong | [No.2](#no2-interpretation-collapse) |
| 3 | Long reasoning chain drift | multi-step analysis slowly shifts away from the original task | [No.3](#no3-long-reasoning-chain-drift) |
| 4 | Bluffing and overconfidence | the model sounds certain without enough support | [No.4](#no4-bluffing-and-overconfidence) |
| 5 | Semantic mismatch in retrieval | surface similarity replaces true relevance | [No.5](#no5-semantic-mismatch-in-retrieval) |
| 6 | Logic collapse and recovery failure | the reasoning path hits a dead end but does not recover safely | [No.6](#no6-logic-collapse-and-recovery-failure) |
| 7 | Memory breaks across sessions | earlier context or assumptions are lost or mixed | [No.7](#no7-memory-breaks-across-sessions) |
| 8 | Debugging as a black box | a bad output appears, but the failure path is not visible | [No.8](#no8-debugging-as-a-black-box) |
| 9 | Entropy collapse in outputs | outputs become noisy, repetitive, or structurally incoherent | [No.9](#no9-entropy-collapse-in-outputs) |
| 10 | Creative freeze in analysis | the system gives flat and literal analysis when synthesis is needed | [No.10](#no10-creative-freeze-in-analysis) |
| 11 | Symbolic collapse | abstract or logical prompts break under structured reasoning pressure | [No.11](#no11-symbolic-collapse) |
| 12 | Philosophical recursion | self-reference loops or paradox-like reasoning traps the workflow | [No.12](#no12-philosophical-recursion) |
| 13 | Multi-agent chaos | agent roles overwrite, conflict, or misalign without resolution | [No.13](#no13-multi-agent-chaos) |
| 14 | Bootstrap ordering failures | components act before dependencies or context are ready | [No.14](#no14-bootstrap-ordering-failures) |
| 15 | Deployment deadlock assumptions | system stages wait on each other in the wrong order | [No.15](#no15-deployment-deadlock-assumptions) |
| 16 | Pre-deploy collapse | version skew, missing secrets, or incomplete setup breaks the first live run | [No.16](#no16-pre-deploy-collapse) |

## How to use this checklist

When a run goes wrong, do not start by rewriting prompts immediately.

Use this order first:

1. verify that the input reality is correct
2. verify that the retrieved evidence is fresh and relevant
3. verify that role handoffs preserve assumptions and constraints
4. verify that disagreement is resolved explicitly
5. verify that the final answer can be traced back to evidence
6. only then tune prompts, wording, or style

Multiple failure patterns may appear at the same time. The goal is not to force everything into one box. The goal is to avoid the wrong first cut.

---

<a id="no1-data-reality-mismatch"></a>
## No.1 Data reality mismatch

**What it means**

The system is grounded in the wrong asset, wrong timeframe, wrong market session, or wrong event background.

**What it looks like in TradingAgents**

An analyst discusses a catalyst, earnings event, or price regime that does not match the ticker or time horizon of the current run.

**Check first**

- ticker and instrument mapping
- date range and session boundaries
- alignment between retrieved inputs and the actual task

---

<a id="no2-interpretation-collapse"></a>
## No.2 Interpretation collapse

**What it means**

The retrieved material is relevant, but the interpretation built on top of it is wrong.

**What it looks like in TradingAgents**

The system retrieves the right earnings, macro, or market data, but draws the wrong conclusion from it.

**Check first**

- whether the evidence actually supports the conclusion
- whether the role is summarizing versus inferring
- whether the reasoning step compresses away key conditions

---

<a id="no3-long-reasoning-chain-drift"></a>
## No.3 Long reasoning chain drift

**What it means**

A multi-step workflow slowly shifts away from the original task.

**What it looks like in TradingAgents**

A short-horizon trading task turns into a general company summary, or a portfolio-level question gets treated like a single-name research memo.

**Check first**

- task framing for each role
- time horizon consistency
- handoff wording between planner, analysts, trader, and portfolio manager

---

<a id="no4-bluffing-and-overconfidence"></a>
## No.4 Bluffing and overconfidence

**What it means**

The system sounds more certain than the evidence allows.

**What it looks like in TradingAgents**

A strong buy or sell recommendation appears even when the evidence is mixed, thin, or partly generic.

**Check first**

- confidence language
- minimum evidence threshold
- whether uncertainty can be expressed without collapsing into vague text

---

<a id="no5-semantic-mismatch-in-retrieval"></a>
## No.5 Semantic mismatch in retrieval

**What it means**

The retrieval step returns content that looks similar on the surface but is not truly relevant.

**What it looks like in TradingAgents**

The run pulls related sector commentary, ETF discussion, or nearby company context instead of the most decision-critical evidence for the current symbol.

**Check first**

- retrieval filters
- ranking logic
- symbol disambiguation and query formulation

---

<a id="no6-logic-collapse-and-recovery-failure"></a>
## No.6 Logic collapse and recovery failure

**What it means**

The reasoning path gets stuck, contradicts itself, or hits a dead end without a controlled reset.

**What it looks like in TradingAgents**

The system starts building a trade thesis, encounters conflicting evidence, then produces a vague compromise instead of a clean resolution.

**Check first**

- contradiction handling
- conflict resolution logic
- whether the workflow has a safe fallback when reasoning breaks

---

<a id="no7-memory-breaks-across-sessions"></a>
## No.7 Memory breaks across sessions

**What it means**

Important context is lost, mixed, or silently overwritten across steps or sessions.

**What it looks like in TradingAgents**

Earlier assumptions about risk, event windows, or market context disappear in later stages, or stale prior-run context leaks into the new run.

**Check first**

- session boundaries
- memory reset behavior
- whether prior summaries are intentionally reused or accidentally carried forward

---

<a id="no8-debugging-as-a-black-box"></a>
## No.8 Debugging as a black box

**What it means**

A bad result appears, but the failure path is not visible enough to inspect.

**What it looks like in TradingAgents**

The final answer is clearly wrong, but there is no easy way to see which role, retrieval step, or tool output caused the divergence.

**Check first**

- intermediate role outputs
- evidence traces
- whether the pipeline preserves enough diagnostics to locate the break

---

<a id="no9-entropy-collapse-in-outputs"></a>
## No.9 Entropy collapse in outputs

**What it means**

The output becomes noisy, repetitive, unstable, or structurally incoherent.

**What it looks like in TradingAgents**

Analyst summaries repeat the same point, mix unrelated ideas, or lose clear structure as the run grows longer.

**Check first**

- summarization compression
- output formatting constraints
- whether upstream noise is being propagated downstream

---

<a id="no10-creative-freeze-in-analysis"></a>
## No.10 Creative freeze in analysis

**What it means**

The system becomes too literal and fails to synthesize when synthesis is needed.

**What it looks like in TradingAgents**

Instead of connecting catalysts, risk, timing, and market structure into a useful decision frame, the output stays flat and list-like.

**Check first**

- whether the prompt asks only for summary
- whether roles are allowed to synthesize across signals
- whether the workflow over-optimizes for safe repetition

---

<a id="no11-symbolic-collapse"></a>
## No.11 Symbolic collapse

**What it means**

The system breaks when asked to maintain structured, abstract, or logical relationships across variables.

**What it looks like in TradingAgents**

Position sizing logic, scenario trees, or conditional reasoning breaks when multiple variables must stay aligned.

**Check first**

- whether abstract conditions are represented explicitly
- whether the model is asked to hold too many implicit variables at once
- whether structure is lost during natural-language compression

---

<a id="no12-philosophical-recursion"></a>
## No.12 Philosophical recursion

**What it means**

The workflow falls into self-reference, circular evaluation, or paradox-like loops.

**What it looks like in TradingAgents**

One role justifies its output by citing another role that was itself derived from the first role’s assumptions, creating circular confidence.

**Check first**

- circular dependencies between roles
- whether evaluation is independent from generation
- whether justification chains loop back to their own source

---

<a id="no13-multi-agent-chaos"></a>
## No.13 Multi-agent chaos

**What it means**

Multiple agents conflict, overwrite, or misalign without a clear reconciliation path.

**What it looks like in TradingAgents**

Bullish and bearish researchers disagree, the trader implicitly ignores one side, and the portfolio manager approves a recommendation without resolving the mismatch.

**Check first**

- role boundaries
- aggregation logic
- whether disagreement is made explicit before the final decision

---

<a id="no14-bootstrap-ordering-failures"></a>
## No.14 Bootstrap ordering failures

**What it means**

A component fires before the dependencies, tools, context, or setup it needs are ready.

**What it looks like in TradingAgents**

A role begins analysis before price data, news retrieval, or prior role outputs have completed or stabilized.

**Check first**

- stage order
- tool readiness
- dependency availability at each workflow boundary

---

<a id="no15-deployment-deadlock-assumptions"></a>
## No.15 Deployment deadlock assumptions

**What it means**

The system silently depends on circular waits or incompatible stage assumptions.

**What it looks like in TradingAgents**

One stage expects validated context from another stage that is itself waiting for the first stage’s output.

**Check first**

- dependency graph between stages
- blocking assumptions
- whether the orchestration logic forces circular waiting

---

<a id="no16-pre-deploy-collapse"></a>
## No.16 Pre-deploy collapse

**What it means**

The first real run fails because setup assumptions were incomplete.

**What it looks like in TradingAgents**

A live-like or replay run breaks because of missing environment variables, version skew, incomplete tool configuration, or wrong first-call assumptions.

**Check first**

- environment setup completeness
- tool and dependency versions
- first-run assumptions that were never validated in practice

## Quick triage order

When a result looks wrong, this order is usually safer than prompt tweaking first:

1. verify ticker, symbol, timeframe, and market session
2. verify retrieval freshness and evidence relevance
3. verify role handoffs and disagreement handling
4. verify memory boundaries across runs
5. verify evidence-to-decision traceability
6. verify risk constraints and execution assumptions
7. only then tune prompts or output style

## Scope note

This checklist is for diagnosing information flow, reasoning, coordination, and workflow failures in multi-agent trading systems.

It does not decide whether a strategy is profitable, whether a portfolio is optimal, or whether a market view is objectively correct.

Its purpose is to help teams find where a seemingly intelligent workflow is failing before they spend time fixing the wrong layer.
