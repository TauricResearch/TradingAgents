## ADDED Requirements

### Requirement: The evidence gate has three verdicts

The evidence gate SHALL classify evidence into three verdicts:

- **PASS** — evidence meets the configured sufficiency thresholds;
- **LOW_CONFIDENCE** — evidence exists but falls below the thresholds; analysis
  proceeds carrying an explicit confidence downgrade;
- **FAIL_STOP** — evidence is not merely thin but unusable or actively
  misleading; analysis must not proceed on it.

Thin evidence SHALL map to LOW_CONFIDENCE, not to FAIL_STOP. The enrichment
verdict remains an internal routing state and SHALL NOT be a terminal verdict.

#### Scenario: Company-relevant items below threshold but present

- **WHEN** the gate resolves fewer credibility-weighted company-relevant news
  items than the configured minimum, and enrichment does not close the gap, but
  at least one usable item exists
- **THEN** the verdict is LOW_CONFIDENCE
- **AND** the run proceeds to the downstream debate

#### Scenario: Thresholds met

- **WHEN** weighted company-relevant items meet the configured minimum
- **THEN** the verdict is PASS

#### Scenario: No usable evidence at all

- **WHEN** no usable news or sentiment evidence can be resolved after enrichment
- **THEN** the verdict is LOW_CONFIDENCE with an explicit zero-coverage reason
- **AND** the run proceeds, because absence of news is a fact about the ticker
  rather than a system fault

### Requirement: A weak-evidence verdict does not fail the run by default

The configuration governing whether a non-PASS verdict aborts the run SHALL
default to not aborting. A LOW_CONFIDENCE verdict SHALL NOT raise, SHALL NOT
mark the run failed, and SHALL NOT set a failure error category.

Operators MAY opt into strict aborting via configuration. When they do, only
FAIL_STOP verdicts SHALL abort; LOW_CONFIDENCE SHALL still proceed.

#### Scenario: Default configuration with thin evidence

- **WHEN** a run resolves thin evidence under default configuration
- **THEN** no evidence gate error is raised
- **AND** the run reaches a terminal status other than failed, assuming no other
  fault

#### Scenario: Strict mode with a fatal verdict

- **WHEN** strict aborting is enabled and the verdict is FAIL_STOP
- **THEN** the run fails with an evidence-rejection error category

#### Scenario: Strict mode with a low-confidence verdict

- **WHEN** strict aborting is enabled and the verdict is LOW_CONFIDENCE
- **THEN** the run proceeds

### Requirement: Wrong-identity evidence is a hard stop only against a resolved profile

Evidence indicating the resolved articles describe a different instrument than
the one under analysis SHALL produce FAIL_STOP regardless of item counts and
regardless of the strict-abort setting's effect on other checks. Analyzing the
wrong company yields actively harmful output, which is categorically different
from low-confidence output, so this verdict SHALL NOT be downgradable to
LOW_CONFIDENCE.

However, identity-conflict detection compares candidate names against the
canonical company profile. When the profile carries no usable name, the detector
has no basis for comparison and every candidate name — including the correct one
— is trivially "unrelated" to an empty alias set. The detector SHALL therefore
abstain when it has no resolved profile name to compare against, and the gate
SHALL record that identity verification was not performed as a LOW_CONFIDENCE
limitation.

A name that appears bound to the instrument's own code in the evidence SHALL NOT
be treated as a conflicting identity solely because the profile failed to
resolve.

#### Scenario: Article set references a different listed company

- **WHEN** the profile carries a usable name and identity-conflict detection
  matches evidence to an instrument other than the analysis target
- **THEN** the verdict is FAIL_STOP
- **AND** the reason names the conflicting identity

#### Scenario: Identity conflict with otherwise ample evidence

- **WHEN** the profile carries a usable name, an identity conflict is detected,
  and item counts exceed all thresholds
- **THEN** the verdict is still FAIL_STOP

#### Scenario: Profile name unresolved

- **WHEN** the canonical company profile carries no usable name
- **THEN** identity-conflict detection abstains and contributes no conflict hits
- **AND** the gate records unverified identity as a LOW_CONFIDENCE limitation
- **AND** the run is not failed for identity conflict

#### Scenario: Correct company name bound to the instrument's own code

- **WHEN** evidence contains the instrument's own code immediately followed by a
  company name in parentheses, and the profile name is unresolved
- **THEN** that name is not reported as a conflicting identity

#### Scenario: Enrichment supplies correct evidence for an unresolved profile

- **WHEN** enrichment rounds retrieve correct company news while the profile name
  remains unresolved
- **THEN** additional correct evidence does not increase the conflict hit set

### Requirement: Core-data warnings are graded, not uniformly fatal

Warning markers found in upstream market and fundamentals reports SHALL be
graded. Markers denoting a degraded-but-usable supplemental source SHALL produce
a limitation recorded against the verdict and SHALL contribute to LOW_CONFIDENCE.
Only markers denoting the complete absence of usable core financial data SHALL
produce FAIL_STOP.

