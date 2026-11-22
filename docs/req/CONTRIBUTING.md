# How to contribute to `requirements.yaml` (D1)

`docs/req/requirements.yaml` is the **single source of truth** for every requirement in
this project. It is assembled by A and supplied by each module owner — no one else's
acceptance criteria are written by A (see `TimeLine.md`: "全员各自供稿 FR/NFR/INV，
A 汇总但不替他人定义验收").

**One collection point: PR `docs/req-registry` (the "D1 requirement registry" PR).**
Do not open a separate PR per module — this PR must stay the only place where D1 entries
are reviewed, otherwise there is no single record of who approved what.

## Entry format (already applied — do not re-invent it)

```yaml
- id: FR-04
  type: functional            # functional | non_functional | invariant | governance | gate | submission
  statement: "…"              # one sentence, testable
  priority: Must              # MoSCoW: Must | Should | Could | Won't
  component: risk_gate
  fit_criterion:
    metric: <name>
    operator: gte             # gte | lte | eq | zero_tolerance | exists
    threshold: <value or null>
    unit: <optional>
    verification: "<command or review step that proves it>"
  evidence: [<paths>]
  source: ["§…"]
  tradeoff: <null or "…">
  owner: D                    # who owns the requirement
  supplied_by: D              # who must confirm the wording
  status: draft_from_plan     # see vocabulary below
```

## Status vocabulary

| status | meaning |
|---|---|
| `confirmed_by_owner` | the named owner has confirmed the wording/threshold in a PR comment or commit |
| `draft_from_plan` | transcribed faithfully from `execution_plan_261111.md`; **not yet confirmed**, must not be read as agreed acceptance criteria |
| `pending_owner_supply` | the plan names the artefact but states no number/value, so the field is empty — the owner must supply it |

A never promotes an entry to `confirmed_by_owner` on someone else's behalf.

## How to reply — one line per id

Comment on the collection PR:

```
<id>: confirmed
<id>: <field> -> <value>          # plus one line of reason
```

Examples:

```
NFR-01: confirmed
NFR-01: fit_criterion.threshold -> 20   # plan's 25% was a median, we gate on p95
INV-04: statement -> "…", the §3.5 row is wrong
```

Long prose is hard to apply mechanically, so keep to these two forms. If you prefer to
commit instead of comment, push a branch off the collection PR's head and edit only your
own ids; A will merge the entries.

## What each owner supplies

| owner | confirm (`draft_from_plan`) | supply a value (`pending_owner_supply`) |
|---|---|---|
| B | `FR-02`, `NFR-01`, `INV-03`, `NFR-02` (B+E), `NFR-04` (B+D) | `GOV-02` (D2 architecture artefacts) |
| C | `FR-03`, `INV-05`, `NFR-03` (C+E) | — |
| D | `FR-04`, `NFR-05`, `INV-01`, `INV-04`, `INV-06`, `INV-07`, `NFR-04` (B+D), `NFR-07`, `NFR-09`, `GATE-01`…`GATE-04`, `GATE-06` | `GOV-03` (D3), `GOV-09` (D9) |
| E | `FR-05`, `NFR-06`, `NFR-08`, `GATE-05`, `GOV-06`, `NFR-02` (B+E), `NFR-03` (C+E), `NFR-07`, `NFR-09`, `GATE-01`…`GATE-04`, `GATE-06`, `GOV-05` (A+E) | `GOV-04` (D4), `GOV-07` (D7), `GOV-08` (D8, A+E) |
| A | `GOV-01`, `SUB-01` | `GOV-05`, `GOV-08` (shared with E) |

## The governance entries (GOV-01…09 = D1…D9 deliverables)

The registry must carry the governance requirements as well, because "governance
requirements cannot live only in the README" (`execution_plan_261111.md` §3.5). Each
`GOV-0n` therefore belongs to whoever owns deliverable `Dn`.

The plan names the artefact but **states no number**, so `fit_criterion.threshold` is
`null` for six of them. An entry with a null threshold has no acceptance criterion and
cannot be verified, so each needs either:

- a number, e.g. `GOV-02: threshold -> 8` (D2 must contain 8 named sections), or
- an explicit "all named sections present" definition — say so and A will change
  `metric`/`operator` from a count to `exists`.

## Rules

1. Never invent a threshold on someone else's behalf; an entry stays `draft_from_plan`
   until its `supplied_by` owner answers.
2. Do not edit another owner's entry; propose the change in a comment and A applies it.
3. Do not touch `test/`, `src/`, `pyproject.toml`, `docs/approvals/` in the collection PR —
   it is a docs-only registry PR.
4. Numbers must match the plan exactly (80,000 tokens / 2 USD / 24 calls; ≥25 % token
   median and ≥20 % latency median; ≥90 % entailment and ≤5 pp; ≥50 security cases;
   30 s / 90 s / 300 s; ≥85 % line coverage with 100 % on safety branches; 100
   injections; zero tolerance on every invariant threshold). If the plan is wrong, say so
   explicitly rather than silently changing the number.
