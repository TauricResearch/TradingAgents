<p align="center">
  <img src="assets/TauricResearch.png" style="width: 60%; height: auto;" alt="Handels-Agenten">
</p>

<div align="center" style="line-height: 1;">
  <a href="https://arxiv.org/abs/2412.20138" target="_blank"><img alt="arXiv" src="https://img.shields.io/badge/arXiv-2412.20138-B31B1B?logo=arxiv"/\u003e</a>
  <a href="https://discord.com/invite/hk9PGKShPK" target="_blank"><img alt="Discord" src="https://img.shields.io/badge/Discord-TradingResearch-7289da?logo=discord&logoColor=white&color=7289da"/\u003e</a>
  <a href="https://x.com/TauricResearch" target="_blank"><img alt="X Follow" src="https://img.shields.io/badge/X-TauricResearch-white?logo=x&logoColor=white"/\u003e</a>
  <a href="https://github.com/TauricResearch/" target="_blank"><img alt="Community" src="https://img.shields.io/badge/GitHub_Community-TauricResearch-14C290?logo=discourse"/\u003e</a>
</div>
<br>
<div align="center">
  <a href="https://github.com/TauricResearch" target="_blank"><img alt="TradingAgents #1 Repository of the Day" src="https://trendshift.io/api/badge/repositories/16192" width="250" height="55"/\u003e</a>
</div>
<br>
<div align="center">
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=de">Deutsch</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=es">Español</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=fr">français</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=ja">日本語</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=ko">한국어</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=pt">Português</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=ru">Русский</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=zh">中文</a>
</div>

---

# Handels-Agenten: KI-gestütztes Multi-Agent-Framework für professionelle Finanzanalyse

## Neuigkeiten
- [2026-07] **Handels-Agenten v0.3.1** mit Stabilitäts- und Korrektheits-Fixes. Siehe [CHANGELOG.md](CHANGELOG.md).
- [2026-06] **v0.3.0** mit erweitertem Provider-Support (NVIDIA, Kimi, Groq, Mistral, Bedrock) und CI-Gate.
- [2026-05] **v0.2.5** mit Sentiment-Analyst, GPT-5.5-Support, `HANDELSAGENTEN_*` Env-Var-Konfiguration und mehr.

<div align="center">

