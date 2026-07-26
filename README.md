原始來源
https://github.com/TauricResearch/TradingAgents

# TradingAgents（繁體中文 README）

## 本專案會調用哪些 AI？

依目前程式碼與預設設定，TradingAgents 是一個可切換多家 LLM 供應商的多代理交易研究框架。預設會使用：

- 預設供應商：`openai`
- 深度思考模型：`gpt-5.4`
- 快速思考模型：`gpt-5.4-mini`

目前支援或可透過設定調用的 AI / LLM 供應商如下：

- OpenAI：GPT 系列，例如 `gpt-5.5`、`gpt-5.5-pro`、`gpt-5.4`、`gpt-5.4-mini`、`gpt-5.4-nano`、`gpt-5.2`、`gpt-4.1`
- Anthropic：Claude 系列，例如 Claude Opus、Sonnet、Haiku
- Google：Gemini 系列，例如 Gemini 3、Gemini 3.1、Gemini 2.5
- xAI：Grok 系列，例如 Grok 4 / 4.20 / 4 Fast
- DeepSeek：DeepSeek V4 / V3.2 / reasoner 相關模型
- Qwen：阿里雲 DashScope 國際版與中國版端點
- GLM：Z.AI / BigModel 的 GLM 系列
- MiniMax：MiniMax 全球版與中國版端點
- OpenRouter：可路由到使用者選擇的第三方模型
- Ollama：本機或遠端 Ollama 模型，例如 Qwen3、GPT-OSS、GLM-4.7-Flash，也可自訂已拉取的模型 ID
- Azure OpenAI：企業部署的 Azure OpenAI 模型

這些 AI 會被用在多代理流程中，包含基本面分析師、情緒分析師、新聞分析師、技術分析師、多空研究員、交易員、風險管理辯論者、研究經理與投資組合經理等角色。`LangGraph` 負責代理流程編排；`yfinance`、Alpha Vantage、StockTwits、Reddit、Yahoo Finance 等屬於資料來源或工具，不是主要的 AI 模型。

---

## 繁體中文目錄

