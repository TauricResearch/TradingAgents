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

# TradingAgents：多智能体 LLM 金融交易框架

> TradingAgents 是一个用于研究的多智能体交易框架。它模拟真实交易公司的运作方式：基本面分析师、情绪分析师、新闻分析师、技术分析师、交易员、风险管理团队和投资组合经理各司其职，通过动态讨论形成最终交易决策。
>
> ⚠️ 本框架仅供研究使用，不构成任何投资、交易或财务建议。

## 最新动态

- [2026-07] **TradingAgents v0.3.1** 发布：Alpha Vantage 前瞻过滤、图路由崩溃保护、检查点恢复、可用的加密货币情绪源、LLM 重试预算、Bedrock API Key 认证以及对 Claude Sonnet 5 / Fable 5 的支持。详见 [CHANGELOG.md](CHANGELOG.md)。
- [2026-06] **TradingAgents v0.3.0** 发布：数据访问契约、扩展的模型提供商列表（NVIDIA、Kimi、Groq、Mistral、Bedrock 及任意 OpenAI 兼容端点）、FRED 与 Polymarket 数据源、新一代模型目录与 CI 门禁。
- [2026-05] **TradingAgents v0.2.5** 发布：扎实的情绪分析师、GPT-5.5 等模型支持、Qwen/GLM/MiniMax 双区域支持、`TRADINGAGENTS_*` 环境变量配置、远程 Ollama、非美国 alpha 基准、路径遍历加固。
- [2026-04] **TradingAgents v0.2.4** 发布：结构化输出智能体、LangGraph 检查点恢复、持久化决策日志、DeepSeek/Qwen/GLM/Azure 支持、Docker 与 Windows UTF-8 修复。

## 框架组成

<p align="center">
  <img src="assets/schema.png" style="width: 100%; height: auto;">
</p>

### 分析师团队
- **基本面分析师**：评估公司财务状况与经营业绩，识别内在价值与潜在风险。
- **情绪分析师**：汇总新闻标题、股吧帖子等情绪信息，判断短期市场情绪。
- **新闻分析师**：监控全球新闻与宏观经济指标，解读事件对市场的影响。
- **技术分析师**：使用 MACD、RSI 等技术指标识别交易形态并预测价格走势。

<p align="center">
  <img src="assets/analyst.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

### 研究团队
- 由看涨与看跌研究员组成，对分析师团队的结论进行批判性评估，通过结构化辩论平衡潜在收益与风险。

<p align="center">
  <img src="assets/researcher.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

### 交易员智能体
- 综合分析师与研究员的报告，做出交易决策，确定交易时机与仓位大小。

<p align="center">
  <img src="assets/trader.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

### 风险管理与投资组合经理
- 持续评估组合风险，包括市场波动性与流动性等因素；风险管理团队评估并调整交易策略，向投资组合经理提交最终建议。
- 投资组合经理批准或拒绝交易方案；若批准，订单将发送至模拟交易所执行。

<p align="center">
  <img src="assets/risk.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

## 安装与命令行

### 安装

克隆仓库：

```bash
git clone https://github.com/TauricResearch/TradingAgents.git
cd TradingAgents
```

创建并激活虚拟环境：

```bash
conda create -n tradingagents python=3.12
conda activate tradingagents
```

安装包与依赖：

```bash
pip install .
```

### Docker

也可使用 Docker：

```bash
cp .env.example .env  # 填入你的 API Key
docker compose run --rm tradingagents
```

使用本地 Ollama 模型：

```bash
docker compose --profile ollama run --rm tradingagents-ollama
```

### 所需 API

TradingAgents 支持多种大模型提供商，按需设置 API Key：

```bash
export OPENAI_API_KEY=...          # OpenAI (GPT)
export GOOGLE_API_KEY=...          # Google (Gemini)
export ANTHROPIC_API_KEY=...       # Anthropic (Claude)
export XAI_API_KEY=...             # xAI (Grok)
export DEEPSEEK_API_KEY=...        # DeepSeek
export DASHSCOPE_API_KEY=...       # Qwen 国际站
export DASHSCOPE_CN_API_KEY=...    # Qwen 中国站
export ZHIPU_API_KEY=...           # GLM 国际站
export ZHIPU_CN_API_KEY=...        # GLM 中国站
export MINIMAX_API_KEY=...         # MiniMax 国际站
export MINIMAX_CN_API_KEY=...      # MiniMax 中国站
export OPENROUTER_API_KEY=...      # OpenRouter
export ALPHA_VANTAGE_API_KEY=...   # Alpha Vantage
export FRED_API_KEY=...            # FRED 宏观数据
```

Azure OpenAI 请复制 `.env.enterprise.example` 为 `.env.enterprise` 并填写凭证。

