# Workbench analyst presets

The workbench loads YAML presets for the four existing analyst roles. A preset
can enable a subset and choose their execution order; it cannot add tools,
agents, prompts, retries, or graph edges.

The remaining stages are deliberately fixed: Evidence Steward, Bull/Bear,
Research Manager, Trader, the three risk analysts, and Portfolio Manager always
run. This preserves a complete evidence-to-decision path for every preset.

Built-in presets live in `tradingagents/presets/`. To create a local override
that survives package upgrades, place a file in `~/.tradingagents/presets/`
with the same `id`:

```yaml
id: news-first
label: 新闻优先
analysts:
  - news
  - market
```

The loader accepts only `id`, `label`, and `analysts`. Analyst IDs must be one
or more unique values chosen from `market`, `social`, `news`, and
`fundamentals`. Invalid local files are ignored and do not block the built-in
presets; `inspect_preset(path)` provides the same validation for tooling. Its
dry-run invariant also confirms the selected sequence feeds the fixed nine-role
convergence path; YAML v1 deliberately cannot declare nodes, edges, tools,
variables, or downstream input mappings.

For a deterministic, no-LLM command-line check before committing a local
preset, run:

```bash
tradingagents inspect-preset ~/.tradingagents/presets/news-first.yaml
```

On success it prints the requested analyst order and all nine mandatory
downstream convergence roles. Invalid YAML exits with status `2` and one
stable error line, so it is suitable for local scripts and CI checks.

Duplicate preset IDs in a single directory are rejected during catalog loading.
A valid file in `~/.tradingagents/presets/` may still override a built-in ID;
that is the documented upgrade-safe customization mechanism.

The code-owned `tradingagents.analysts.ANALYST_CONFIG` is the single metadata
registry for those selectable roles. It supplies the stable wire key, display
metadata, style, factory reference, graph-node identifiers, and API config
listing. The role factory itself stays in code and is allow-listed, so a YAML
file cannot import or execute an arbitrary implementation.

Preset order is part of the analysis request and resume fingerprint. Retrying
or resuming a run therefore uses the exact analyst order that created it.
