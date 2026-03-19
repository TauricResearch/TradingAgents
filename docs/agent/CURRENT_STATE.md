# Current Milestone

Report path unification complete. Observability logging (data sources, LLM calls, tool calls, token counts) is the active task. Next: `pipeline` CLI command.

# Recent Progress

- **PR #21 merged**: Memory system v2 — builder/reader skills, 5 context files, post-commit hook
- **PR #18 merged**: Opt-in vendor fallback — fail-fast by default, `FALLBACK_ALLOWED` whitelist for fungible data only (ADR 011)
- **PR #19 merged**: Merge conflict resolution after PR #18
- **Report path unification** (`80e174c`): All reports now written under `reports/daily/{date}/{ticker}/` for per-ticker analysis and `reports/daily/{date}/market/` for scanner output
- `pipeline` CLI command implemented — scan JSON → filter by conviction → per-ticker deep dive via `MacroBridge`
- `extract_json()` utility in `agents/utils/json_utils.py` handles DeepSeek R1 `<think>` blocks and markdown fences
- Memory builder and reader skills created in `.claude/skills/`
- Structured context files generated under `docs/agent/context/` (ARCHITECTURE, CONVENTIONS, COMPONENTS, TECH_STACK, GLOSSARY)
- 220+ offline tests passing
- 12 pre-existing test failures fixed across 5 files

# In Progress

- **Observability logging**: Structured logging for data source calls (vendor, endpoint, success/failure), LLM requests (model name, agent, token counts), and tool invocations (tool name, duration). Goal: understand what's being called, by whom, and at what cost per run.

# Planned Next

- Report path unification tests (verify new paths in integration tests)

# Active Blockers

- None currently
