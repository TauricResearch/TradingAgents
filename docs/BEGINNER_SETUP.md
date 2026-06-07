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
cp .env.example.india .env
```

Open `.env` and add your API keys.

## 6. Run Doctor

```bash
indiamarketagents doctor --ticker RELIANCE.NS
```

## 7. First Analysis

```bash
indiamarketagents analyze --ticker RELIANCE.NS --date 2026-06-05 --research-depth 1 --no-display --no-save-prompt
```

## 8. Open Dashboard

```bash
python3 -m pip install -e ".[dashboard]"
streamlit run dashboard/app.py
```

## Common Errors

- `India-only by default`: use `.NS` or `.BO`.
- `Analysis date cannot be in the future`: pick today or an earlier date.
- `UNAVAILABLE`: a source could not be verified or accessed; use local filings.
