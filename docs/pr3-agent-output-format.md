# PR3 Agent Output Format

This phase adds a stable structured envelope for agent outputs so the local research platform can render reports, cache artifacts, and later power an equity-research cockpit without reparsing markdown.

## Scope

- Add `AgentOutputEnvelope`, `AgentOutputSection`, and `AgentOutputType`.
- Preserve existing typed payloads: `AnalystNote`, `InvestmentThesis`, and `TradeSignal`.
- Add adapters that wrap notes, thesis packages, and signals into one common envelope.
- Add deterministic Markdown rendering for one or many agent outputs.
- Store agent outputs in `JsonArtifactStore` under `agent_outputs/{SYMBOL}.jsonl`.
- Include structured agent outputs in `ResearchReportBundle` and the generated Markdown report.

## Why

Agent output should be both human-readable and machine-consumable. The envelope keeps report/cockpit metadata separate from the typed payload, making it possible to diff outputs, cache them, and route them into risk, backtest, and report steps.

## Validation

```bash
python -m pytest tests/test_agent_output_format.py tests/test_agent_artifacts.py tests/test_artifact_store.py tests/test_research_report.py tests/test_research_workflow.py -q
```

```bash
python -m pytest tests/test_research_platform_contracts.py tests/test_legacy_dataflow_provider.py tests/test_yfinance_provider.py tests/test_artifact_store.py tests/test_agent_artifacts.py tests/test_agent_output_format.py tests/test_signal_pipeline.py tests/test_backtest_engine.py tests/test_research_report.py tests/test_research_workflow.py tests/test_cli_report.py -q
```
