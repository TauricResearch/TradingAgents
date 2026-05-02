---
date: 2026-05-02
tags: [infrastructure, verification, documentation]
agent: local-ai
environment: local
---

## Debrief: TradingAgents Installation & Initial Configuration

## Accomplishments

- **Environment setup via `uv` instead of `conda`:** The README only documents conda, but the project ships with a `uv.lock` file. Used `uv venv --python 3.13` + `uv sync` to install all 111 packages in one command.
- **API key configuration:** Created `.env` from `.env.example`, populated `OPENROUTER_API_KEY`. Verified `.env` is already in `.gitignore` (line 151).
- **CLI verification:** `tradingagents --help` confirmed the installed command works.
- **End-to-end test run:** Successfully ran full analysis on TKA.DE (thyssenkrupp AG) — all 5 agent teams executed, final decision: Overweight.
- **Created PLAYBOOK.md:** Comprehensive practical guide covering architecture, configuration, cost management, workflows, and troubleshooting.
- **Created implementation brief:** `briefs/brief-dashboard-2026-05-02.md` — full spec for Bun/Hono dashboard with SSE streaming, portfolio tracking, and position-aware analysis.

## Problems

- **conda not installed, README only mentions conda:** The installation instructions reference `conda create -n tradingagents python=3.13` as the only method. The project already has `uv.lock` but this isn't documented. The conda references appear in exactly two places in the README — nowhere in actual code.
  - **Resolution:** Used `uv` throughout. No code changes needed.

- **Python 3.14 build failure:** System Python is 3.14.4, but PyO3 (used by `tiktoken`, a transitive dependency of `langchain-openai`) maxes out at Python 3.13. Build failed with:
  ```
  error: the configured Python interpreter version (3.14) is newer than
  PyO3's maximum supported version (3.13)
  ```
  - **Resolution:** Used `uv venv --python 3.13` explicitly. The `uv.lock` was already pinned for 3.13, so this was the correct version all along.
  - **Implication:** Any setup script that uses the system default Python will fail on 3.14.

- **OpenRouter API key not picked up by Python API:** When running TradingAgents programmatically (not via CLI), the `OPENROUTER_API_KEY` from `.env` was not loaded. The CLI calls `load_dotenv()` in `cli/main.py`, but the Python API (`TradingAgentsGraph`) does not. The OpenAI client was being used without any API key, causing:
  ```
  openai.OpenAIError: The api_key client option must be set either by
  passing api_key to the client or by setting the OPENAI_API_KEY
  environment variable
  ```
  - **Resolution:** Added `from dotenv import load_dotenv; load_dotenv()` before importing TradingAgents in the script.
  - **Implication:** The Python API requires manual `.env` loading. This is not documented. The CLI hides this from users.

- **`td` task manager not initialized:** `td usage --new-session` failed with "database not found: run 'td init' first". The project didn't have a `.todos` directory.
  - **Resolution:** Ran `td init --work-dir` to initialize.

## Lessons Learned

- **README installation docs are stale:** Only documents conda. Should include `uv` as a first-class option. The `uv.lock` file being present suggests this was intended but never documented.

- **Python version pinning matters:** The `uv.lock` implicitly targets Python 3.13. On a system with only Python 3.14, `uv sync` will fail during native extension builds (tiktoken/PyO3). Setup instructions should explicitly call out `--python 3.13`.

- **`.env` loading is inconsistent:** The CLI loads dotenv, the Python API does not. If you use `TradingAgentsGraph` directly, you must load dotenv yourself. This is a footgun — the CLI works, the import-from-module pattern silently fails.

- **OpenRouter model names require provider prefix:** Model names in OpenRouter use format `openai/gpt-5.4`, not just `gpt-5.4`. The config accepts both but only the prefixed form routes correctly.

- **First-run analysis is slow:** The initial TKA.DE analysis took several minutes, largely due to `tiktoken` needing to compile from source (Rust build). Subsequent runs will be faster since the compiled wheel is cached.

- **TradingAgents output is verbose in debug mode:** The debug output is useful for development but overwhelming for production use. The planned `scripts/analyze_stream.py` wrapper will need to filter and structure this output into clean JSON-line events.

- **The decision memory system works out of the box:** After the TKA.DE run, `~/.tradingagents/memory/trading_memory.md` was automatically populated with the decision, rating, and rationale. This will be useful for the position-aware analysis feature — the memory already contains analysis history that can be cross-referenced with positions.
