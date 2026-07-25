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

**F6. Debate turns contain other speakers' dialogue, and every turn carries a
doubled speaker label.** Three distinct defects, all reproduced against the real
run store.

*F6a — a debate role authors the other side's speech.* The bull researcher's
`investment_debate_state.current_response` (7374 chars) contains three speaker
labels: `**Moderator:**` at offset 118, `**Bear Analyst:**` at offset 252, and
`**Bull Analyst:**` only at offset 1282. The bull's own turn opens with ~1300
characters of moderator narration and bear argument that the bull's own LLM
authored.

The polluted turn is `count = 1`, the debate's **first** round, where
`bear_history` is empty (0 chars) and `current_response` is empty. The prompt
nevertheless instructs the bull to "refute the bear's concerns" and lists `Last
bear argument: {current_response}` with nothing after it
(`tradingagents/agents/researchers/bull_researcher.py:64`). Given an instruction
to rebut an argument that does not exist, the model invented a moderator handoff
and a bear argument so it would have something to rebut. The root cause is an
unconditional rebuttal instruction on an empty first round, not model
misbehaviour in general.

*F6b — the speaker label is applied twice.* The bear's turn is **not** clean, as
an earlier reading of this finding claimed. Its `current_response` begins
`Bear Analyst: **Bear Analyst:** Thank you, Moderator.` — the code prepends
`Bear Analyst: ` at `bear_researcher.py:73` while the model also emits its own
`**Bear Analyst:**` heading, because the `history` fed back into the prompt is
formatted as a labelled transcript and the model reproduces that format. The
bull path has the identical construction at `bull_researcher.py:76`. Both sides
are affected; the doubled label is systematic, not incidental.

*F6c — the debate addresses a moderator that does not exist in the graph.* Both
researchers write to a "Moderator", and the research manager's verdict opens
`### Moderator's Ruling & Action Plan`. There is no moderator node in the role
registry or the LangGraph pipeline. The transcript therefore narrates a
participant the flow map cannot show, which will read as a missing role once the
map draws explicit stages and edges.

Scope of pollution: of 35 debate payloads across all runs in the store, 2 carry
multiple speaker labels, both originating from the bull researcher. The risk
three-way debate payloads are free of foreign-speaker labels in the current
store, but `aggressive_debator.py:45`, `conservative_debator.py:45` and
`neutral_debator.py:45` share the same prompt construction and the same
code-side label prefix (`:54` in each), so they carry the same latent defect.

Impact on this change: the opposed-lane debate stage assumes one turn equals one
speaker. Rendered as-is, the bull lane would display the bear's argument, and
every lane would show a redundant label directly under the avatar that already
names the speaker. This is a prompt and state-construction defect, not a
rendering defect.

*F6d — the label is load-bearing for compaction, and the transcript is clipped
mid-sentence.* `investment_debate_state.history` is exactly 12000 characters
while `bull_history` (7375) and `bear_history` (8411) are untruncated. This is
`compact_debate_history`'s `bounded_tail` branch
(`tradingagents/graph/context_compaction.py`): with `count = 2` the transcript
holds 2 speaker turns, which is `<= recent_turns=3`, so no whole turn can be
dropped and the function falls back to `history[-max_characters:]`. The stored
string confirms it — it begins mid-sentence, `"on; Zhipu is raising $4 billion."`
The behavior is the documented fallback rather than silent corruption, but the
prompt does receive a transcript that starts mid-clause.

This makes the speaker label load-bearing: `_SPEAKER`
(`context_compaction.py:20`) is a `re.MULTILINE` regex splitting on
`^(?:Bull Analyst|Bear Analyst|Aggressive Analyst|Conservative Analyst|Neutral
Analyst):`, so removing the label from the composed `history` would collapse
every transcript into a single unsplittable turn and force the mid-sentence
clip on every run. Labels must stay in `history` even as they leave the
individual turn body.

Note on the moderator: `grep -rn "oderator" --include="*.py" tradingagents/`
returns nothing. No prompt asks for a moderator; the researchers invent it, and
the research manager picks up the framing from the transcript it reads.

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
