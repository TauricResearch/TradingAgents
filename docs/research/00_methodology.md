# 00 — Research Methodology & Protocol

Governs every artifact in `docs/research/`. Written first; everything else conforms to it.

## 1. Honesty contract (non-negotiable)

1. **Null means "not disclosed."** An empty field is a correct answer. Nothing is ever estimated, imputed, or guessed to fill a field.
2. **Every non-null quantitative value cites a source** (the `sourced_value` pattern: value + unit + basis + source_idx). If a number cannot be traced to a source, it does not enter the knowledge base.
3. **N is reported with every statistic.** Percentages print only when the disclosed-N is ≥ 10; below that, raw counts ("4 of 7 disclosed"). Denominators never include nulls; `undisclosed` is its own reported line, never silently dropped.
4. **Verification tiers are visible everywhere.** Every aggregate table is produced twice: all tiers, and tier A+B only.
5. **Caution flags are recorded, not laundered.** Disputed track records, blow-ups, and regulatory actions stay attached to the profile (`caution_flags`), and cautionary cases (e.g., Niederhoffer 1997) are analyzed as negative evidence.
6. **Paraphrase only.** No verbatim reproduction of copyrighted material; at most one quote < 15 words per profile, in quotation marks with attribution. Trigger/rule descriptions are paraphrased and cited.
7. **If fewer than the ~150 target clear verification, ship the honest number** and state it in `01_trader_statistics.md`.

## 2. Verification tiers

| Tier | Meaning | Examples of qualifying evidence |
|---|---|---|
| **A** | Audited / regulatory / exchange-verified track record | CTA disclosure documents, fund filings and audited letters, exchange competition records with published audits |
| **B** | Documented in reputable published secondary sources | Schwager's *Market Wizards* series interviews, biographies from established publishers, peer-reviewed papers, long-form journalism with named sources |
| **C** | Self-reported only | Podcasts, personal sites, social media, unaudited broker screenshots — retained but flagged; capped per cohort |

Tier assignment requires a written justification (`verification.tier_justification`). A tier-A claim without a checkable source is downgraded at QA.

## 3. Sourcing rules

- Public, legally accessible information only. No paywalled scraping, no private material, no leaked documents.
- Preferred source types in order: audited_record / regulatory_filing > book > paper > fund_letter > article (reputable outlet) > documentary > interview > podcast.
- Each source records: title, author, year, type, url (if online), locator (chapter/page/timestamp), access date.
- Performance claims additionally carry their own verification level (`audited | reported | anecdotal`) — a tier-B trader can still have an audited fund number and an anecdotal win-rate claim in the same profile.

## 4. Research agent prompt template

Every research agent receives this contract (fill the bracketed parts):

```
You are researching [N] traders for a verified knowledge base: [names].
Repo honesty culture applies — sourced facts only.

For each trader produce ONE JSON object conforming to docs/research/data/traders.schema.json,
using ONLY vocabulary values from docs/research/data/vocabularies.json (version [X]).

Rules:
1. null / "undisclosed" are CORRECT answers. Never estimate a number the sources
   don't state. An honest sparse profile beats a complete invented one.
2. Every non-null quantitative value must have {value, unit, basis, source_idx}
   where source_idx points into verification.sources. basis="inferred" only when
   derived arithmetically from stated facts — explain the derivation in note.
3. Assign verification.tier (A/B/C per 00_methodology.md §2) with a written
   justification. Performance claims get their own verification level.
4. Paraphrase everything. At most one quote under 15 words per profile, attributed.
5. Record caution_flags for disputed records, blow-ups, regulatory actions.
6. Search broadly (books, interviews, filings, papers), cite every source with
   title/author/year/type/url/locator/access-date.
7. extraction = {batch_id: "[BATCH]", date: "[TODAY]", agent_notes: <anything the
   QA reviewer must know>, qa_reviewed: false}.

Return: a JSON array of the profile objects, then a short per-trader note on
source quality and what could NOT be verified.
```

## 5. Batch → QA → merge pipeline

- **Unit**: one general-purpose agent researches 4–5 traders; 5–6 agents run in parallel per batch (~25–30 profiles/batch). Batch IDs: `B1`, `B2`, …
- **QA (orchestrating session, after every batch):**
  1. `python docs/research/data/analyze_traders.py --validate <batch.json>` — schema shape, vocab membership, source_idx bounds, duplicate ids.
  2. Dedup by name/alias against `traders.json`; cross-cohort duplicates resolve to the cohort listed in `cohorts.md` dedup notes.
  3. Citation spot-check: 3 randomly chosen profiles per batch + **every** tier-A designation and every `verification: audited` performance claim.
  4. Tier audit: downgrade anything whose evidence doesn't match its tier.
  5. Set `qa_reviewed: true` (+ `qa_notes`), append to `traders.json`, regenerate `traders.csv` (`--export-csv`), update the coverage table in `data/cohorts.md`.
- **Vocabulary changes** after the S1 checkpoint require a version bump in `vocabularies.json` (changelog entry) and re-QA of profiles using affected fields.

## 6. Pattern-mining rules (enforced by `analyze_traders.py --analyze`)

- Frequency tables per vocabulary field: `count / N_disclosed`, always printing `N_disclosed` and `N_total`.
- Numeric distributions: median and quartiles over disclosed values only, split by basis (disclosed vs inferred); no bare means.
- Co-occurrence: support + lift over rows where both fields are non-null (archetype×filter, archetype×stop_basis, style×sizing, pyramids×trailing).
- Missing-data report per cohort — disclosure rates are themselves findings.
- No significance claims without a stated test and N.

## 7. Framework-study rules (Sessions S5)

Desk study only — official documentation and public GitHub sources, cited with URL + access date; nothing installed or executed. Any performance number is labeled **"vendor/community claim — not benchmarked."** Our own engine's row is filled from the code inventory, never from marketing.

## 8. Session log & continuity

`README.md` holds the status table (single source of progress truth). Each session: read README + this file, do the work, update the status table, commit locally (branch is never pushed without explicit operator instruction).
