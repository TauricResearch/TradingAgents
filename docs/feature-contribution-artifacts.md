# Measured Feature Contribution Artifacts

The Portfolio Manager may display top measured feature drivers only when a
deterministic numeric calculator provides a versioned artifact.  TradingAgents
does not infer a z-score, importance, or causal attribution from analyst,
researcher, trader, or risk-debate prose.

Programmatic callers pass a `FeatureContributionArtifact` as
`AnalysisRequest.feature_contribution_artifact`.  The runner copies its
JSON-safe entries into `AgentState.feature_contributions`; the Portfolio
Manager ranks them deterministically as `abs(z_score) * importance` and keeps
both the evidence reference and source artifact ID in the public final report.

The v1 wire shape is:

```json
{
  "schema_version": "measured-feature-contributions/v1",
  "artifact_id": "calc:factor-model:2026-07-18",
  "producer": "factor-model-v2",
  "methodology_ref": "docs/factor-model-v2.md#normalization",
  "as_of_date": "2026-07-18",
  "contributions": [
    {
      "feature": "cash_flow",
      "z_score": -2.0,
      "importance": 0.7,
      "direction": "risk",
      "evidence_ref": "dataset:financials:2026-07-18"
    }
  ]
}
```

`schema_version`, producer, methodology reference, date, and at least one
numeric contribution are required.  Unknown schema versions and malformed
inputs are rejected.  The browser run API does not expose this field yet:
that omission is intentional until it can authenticate the calculator and
store the referenced artifact durably.  The programmatic request is the
typed ingestion seam; when no verified calculator exists, no driver is shown.