AWS Bedrock 请安装 `pip install ".[bedrock]"`，设置 `llm_provider: "bedrock"` 并配置 AWS 凭证。

本地模型请配置 `llm_provider: "ollama"`，默认端点 `http://localhost:11434/v1`。

任意 OpenAI 兼容服务（vLLM、LM Studio 等）使用 `llm_provider: "openai_compatible"` 并通过 `TRADINGAGENTS_LLM_BACKEND_URL` 设置端点。

也可以直接复制 `.env.example` 为 `.env` 并填写：

```bash
cp .env.example .env
```

### 命令行使用

启动交互式 CLI：

```bash
tradingagents          # 已安装命令
python -m cli.main     # 直接从源码运行
```

界面会让你选择标的、分析日期、LLM 提供商、研究深度等，并实时展示分析进度。

<p align="center">
  <img src="assets/cli/cli_init.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

<p align="center">
  <img src="assets/cli/cli_news.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

<p align="center">
  <img src="assets/cli/cli_transaction.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

### 市场与代码

TradingAgents 使用带交易所后缀的标准代码。公司身份与 alpha 基准会根据交易所自动解析：

- 美股：`AAPL`、`SPY`
- 港股：`0700.HK`；日股：`7203.T`；英股：`AZN.L`
- 印度：`RELIANCE.NS`、`.BO`；加拿大：`.TO`；澳大利亚：`.AX`
- A 股：上海 `.SS`、深圳 `.SZ`（例如 `600519.SS` 贵州茅台）
- 加密货币：`BTC-USD`、`ETH-USD`

## 数据源与 A 股支持

本分支针对中国 A 股做了本地化，默认使用国内数据源，无需依赖 Yahoo Finance 即可分析沪深主板股票。

### 国内数据源

| 数据类别 | 默认源 | 可选回退 |
|---|---|---|
| 股价 / OHLCV | 新浪财经 | Alpha Vantage |
| 技术指标 | 新浪财经 | Alpha Vantage |
| 基本面数据 | 东方财富 | AkShare、Alpha Vantage |
| 新闻与情绪 | 新浪财经 + 东方财富股吧 | Alpha Vantage |
| 宏观数据 | FRED（需 `FRED_API_KEY`） | — |
| 预测市场 | Polymarket | — |

A 股代码使用后缀区分：`600519.SS`（上海）、`000858.SZ`（深圳）。

### Python 分析 A 股示例

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "deepseek"
config["deep_think_llm"] = "deepseek-v4-pro"
config["quick_think_llm"] = "deepseek-v4-flash"
config["output_language"] = "Chinese"

ta = TradingAgentsGraph(
    selected_analysts=("market", "social", "news", "fundamentals"),
    debug=True,
    config=config,
)
_, decision = ta.propagate("600519.SS", "2026-08-24", asset_type="stock")
print(decision)
```

### 辅助脚本

仓库根目录包含几个 A 股批量分析便利脚本：

- `pick_five_sina.py`：从全市场筛选 5 只趋势候选股。
- `list_more.py`：列出下一批 60 只候选股。
- `find_buy.py`：逐个分析候选股，直到出现 `Buy` 评级。
- `analyze_ticker.py`：非交互式单只股票分析。

```bash
.venv\Scripts\python.exe analyze_ticker.py 601665.SS --fresh
```

## 持久化与恢复

### 决策日志

每次运行完成后，决策会自动追加到 `~/.tradingagents/memory/trading_memory.md`。下一次分析同一标的时，框架会获取实际收益并生成反思，注入投资组合经理的提示词中。

可通过 `TRADINGAGENTS_MEMORY_LOG_PATH` 覆盖路径。

### 检查点恢复

通过 `--checkpoint` 开启。LangGraph 会在每个节点后保存状态，崩溃或中断后可从最后成功步骤恢复。

```bash
tradingagents analyze --checkpoint
tradingagents analyze --clear-checkpoints
```

```python
config = DEFAULT_CONFIG.copy()
config["checkpoint_enabled"] = True
ta = TradingAgentsGraph(config=config)
_, decision = ta.propagate("600519.SS", "2026-08-24")
```

## 可复现性

TradingAgents 基于大模型，因此同一标的、同一日期的两次运行结果可能不同，这是研究工具的预期特性。差异来源包括：

- 大模型采样本身的随机性，尤其是推理模型。
- 新闻、情绪等实时数据会随时间变化。
- 可通过降低 `temperature`（`TRADINGAGENTS_TEMPERATURE`）减少部分波动；但推理模型通常忽略温度参数。

回测结果不代表任何已发布收益，请仅将本框架视为研究多智能体分析的脚手架。

## 贡献

欢迎提交 bug 修复、文档改进与功能建议；历史贡献者见 [CHANGELOG.md](CHANGELOG.md)。

## 引用

如果本工作对你有帮助，请引用：

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
