# E2E verification findings (2026-07-25)

Method: served the real run store (`~/.tradingagents/web/runs`, 23 historical
runs) through `scripts/e2e_server.py` with `TRADINGAGENTS_E2E_RUN_ROOT`
overridden, then drove the workbench with Playwright and cross-checked the DOM
against the raw `events.jsonl` / artifact payloads. Subject run:
`run_20260724T170048041812Z_6d2f757a` — 2513.HK, `completed`, 1077 events, the
only completed run with full-length reports.

## Confirmed (already in the proposal)

**F1. Markdown is not parsed.** The bull turn's rendered `<p>` contains 36
literal `**` sequences and zero `strong`/`b`/`h1..h3`/`ul`/`table` descendants.
Body text is 13px sans at 842px width ≈ 130 characters per line, roughly double
a comfortable measure.

**F2. All debate content is hidden by default.** All 13 turns render the literal
string `点击展开` as their body. Zero characters of the debate are visible on
arrival.

**F3. Durations are absent.** Every `turn.completed` event in the run carries
`duration_ms: 0` (0 of 13 non-zero), and the role-status table renders `0s` for
all 13 rows. This confirms the spec requirement that missing execution facts be
marked unavailable rather than displayed as zero.

## New — not in the original proposal

**F4. `input.data_snapshot` is never emitted, so two inspector tabs are
structurally dead.** Across all 23 runs there are 414 `input.*` events:
`input.state_snapshot` 188, `input.prompt_snapshot` 219,
`input.config_snapshot` 7, and `input.data_snapshot` **0**. The string
`data_snapshot` does not appear anywhere in `tradingagents/observability/`.

`RoleInputPanel.tsx:38` filters the default `数据字段` tab on `data_snapshot`,
and `:280` reuses the same `dataArts` list for `原始值`. Both therefore render
`该视图暂无数据` permanently, for every turn of every run. Observed live: the
default tab of the default inspector panel is empty for a fully completed turn.

Two of five sub-tabs (40%) are unreachable content. This is a contract mismatch
between `runReducer.ts:689` (which maps a capture kind the producer never emits)
and the observability layer — not merely the information-architecture confusion
the proposal described.

**F5. `上游资料` shows metadata keys instead of upstream content.** The tab
renders `actor_id`, `effective_config_artifact_id`, `node_id`,
`projection_version`, `state_fields` — the artifact envelope's five top-level
keys. The actual upstream material lives one level down in `state_fields`, whose
`fundamentals_report` alone is a multi-thousand-character report.
`StateRefs` (`RoleInputPanel.tsx:124`) renders `Object.keys(parsed)` of the
envelope, so the user sees five meaningless identifiers and none of the content
the tab claims to show.

**F6. A single turn's payload contains multiple speakers' dialogue.** The bull
researcher's `investment_debate_state.current_response` (7374 chars) contains
three speaker labels: `**Moderator:**` at offset 118, `**Bear Analyst:**` at
offset 252, and `**Bull Analyst:**` only at offset 1282. The bull's own turn
opens with ~1300 characters of moderator narration and bear argument that the
bull's LLM authored itself. The bear's turn (8410 chars) is clean — one label at
offset 14.

This breaks the premise of the opposed-lane debate stage: the design assumes one
turn equals one speaker, so the bull lane would display bear argument. It is a
prompt-constraint defect in the agent, not a rendering defect, and it must be
resolved before or alongside the debate stage work.

Related: `investment_debate_state.history` is exactly 12000 characters — a
compaction truncation boundary — while `bull_history` (7375) and `bear_history`
(8411) are untruncated.

**F7. The identity-conflict hard stop produces false positives, and the failing
case is real.** Run `run_20260725T043002089090Z_0ff7ebc5` failed with
`error_category=evidence_rejection`:

```
EvidenceGateError: Tavily 补充 3 轮后仍不足：身份冲突：智谱AI。
Canonical company profile: canonical ticker: `2513.HK`; company short name: `unknown`.
```

2513.HK **is** 智谱 (北京智谱华章科技股份有限公司, listed on HKEX 2026-01-08,
verified against CICC, Futu, and Yahoo Finance HK sources). The gate rejected
the correct company as a wrong identity.

Mechanism, in `tradingagents/dataflows/evidence.py`:

1. profile resolution fails → `profile["name"]` empty → `_profile_name_aliases`
   (`:882`) returns an **empty set**;
2. enrichment retrieves correct news containing `智谱（2513.HK）`;
   `_wrong_names_bound_to_profile_code` (`:909`) captures `智谱AI` as a
   candidate bound to the profile's own code;
3. `_is_profile_alias(candidate, ∅)` → `any()` over an empty set → `False`;
4. `_names_are_related(candidate, ∅)` → loop over an empty set → `False`;
5. → flagged as an identity conflict → `FAIL_STOP` → run failed.

The check is **most aggressive precisely when identity is least known**, and
each additional enrichment round supplies more correct evidence that deepens the
misjudgement. Note also that `智谱AI` is not in the built-in
`WRONG_IDENTITY_HINTS` (`恒瑞医药`, `安洁科技`) and `wrong_identity_hints`
defaults to `[]`, so this fired through the unrelated-name branch, not a
configured blacklist.

This contradicts the original proposal's claim that identity conflict is
categorically non-downgradable. The check remains correct in principle — but
only when it has a resolved profile to compare against. With no profile it has
no basis for any comparison and must abstain rather than reject.

**F8. Historical run failure rate is 18/23 (78%).** By category:
`unexpected_internal_failure` 16, `evidence_rejection` 2. Two captured messages:
`ObservationPersistenceError: unable to persist observation artifact
methodology_report`, and `DataUnavailableError: DATA_UNAVAILABLE for
'get_stock_data'`. Most failures record `error_message: null`, so the categories
alone do not identify root causes. This is outside the current change's scope but
indicates the evidence gate is not the only stability problem.

**F9. The `产物` tab lists 6 of 13 role outputs.** Only 6 `report.updated`
events fire (market, sentiment, news, fundamentals, trader, portfolio); the
evidence, research-manager, and risk-role verdicts produce no report revision and
are absent from the artifact list.

## Minor

**F10. `.inspector` is applied to two nested elements** —
`WorkbenchLayout.tsx:122` (`aside`) and `Inspector.tsx:195` (`div`). Verified
cosmetically harmless (the CSS padding/border resolve to the outer element only),
but it is a duplicated class contract worth collapsing during the inspector
rewrite.

**F11. `.main` declares `overflow: auto` but never scrolls** — its
`scrollHeight` is 2958px while `scrollTop` stays 0; the document scrolls at
window level instead. Worth confirming the three-column shell's intended scroll
containment during the layout work.
