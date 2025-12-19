# TradingAgents 输入输出检查指南

## 📍 快速定位

### 1. **状态定义位置** (输入/输出的数据结构)
**文件**: `tradingagents/agents/utils/agent_states.py`

这是所有输入输出的数据结构定义，包含三个阶段的所有字段：

```python
class AgentState:
    # 输入
    company_of_interest: str      # 公司名称
    trade_date: str               # 交易日期
    messages: List[Message]       # 消息历史
    
    # 阶段1输出: 分析师报告
    market_report: str           # 市场分析师报告
    sentiment_report: str         # 社交媒体分析师报告
    news_report: str             # 新闻分析师报告
    fundamentals_report: str     # 基本面分析师报告
    
    # 阶段2输出: 投资辩论
    investment_debate_state: InvestDebateState  # 包含 bull_history, bear_history, judge_decision
    investment_plan: str          # 研究经理的投资计划
    trader_investment_plan: str  # 交易员的投资计划
    
    # 阶段3输出: 风险分析
    risk_debate_state: RiskDebateState  # 包含 risky/safe/neutral 历史
    final_trade_decision: str    # 最终交易决策
```

---

## 🔍 各阶段输入输出检查位置

### **阶段 1: 分析师阶段 (Analyst Phase)**

#### 输入检查:
- **初始状态**: `tradingagents/graph/propagation.py` 第 18-42 行
  ```python
  init_state = {
      "company_of_interest": company_name,
      "trade_date": trade_date,
      "market_report": "",      # 初始为空
      "sentiment_report": "",    # 初始为空
      "news_report": "",         # 初始为空
      "fundamentals_report": "", # 初始为空
      ...
  }
  ```

#### 输出检查:
- **运行时 (Debug模式)**: `tradingagents/graph/trading_graph.py` 第 171-179 行
  ```python
  for chunk in self.graph.stream(init_agent_state, **args):
      # chunk 包含每个节点的输出
      if "market_report" in chunk:
          print(chunk["market_report"])
  ```

- **最终状态**: `tradingagents/graph/trading_graph.py` 第 184 行
  ```python
  final_state = self.graph.invoke(init_agent_state, **args)
  # 访问各报告:
  final_state["market_report"]
  final_state["sentiment_report"]
  final_state["news_report"]
  final_state["fundamentals_report"]
  ```

- **日志文件**: `tradingagents/graph/trading_graph.py` 第 195-225 行
  - 保存位置: `eval_results/{ticker}/TradingAgentsStrategy_logs/full_states_log_{date}.json`
  - 包含所有报告字段

- **Agent实现**: 查看各分析师如何写入报告
  - Market: `tradingagents/agents/analysts/market_analyst.py` 第 80-83 行
  - Social: `tradingagents/agents/analysts/social_media_analyst.py`
  - News: `tradingagents/agents/analysts/news_analyst.py`
  - Fundamentals: `tradingagents/agents/analysts/fundamentals_analyst.py`

---

### **阶段 2: 研究辩论阶段 (Research Debate Phase)**

#### 输入检查:
- **从阶段1接收**: `final_state["market_report"]`, `final_state["sentiment_report"]`, etc.
- **初始辩论状态**: `tradingagents/graph/propagation.py` 第 26-28 行
  ```python
  "investment_debate_state": {
      "history": "",
      "current_response": "",
      "count": 0
  }
  ```

#### 输出检查:
- **运行时**: 在 `graph.stream()` 的 chunk 中检查
  ```python
  if "investment_debate_state" in chunk:
      debate_state = chunk["investment_debate_state"]
      print(f"Bull history: {debate_state['bull_history']}")
      print(f"Bear history: {debate_state['bear_history']}")
      print(f"Judge decision: {debate_state['judge_decision']}")
  ```

- **最终状态**:
  ```python
  final_state["investment_debate_state"]["bull_history"]
  final_state["investment_debate_state"]["bear_history"]
  final_state["investment_debate_state"]["judge_decision"]
  final_state["investment_plan"]              # Research Manager 的输出
  final_state["trader_investment_plan"]      # Trader 的输出
  ```

- **日志文件**: `tradingagents/graph/trading_graph.py` 第 204-214 行
  ```json
  {
    "investment_debate_state": {
      "bull_history": "...",
      "bear_history": "...",
      "history": "...",
      "current_response": "...",
      "judge_decision": "..."
    },
    "trader_investment_decision": "..."
  }
  ```

- **Agent实现**:
  - Bull Researcher: `tradingagents/agents/researchers/bull_researcher.py`
  - Bear Researcher: `tradingagents/agents/researchers/bear_researcher.py`
  - Research Manager: `tradingagents/agents/managers/research_manager.py`
  - Trader: `tradingagents/agents/trader/trader.py`

---

### **阶段 3: 风险分析阶段 (Risk Analysis Phase)**

