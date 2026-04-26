<p align="center">
  <img src="assets/TauricResearch.png" style="width: 60%; height: auto;">
</p>

<div align="center" style="line-height: 1;">
  <a href="https://arxiv.org/abs/2412.20138" target="_blank"><img alt="arXiv" src="https://img.shields.io/badge/arXiv-2412.20138-B31B1B?logo=arxiv"/></a>
  <a href="https://discord.com/invite/hk9PGKShPK" target="_blank"><img alt="Discord" src="https://img.shields.io/badge/Discord-TradingResearch-7289da?logo=discord&logoColor=white&color=7289da"/></a>
  <a href="./assets/wechat.png" target="_blank"><img alt="WeChat" src="https://img.shields.io/badge/微信-TauricResearch-brightgreen?logo=wechat&logoColor=white"/></a>
  <a href="https://x.com/TauricResearch" target="_blank"><img alt="X 关注" src="https://img.shields.io/badge/X-TauricResearch-white?logo=x&logoColor=white"/></a>
  <br>
  <a href="https://github.com/TauricResearch/" target="_blank"><img alt="社区" src="https://img.shields.io/badge/加入_GitHub_社区-TauricResearch-14C290?logo=discourse"/></a>
</div>

<div align="center">
  <a href="README.md">English</a> | 
  <a href="README.zh.md">简体中文</a> |
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=de">Deutsch</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=es">Español</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=fr">français</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=ja">日本語</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=ko">한국어</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=pt">Português</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=ru">Русский</a>
</div>

---

# TradingAgents: 基于大模型的金融交易多智能体框架

