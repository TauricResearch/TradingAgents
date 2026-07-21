---
id: 003
title: "Prototype: web UI look — configure / live progress / report screens"
labels: [wayfinder:prototype]
status: closed
assignee: JMAN730
blocked-by: []
---

## Question

What should the three core screens look and feel like?

1. Configure-run screen (ticker, date, asset type, analyst selection, provider/model pickers — mirror `cli/utils.py` prompts).
2. Live progress screen (agent-team status board + streaming report sections, the web analogue of the Rich layout in `cli/main.py`).
3. Report browser (final reports per run; run history list).

Build a throwaway static HTML/CSS mock via /prototype (frontend-design skill applies). HITL: user reacts to the artifact before this closes. Link the prototype from this ticket.

## Resolution

Prototype built (3 parallel design agents, one per structural brief), assembled into a single switchable page:

- **Artifact (view in browser):** https://claude.ai/code/artifact/b2abcc02-a706-4f18-8a37-600c00586a73 — flip variants with the floating bar, ← / → keys, or `?variant=a|b|c`.
- **Primary source:** branch `prototype/web-ui-look`, commit `1161fa8`, file `tradingagents/web/static/prototype-web-ui-look.html`.

Variants (each contains all three screens — configure / live run / reports):
- **a — Terminal Deck:** dark terminal, one continuous surface; config strip top, agent-pipeline rail left, streaming feed center, tool-call ticker right; reports as slide-up drawer.
- **b — Analyst Desk:** light editorial; wizard-based configure with stepper, live run as per-team board + accordion report sections, reports as magazine library.
- **c — Ops Workspace:** SaaS app shell; left sidebar nav with pinned live-run status, pipeline DAG over split detail pane, configure as form page, reports master-detail.

**Verdict (self-grilled per delegation; user may override by reacting to the artifact — reopens via ticket 004):** Variant **c (Ops Workspace)** as the base shell — the persistent sidebar is the only structure that naturally carries the full destination scope (new run + history + reports + future settings) and the pinned live-run item solves "navigate away and come back" for long runs. Steal two pieces: **b's** article-style report reading view for the reports pane (long-form LLM prose reads far better in an editorial column than in a dense panel), and **a's** compact tool-call ticker as a collapsible strip in the live-run detail pane (high signal for a power user, cheap to hide).