#### 输入检查:
- **从阶段2接收**: `final_state["trader_investment_plan"]`
- **初始风险状态**: `tradingagents/graph/propagation.py` 第 29-37 行
  ```python
  "risk_debate_state": {
      "history": "",
      "current_risky_response": "",
      "current_safe_response": "",
      "current_neutral_response": "",
      "count": 0
  }
  ```

#### 输出检查:
- **运行时**: 在 `graph.stream()` 的 chunk 中检查
  ```python
  if "risk_debate_state" in chunk:
      risk_state = chunk["risk_debate_state"]
      print(f"Risky history: {risk_state['risky_history']}")
      print(f"Safe history: {risk_state['safe_history']}")
      print(f"Neutral history: {risk_state['neutral_history']}")
      print(f"Judge decision: {risk_state['judge_decision']}")
  ```

- **最终状态**:
  ```python
  final_state["risk_debate_state"]["risky_history"]
  final_state["risk_debate_state"]["safe_history"]
  final_state["risk_debate_state"]["neutral_history"]
  final_state["risk_debate_state"]["judge_decision"]
  final_state["final_trade_decision"]  # 最终交易决策
  ```

- **日志文件**: `tradingagents/graph/trading_graph.py` 第 216-222 行
  ```json
  {
    "risk_debate_state": {
      "risky_history": "...",
      "safe_history": "...",
      "neutral_history": "...",
      "history": "...",
      "judge_decision": "..."
    },
    "final_trade_decision": "..."
  }
  ```

- **Agent实现**:
  - Risky Analyst: `tradingagents/agents/risk_mgmt/aggresive_debator.py`
  - Safe Analyst: `tradingagents/agents/risk_mgmt/conservative_debator.py`
  - Neutral Analyst: `tradingagents/agents/risk_mgmt/neutral_debator.py`
  - Risk Manager: `tradingagents/agents/managers/risk_manager.py`

---

## 🛠️ 实际使用示例

### 方法 1: 在代码中检查 (推荐用于调试)

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())

# 运行分析
final_state, decision = ta.propagate("NVDA", "2024-05-10")

# 检查阶段1输出
print("=== 阶段1: 分析师报告 ===")
print(f"Market Report: {final_state['market_report']}")
print(f"Sentiment Report: {final_state['sentiment_report']}")
print(f"News Report: {final_state['news_report']}")
print(f"Fundamentals Report: {final_state['fundamentals_report']}")

# 检查阶段2输出
print("\n=== 阶段2: 投资辩论 ===")
debate = final_state['investment_debate_state']
print(f"Bull History: {debate['bull_history']}")
print(f"Bear History: {debate['bear_history']}")
print(f"Judge Decision: {debate['judge_decision']}")
print(f"Investment Plan: {final_state['investment_plan']}")
print(f"Trader Plan: {final_state['trader_investment_plan']}")

# 检查阶段3输出
print("\n=== 阶段3: 风险分析 ===")
risk = final_state['risk_debate_state']
print(f"Risky History: {risk['risky_history']}")
print(f"Safe History: {risk['safe_history']}")
print(f"Neutral History: {risk['neutral_history']}")
print(f"Risk Judge Decision: {risk['judge_decision']}")
print(f"Final Trade Decision: {final_state['final_trade_decision']}")
```

### 方法 2: 查看日志文件

运行后，检查 JSON 日志文件:
```bash
cat eval_results/NVDA/TradingAgentsStrategy_logs/full_states_log_2024-05-10.json
```

### 方法 3: 使用 Debug 模式实时查看

在 `trading_graph.py` 第 171-179 行，debug 模式会打印每个节点的输出:
```python
for chunk in self.graph.stream(init_agent_state, **args):
    if len(chunk["messages"]) == 0:
        pass
    else:
        chunk["messages"][-1].pretty_print()  # 打印消息
        # 可以在这里检查 chunk 中的其他字段
```

### 方法 4: 使用 CLI 界面

运行 CLI 可以看到实时输出:
```bash
python -m cli.main
```

CLI 会显示每个阶段的进度和输出 (`cli/main.py` 第 888-923 行处理各阶段的输出显示)

---

## 📊 数据流总结

```
输入 → 阶段1 → 阶段2 → 阶段3 → 输出
     ↓         ↓         ↓
  reports   debate   risk    final_decision
```

- **输入**: `propagation.py` 的 `create_initial_state()`
- **阶段1输出**: `AgentState` 中的 `*_report` 字段
- **阶段2输出**: `AgentState` 中的 `investment_debate_state` 和 `trader_investment_plan`
- **阶段3输出**: `AgentState` 中的 `risk_debate_state` 和 `final_trade_decision`
- **最终日志**: `eval_results/{ticker}/TradingAgentsStrategy_logs/full_states_log_{date}.json`