## 新闻
- [2026-03] **TradingAgents v0.2.1** 发布，涵盖 GPT-5.4、Gemini 3.1、Claude 4.6 等最新模型，并提升了系统稳定性。
- [2026-02] **TradingAgents v0.2.0** 发布，支持多 LLM 提供商（GPT-5.x, Gemini 3.x, Claude 4.x, Grok 4.x）并优化了系统架构。
- [2026-01] **Trading-R1** [技术报告](https://arxiv.org/abs/2509.11420) 发布，[Terminal](https://github.com/TauricResearch/Trading-R1) 预计很快面世。

<div align="center">
<a href="https://www.star-history.com/#TauricResearch/TradingAgents&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=TauricResearch/TradingAgents&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=TauricResearch/TradingAgents&type=Date" />
   <img alt="TradingAgents Star 增长趋势" src="https://api.star-history.com/svg?repos=TauricResearch/TradingAgents&type=Date" style="width: 80%; height: auto;" />
 </picture>
</a>
</div>

> 🎉 **TradingAgents** 正式发布！我们收到了大量关于此项工作的咨询，衷心感谢社区的热情。
>
> 因此，我们决定将该框架完全开源。期待与您共同构建具有影响力的项目！

<div align="center">

🚀 [框架介绍](#tradingagents-框架) | ⚡ [安装与命令行](#安装与-cli) | 🎬 [视频演示](https://www.youtube.com/watch?v=90gr5lwjIho) | 📦 [软件包用法](#tradingagents-软件包用法) | 🤝 [参与贡献](#参与贡献) | 📄 [引用](#引用)

</div>

## TradingAgents 框架

TradingAgents 是一个多智能体交易框架，它模拟了现实世界中交易公司的运作动态。通过部署专业化的 LLM 智能体：从基本面分析师、情绪专家、技术分析师到交易员及风控团队，该平台通过协作评估市场状况并辅助交易决策。此外，这些智能体还会进行动态讨论，以确定最优策略。

<p align="center">
  <img src="assets/schema.png" style="width: 100%; height: auto;">
</p>

> TradingAgents 框架专为研究目的设计。交易表现可能因多种因素而异，包括所选的基座语言模型、模型采样温度、交易周期、数据质量以及其他非确定性因素。**本框架不旨在提供任何金融、投资或交易建议。** 详见 [免责声明](https://tauric.ai/disclaimer/)。

我们的框架将复杂的交易任务分解为多个专业角色。这确保了系统在市场分析和决策过程中具备稳健性和可扩展性。

### 分析师团队 (Analyst Team)
- **基本面分析师 (Fundamentals Analyst)**：评估公司财务状况和业绩指标，识别内在价值及潜在的预警信号（红旗）。
- **情绪分析师 (Sentiment Analyst)**：使用情绪评分算法分析社交媒体和公众情绪，以衡量短期市场情绪。
- **新闻分析师 (News Analyst)**：监测全球新闻和宏观经济指标，解读重大事件对市场状况的影响。
- **技术分析师 (Technical Analyst)**：利用技术指标（如 MACD 和 RSI）检测交易模式并预测价格走势。

<p align="center">
  <img src="assets/analyst.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

### 研究员团队 (Researcher Team)
- 由**看涨**和**看跌**研究员组成，他们对分析师团队提供的见解进行辩证评估。通过结构化辩论，平衡潜在收益与固有风险。

<p align="center">
  <img src="assets/researcher.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

### 交易员智能体 (Trader Agent)
- 汇总分析师和研究员的报告，做出明智的交易决策。它根据全面的市场洞察确定交易的时机和规模。

<p align="center">
  <img src="assets/trader.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

### 风险管理与投资组合经理 (Risk Management & Portfolio Manager)
- **风险管理团队**：通过评估市场波动性、流动性和其他风险因素，持续评估投资组合风险。评估并调整交易策略，向投资组合经理提供评估报告以供最终决策。
- **投资组合经理**：批准或拒绝交易提案。如果批准，订单将被发送到模拟交易所并执行。

<p align="center">
  <img src="assets/risk.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

## 安装与 CLI

### 安装步骤

克隆 TradingAgents 仓库：
```bash
git clone https://github.com/TauricResearch/TradingAgents.git
cd TradingAgents
```

在您偏好的环境管理器中创建虚拟环境：
```bash
conda create -n tradingagents python=3.13
conda activate tradingagents
```

安装依赖：
```bash
pip install -r requirements.txt
```

### 必需的 API 密钥

TradingAgents 支持多个 LLM 提供商。请为您选择的提供商设置 API 密钥：

```bash
export OPENAI_API_KEY=...          # OpenAI (GPT)
export GOOGLE_API_KEY=...          # Google (Gemini)
export ANTHROPIC_API_KEY=...       # Anthropic (Claude)
export XAI_API_KEY=...             # xAI (Grok)
export OPENROUTER_API_KEY=...      # OpenRouter
export ALPHA_VANTAGE_API_KEY=...   # Alpha Vantage (金融数据)
```

对于本地模型，请在配置中设置 `llm_provider: "ollama"`。

或者，复制 `.env.example` 为 `.env` 并填写您的密钥：
```bash
cp .env.example .env
```

### CLI 使用方法

您可以直接运行以下命令体验命令行界面：
```bash
python -m cli.main
```
您将看到一个交互界面，可以在其中选择感兴趣的股票代码、日期、LLM、研究深度等。

<p align="center">
  <img src="assets/cli/cli_init.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

界面将随着结果加载实时更新，让您可以跟踪智能体在运行过程中的进度。

<p align="center">
  <img src="assets/cli/cli_news.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

<p align="center">
  <img src="assets/cli/cli_transaction.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

## TradingAgents 软件包用法

### 实现细节

我们使用 LangGraph 构建了 TradingAgents，以确保框架的灵活性和模块化。该框架支持多家 LLM 提供商：OpenAI, Google, Anthropic, xAI, OpenRouter 以及 Ollama。

### Python 代码调用

要在代码中使用 TradingAgents，您可以导入 `tradingagents` 模块并初始化 `TradingAgentsGraph()` 对象。调用 `.propagate()` 函数将返回一个决策。您可以直接运行 `main.py`，以下是一个快速示例：

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())

# 向前传播
_, decision = ta.propagate("NVDA", "2026-01-15")
print(decision)
```

您还可以调整默认配置，以设置您选择的 LLM、辩论轮数等。

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openai"        # 可选: openai, google, anthropic, xai, openrouter, ollama
config["deep_think_llm"] = "gpt-5.2"     # 用于复杂推理的模型
config["quick_think_llm"] = "gpt-5-mini" # 用于快速任务的模型
config["max_debate_rounds"] = 2

ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("NVDA", "2026-01-15")
print(decision)
```

查看 `tradingagents/default_config.py` 以了解所有配置选项。

## 参与贡献

我们欢迎社区的贡献！无论是修复 Bug、完善文档还是建议新功能，您的反馈都能让项目变得更好。如果您对该研究方向感兴趣，请考虑加入我们的开源金融 AI 研究社区 [Tauric Research](https://tauric.ai/)。

## 引用

如果 *TradingAgents* 对您的工作有所帮助，请引用我们的论文：

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
