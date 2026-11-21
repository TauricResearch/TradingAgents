# GOV004 portable evidence and frozen population

The November 18 historical live PASS remains **PENDING independent audit**: the original reports, manifests and score file are not present in this checkout. Repairing the scorer or creating fresh diagnostics cannot recover or approve those historical judgments. Preserve the original review and do not fabricate missing scores, timestamps or approval.

## Freeze a formal cohort before outcomes

A/C must approve the actual provider/model configuration, applicability and critical-item policy before formal use. The scorer retains the documented fixed `deepseek` configuration; the saved school `openai_compatible` configuration is diagnostic until that difference is explicitly approved. Critical R1/R2/R3/R5/R6/R7 failures conservatively prevent PASS, regardless of optional caller flags. A/C should ratify this explicit policy rather than infer safety from a missing flag.

Create `tests/member_c_verification/live/evidence/cohort.json` with:

- `schema_version`: integer 1.
- `approved_by`: attributable real approver, never a generated identity.
- `frozen_at_utc`: actual timezone-aware freeze timestamp, before the recorded run start.
- `source_revision`: exact revision label, including `+dirty` where applicable.
- `prompt_hash`: the application's full SHA256 prompt-source hash.
- `members`: exactly ten objects with `case_id`, `trial` (`1` or `2`) and unique preallocated safe `run_id`. Each fixed case has one slot per trial.

Retain the approval and cohort externally or in version control before execution; editable local timestamps alone cannot prove historical chronology. The application and capture harness record hashes, but that is not a digital signature or a substitute for review.

Set `GOV004_TRIAL=1` or `2` for approved formal replay. The harness reads the cohort, uses its run IDs and refuses to reuse a started slot. A diagnostic run leaves the trial unset. Store diagnostic evidence separately from formal evidence. Every recorded formal start remains in overall completion accounting; retries do not replace failed cohort slots. Completion is reported separately from semantic scores on eligible completed reports.

## Record evidence and human scores

The capture harness records portable relative report and manifest paths and their SHA256 digests. Manifests must match the run identity, result, source revision, fixed configuration, prompt hash and report path. Each report must contain the corresponding trusted Run ID header. A completed record needs all of this evidence; incomplete/error attempts remain counted even without completed artifacts.

The score JSON contains a real `reviewer` and an `answers` list. Each applicable answer has `case_id`, `run_id`, `trial`, `item`, integer `score` (0 or 1), and a nonempty `citation` found in that run's report. Record rationale and disagreements alongside it. Do not submit N/A rows for inapplicable cells. The scorer derives applicability; missing, duplicate, unknown, incorrectly N/A or unrelated cells fail. Challenge markers and actual exposure must be retained and independently checked. Q1–Q4 NEEDS_REVIEW and human semantic judgments remain separate.

## Package and verify from a fresh checkout

After sanitization and human review, run from the repository root:

```sh
python tests/member_c_verification/live/package_gov004.py tests/member_c_verification/live/evidence /tmp/gov004-package --scores tests/member_c_verification/live/evidence/gov004_scores.json
GOV004_EVIDENCE_DIR=/tmp/gov004-package python tests/member_c_verification/live/score_gov004.py /tmp/gov004-package/gov004_scores.json
```

The destination must not already exist. The exporter copies only referenced reports/manifests and the cohort, evidence and scoring files, rewrites paths, and emits `integrity.json`. It refuses detected credential text rather than silently changing scored evidence. Review other sensitive content manually; automatic scanning cannot certify privacy. Move the package to a second path or fresh checkout and repeat scoring. PASS=0, FAIL=1, PENDING=2. PENDING is never acceptance. Compare integrity hashes after transfer; retain the archive in an agreed durable location.

The tracked ignore rules exclude private generated live evidence. Deliberate sanitized packages may be retained outside that tree after owner review. This workflow is not recovery of missing historical evidence and does not itself grant formal approval.