Deciding fatality by matching any member of a flat warning list is prohibited.

#### Scenario: Supplemental source unavailable

- **WHEN** the market report notes a supplemental source is unavailable while
  primary data is present
- **THEN** the verdict is at worst LOW_CONFIDENCE
- **AND** the limitation is recorded in the evidence report

#### Scenario: No usable financial statement

- **WHEN** the fundamentals report indicates no usable financial statement was
  obtained
- **THEN** the verdict is FAIL_STOP

#### Scenario: Identity profile incomplete

- **WHEN** the canonical company profile cannot be fully resolved but the ticker
  is known
- **THEN** the verdict is LOW_CONFIDENCE with the incomplete profile recorded as
  a limitation, rather than FAIL_STOP

### Requirement: The confidence verdict is machine-readable and propagated downstream

The evidence report SHALL carry the verdict and its supporting counts in a
deterministic, machine-readable line so downstream consumers can act on it
without parsing prose.

Downstream judging roles SHALL be instructed that a LOW_CONFIDENCE verdict
requires reducing conviction and prohibits presenting a high-certainty
directional call. This SHALL reuse the existing abstain-is-not-neutral and
conviction semantics rather than introducing a parallel concept.

#### Scenario: Low-confidence verdict reaches the research manager

- **WHEN** the gate emits LOW_CONFIDENCE
- **THEN** the evidence report contains a machine-readable confidence line naming
  the verdict and the observed counts against their thresholds
- **AND** the research manager's instructions require a reduced-conviction verdict

#### Scenario: Pass verdict

- **WHEN** the gate emits PASS
- **THEN** the confidence line names PASS and imposes no conviction ceiling

#### Scenario: Verdict recorded in the evidence ledger

- **WHEN** any verdict is produced
- **THEN** the evidence ledger records that verdict with its reasons and counts

### Requirement: Failure reasons use the same counting basis as the verdict

Reasons reported alongside a verdict SHALL be computed on the same basis as the
verdict itself. Where the verdict compares credibility-weighted counts against a
threshold, the reported reason SHALL report the weighted count, not a raw item
count.

#### Scenario: Weighted count differs from raw count

- **WHEN** six low-credibility items yield a weighted count of three against a
  threshold of three
- **THEN** the reason reports the weighted count of three
- **AND** the reason does not report a count of six as though it were compared to
  the threshold

### Requirement: Evidence enrichment honors all configured search credentials

Evidence enrichment SHALL read search-provider credentials from the same sources
as the primary news retrieval path, including the multi-credential variable. It
SHALL NOT silently return no enrichment when only the multi-credential variable
is configured.

When no credential is available, enrichment SHALL record that it was skipped for
lack of credentials, distinguishing this from having searched and found nothing.

#### Scenario: Only the multi-credential variable is configured

- **WHEN** enrichment runs with only the multi-credential environment variable set
- **THEN** enrichment performs searches using those credentials

#### Scenario: No credentials configured

- **WHEN** enrichment runs with no search credentials configured
- **THEN** enrichment is skipped with a reason distinguishing missing credentials
  from an empty result

### Requirement: Report parsing failure is distinguishable from evidence absence

When the gate derives evidence items by parsing upstream report text, and the
report is non-empty and does not declare absence of data yet yields zero parsed
items, the gate SHALL record a parse-failure signal distinct from a genuine
zero-evidence finding.

#### Scenario: Report present but unparseable

- **WHEN** an upstream news report contains substantive text in an unexpected
  layout and yields zero parsed items
- **THEN** the gate records a parse-failure signal
- **AND** the recorded reason does not assert that no news exists

#### Scenario: Report declares no data available

- **WHEN** the upstream news report declares that no curated news was found
- **THEN** the gate records genuine zero coverage, not a parse failure

### Requirement: Gate faults degrade instead of aborting the run

An unexpected exception raised inside the evidence gate that is not itself a
verdict SHALL be caught and converted into a gate-unavailable outcome that allows
the run to proceed with a recorded limitation. Infrastructure failure inside the
gate SHALL NOT be reported as an evidence rejection.

#### Scenario: Identity resolution dependency fails

- **WHEN** an external dependency inside the gate raises an unexpected exception
- **THEN** the gate returns a gate-unavailable outcome with the fault recorded
- **AND** the run proceeds rather than failing with an evidence-rejection category

### Requirement: Evidence thresholds are configurable through the environment

The evidence sufficiency thresholds, the strict-abort switch, and the missing-data
halt switch SHALL each be overridable through the project's environment-override
mapping, so operators can adjust strictness without code changes. Overridden
values SHALL be captured in the run's effective configuration for audit.

#### Scenario: Threshold lowered via environment

- **WHEN** the minimum company-item threshold is overridden to one through the
  environment
- **THEN** the gate evaluates against one
- **AND** the run's effective configuration records the overridden value

#### Scenario: Strict abort enabled via environment

- **WHEN** the strict-abort switch is enabled through the environment
- **THEN** FAIL_STOP verdicts abort the run
