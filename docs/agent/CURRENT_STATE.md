# Current Milestone

Opt-in vendor fallback (ADR 011) merged (PR #18). Pipeline CLI command implemented. Memory system v2 being built. Next: PR #20 review (Copilot memory rebuild), structured context files under `docs/agent/context/`.

# Recent Progress

- **PR #18 merged**: Fail-fast vendor routing — `FALLBACK_ALLOWED` whitelist for 5 fungible-data methods only. ADR 011 written, ADR 002 superseded.
- `pipeline` CLI command implemented — scan JSON → filter by conviction → per-ticker deep dive via `MacroBridge`
- `extract_json()` utility in `agents/utils/json_utils.py` handles DeepSeek R1 `<think>` blocks and markdown fences
- All 3 `@dataclass` types defined: `MacroContext`, `StockCandidate`, `TickerResult` in `pipeline/macro_bridge.py`
- 12 pre-existing test failures fixed across 5 files (PR merged to main)
- Memory builder and reader skills created in `.claude/skills/`
- Structured context files generated under `docs/agent/context/` (ARCHITECTURE, CONVENTIONS, COMPONENTS, TECH_STACK, GLOSSARY)

# Active Blockers

- PR #20 (Copilot memory rebuild) is open/draft — needs review for aspirational deps and model name accuracy before merge
- Some scanner integration tests lack `@pytest.mark.integration` marker despite making live network calls
