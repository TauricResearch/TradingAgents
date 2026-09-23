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
fetchers in [`yfinance_news.py`](../tradingagents/dataflows/yfinance_news.py),
[`alpha_vantage_news.py`](../tradingagents/dataflows/alpha_vantage_news.py),
[`reddit.py`](../tradingagents/dataflows/reddit.py),
[`stocktwits.py`](../tradingagents/dataflows/stocktwits.py).

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
End them early when a turn adds nothing new, which saves deep-model calls.

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
level and spread), each Noul one probability column. Train a small model
(CatBoost or logistic) on the alpha outcomes already stored in the decision
log. Grow the question set by proposing new questions from the worst-predicted
cases, keeping only questions that improve held-out error.

**Where:** [`backtest.py`](../tradingagents/backtest.py) and the resolved
entries in [`memory.py`](../tradingagents/agents/utils/memory.py).

**Prerequisite:** enough resolved backtest decisions to train and hold out
data. This is the largest potential upside and the last to build.

**Jev sources:** [Autoresearch Feature Discovery](https://docs.typesafe.ai/cookbooks/autoresearch_feature_discovery.md),
[Composite Scoring](https://docs.typesafe.ai/patterns/composite-scoring.md).

## Moderate fits

### 6. Pick past lessons by relevance, not recency

`get_past_context` takes the 5 most recent same-ticker entries and 3
cross-ticker ones. Instead, score each resolved lesson for relevance to the
current setup (Score) and inject the best ones. Keep the `as_of` point-in-time
filter in code.

**Where:** `get_past_context` in [`memory.py`](../tradingagents/agents/utils/memory.py).
**Jev sources:** [Re-Ranking](https://docs.typesafe.ai/cookbooks/rerank_typesafe.md),
[Line-by-Line Search](https://docs.typesafe.ai/cookbooks/semantic_find.md).

### 7. Rescue the rating when parsing fails

When `extract_rating` returns `None` on the free-text fallback path, ask a
Choice over Buy / Overweight / Hold / Underweight / Sell / no rating stated.
Low confidence or "no rating stated" still yields `REVIEW`. A second check
(Noul): does the stated rating agree with the Executive Summary? Structured
output already covers most runs, so this is a rarely-used fallback.

**Where:** [`rating.py`](../tradingagents/agents/utils/rating.py),
[`signal_processing.py`](../tradingagents/graph/signal_processing.py).
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
3. **Fit 3**: debate convergence, a direct cost saving.
4. **Fits 6–10** as needed.
5. **Fit 5** once the backtest has enough resolved decisions.

Every integration should degrade to current behavior when `TYPESAFE_API_KEY`
is unset or the `jev` extra is not installed.

## Fits 1 and 2 as built

**Code:** [`sentiment_judgments.py`](../tradingagents/agents/utils/sentiment_judgments.py)
(questions, `SentimentPolicy`, aggregate, prompt blocks),
[`jev.py`](../tradingagents/agents/utils/jev.py) (client and concurrent requests),
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

**Code:** [`claim_check.py`](../tradingagents/agents/utils/claim_check.py)
(claim and section splitting, questions, `ClaimCheckPolicy`, figures, output),
one call at the end of
[`portfolio_manager.py`](../tradingagents/agents/managers/portfolio_manager.py),
and the `REVIEW` label in [`rating.py`](../tradingagents/agents/utils/rating.py).
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
`memory.get_past_context`:

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
Portfolio Manager's own rating stays in the text. A quoted claim has any
`rating:` separator removed, so it can never read as a later rating label.

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
