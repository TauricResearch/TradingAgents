---
name: scaffold
description: Create new module files following the project's modular layout
disable-model-invocation: true
argument-hint: <package/module-name>
---

Scaffold new files for the feature named $ARGUMENTS following the project layout in `.claude/rules/rules.md`.

**Determine where the new code belongs based on its responsibility:**

| Responsibility | Package | Example |
|---|---|---|
| New data source | `tradingagents/dataflows/` | `tradingagents/dataflows/reddit_client.py` |
| New agent role | `tradingagents/agents/<category>/` | `tradingagents/agents/analysts/crypto_analyst.py` |
| New @tool function | `tradingagents/agents/utils/` | `tradingagents/agents/utils/social_data_tools.py` |
| New LLM provider | `tradingagents/llm_clients/` | `tradingagents/llm_clients/gemini_client.py` |
| New graph logic | `tradingagents/graph/` | `tradingagents/graph/post_processing.py` |
| New CLI feature | `cli/` | `cli/notion_chart_publisher.py` |
| New data models | `tradingagents/agents/schemas.py` or new file in relevant package | |

**Each stub must include:**
- Module docstring stating its purpose and responsibility.
- A `TODO` comment indicating what to implement.
- Correct relative imports.
- Type hints on all function signatures.

**After creation:**
1. List the files created.
2. Remind the user to register the new code where needed:
   - Data source → register in `dataflows/interface.py` VENDOR_METHODS
   - Agent role → wire into `graph/setup.py`
   - @tool → re-export in `agents/utils/agent_utils.py`, add to tool nodes in `graph/trading_graph.py`
   - LLM provider → register in `llm_clients/factory.py`, update `model_catalog.py` + `validators.py`
3. Add test file: `tests/test_<module>.py`