🚀 [Framework](#handels-agenten-framework) | ⚡ [Installation & CLI](#installation-und-cli) | 🎬 [Demo](https://www.youtube.com/watch?v=90gr5lwjIho) | 📦 [Paket-Nutzung](#handels-agenten-paket) | 🤝 [Mitwirken](#mitwirken) | 📄 [Zitation](#zitation)

</div>

> 🎉 **Handels-Agenten** ist jetzt Open Source! Vielen Dank für das große Interesse in der Community — wir freuen uns auf gemeinsame Projekte.

## Handels-Agenten Framework

**Handels-Agenten** ist ein Multi-Agent-Handelsframework, das die Dynamik realer Handelsfirmen nachbildet. Spezialisierte KI-Agenten — von Fundamentalanalysten über Sentiment-Experten bis hin zu Risiko-Managern — bewerten gemeinsam Marktbedingungen und treffen fundierte Handelsentscheidungen.

<p align="center">
  <img src="assets/schema.png" style="width: 100%; height: auto;">
</p>

> Das Framework ist ausschließlich für **Forschungszwecke** gedacht. Die Performance variiert je nach gewähltem Sprachmodell, Temperatur, Handelszeitraum, Datenqualität und anderen nicht-deterministischen Faktoren. [Es dient nicht als Finanz-, Anlage- oder Handelsberatung.](https://tauric.ai/disclaimer/)

### Agenten-Teams

| Team | Rolle |
|------|-------|
| **Fundamental-Analyst** | Bewertet Unternehmenskennzahlen und Finanzdaten |
| **Sentiment-Analyst** | Aggregiert Nachrichten, StockTwits und Reddit-Chatter |
| **Nachrichten-Analyst** | Monitort globale Nachrichten und makroökonomische Indikatoren |
| **Technischer Analyst** | Nutzt Indikatoren (MACD, RSI) für Mustererkennung |
| **Bull/Bär Researcher** | Strukturierte Debatten zur Risiko-/Chance-Abwägung |
| **Trader-Agent** | Trifft Kauf-/Verkaufsentscheidungen |
| **Risiko-Management** | Bewertet Volatilität, Liquidität und Positionsrisiken |
| **Portfolio-Manager** | Gibt finale Freigabe oder Ablehnung |

## Installation und CLI

### Installation

```bash
git clone https://github.com/mark-baumann/handels-agenten.git
cd handels-agenten
```

**Mit uv (empfohlen):**
```bash
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e .
```

**Mit pip:**
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Docker

```bash
cp .env.example .env  # API-Keys eintragen
docker compose run --rm handels-agenten
```

### Benötigte APIs

```bash
export OPENAI_API_KEY=...          # OpenAI (GPT)
export GOOGLE_API_KEY=...          # Google (Gemini)
export ANTHROPIC_API_KEY=...       # Anthropic (Claude)
export XAI_API_KEY=...             # xAI (Grok)
export DEEPSEEK_API_KEY=...        # DeepSeek
export DASHSCOPE_API_KEY=...       # Qwen — International
export DASHSCOPE_CN_API_KEY=...    # Qwen — China
export ZHIPU_API_KEY=...           # GLM International
export ZHIPU_CN_API_KEY=...        # GLM China
export MINIMAX_API_KEY=...         # MiniMax — Global
export MINIMAX_CN_API_KEY=...      # MiniMax — China
export OPENROUTER_API_KEY=...      # OpenRouter
export ALPHA_VANTAGE_API_KEY=...   # Alpha Vantage
```

Alternativ `.env.example` kopieren und ausfüllen:
```bash
cp .env.example .env
```

### CLI-Nutzung

```bash
handels-agenten          # installierter Befehl
python -m cli.main       # direkt aus Quelle
```

### Märkte und Ticker

| Markt | Beispiel |
|-------|----------|
| USA | `AAPL`, `SPY` |
| Deutschland | `SAP.DE`, `DAI.DE`, `BMW.DE` |
| Hongkong | `0700.HK` |
| Tokio | `7203.T` |
| London | `AZN.L` |
| Indien | `RELIANCE.NS` |
| China A-Shares | `600519.SS` |
| Krypto | `BTC-USD`, `ETH-USD` |

## Handels-Agenten Paket

### Python-Nutzung

```python
from handelsagenten.default_config import DEFAULT_CONFIG
from handelsagenten.graph.trading_graph import TradingAgentsGraph

ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())
_, decision = ta.propagate("NVDA", "2026-01-15")
print(decision)
```

Mit benutzerdefinierter Konfiguration:

```python
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openai"
config["deep_think_llm"] = "gpt-5.5"
config["quick_think_llm"] = "gpt-5.4-mini"
config["max_debate_rounds"] = 2

ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("NVDA", "2026-01-15")
```

Siehe `handelsagenten/default_config.py` für alle Optionen.

## Persistenz und Recovery

### Entscheidungs-Log

Jede Analyse wird in `~/.handelsagenten/memory/trading_memory.md` gespeichert. Bei wiederholtem Ticker werden realisierte Renditen und Reflexionen in den Portfolio-Manager Prompt injiziert.

Pfad überschreiben mit `HANDELSAGENTEN_MEMORY_LOG_PATH`.

### Checkpoint-Resume

Aktivierbar via `--checkpoint`. LangGraph speichert den Zustand nach jedem Knoten, sodass abgestürzte Läufe fortgesetzt werden können.

```bash
handels-agenten analyze --checkpoint        # für diesen Lauf aktivieren
handels-agenten analyze --clear-checkpoints # vorher zurücksetzen
```

## Reproduzierbarkeit

Handels-Agenten ist LLM-gesteuert — zwei Läufe desselben Tickers und Datums können unterschiedliche Ergebnisse liefern. Variationen entstehen durch:

- **Sprachmodell-Sampling** (nicht-deterministisch, auch bei fester Temperatur)
- **Live-Daten** (Nachrichten, StockTwits, Reddit ändern sich ständig)
- **Modell-Wahl** (Reasoning-Modelle variieren am stärksten)

Zur Reduktion: Temperatur senken oder nicht-reasoning Modell wählen.

## Mitwirken

Beiträge sind willkommen: Bugfixes, Dokumentation, Feature-Ideen. Siehe [CHANGELOG.md](CHANGELOG.md).

## Zitation

```
@misc{xiao2025tradingagents,
      title={TradingAgents: Multi-Agents LLM Financial Trading Framework}, 
      author={Yijia Xiao and Edward Sun and Di Luo and Wei Wang},
      year={2025},
      eprint={2412.20138},
      archivePrefix={arXiv},
      primaryClass={q-fin.TR},
      url={https://arxiv.org/abs/2412.20138}, 
}
```

---

<p align="center">
  Entwickelt von <strong>Mark Baumann</strong> · <a href="https://markb.de">markb.de</a>
</p>