🚀 [TradingAgents 框架](#tradingagents-框架) | ⚡ [安裝與 CLI](#安裝與-cli) | 📦 [套件用法](#tradingagents-套件) | 💾 [持久化與復原](#持久化與復原) | 🤝 [貢獻](#貢獻) | 📄 [引用](#引用)

## 最新消息

- [2026-05] **TradingAgents v0.2.5** 發布，加入更扎實的情緒分析師、GPT-5.5 等模型覆蓋、Qwen / GLM / MiniMax 雙區域支援、`TRADINGAGENTS_*` 環境變數設定、API 金鑰自動偵測、遠端 Ollama、非美股 alpha 基準，以及 ticker 路徑穿越防護。完整內容請見 [CHANGELOG.md](CHANGELOG.md)。
- [2026-04] **TradingAgents v0.2.4** 發布，加入結構化輸出代理、LangGraph checkpoint 續跑、持久化決策紀錄、DeepSeek / Qwen / GLM / Azure 供應商支援、Docker，以及 Windows UTF-8 編碼修正。
- [2026-03] **TradingAgents v0.2.3** 發布，加入多語系支援、GPT-5.4 家族模型、統一模型目錄、回測日期一致性，以及 proxy 支援。
- [2026-03] **TradingAgents v0.2.2** 發布，加入 GPT-5.4 / Gemini 3.1 / Claude 4.6 模型覆蓋、五級評等、OpenAI Responses API、Anthropic effort 控制，以及跨平台穩定性改善。
- [2026-02] **TradingAgents v0.2.0** 發布，加入多供應商 LLM 支援（GPT-5.x、Gemini 3.x、Claude 4.x、Grok 4.x）與改良後的系統架構。
- [2026-01] **Trading-R1** [技術報告](https://arxiv.org/abs/2509.11420) 發布，[Terminal](https://github.com/TauricResearch/Trading-R1) 預計後續推出。

## TradingAgents 框架

TradingAgents 是一個多代理交易框架，用來模擬真實交易公司內部不同角色的協作方式。它透過多個由 LLM 驅動的專業代理，例如基本面分析師、情緒專家、技術分析師、交易員與風險管理團隊，共同評估市場條件並形成交易決策。這些代理也會進行動態討論，以協助找出更合適的策略。

<p align="center">
  <img src="assets/schema.png" style="width: 100%; height: auto;">
</p>

> TradingAgents 框架設計目的為研究用途。交易表現會受到許多因素影響，包含選用的基礎語言模型、模型溫度、交易期間、資料品質與其他非決定性因素。[本專案不構成財務、投資或交易建議。](https://tauric.ai/disclaimer/)

本框架將複雜交易任務拆分為多個專業角色，讓市場分析與決策流程更具擴充性與穩健性。

### 分析師團隊

- 基本面分析師：評估公司財務與營運指標，辨識內在價值與潛在警訊。
- 情緒分析師：整合新聞標題、StockTwits 與 Reddit 討論，形成短期市場情緒判讀。
- 新聞分析師：追蹤全球新聞與總體經濟指標，解讀事件對市場環境的影響。
- 技術分析師：使用 MACD、RSI 等技術指標辨識交易型態並推估價格走勢。

<p align="center">
  <img src="assets/analyst.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

### 研究員團隊

- 由看多與看空研究員組成，負責批判性地審視分析師團隊提供的洞察。透過結構化辯論，系統會平衡潛在收益與內在風險。

<p align="center">
  <img src="assets/researcher.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

### 交易員代理

- 交易員會彙整分析師與研究員的報告，做出更完整的交易判斷。它會根據綜合市場洞察，決定交易時機與交易規模。

<p align="center">
  <img src="assets/trader.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

### 風險管理與投資組合經理

- 風險管理團隊會持續評估市場波動性、流動性與其他風險因子，並對交易策略進行檢視與調整，再將評估報告交給投資組合經理做最後決策。
- 投資組合經理會核准或拒絕交易提案；若核准，訂單會送至模擬交易所並執行。

<p align="center">
  <img src="assets/risk.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

## 安裝與 CLI

### 安裝

複製 TradingAgents：

```bash
git clone https://github.com/TauricResearch/TradingAgents.git
cd TradingAgents
```

建立虛擬環境：

```bash
conda create -n tradingagents python=3.13
conda activate tradingagents
```

安裝套件與相依套件：

```bash
pip install .
```

### Docker

也可以用 Docker 執行：

```bash
cp .env.example .env  # 填入你的 API keys
docker compose run --rm tradingagents
```

如果要使用 Ollama 本機模型：

```bash
docker compose --profile ollama run --rm tradingagents-ollama
```

### 必要 API 設定

TradingAgents 支援多個 LLM 供應商。請依照你選擇的供應商設定 API key：

```bash
export OPENAI_API_KEY=...          # OpenAI (GPT)
export GOOGLE_API_KEY=...          # Google (Gemini)
export ANTHROPIC_API_KEY=...       # Anthropic (Claude)
export XAI_API_KEY=...             # xAI (Grok)
export DEEPSEEK_API_KEY=...        # DeepSeek
export DASHSCOPE_API_KEY=...       # Qwen 國際版 (dashscope-intl.aliyuncs.com)
export DASHSCOPE_CN_API_KEY=...    # Qwen 中國版 (dashscope.aliyuncs.com)
export ZHIPU_API_KEY=...           # GLM via Z.AI 國際版
export ZHIPU_CN_API_KEY=...        # GLM via BigModel 中國版 (open.bigmodel.cn)
export MINIMAX_API_KEY=...         # MiniMax 全球版 (api.minimax.io, M2.x, 204K ctx)
export MINIMAX_CN_API_KEY=...      # MiniMax 中國版 (api.minimaxi.com, M2.x, 204K ctx)
export OPENROUTER_API_KEY=...      # OpenRouter
export ALPHA_VANTAGE_API_KEY=...   # Alpha Vantage
```

在 PowerShell 中可改用：

```powershell
$env:OPENAI_API_KEY="..."
```

企業供應商（例如 Azure OpenAI）可複製 `.env.enterprise.example` 為 `.env.enterprise`，再填入憑證。

若使用本機模型，請將 `llm_provider` 設為 `"ollama"`。預設端點是 `http://localhost:11434/v1`；如需連到遠端 `ollama-serve`，可設定 `OLLAMA_BASE_URL`。先用 `ollama pull <name>` 拉取模型，再在 CLI 中選擇「Custom model ID」即可使用預設清單以外的模型。

也可以複製 `.env.example` 並填入金鑰：

```bash
cp .env.example .env
```

### CLI 用法

啟動互動式 CLI：

```bash
tradingagents          # 已安裝後的指令
python -m cli.main     # 或直接從原始碼執行
```

你會看到可選擇股票代號、分析日期、LLM 供應商、研究深度等選項的畫面。

<p align="center">
  <img src="assets/cli/cli_init.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

執行後會出現結果介面，讓你追蹤各代理分析進度。

<p align="center">
  <img src="assets/cli/cli_news.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

<p align="center">
  <img src="assets/cli/cli_transaction.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

## TradingAgents 套件

### 實作細節

TradingAgents 使用 LangGraph 建構，以提高流程彈性與模組化程度。框架支援多個 LLM 供應商：OpenAI、Google、Anthropic、xAI、DeepSeek、Qwen（阿里雲 DashScope 國際與中國端點）、GLM（Zhipu）、MiniMax（全球與中國端點）、OpenRouter、Ollama 本機或遠端模型，以及企業用 Azure OpenAI。

### Python 用法

如果要在自己的程式中使用 TradingAgents，可以匯入 `tradingagents` 模組並初始化 `TradingAgentsGraph()`。`.propagate()` 會回傳決策結果。你可以執行 `main.py`，也可以參考以下簡短範例：

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())

# forward propagate
_, decision = ta.propagate("NVDA", "2026-01-15")
print(decision)
```

你也可以調整預設設定，選擇自己的 LLM、辯論回合數等：

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openai"          # openai, google, anthropic, xai, deepseek, qwen, qwen-cn, glm, glm-cn, minimax, minimax-cn, openrouter, ollama, azure
config["deep_think_llm"] = "gpt-5.4"       # 複雜推理模型
config["quick_think_llm"] = "gpt-5.4-mini" # 快速任務模型
config["max_debate_rounds"] = 2

ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("NVDA", "2026-01-15")
print(decision)
```

完整設定請參考 `tradingagents/default_config.py`。

## 持久化與復原

TradingAgents 會在多次執行之間保留兩類狀態。

### 決策紀錄

決策紀錄預設啟用。每次完成執行後，系統會將決策附加到 `~/.tradingagents/memory/trading_memory.md`。下次針對同一 ticker 執行時，TradingAgents 會抓取實際報酬（原始報酬與相對 SPY 的 alpha）、產生一段反思，並把最近同 ticker 的決策與跨 ticker 經驗注入投資組合經理提示詞中，讓後續分析能承接過往經驗。

可用 `TRADINGAGENTS_MEMORY_LOG_PATH` 覆寫路徑。

### Checkpoint 續跑

Checkpoint 續跑可透過 `--checkpoint` 選擇性啟用。啟用後，LangGraph 會在每個節點後儲存狀態，因此當程式崩潰或中斷時，可以從最後成功步驟繼續執行，而不是從頭開始。續跑時 log 會顯示 `Resuming from step N for <TICKER> on <date>`；全新執行則會顯示 `Starting fresh`。成功完成後，checkpoint 會自動清除。

每個 ticker 的 SQLite 資料庫會放在 `~/.tradingagents/cache/checkpoints/<TICKER>.db`，可透過 `TRADINGAGENTS_CACHE_DIR` 覆寫基礎路徑。使用 `--clear-checkpoints` 可在執行前重設所有 checkpoint。

```bash
tradingagents analyze --checkpoint           # 本次執行啟用 checkpoint
tradingagents analyze --clear-checkpoints    # 執行前清除 checkpoint
```

```python
config = DEFAULT_CONFIG.copy()
config["checkpoint_enabled"] = True
ta = TradingAgentsGraph(config=config)
_, decision = ta.propagate("NVDA", "2026-01-15")
```

## 貢獻

歡迎社群貢獻。無論是修 bug、改善文件或提出新功能建議，都能讓專案變得更好。如果你對這個研究方向有興趣，也歡迎加入開源金融 AI 研究社群 [Tauric Research](https://tauric.ai/)。

過往貢獻者，包含程式碼、設計回饋與 bug 回報，會依版本列在 [`CHANGELOG.md`](CHANGELOG.md)。

## 引用

如果 *TradingAgents* 對你有幫助，請引用我們的工作：

```bibtex
@misc{xiao2025tradingagentsmultiagentsllmfinancial,
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

# English README (Original)

<p align="center">
  <img src="assets/TauricResearch.png" style="width: 60%; height: auto;">
</p>

<div align="center" style="line-height: 1;">
  <a href="https://arxiv.org/abs/2412.20138" target="_blank"><img alt="arXiv" src="https://img.shields.io/badge/arXiv-2412.20138-B31B1B?logo=arxiv"/></a>
  <a href="https://discord.com/invite/hk9PGKShPK" target="_blank"><img alt="Discord" src="https://img.shields.io/badge/Discord-TradingResearch-7289da?logo=discord&logoColor=white&color=7289da"/></a>
  <a href="https://x.com/TauricResearch" target="_blank"><img alt="X Follow" src="https://img.shields.io/badge/X-TauricResearch-white?logo=x&logoColor=white"/></a>
  <a href="https://github.com/TauricResearch/" target="_blank"><img alt="Community" src="https://img.shields.io/badge/GitHub_Community-TauricResearch-14C290?logo=discourse"/></a>
</div>
<br>
<div align="center">
  <a href="https://github.com/TauricResearch" target="_blank"><img alt="TradingAgents #1 Repository of the Day" src="https://trendshift.io/api/badge/repositories/16192" width="250" height="55"/></a>
</div>
<br>
<div align="center">
  <!-- Keep these links. Translations will automatically update with the README. -->
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

# TradingAgents: Multi-Agents LLM Financial Trading Framework

## News
- [2026-07] **TradingAgents v0.3.1** released with correctness and stability fixes: Alpha Vantage look-ahead filtering, graph-router crash-safety, graph-shape-aware checkpoint resume, working crypto sentiment sources, a configurable LLM retry budget, Bedrock API-key auth, and Claude Sonnet 5 / Fable 5 support. See [CHANGELOG.md](CHANGELOG.md) for the full list.
- [2026-06] **TradingAgents v0.3.0** released with a verified data-access contract, an expanded provider registry (NVIDIA, Kimi, Groq, Mistral, Bedrock, and any OpenAI-compatible endpoint), FRED and Polymarket data vendors, a current-generation model catalog, and a CI gate.
- [2026-05] **TradingAgents v0.2.5** released with the grounded Sentiment Analyst, GPT-5.5 etc. model coverage, Qwen/GLM/MiniMax dual-region support, `TRADINGAGENTS_*` env-var configurability with API-key auto-detection, remote Ollama support, non-US alpha benchmarks, and ticker path-traversal hardening.
- [2026-04] **TradingAgents v0.2.4** released with structured-output agents (Research Manager, Trader, Portfolio Manager), LangGraph checkpoint resume, persistent decision log, DeepSeek/Qwen/GLM/Azure provider support, Docker, and a Windows UTF-8 encoding fix.
- [2026-03] **TradingAgents v0.2.3** released with multi-language support, GPT-5.4 family models, unified model catalog, backtesting date fidelity, and proxy support.
- [2026-03] **TradingAgents v0.2.2** released with GPT-5.4/Gemini 3.1/Claude 4.6 model coverage, five-tier rating scale, OpenAI Responses API, Anthropic effort control, and cross-platform stability.
- [2026-02] **TradingAgents v0.2.0** released with multi-provider LLM support (GPT-5.x, Gemini 3.x, Claude 4.x, Grok 4.x) and improved system architecture.
- [2026-01] **Trading-R1** [Technical Report](https://arxiv.org/abs/2509.11420) released, with [Terminal](https://github.com/TauricResearch/Trading-R1) expected to land soon.

<div align="center">

🚀 [TradingAgents](#tradingagents-framework) | ⚡ [Installation & CLI](#installation-and-cli) | 🎬 [Demo](https://www.youtube.com/watch?v=90gr5lwjIho) | 📦 [Package Usage](#tradingagents-package) | 🤝 [Contributing](#contributing) | 📄 [Citation](#citation)

</div>

> 🎉 **TradingAgents** officially released! We have received numerous inquiries about the work, and we would like to express our thanks for the enthusiasm in our community.
>
> So we decided to fully open-source the framework. Looking forward to building impactful projects with you!

## TradingAgents Framework

TradingAgents is a multi-agent trading framework that mirrors the dynamics of real-world trading firms. By deploying specialized LLM-powered agents: from fundamental analysts, sentiment experts, and technical analysts, to trader, risk management team, the platform collaboratively evaluates market conditions and informs trading decisions. Moreover, these agents engage in dynamic discussions to pinpoint the optimal strategy.

<p align="center">
  <img src="assets/schema.png" style="width: 100%; height: auto;">
</p>

> TradingAgents framework is designed for research purposes. Trading performance may vary based on many factors, including the chosen backbone language models, model temperature, trading periods, the quality of data, and other non-deterministic factors. [It is not intended as financial, investment, or trading advice.](https://tauric.ai/disclaimer/)

Our framework decomposes complex trading tasks into specialized roles.

### Analyst Team
- Fundamentals Analyst: Evaluates company financials and performance metrics, identifying intrinsic values and potential red flags.
- Sentiment Analyst: Aggregates news headlines, StockTwits, and Reddit chatter into a single sentiment read to gauge short-term market mood.
- News Analyst: Monitors global news and macroeconomic indicators, interpreting the impact of events on market conditions.
- Technical Analyst: Utilizes technical indicators (like MACD and RSI) to detect trading patterns and forecast price movements.

<p align="center">
  <img src="assets/analyst.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

### Researcher Team
- Comprises both bullish and bearish researchers who critically assess the insights provided by the Analyst Team. Through structured debates, they balance potential gains against inherent risks.

<p align="center">
  <img src="assets/researcher.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

### Trader Agent
- Composes reports from the analysts and researchers to make informed trading decisions, determining the timing and magnitude of trades.

<p align="center">
  <img src="assets/trader.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

### Risk Management and Portfolio Manager
- Continuously evaluates portfolio risk by assessing market volatility, liquidity, and other risk factors. The risk management team evaluates and adjusts trading strategies, providing assessment reports to the Portfolio Manager for final decision.
- The Portfolio Manager approves/rejects the transaction proposal. If approved, the order will be sent to the simulated exchange and executed.

<p align="center">
  <img src="assets/risk.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

## Installation and CLI

### Installation

Clone TradingAgents:
```bash
git clone https://github.com/TauricResearch/TradingAgents.git
cd TradingAgents
```

Create a virtual environment in any of your favorite environment managers:
```bash
conda create -n tradingagents python=3.12
conda activate tradingagents
```

Install the package and its dependencies:
```bash
pip install .
```

### Docker

Alternatively, run with Docker:
```bash
cp .env.example .env  # add your API keys
docker compose run --rm tradingagents
```

For local models with Ollama:
```bash
docker compose --profile ollama run --rm tradingagents-ollama
```

### Required APIs

TradingAgents supports multiple LLM providers. Set the API key for your chosen provider:

```bash
export OPENAI_API_KEY=...          # OpenAI (GPT)
export GOOGLE_API_KEY=...          # Google (Gemini)
export ANTHROPIC_API_KEY=...       # Anthropic (Claude)
export XAI_API_KEY=...             # xAI (Grok)
export DEEPSEEK_API_KEY=...        # DeepSeek
export DASHSCOPE_API_KEY=...       # Qwen — International (dashscope-intl.aliyuncs.com)
export DASHSCOPE_CN_API_KEY=...    # Qwen — China (dashscope.aliyuncs.com)
export ZHIPU_API_KEY=...           # GLM via Z.AI (international)
export ZHIPU_CN_API_KEY=...        # GLM via BigModel (China, open.bigmodel.cn)
export MINIMAX_API_KEY=...         # MiniMax — Global (api.minimax.io)
export MINIMAX_CN_API_KEY=...      # MiniMax — China (api.minimaxi.com)
export OPENROUTER_API_KEY=...      # OpenRouter
export ALPHA_VANTAGE_API_KEY=...   # Alpha Vantage
```

For Azure OpenAI, copy `.env.enterprise.example` to `.env.enterprise` and fill in your credentials.

For AWS Bedrock, install the extra with `pip install ".[bedrock]"`, set `llm_provider: "bedrock"`, configure AWS credentials (environment variables, `~/.aws/credentials`, or an IAM role) and `AWS_DEFAULT_REGION`, and use a Bedrock model ID, e.g. `us.anthropic.claude-opus-4-8-v1:0`.

For local models, configure Ollama with `llm_provider: "ollama"`. The default endpoint is `http://localhost:11434/v1`; set `OLLAMA_BASE_URL` to point at a remote `ollama-serve`. Pull models with `ollama pull <name>`, and pick "Custom model ID" in the CLI for any model not listed by default.

For any other OpenAI-compatible server (vLLM, LM Studio, llama.cpp, or a custom relay), use `llm_provider: "openai_compatible"` and set the endpoint via `backend_url` (or `TRADINGAGENTS_LLM_BACKEND_URL`), e.g. `http://localhost:8000/v1` for vLLM or `http://localhost:1234/v1` for LM Studio. The model is whatever your server serves. No key is needed for local servers; set `OPENAI_COMPATIBLE_API_KEY` when the endpoint requires one.

Alternatively, copy `.env.example` to `.env` and fill in your keys:
```bash
cp .env.example .env
```

### CLI Usage

Launch the interactive CLI:
```bash
tradingagents          # installed command
python -m cli.main     # alternative: run directly from source
```
You will see a screen where you can select your desired tickers, analysis date, LLM provider, research depth, and more.

### Markets and tickers

TradingAgents works with any market Yahoo Finance covers, using the exchange-suffixed ticker. Company identity and the alpha benchmark resolve automatically per market.

- US: `AAPL`, `SPY`
- Hong Kong: `0700.HK` · Tokyo: `7203.T` · London: `AZN.L`
- India: `RELIANCE.NS`, `.BO` · Canada: `.TO` · Australia: `.AX`
- China A-shares: Shanghai `.SS`, Shenzhen `.SZ` (e.g. `600519.SS` for Kweichow Moutai)
- Crypto: `BTC-USD`, `ETH-USD`

<p align="center">
  <img src="assets/cli/cli_init.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

An interface will appear showing results as they load, letting you track the agent's progress as it runs.

<p align="center">
  <img src="assets/cli/cli_news.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

<p align="center">
  <img src="assets/cli/cli_transaction.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

## TradingAgents Package

### Implementation Details

We built TradingAgents with LangGraph to ensure flexibility and modularity. The framework supports multiple LLM providers: OpenAI, Google, Anthropic, xAI, DeepSeek, Qwen (Alibaba DashScope, international and China endpoints), GLM (Zhipu), MiniMax (global + China), OpenRouter, Ollama for local models, and Azure OpenAI for enterprise.

### Python Usage

To use TradingAgents inside your code, you can import the `tradingagents` module and initialize a `TradingAgentsGraph()` object. The `.propagate()` function will return a decision. You can run `main.py`, here's also a quick example:

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())

# forward propagate
_, decision = ta.propagate("NVDA", "2026-01-15")
print(decision)
```

You can also adjust the default configuration to set your own choice of LLMs, debate rounds, etc.

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openai"        # e.g. openai, google, anthropic, deepseek, groq, ollama; openai_compatible covers any OpenAI-compatible endpoint (vLLM, LM Studio, llama.cpp, ...)
config["deep_think_llm"] = "gpt-5.5"     # Model for complex reasoning
config["quick_think_llm"] = "gpt-5.4-mini" # Model for quick tasks
config["max_debate_rounds"] = 2

ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("NVDA", "2026-01-15")
print(decision)
```

See `tradingagents/default_config.py` for all configuration options.

## Persistence and Recovery

TradingAgents persists two kinds of state across runs.

### Decision log

The decision log is always on. Each completed run appends its decision to `~/.tradingagents/memory/trading_memory.md`. On the next run for the same ticker, TradingAgents fetches the realised return (raw and alpha vs SPY), generates a one-paragraph reflection, and injects the most recent same-ticker decisions plus recent cross-ticker lessons into the Portfolio Manager prompt, so each analysis carries forward what worked and what didn't.

Override the path with `TRADINGAGENTS_MEMORY_LOG_PATH`.

### Checkpoint resume

Checkpoint resume is opt-in via `--checkpoint`. When enabled, LangGraph saves state after each node so a crashed or interrupted run resumes from the last successful step instead of starting over. On a resume run you will see `Resuming from step N for <TICKER> on <date>` in the logs; on a new run you will see `Starting fresh`. Checkpoints are cleared automatically on successful completion.

Per-ticker SQLite databases live at `~/.tradingagents/cache/checkpoints/<TICKER>.db` (override the base with `TRADINGAGENTS_CACHE_DIR`). Use `--clear-checkpoints` to reset all of them before a run.

```bash
tradingagents analyze --checkpoint           # enable for this run
tradingagents analyze --clear-checkpoints    # reset before running
```

```python
config = DEFAULT_CONFIG.copy()
config["checkpoint_enabled"] = True
ta = TradingAgentsGraph(config=config)
_, decision = ta.propagate("NVDA", "2026-01-15")
```

## Reproducibility

TradingAgents is LLM-driven, so two runs of the same ticker and date can differ. This is expected for a research tool built on language models, not a defect. The variation comes from a few distinct sources, and it helps to separate them.

Language model sampling is non-deterministic. Even at a fixed temperature, providers do not guarantee byte-identical output across calls, and reasoning models (the default GPT-5.x family, and any thinking-mode model) vary the most because their internal reasoning is itself sampled.

Live data moves. News, StockTwits, and Reddit return different content as time passes, so a run today sees different inputs than a run last week even for the same historical trade date. Pin the analysis date to hold the price and indicator window fixed, but the social and news sources still reflect "now".

To reduce variation you can lower the sampling temperature. Set `temperature` in your config (or `TRADINGAGENTS_TEMPERATURE` in `.env`); lower values make models that honor it more repeatable. The current curated models are reasoning-first and largely ignore temperature, so for tighter reproducibility use a non-reasoning model, which you can set explicitly via the Custom model ID option.

```python
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openai"
config["temperature"] = 0.0
# Reasoning models ignore temperature. For tighter reproducibility, set a
# non-reasoning deep/quick model explicitly (e.g. via the Custom model ID option).
```

What does not vary anymore: the analyzed company identity is resolved deterministically from the ticker before any agent runs, and the market analyst grounds exact price and indicator claims in a verified data snapshot. Earlier reports of "different companies" or fabricated price levels across runs are addressed by these two mechanisms.

Backtest results are not guaranteed to match any published figure. Returns depend on the model, the temperature, the date range, data quality, and the sampling above. Treat the framework as a research scaffold for studying multi-agent analysis, not as a strategy with a fixed, replicable return.

## Contributing

Contributions are welcome: bug fixes, documentation, and feature ideas; past contributions are credited per release in [`CHANGELOG.md`](CHANGELOG.md).

## Citation

Please reference our work if you find *TradingAgents* provides you with some help :)

```
@misc{xiao2025tradingagentsmultiagentsllmfinancial,
      title={TradingAgents: Multi-Agents LLM Financial Trading Framework}, 
      author={Yijia Xiao and Edward Sun and Di Luo and Wei Wang},
      year={2025},
      eprint={2412.20138},
      archivePrefix={arXiv},
      primaryClass={q-fin.TR},
      url={https://arxiv.org/abs/2412.20138}, 
}
```
