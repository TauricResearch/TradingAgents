<div align="center">

### 📌 **Note:** This repository is a fork of the original [TradingAgents](https://github.com/TauricResearch/TradingAgents) repository from the paper "TradingAgents: Multi-Agents LLM Financial Trading Framework" ([arXiv:2412.20138](https://arxiv.org/abs/2412.20138)). This fork implements **FinAgents**, an extension that integrates a domain-adapted language model (FinLLaMA+) to enhance sentiment analysis and improve trading performance.

</div>

---

# FinAgents: Multi-Agent Financial Trading with Domain-Adapted Language Models

> **FinAgents** extends the TradingAgents framework by integrating **FinLLaMA+**, a fine-tuned version of Llama 3.1–8B trained via LoRA on financial filings, earnings calls, and labeled sentiment datasets. This domain-adapted model provides ticker-grounded, confidence-calibrated sentiment embeddings that enhance textual reasoning and improve decision precision in multi-agent trading systems.

<div align="center">

🚀 [FinAgents Framework](#finagents-framework) | ⚡ [Installation](#installation-and-cli) | 🎬 [Demo](https://www.youtube.com/watch?v=90gr5lwjIho) | 📦 [Package Usage](#tradingagents-package) | 🤝 [Contributing](#contributing) | 📄 [Citation](#citation)

</div>

## FinAgents Framework

FinAgents extends the TradingAgents multi-agent trading framework, which mirrors the dynamics of real-world trading firms. By deploying specialized LLM-powered agents—from fundamental analysts, sentiment experts, and technical analysts, to trader and risk management teams—the platform collaboratively evaluates market conditions and informs trading decisions. These agents engage in dynamic discussions to pinpoint the optimal strategy.

### Key Enhancements

**FinLLaMA+ Integration**: The framework integrates a domain-adapted language model (FinLLaMA+) that replaces the generic sentiment analysis used in the original TradingAgents. This enhancement includes:

- **Domain-Adaptive Pretraining (DAPT)**: Pre-training on earnings call transcripts (~304M tokens) to improve financial language understanding, achieving a 22.52% reduction in perplexity
- **Supervised Fine-Tuning (SFT)**: Fine-tuning on Financial PhraseBank and SemEval-2017 Task 5 datasets (~6,000 labeled examples) for sentiment classification
- **Ticker-Grounded Sentiment Analysis**: Produces structured JSON outputs with sentiment polarity, confidence scores, and relevance metrics
- **Confidence-Weighted Aggregation**: Aggregates multiple news items into daily sentiment scores using confidence-weighted means

### Project Team

- **Vaibhav Dhanuka** ([vdhanuka@wisc.edu](mailto:vdhanuka@wisc.edu)) - Infrastructure, LLM training, evaluation
- **Negi Shashwat** ([negi3@wisc.edu](mailto:negi3@wisc.edu)) - LLM fine-tuning, agent coordination, system design
- **Zichen Liu** ([zliu2263@wisc.edu](mailto:zliu2263@wisc.edu)) - Data collection/preprocessing, pipelines
- **Quanliang Liu** ([qliu388@wisc.edu](mailto:qliu388@wisc.edu)) - Backtesting, visualization, performance

<p align="center">
  <img src="assets/schema.png" style="width: 100%; height: auto;">
</p>

> TradingAgents framework is designed for research purposes. Trading performance may vary based on many factors, including the chosen backbone language models, model temperature, trading periods, the quality of data, and other non-deterministic factors. It is not intended as financial, investment, or trading advice.

Our framework decomposes complex trading tasks into specialized roles. This ensures the system achieves a robust, scalable approach to market analysis and decision-making.

### Analyst Team
- **Fundamentals Analyst**: Evaluates company financials and performance metrics, identifying intrinsic values and potential red flags.
- **Sentiment Analyst**: Analyzes social media and public sentiment using sentiment scoring algorithms to gauge short-term market mood.
- **News Analyst**: Enhanced with FinLLaMA+ for domain-specialized sentiment analysis. Monitors global news and macroeconomic indicators, interpreting the impact of events on market conditions with improved financial language understanding.
- **Technical Analyst**: Utilizes technical indicators (like MACD and RSI) to detect trading patterns and forecast price movements.

<p align="center">
  <img src="assets/analyst.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

### Researcher Team
- Comprises both bullish and bearish researchers who critically assess the insights provided by the Analyst Team. Through structured debates, they balance potential gains against inherent risks.

<p align="center">
  <img src="assets/researcher.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

### Trader Agent
- Composes reports from the analysts and researchers to make informed trading decisions. It determines the timing and magnitude of trades based on comprehensive market insights.

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

Clone this fork:
```bash
git clone <YOUR_REPO_URL>
cd TradingAgents
```

Or clone the original repository:
```bash
git clone https://github.com/TauricResearch/TradingAgents.git
cd TradingAgents
```

Create a virtual environment in any of your favorite environment managers:
```bash
conda create -n tradingagents python=3.13
conda activate tradingagents
```

Install dependencies:
```bash
pip install -r requirements.txt
```

### Required APIs

You will need the OpenAI API for all the agents, and [Alpha Vantage API](https://www.alphavantage.co/support/#api-key) for fundamental and news data (default configuration).

```bash
export OPENAI_API_KEY=$YOUR_OPENAI_API_KEY
export ALPHA_VANTAGE_API_KEY=$YOUR_ALPHA_VANTAGE_API_KEY
```

Alternatively, you can create a `.env` file in the project root with your API keys (see `.env.example` for reference):
```bash
cp .env.example .env
# Edit .env with your actual API keys
```

**Note:** We are happy to partner with Alpha Vantage to provide robust API support for TradingAgents. You can get a free AlphaVantage API [here](https://www.alphavantage.co/support/#api-key), TradingAgents-sourced requests also have increased rate limits to 60 requests per minute with no daily limits. Typically the quota is sufficient for performing complex tasks with TradingAgents thanks to Alpha Vantage's open-source support program. If you prefer to use OpenAI for these data sources instead, you can modify the data vendor settings in `tradingagents/default_config.py`.

## TradingAgents Package

### Implementation Details

We built TradingAgents with LangGraph to ensure flexibility and modularity. We utilize `o1-preview` and `gpt-4o` as our deep thinking and fast thinking LLMs for our experiments. However, for testing purposes, we recommend you use `o4-mini` and `gpt-4.1-mini` to save on costs as our framework makes **lots of** API calls.

### Python Usage

To use TradingAgents inside your code, you can import the `tradingagents` module and initialize a `TradingAgentsGraph()` object. The `.propagate()` function will return a decision. You can run `main.py`, here's also a quick example:

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())

# forward propagate
_, decision = ta.propagate("NVDA", "2024-05-10")
print(decision)
```

You can also adjust the default configuration to set your own choice of LLMs, debate rounds, etc.

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# Create a custom config
config = DEFAULT_CONFIG.copy()
config["deep_think_llm"] = "gpt-4.1-nano"  # Use a different model
config["quick_think_llm"] = "gpt-4.1-nano"  # Use a different model
config["max_debate_rounds"] = 1  # Increase debate rounds

# Configure data vendors (default uses yfinance and Alpha Vantage)
config["data_vendors"] = {
    "core_stock_apis": "yfinance",           # Options: yfinance, alpha_vantage, local
    "technical_indicators": "yfinance",      # Options: yfinance, alpha_vantage, local
    "fundamental_data": "alpha_vantage",     # Options: openai, alpha_vantage, local
    "news_data": "alpha_vantage",            # Options: openai, alpha_vantage, google, local
}

# Initialize with custom config
ta = TradingAgentsGraph(debug=True, config=config)

# forward propagate
_, decision = ta.propagate("NVDA", "2024-05-10")
print(decision)
```

> The default configuration uses yfinance for stock price and technical data, and Alpha Vantage for fundamental and news data. For production use or if you encounter rate limits, consider upgrading to [Alpha Vantage Premium](https://www.alphavantage.co/premium/) for more stable and reliable data access. For offline experimentation, there's a local data vendor option available, though this is still in development.

You can view the full list of configurations in `tradingagents/default_config.py`.

## FinLLaMA+ Model Details

### Training Pipeline

1. **Domain-Adaptive Pretraining (DAPT)**
   - Base model: Llama 3.1–8B
   - Dataset: Earnings call transcripts (~304M tokens, 20% of full dataset)
   - Method: QLoRA with 4-bit NF4 quantization
   - Training: 1 epoch on NVIDIA A40 GPU (~6 days)
   - Result: 22.52% perplexity reduction (6.4076 → 4.9649)

2. **Supervised Fine-Tuning (SFT)**
   - Datasets: Financial PhraseBank + SemEval-2017 Task 5 (~6,000 examples)
   - Task: Sentiment classification (positive/neutral/negative/uncertain)
   - Method: LoRA (rank r=16, α=32, dropout=0.05)
   - Output: Structured JSON with sentiment, confidence, and relevance scores

### Integration Architecture

FinLLaMA+ serves as a drop-in replacement for the News and Social Sentiment agents. It processes financial news and social media updates, producing structured outputs that are aggregated into daily sentiment scores per ticker. The model includes:

- **Caching and Deduplication**: Content hash-based caching and embedding similarity filtering to reduce redundant LLM calls
- **Relevance Scoring**: Hybrid semantic similarity and keyword matching to prioritize ticker-specific news
- **Market Sentiment Reports**: Generates interpretable narrative summaries for the Researcher Team

## Evaluation Metrics

Performance is evaluated using standard financial metrics:
- **Cumulative Return (CR)**: Total portfolio return over the evaluation period
- **Annualized Return (AR)**: Return normalized to an annual basis
- **Sharpe Ratio (SR)**: Risk-adjusted return metric
- **Maximum Drawdown (MDD)**: Largest peak-to-trough decline

## Contributing

This is a fork implementing FinAgents extensions to the TradingAgents framework. For contributions to the original TradingAgents project, please refer to the [original repository](https://github.com/TauricResearch/TradingAgents).

## Citation

### Original TradingAgents Paper

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

### Related Works

This project builds upon several key papers:
- **FinBERT** (Araci, 2019): Domain-specific transformers for finance
- **FinLLaMA** (Konstantinidis et al., 2024): Financial sentiment classification
- **Trading-R1** (Xiao et al., 2025a): Reinforcement learning for trading
- **ElliottAgents** (Wawer & Chudziak, 2025): Multi-agent LLM-based forecasting
