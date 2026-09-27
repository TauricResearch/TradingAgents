# Jev use cases for TradingAgents

A survey of the TypeSafe Jev use-case map, patterns, and cookbooks
([docs.typesafe.ai](https://docs.typesafe.ai/llms.txt)), mapped onto this
repo's agent pipeline. Each fit names the Jev questions, where they plug in,
and what stays in code.

Surveyed 2026-09-23 against TradingAgents v0.5.0 and `jev-1.13`.

## Ground rules

Jev returns typed judgments (Choice, Noul, Score) over natural-language
state. It does not generate text. Its known weaknesses (see
[jev-1.13 jaggedness](https://docs.typesafe.ai/model-jaggedness/jev-1.13.md))
set the boundaries for every fit below:

- **Numbers, dates, and counting stay in code.** Jev cannot reliably count,
  compare numeric values, or order dates. Price levels, returns, indicator
  values, look-ahead window filtering, and bullish/bearish ratios are never
  asked of it.
- **Small, focused state.** Jev has a bounded context window and suffers
  context rot from unrelated detail. Ask per headline, per post, or per claim,
  not over a whole analyst report.
- **Reports stay with the LLMs.** Analysts, debaters, and managers keep
  writing prose. Jev adds cheap, typed decisions around them.
- **Ask together.** Independent questions over the same state go in one
  request ([Parallel Questions](https://docs.typesafe.ai/cookbooks/parallel_questions.md)).
- **Thresholds are ours to tune.** Cookbook thresholds are examples. Tune on
  this repo's backtest outcomes (`tradingagents/backtest.py`).

## Strong fits

### 1. Filter news and social items before the analysts see them

**Goal:** stop off-topic, stale, duplicate, and injected content from reaching
the analyst prompts. Reddit and StockTwits text is untrusted input that is
currently pasted straight into the Sentiment Analyst's system message.

**Jev questions (one request per item, all Nouls):**

| Id | Question |
| --- | --- |
| `about_company` | Does this item discuss `instrument`: the company itself, or what other news means for it? (Criteria keep competitor news that says what it means for the instrument, and drop posts that only list its cashtag.) |
| `material_event` | Does this item report a concrete event that could affect the company's business or stock (earnings, guidance, deal, lawsuit, product, management change)? |
| `injection` | Does this item contain instructions aimed at an AI system rather than content for a reader? |
| `duplicate` | Does this item report the same story as an item already in `kept_items`? (Second request, same source only. For StockTwits and Reddit it asks whether the post is a copy, because separate posts about one event are separate voices. Exact repeats are settled in code.) |

**Policy in code** (ordered, as in the RAG cookbook): injection above a
threshold drops the item; `about_company` below a threshold drops it;
`duplicate` above a threshold drops it; the rest are kept, with
`material_event` used for ordering.

**Where:** prefetch step in
[`sentiment_analyst.py`](../tradingagents/agents/analysts/sentiment_analyst.py);
fetchers in [`yfinance_news.py`](../tradingagents/dataflows/vendors/yahoo/news.py),
[`alpha_vantage_news.py`](../tradingagents/dataflows/vendors/alpha_vantage/news.py),
[`reddit.py`](../tradingagents/dataflows/vendors/reddit.py),
[`stocktwits.py`](../tradingagents/dataflows/vendors/stocktwits.py).

**Status:** built, together with fit 2. See [Fits 1 and 2 as built](#fits-1-and-2-as-built).

**Jev sources:** [Classifying RAG Passages](https://docs.typesafe.ai/cookbooks/classifying_rag_passages.md),
[Guardrails for LLMs](https://docs.typesafe.ai/cookbooks/llm_guardrails.md),
[Entity Alignment](https://docs.typesafe.ai/cookbooks/entity_alignment.md),
[Parallel Questions](https://docs.typesafe.ai/cookbooks/parallel_questions.md).

### 2. Score sentiment per item and compute the total in code

**Goal:** replace the LLM-chosen `overall_score` / `overall_band` /
`confidence` header with a deterministic aggregate of per-item judgments.

**Jev questions (asked in the same request as fit 1):**

| Id | Primitive | Question |
| --- | --- | --- |
| `stance` | Score | How bullish or bearish is this item toward the company's stock? Levels from strongly bearish to strongly bullish, with neutral in the middle. |
| `event_type` | Choice | Which kind of event is this: earnings, guidance, M&A, legal/regulatory, product, management change, macro, analyst action, opinion only, or none of these? |
| `opinion_only` | Noul | Is this item opinion or speculation, rather than a report of something that happened? |

**Policy in code:** weight each item by source (news vs StockTwits vs Reddit)
and by `opinion_only`; the score is the weighted mean of `stance`; confidence
comes from item count and how much the stances agree. The band is derived from
the score by fixed cut-offs. The LLM still writes the `narrative`, and is given
the computed header plus the per-item tags. When `event_type` confidence is
low, report the broader group instead of the specific type.

**Where:** `SentimentReport` / `render_sentiment_report` in
[`schemas.py`](../tradingagents/agents/schemas.py), and the sentiment analyst node.

**Status:** built, together with fit 1.

**Jev sources:** [Composite Scoring](https://docs.typesafe.ai/patterns/composite-scoring.md),
[Hierarchical Classification](https://docs.typesafe.ai/cookbooks/hierarchical_classification.md),
[Classification Using Confidence](https://docs.typesafe.ai/cookbooks/classification_using_confidence.md).

### 3. Stop debates when they converge

**Goal:** the bull/bear and risk debates run a fixed number of rounds today.
End them early when a turn adds nothing new. Each skipped turn saves one
quick-model call whose prompt carries every analyst report.

**Jev questions (after each turn):**

| Id | Primitive | Question |
| --- | --- | --- |
| `new_argument` | Noul | Does `latest_turn` raise a substantive argument or piece of evidence that does not already appear in `prior_turns`? |
| `stronger_side` | Choice | Based on `debate_history`, whose case is better supported by evidence: bull, bear, or evenly matched? |

**Policy in code:** after the minimum rounds, stop when `new_argument` is
below a threshold; never exceed `max_debate_rounds` / `max_risk_discuss_rounds`.
`stronger_side` is passed to the Research Manager as a hint, not a verdict.

**Where:** `should_continue_debate` and `should_continue_risk_analysis` in
[`conditional_logic.py`](../tradingagents/graph/conditional_logic.py).

**Status:** built. See [Fit 3 as built](#fit-3-as-built).

**Jev sources:** [Intent Routing](https://docs.typesafe.ai/patterns/intent-routing.md),
[Confidence-Gated Routing](https://docs.typesafe.ai/patterns/confidence-routing.md).

### 4. Check the Portfolio Manager's claims against the reports

**Goal:** catch evidence the Portfolio Manager invented or misread. It never
reads the analyst reports: its prompt holds the research plan, the trader's
plan, the risk debate and past lessons. A fact in its thesis has passed through
two or three LLM summaries before it gets there.

**Jev questions:**

| Id | Primitive | Asked | Question |
| --- | --- | --- | --- |
| `checkable` | Noul | once per claim | Is `claim` a fact about `instrument`, its business, stock, industry or market that an analyst report could confirm or refute? Assessments such as "margins are expanding" count. Recommendations, plans, price targets, the writer's own forecasts, remarks about the debate or the analysts, past lessons, holdings and generic caveats do not. |
| `source` | Choice | same request | Which analyst report would state the facts in `claim`? The options are the reports written in this run, each described. Skipped when there is only one. |
| `relation` | Choice | once per checkable claim × section | How does `section` relate to `claim`? Options: supports (states or implies at least one of its points and contradicts none), contradicts, says nothing. |

**Policy in code:** split the Investment Thesis into claims (bullets and
sentences). Pair each checkable claim with the sections of every report it
could come from. Accept a claim when some section supports it with high
confidence; otherwise flag it as contradicted when some section contradicts it
with high confidence; otherwise it is unsupported. Send the decision to
`REVIEW` when a claim is contradicted, or when unsupported claims are both
several and at least half of the checkable ones. Figures are matched in code
(the cookbook's string-match step): a number in a checkable claim that no
report states is listed, but does not send the decision to `REVIEW` on its own,
since the Portfolio Manager legitimately derives figures such as the upside to
its target. The first survey planned to check numeric claims with
[`market_data_validator.py`](../tradingagents/dataflows/market_data_validator.py).
That does not work: the module only builds the price and indicator snapshot the
Market Analyst treats as ground truth, checks no claims, and covers none of the
figures from the other three reports.

**Where:** the end of
[`portfolio_manager.py`](../tradingagents/agents/managers/portfolio_manager.py)
(the same check also fits the Research Manager's plan).

**Status:** built. See [Fit 4 as built](#fit-4-as-built).

**Jev sources:** [Double-Checking Citations](https://docs.typesafe.ai/cookbooks/citation_check.md).

### 5. Turn reports into features and learn from outcomes

**Goal:** a calibrated signal learned from resolved decisions, alongside the
LLM's rating.

**Method:** a fixed set of Score and Noul questions per analyst report (for
example: fundamentals trend, valuation stretch, sentiment extremity, catalyst
proximity, risk-debate asymmetry). Each Score becomes two columns (expected
level and spread), each Noul one probability column. Train a small model on the
alpha outcomes in a backtest's decision log, joined to the reports that each
cell saved. The model is logistic, since a sweep has tens to hundreds of
decisions; CatBoost would need more. Grow the question set by proposing new
questions from the worst-predicted cases, keeping only questions that improve
held-out error.

**Where:** a new command, `tradingagents learn`, over a
[`backtest.py`](../tradingagents/backtest.py) run. It reads the resolved entries
of the run's [`decision_log.py`](../tradingagents/decision_log.py) log and the
full state each cell saved.

**Prerequisite:** enough resolved backtest decisions to train and hold out
data. This is the largest potential upside.

**Status:** started. The questions, the model, the evaluation and the command
are built. Proposing new questions is not automated yet, and the signal is not
used in live runs. See [Fit 5 as built](#fit-5-as-built).

**Jev sources:** [Autoresearch Feature Discovery](https://docs.typesafe.ai/cookbooks/autoresearch_feature_discovery.md),
[Composite Scoring](https://docs.typesafe.ai/patterns/composite-scoring.md).

## Moderate fits

### 6. Pick past lessons by relevance, not recency

`get_past_context` takes the 5 most recent same-ticker entries and 3
cross-ticker ones. Instead, score each resolved lesson for relevance to the
current setup (Score) and inject the best ones. Keep the `as_of` point-in-time
filter in code.

**Where:** `get_past_context` in [`decision_log.py`](../tradingagents/decision_log.py).
**Jev sources:** [Re-Ranking](https://docs.typesafe.ai/cookbooks/rerank_typesafe.md),
[Line-by-Line Search](https://docs.typesafe.ai/cookbooks/semantic_find.md).

### 7. Rescue the rating when parsing fails

When `extract_rating` returns `None` on the free-text fallback path, ask a
Choice over Buy / Overweight / Hold / Underweight / Sell / no rating stated.
Low confidence or "no rating stated" still yields `REVIEW`. A second check
(Noul): does the stated rating agree with the Executive Summary? Structured
output already covers most runs, so this is a rarely-used fallback.

**Where:** [`rating.py`](../tradingagents/agents/rating.py),
`process_signal` in [`trading_graph.py`](../tradingagents/graph/trading_graph.py).
**Jev sources:** [Confidence-Gated Routing](https://docs.typesafe.ai/patterns/confidence-routing.md),
[Self-Consistency: Choices](https://docs.typesafe.ai/cookbooks/consistency_choice_cookbook.md).

### 8. Keep only the relevant prediction markets

One Noul per Polymarket market returned for a topic: is this market relevant
to `instrument` or the macro question being asked? Drop the rest.

**Where:** [`polymarket.py`](../tradingagents/dataflows/polymarket.py).
**Jev sources:** [Re-Ranking](https://docs.typesafe.ai/cookbooks/rerank_typesafe.md).

### 9. Tag each reflection with what the outcome showed

Choice on each stored reflection: thesis confirmed, thesis invalidated, or
window too short to judge. Later runs can filter or weight lessons by tag.

**Where:** [`reflection.py`](../tradingagents/graph/reflection.py) and the
memory log entry format.
**Jev sources:** use-case map, Feature Extraction.

### 10. Choose the model tier per ticker

Route clear-cut cases to the quick model and conflicting ones to the deep
model, using analyst-report agreement judgments from fits 2 and 3.

**Where:** [`trading_graph.py`](../tradingagents/graph/trading_graph.py).
**Jev sources:** use-case map, Model Routing;
[Intent Routing](https://docs.typesafe.ai/patterns/intent-routing.md).

## Not applicable

| Jev use case | Why not |
| --- | --- |
| Structure Recovery | No plain text needs converting to Markdown. |
| Skill Suggestion, Function Calling | The LLM analysts already choose tools. |
| Date Extraction, Pre-Parsed Value Extraction | Dates and SEC figures already arrive structured; dates are a Jev weakness. |
| SDE Cascade | The decision agents already use structured output. |
| Real-time applications | The pipeline is a daily batch run; latency is not the constraint. |
| Knowledge graphs | Could model supply-chain links, but nothing in the repo consumes them. |
| Recruiting, lead generation, customer support, insurance, e-commerce, moderation, advertising, gaming, demand forecasting, financial crime, legal/compliance, semantic code linting | Outside this domain. |

## Build order

1. ~~**Fits 1 + 2**~~ (built) together in the Sentiment Analyst: one Jev request per
   item, isolated to one agent, testable with `tests/test_social_lookahead.py`
   and `tests/test_stocktwits_resilience.py`. Fixes untrusted social text in
   prompts and the LLM-chosen sentiment score.
2. ~~**Fit 4**~~ (built, ahead of fit 3): claim verification on the final decision.
3. ~~**Fit 3**~~ (built): debate convergence, a direct cost saving. Live check
   run 2026-09-24; next, measure how often a real debate stops early.
4. **Fits 6–10** as needed.
5. **Fit 5** (started): the features, the model and `tradingagents learn` are
   built. Next, run a backtest with enough settled decisions, then grow the
   question set from what that shows.

Every integration should degrade to current behavior when `TYPESAFE_API_KEY`
is unset or the `jev` extra is not installed.

## Fits 1 and 2 as built

**Code:** [`sentiment_judgments.py`](../tradingagents/agents/sentiment_judgments.py)
(questions, `SentimentPolicy`, aggregate, prompt blocks),
[`jev.py`](../tradingagents/agents/jev.py) (client and concurrent requests),
[`feed.py`](../tradingagents/dataflows/feed.py) (the fetchers now return their
items as well as the prompt block), and the branch in
[`sentiment_analyst.py`](../tradingagents/agents/analysts/sentiment_analyst.py).
Tests: [`test_jev_sentiment.py`](../tests/test_jev_sentiment.py).

**Flow per run:**
1. Fetch news, StockTwits, and Reddit. Each item is kept, along with the prompt block the fetcher would have returned.
2. Send one Jev request per item with all six fit 1 and 2 questions. Code drops, in order: injection above 0.70, then `about_company` below 0.45.
3. Send one request per surviving item that has an earlier survivor from the same source. Code drops `duplicate` above 0.70.
4. Compute the header from the kept items. The score is `5 + 5 ×` the weighted mean stance (news 1.0, social 0.5, halved for opinion). The band uses fixed cut-offs, and a split in the neutral zone reads as Mixed. Confidence comes from the item count, the number of sources, and the stance spread, and is capped at medium when a source is unavailable.
5. The LLM gets only the kept items, tagged with stance, event, and opinion or report, plus the fixed header. It writes the narrative only (`SentimentNarrative`).

**Degrades:** with no `TYPESAFE_API_KEY`, `jev_enabled: False`
(`TRADINGAGENTS_JEV_ENABLED=false`), or no `jev` extra, the analyst runs
exactly as before. If a Jev request fails after the SDK's retries, the
analyst builds the old prompt from the feeds it has already fetched, and the
LLM chooses the header. It does not fetch again, because Reddit's anonymous
feed allows about one request per minute.

**Live check (NVDA, week to 2026-09-23, `jev-1.13.0`):** 63 items were judged
in about 6.5 s. 18 of Yahoo's 20 "NVDA" news articles were general-market
stories (SpaceX, AutoZone, Monster Beverage) and were dropped. Two Reddit
cross-posts were caught as repeats. A planted injection scored 0.99 and was
dropped; its stance of −0.71 would otherwise have pulled the score bearish.

**To tune next:** the thresholds, source weights, and band and confidence
cut-offs are all in `SentimentPolicy`. They are cookbook starting points, not
values fitted to this domain. Once backtest decisions resolve, tune them
against alpha, then pin `jev_model` to the versioned id they were tuned on.

## Fit 4 as built

**Code:** [`claim_check.py`](../tradingagents/agents/claim_check.py)
(claim and section splitting, questions, `ClaimCheckPolicy`, figures, output),
one call at the end of
[`portfolio_manager.py`](../tradingagents/agents/managers/portfolio_manager.py),
and the `REVIEW` label in [`rating.py`](../tradingagents/agents/rating.py).
Tests: [`test_jev_claim_check.py`](../tests/test_jev_claim_check.py) and
[`test_rating_integrity.py`](../tests/test_rating_integrity.py). There is no new
graph node, so the CLI and web UI statuses and the checkpoint signature are
unchanged.

**Flow per decision:**
1. The Investment Thesis is read from the rendered decision: `**Investment Thesis**:`
   up to `**Price Target**` or `**Time Horizon**`, or a `## Investment Thesis`
   heading on the free-text path, or else the whole text minus the rating line.
   Code splits it into bullets and sentences, strips markdown, and drops
   fragments under 25 characters and repeats. The first 20 claims are checked.
2. Each written analyst report is split at its headings (a bold line counts as
   one). Parts over 2,400 characters are cut at paragraph blocks, with tables
   kept whole, and parts under 400 characters are merged with a neighbour.
3. One request per claim asks `checkable` and, with two or more reports,
   `source`. The state is the instrument (ticker, name and classification, read
   from the context resolved at run start) and the claim.
4. One request per checkable claim and section of each report with
   P(source) ≥ 0.15 asks `relation` and `needs_numbers`: would telling the
   relation take comparing numbers, because the section does not say it in
   words? The state adds the section: its report, heading and text.
5. Code gives each claim a verdict. Sections with P(needs_numbers) ≥ 0.50 are
   left out of support and contradiction, since Jev cannot compare numbers.
   Over the rest: supported if the best P(supports) is at least 0.60; otherwise
   contradicted if the best P(contradicts) is at least 0.80. Otherwise the
   claim is unverified if a left-out section addresses it (P(supports) +
   P(contradicts) ≥ 0.50), and not found if none does. The section behind the
   verdict (for a claim not found, the closest one) is kept for the output.
6. Code lists each figure in a checkable claim that no report states when
   rounded to the claim's precision. It reads %, $, x, bps, K/M/B/T and
   million/billion/trillion, and skips years, dates, periods ("12 months"),
   counts under 10, and numbers inside names or labels such as Q3, 10-K, H100
   and S&P 500. Signs are ignored, since direction is Jev's question.
7. The decision goes to `REVIEW` when a claim is contradicted, or when at least
   2 claims are not found and they are at least half of the checkable ones.
   Unverified claims and unmatched figures never do. With no checkable claims,
   only a note is added.

**Output:** a block appended to the decision, so `judge_decision`,
`final_trade_decision`, the saved report and the memory log all carry it. It is
kept short, because past decisions come back into later prompts through
`TradingMemoryLog.get_past_context`:

```
**Claim Check**: 10 statements read from the Investment Thesis, 7 checkable against the analyst reports: 3 supported, 2 contradicted, 1 unverified, 1 not found. 2 figures in no report. (Claims judged by TypeSafe Jev; figures matched in code.)
- Contradicted: "Gross margin expanded to 76% on pricing power, showing the Blackwell ramp is already paying off." (fundamentals report, "Latest quarter (Q2 FY2027, reported 2026-08-27) / Margins /…"; contradicts 1.00)
- Contradicted: "Free cash flow reached $19.2 billion in the quarter, funding the enlarged buyback." (fundamentals report, "Latest quarter (Q2 FY2027, reported 2026-08-27) / Margins /…"; contradicts 0.99)
- Unverified: "At 29.5x forward earnings the stock trades below its five-year average multiple." (fundamentals report, "Latest quarter (Q2 FY2027, reported 2026-08-27) / Margins /…"; needs a numeric comparison 0.94)
- Not found: "Microsoft signed a multi-year supply agreement for Blackwell Ultra systems last week." (closest: news report, "Company news / Industry / Macro"; supports 0.02)
- Figure in no report: 76% in "Gross margin expanded to 76% on pricing power, showing the Blackwell ramp is already paying off."
- Figure in no report: $19.2 billion in "Free cash flow reached $19.2 billion in the quarter, funding the enlarged buyback."

**Rating after claim check**: REVIEW (the Portfolio Manager rated Buy; 2 claims contradicted by the analyst reports)
```

This is a recorded run of the live check below, after the numeric-comparison
fix. `extract_rating` reads a
last labelled `REVIEW` as no rating, so the signal, the memory log tag, the
backtest (as unscored), the CLI and the web UI all show `REVIEW`. The
Portfolio Manager's own rating stays in the text. When the check does not send
the decision to review, the last line restates the Portfolio Manager's rating
(`**Rating after claim check**: Buy (the Portfolio Manager rated Buy)`), or
`REVIEW` when none could be read. The block therefore always ends with the
rating label, and no quoted claim or cited report heading above it can be read
as the rating.

**Degrades:** with no `TYPESAFE_API_KEY`, `jev_enabled: False`, no `jev` extra,
`jev_claim_check: False` (`TRADINGAGENTS_JEV_CLAIM_CHECK=false`), or no analyst
report in the run, the decision is exactly as before. If any Jev request fails
after the SDK's retries, a warning is logged and the decision is kept unchecked,
never partly checked.

**Load:** about one request per claim plus one per checkable claim and routed
section. The live-check script's short reports split into 5 sections, and each
checkable claim routed to one of them: 10 + 8 requests in 1.8–2.4 s. A full
four-report run has longer reports and more sections. The estimate for that is
roughly 10 + 70 requests, or 8–10 s at `MAX_CONCURRENT_REQUESTS = 8`, and it has
not been measured yet.

**Live check (2026-09-23, `jev-1.13.0`, 3 runs):**
[`scripts/jev_claim_check_live.py`](../scripts/jev_claim_check_live.py) holds
hand-written NVDA reports and a Buy decision with three planted failures: a
contradicted fact (gross margin "expanded to 76%" when the report says it fell
to 71.2%), an invented fact (a Microsoft supply deal), and an invented figure
(free cash flow of $19.2 billion when the report says $13.5 billion). All three
were caught on every run. The margin claim was contradicted (≥ 0.99), and so was
the free cash flow claim (≥ 0.99). The figure check also listed 76% and
$19.2 billion. The Microsoft deal was not found (supports ≤ 0.02). Each run sent
the decision to `REVIEW`. The two sourced facts (data-center revenue; moving
averages and MACD) and the Fed cut were supported every time. The three remarks
(who won the debate, the lesson, the plan) scored checkable ≤ 0.08, and the
routing put every checkable claim on the right report.

One false positive in those first runs: "At 29.5x forward earnings the stock
trades below its five-year average multiple" is true by the report (29.5x
against 36x). Jev judged it contradicted on two runs (0.95, 0.85) and supported
on one (0.61). Alone, this claim would have sent a correct decision to `REVIEW`.
A probe showed why. Asked 3 times each, the relation for this claim and for its
false twin ("trades above") came out either way, since Jev cannot compare
numbers. The `needs_numbers` question separated the comparison pairs (0.86–0.94)
from the rest, genuine contradictions included (≤ 0.23), and it held steady
across runs.

**After the fix (3 more runs each):** the P/E claim is unverified every time
(needs_numbers 0.93–0.94), and the three planted failures are caught as before,
still sending the decision to `REVIEW`. The same thesis without the planted
failures now keeps its Buy on every run (3 supported, 1 unverified). A worded
contradiction whose figures all appear in a report ("Operating margin rose to
60.8%" against "60.8%, down from 62.1%") has needs_numbers 0.14–0.17, so the fix
leaves it alone. Its P(contradicts) sits at 0.85–0.90, near the 0.80 bar, and
one run in three fell under it (not found).

The cost: a comparison whose direction is wrong ("trades above its average" at
29.5x against 36x) is also unverified, not contradicted. Jev could not tell it
apart from the true one either way.

**To tune next:** every threshold is in `ClaimCheckPolicy` and is a cookbook
starting point (the cookbook auto-accepts at 0.8). A decision sent to `REVIEW`
is left out of the backtest figures, so tuning needs the Portfolio Manager's
own rating from the text of those decisions, compared with the outcomes of the
ones that passed. To catch comparisons with the wrong direction, code would
have to find the two numbers being compared, which is not done yet. Also worth
watching live: sentences that open with a pronoun
("It grew 22%") reach Jev without their subject, and the checkable filter
decides how many of the Portfolio Manager's remarks about the debate are
checked at all.

## Fit 5 as built

**Code:** [`report_features.py`](../tradingagents/report_features.py)
(documents, questions, answer cache, extraction, loading decisions,
`learn_from_run`), [`outcome_model.py`](../tradingagents/outcome_model.py)
(logistic model, chronological splits, evaluation), and the `learn` command in
[`cli/main.py`](../cli/main.py). Tests:
[`test_jev_report_features.py`](../tests/test_jev_report_features.py) and
[`test_outcome_model.py`](../tests/test_outcome_model.py). Nothing in an
analysis run changes: this reads a finished backtest.

```bash
tradingagents backtest NVDA,AAPL,MSFT,AMD --start 2026-03-02 --end 2026-08-31 --every 7 --run-id sweep1
tradingagents learn sweep1
```

**Flow per backtest run:**
1. Read the run's decision log, and keep each settled decision that has an
   alpha and a resolution date. Join it to the full state its cell saved,
   `<TICKER>/TradingAgentsStrategy_logs/full_states_log_<date>.json` in the run
   folder. A run with fewer than 40 such decisions, or fewer than 6 analysis
   dates, is refused before any Jev request.
2. Each decision has seven documents: the four analyst reports, the bull and
   bear debate, the risk debate, and the Portfolio Manager's decision without
   its claim-check block. One request per document asks all of that document's
   questions. The state is the ticker and the document's kind and text.
3. Each Score becomes two columns: its expected level (0 to its top level) and
   the standard deviation of its level distribution. Each Noul becomes one, its
   probability. That makes 24 Jev columns. Code adds `rating`, the Portfolio
   Manager's own rating from Buy (1) to Sell (−1), read from the text before the
   claim-check block, so a decision sent to `REVIEW` keeps it. It also adds
   `review`, 1 when the logged rating is `REVIEW`.
4. Answers are cached in `<data_cache_dir>/jev_report_features.json`, keyed by
   the model name, the question and the state. Asking again sends nothing. A new
   or reworded question sends only that question. After a failed request, the
   answers already received stay cached.
5. The target is whether the decision's alpha was above 0. Three L2-penalised
   logistic models are fitted: the base rate (no columns), the rating (`rating`
   and `review`), and the rating plus the Jev columns. A missing document's
   columns take the training mean.
6. The last 25% of analysis dates are held out (`--holdout`). The earlier dates
   are cross-validated walk-forward, in 4 expanding folds. A decision trains a
   model only if its resolution date is before the first date that model is
   tested on: its holding window overlaps the next week's, and a shuffled split
   would train on outcomes from the test period. Each model's penalty is chosen
   on those folds (0.3 to 30), and each model is then scored once on the held-out
   dates.
7. For each question, the dev log loss of the full model without its columns,
   minus with them. Keep a question while this is above 0, as the cookbook
   does. A question whose columns all have a standard deviation under 0.05 on
   the dev decisions is flat. The five decisions the full model predicted worst
   are listed as the cases to read when proposing new questions.

**Questions (14):**

| Id | Document | Primitive | Asks |
| --- | --- | --- | --- |
| `price_trend` | market | Score (5) | the trend the report describes, strong downtrend to strong uptrend |
| `overbought` | market | Noul | whether it calls the stock overbought or stretched upward |
| `oversold` | market | Noul | whether it calls the stock oversold or stretched downward |
| `fundamentals_trend` | fundamentals | Score (5) | deteriorating sharply to improving strongly |
| `valuation_stretch` | fundamentals | Score (5) | clearly cheap to stretched, with "fair, or not judged" in the middle |
| `balance_sheet_risk` | fundamentals | Noul | whether it flags heavy debt, weak liquidity, cash burn or dilution |
| `sentiment_tone` | sentiment | Score (5) | strongly bearish to strongly bullish |
| `sentiment_extremity` | sentiment | Score (5) | quiet or evenly mixed to euphoria or panic, either direction |
| `news_tone` | news | Score (5) | clearly bad to clearly good for the stock |
| `catalyst_proximity` | news | Score (4) | no upcoming event named to an event due in the coming days |
| `macro_headwind` | news | Noul | whether the macro or sector backdrop is described as a headwind |
| `bull_bear_balance` | research debate | Score (5) | bear case much stronger to bull case much stronger, on the evidence cited |
| `risk_debate_asymmetry` | risk debate | Score (5) | strongly toward caution to strongly toward taking the risk |
| `conviction` | decision | Score (5) | very low (heavily hedged) to very high (clear-cut) |

`catalyst_proximity` reads timing as the report words it. Jev is not given the
analysis date, since it reads dates as text and cannot count from them.

**Output:** the evaluation below, and `report_features.csv` in the run folder,
with one row per decision: the ticker, the dates, the logged and the Portfolio
Manager's rating, the alpha and every column. The CSV is there for a closer
look, or for another model. This example is the synthetic data in
`test_outcome_model.py`, where one column carries the outcome and the rating
carries none. No real sweep has been scored yet.

```
Settled decisions: 64 over 16 analysis dates. Held out 2026-03-30 to 2026-04-20: 16 decisions. Trained on the 44 settled before 2026-03-30, of which 52% beat the benchmark.

Log loss of P(beats the benchmark), lower is better (0.693 is a coin flip):
- base rate: dev CV 0.687, held out 0.688
- rating: dev CV 0.687, held out 0.688 (L2 0.3)
- rating + Jev features: dev CV 0.324, held out 0.071 (L2 0.3); held-out alpha +2.09% (n=9) where it favours the stock vs -2.40% (n=7) elsewhere

Questions, by how much dropping each one raises the dev CV log loss of the full model. Keep one only while this is above 0; a small gain is often noise:
- signal: +0.3672 (keep)
- noise: +0.0056 (keep)
- flat: +0.0000 (flat: drop)

Worst-predicted dev decisions, the cases to read when proposing new questions:
- T32 2026-03-02 Buy: P(beats) 0.83, alpha -1.3%
...
```

The pure-noise column there passes the keep rule by 0.006. With a few dozen
decisions, a small gain is not evidence. A question should earn its place on the
held-out dates and again on a later or wider sweep.

**Refuses:** without the `jev` extra or `TYPESAFE_API_KEY`, or with
`jev_enabled: False`, the command says what it needs and exits. A run that is
too small exits before any request, with its counts: settled, pending, and
settled without a saved state. When a request fails, the error is printed and
the answers already received stay cached, so running the command again
continues from there. The command warns when the cached answers come from more
than one model.

**Load:** 7 requests per decision the first time, so 700 for 100 decisions, and
none after that. The live check below sent 21 requests in 3.0–3.7 s. Its
documents are short; real reports are longer, and their token counts have not
been measured. At $0.042 per million input tokens, even 20,000 tokens per
decision costs under a tenth of a cent. The backtest's LLM runs cost far more
than this step.

**Live check (2026-09-23, `jev-1.13.0`, 3 runs):**
[`scripts/jev_report_features_live.py`](../scripts/jev_report_features_live.py)
holds one decision's seven documents written three ways: bullish (A), mixed
(C) and bearish (B). Each is written to have a known answer per question. For
example, A is a strong uptrend at RSI 77 that is called overbought, with a
valuation called attractive, earnings due next week, and an emphatic Buy. B is a
steep downtrend called oversold, with a stretched valuation, a heavy debt load,
panic on social media, no upcoming event, and an Underweight called "a close
call". C is range-bound, fairly valued and evenly argued.

All 14 questions ordered A and B the expected way on every run. Most sat at or
near the ends of the scale: `price_trend` 4.00 against 0.00, `overbought` 0.99
against 0.02, `balance_sheet_risk` 0.02 against 0.98, `conviction` 4.00 against
0.06–0.09. `valuation_stretch` placed A at 0.89–0.90 ("somewhat cheap", as
written) and B at 4.00. The answers barely moved between runs: no expected
level or probability changed by more than 0.05. This is far steadier than fit
4's relation answers. The mixed run fell between A and B on 9 of the 10 Scores. The exception
is `sentiment_extremity`, which has no direction, so the calm, evenly split
run is the lowest (0.00), as its levels define. The spread columns were small
on these clear-cut documents (mean standard deviation 0.00–0.17).

This shows that each question reads what it asks about. It does not show that
any column predicts alpha. The documents were written to be unambiguous, and
real reports hedge. That question is for `tradingagents learn` on a real sweep.

**Not built yet:**
- A sweep large enough to learn from. It needs at least 40 settled decisions
  over 6 dates to run at all, and far more to trust. The cookbook's dev set had
  1,200 rows. Four tickers weekly for six months gives about 100 cells, each a
  full pipeline run.
- Proposing questions automatically. The command lists the worst-predicted
  decisions, but reading their reports and adding questions to `QUESTIONS` is
  done by hand. The cookbook's loop gives an LLM the 30 worst and 30 best
  predicted cases, with each feature's importance, and asks it to add, revise or
  drop questions. Automating that is the next step.
- Using the signal. Nothing reads the model in an analysis run. Only once it
  beats the rating on the held-out dates of a large sweep, and again on a later
  one, should P(beats the benchmark) appear next to the rating.
- More columns from code, at no Jev cost: the computed sentiment score from
  fit 2, and the claim-check counts from fit 4.

**Watch:** the cache key uses the configured model name. Pin `jev_model` to a
versioned id before collecting answers you mean to compare, since an alias such
as `jev-latest` moves. Each backtest cell is also one sampling of every LLM, and
the text feeds are not archived, so re-running a cell gives different reports
and different answers.

## Fit 3 as built

**Code:** [`debate_judgments.py`](../tradingagents/agents/debate_judgments.py)
(questions, `DebatePolicy`, the convergence rule, the Research Manager's hint),
`judge_turns` and the two debate routers in
[`conditional_logic.py`](../tradingagents/graph/conditional_logic.py), the
wrapped debater nodes in [`setup.py`](../tradingagents/graph/setup.py), and the
hint in [`research_manager.py`](../tradingagents/agents/managers/research_manager.py).
Tests: [`test_jev_debate.py`](../tests/test_jev_debate.py).

**Flow per debate:**
1. Each debater node is wrapped. After its turn, the wrapper asks `new_argument`
   in one request. The state is the debate so far (`prior_turns`) and the new turn
   (`latest_turn`). The answer is appended to the debate state's `new_argument`
   list, one entry per turn.
2. Only turns whose answer could end the debate are asked about. That excludes
   round 1, which holds every side's opening, and the last configured round,
   which ends the debate anyway. Every other turn records `None`.
3. At the end of each round from round 2 on, the router stops the debate when
   every turn in that round scored below 0.30. A turn with a `None` answer keeps
   the debate going. The debate still never runs past its configured rounds, and
   it stops only at a round boundary, so every side gets the same number of turns.
4. When the investment debate ends, the Research Manager asks `stronger_side`
   over the bull and bear histories in one request. The answer is added to the
   prompt as a hint with all three probabilities, after the debate history. It is
   marked as coming from a classifier that saw only the debate. It names a side
   only when that side gets at least `side_lead_min` (0.50); below that it says
   there was no clear winner. The probabilities are stored as `stronger_side` in
   the debate state.
5. The run log (`full_states_log_<date>.json`) records `turns`, `new_argument`,
   and `stronger_side` for each debate, for tuning `DebatePolicy`.

**Input limit:** Jev rejects a request above about 33K input tokens with
`400 max_tokens_exceeded`. For debate text that is about 110K characters
(measured 2026-09-24). Deep debates pass it. In a real Deep run the bull and
bear histories came to 135K characters, `stronger_side` failed, and the Research
Manager got no hint. Every debate state is now capped at `MAX_STATE_CHARS`
(80,000, in [`jev.py`](../tradingagents/agents/jev.py)). The oldest whole
turns are dropped first, and an `[Earlier turns omitted for length.]` line
replaces them. `new_argument` gets whatever room the latest turn leaves. A point
last made in a dropped turn then reads as new, which keeps the debate going, the
safe direction. `stronger_side` gives each side half the budget.

**When it saves calls:** early stopping needs at least three configured rounds,
because round 1 is the openings and the last round ends the debate anyway. The
default (`max_debate_rounds: 1`) and the Shallow depth never stop early. At Medium
depth (3 rounds), a converged investment debate saves up to one round (two
calls) at the cost of two Jev requests, and a converged risk debate saves up to
one round (three calls) at the cost of three. At Deep depth (5 rounds), the savings are up to three
rounds per debate. With Jev on, every run also sends one `stronger_side`
request.

**Degrades:** with no `TYPESAFE_API_KEY`, `jev_enabled: False`, or no `jev`
extra, every `new_argument` entry is `None`, the debates run their configured
rounds, and the Research Manager's prompt is unchanged. A failed request is
logged and treated the same way for that turn or hint.

**Live check (2026-09-24, `jev-1.13.0`, 3 runs, done twice):**
[`scripts/jev_debate_live.py`](../scripts/jev_debate_live.py) asks about
hand-written NVDA turns and debates, and with `--log` it replays a real run log.
All 13 labelled cases passed on every run.
- `new_argument`, judged against the round-1 openings: two rebuttals that
  brought new evidence scored 0.97–0.98. A turn that restated the bear's case
  and added one fact (the 10-year yield) scored 0.93–0.94. Two restatements and
  a turn of pure rhetoric scored 0.04–0.09. No answer moved more than 0.02
  between runs, so the 0.30 bar has a wide margin both ways.
- Whole debates, through the real debater nodes, `judge_turns` and the routers,
  with scripted replies and 3 configured rounds: when round 2 only repeated,
  the investment debate stopped at 4 turns and the risk debate at 6. When round
  2 brought new evidence, both ran all 3 rounds.
- `stronger_side`: when only one side cited evidence, Jev gave that side 1.00.
  When both did, the answer was close to a three-way split (bull 0.20–0.28,
  bear 0.36–0.46, even 0.34–0.36). The hint read that as "judged the bear case
  better supported", which is why `side_lead_min` was added.
- Replay of a real Deep run (NVDA, 2026-09-23, 5 rounds, turns of 5.5K–17K
  characters): every judged turn was asked again, and each score stayed within
  0.04 of the logged one. That includes the three requests the cap now cuts.
  Before the cap, `stronger_side` on the real 63K + 72K character histories
  failed with `max_tokens_exceeded` 3 times out of 3. With the cap it sent
  29K + 32K characters and answered bull 0.36–0.38, bear 0.37–0.39, even
  0.23–0.26, so the hint names no side. The run's Research Manager chose
  Overweight.

**What the real run says about savings:** neither debate converged. The
investment turns scored 0.79–0.93. The risk turns scored 0.62–0.96, except the
Neutral Analyst's (0.25–0.55), which mostly weigh the other two. A long LLM turn
nearly always adds some new detail, so a round rarely has every turn below
0.30. Early stopping works when the turns do repeat, but with verbose models it
may seldom fire. Measure the stop rate over a backtest before deciding whether
it earns its requests.

**To tune next:** `min_rounds` (2), `new_argument_min` (0.30) and
`side_lead_min` (0.50) are in `DebatePolicy`. The bar is low on purpose, because
stopping too early costs the manager an argument, while continuing only costs
one round of calls.
