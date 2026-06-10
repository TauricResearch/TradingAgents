# Beginner Setup

## 1. Install Git

- macOS: install Xcode Command Line Tools with `xcode-select --install`.
- Windows: install Git from `https://git-scm.com/download/win`.
- Linux: use your package manager, for example `sudo apt install git`.

## 2. Install GitHub CLI

If you want to create your own fork from the command line:

```bash
gh auth login
gh repo fork TauricResearch/TradingAgents --clone --remote
cd TradingAgents
git checkout -b india-market-agents
```

If `gh` is unavailable, fork from GitHub in your browser, then clone your fork.

## 3. Install Python

Use Python 3.10, 3.11, or 3.12 for the most predictable dependency support.

## 4. Create A Virtual Environment

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

## 5. Install

```bash
python3 -m pip install -e ".[dev]"
indiamarketagents init-env
```

Open `.env` and add one provider setting. For the lowest-cost local path,
configure Ollama with `OLLAMA_BASE_URL=http://localhost:11434/v1`.

For a credential-safe first research-pack workflow, see `docs/FIRST_RUN_CHECKLIST.md`.

## 6. Run Doctor

```bash
indiamarketagents doctor --ticker RELIANCE.NS
```

## 7. First Analysis

```bash
indiamarketagents use-case
indiamarketagents sample-report --ticker RELIANCE.NS --date 2026-06-05
indiamarketagents report-status --ticker RELIANCE.NS --date 2026-06-05
indiamarketagents provider-status
indiamarketagents workflow-status --ticker RELIANCE.NS --date 2026-06-05
indiamarketagents first-run-check --ticker RELIANCE.NS --date 2026-06-05
```

When `first-run-check` passes, run the shallow `indiamarketagents analyze` command that it prints.

## 8. Open Dashboard

```bash
python3 -m pip install -e ".[dashboard]"
streamlit run dashboard/app.py
```

## Common Errors

- `India-only by default`: use `.NS` or `.BO`.
- `Analysis date cannot be in the future`: pick today or an earlier date.
- `UNAVAILABLE`: a source could not be verified or accessed; use local filings.
