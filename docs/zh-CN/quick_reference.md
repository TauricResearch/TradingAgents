# TradingAgents 快速参考卡片

## 🚀 快速开始

### 1. 修改LLM提供商
```python
# 编辑 main.py
config["llm_provider"] = "google"  # 或 "openai", "anthropic"
config["backend_url"] = "https://generativelanguage.googleapis.com/v1"
config["deep_think_llm"] = "gemini-2.0-flash"
config["quick_think_llm"] = "gemini-2.0-flash"
```

### 2. 修改辩论轮数
```python
# 编辑 main.py 或 default_config.py
config["max_debate_rounds"] = 3  # 增加到3轮
config["max_risk_discuss_rounds"] = 2  # 风险讨论2轮
```

### 3. 启用/禁用在线工具
```python
config["online_tools"] = True   # 启用在线API
config["online_tools"] = False  # 使用本地数据
```

## 📁 关键文件位置

| 需要修改的内容 | 文件路径 | 具体位置 |
|---------------|----------|----------|
| **系统配置** | `tradingagents/default_config.py` | 整个文件 |
| **运行时配置** | `main.py` | 第15-22行 |
| **市场分析师提示词** | `tradingagents/agents/analysts/market_analyst.py` | 第24-50行 |
| **基本面分析师提示词** | `tradingagents/agents/analysts/fundamentals_analyst.py` | 第23-26行 |
| **新闻分析师提示词** | `tradingagents/agents/analysts/news_analyst.py` | 第20-23行 |
| **社媒分析师提示词** | `tradingagents/agents/analysts/social_media_analyst.py` | 第19-22行 |
| **多头研究员提示词** | `tradingagents/agents/researchers/bull_researcher.py` | 第25-43行 |
| **空头研究员提示词** | `tradingagents/agents/researchers/bear_researcher.py` | 第25-43行 |
| **交易员提示词** | `tradingagents/agents/trader/trader.py` | 第30-36行 |
| **反思系统提示词** | `tradingagents/graph/reflection.py` | 第15-47行 |
| **缓存配置** | `tradingagents/dataflows/cache_manager.py` | 第20-35行 |

## 🎯 常用修改模板

### 1. 中文化提示词模板
```python
system_message = f"""
您是一位专业的{role_name}，具有以下特点：

专业领域：
- {domain_1}
- {domain_2}
- {domain_3}

分析要求：
1. 使用中文进行分析
2. 提供详细的分析理由
3. 包含风险提示
4. 以表格形式总结关键指标

输出格式：
{output_format}

注意事项：
- 避免简单地说"趋势混合"
- 提供具体的数据支持
- 考虑中国市场特色因素
"""
```

### 2. 风险控制模板
```python
system_message = f"""
您是一位风险意识强烈的{role_name}。

风险控制原则：
1. 风险第一，收益第二
2. 严格止损，保护本金
3. 分散投资，降低风险
4. 基于数据，理性决策

必须包含：
- 风险评估等级（低/中/高）
- 建议止损点位
- 最大仓位建议
- 风险提示说明

决策格式：
最终建议: **买入/持有/卖出**
风险等级: **低/中/高**
止损点位: **具体价格**
建议仓位: **百分比**
"""
```

### 3. 技术分析专用模板
```python
system_message = f"""
您是一位专业的技术分析师，专注于以下指标：

核心指标：
- 移动平均线：SMA、EMA
- 动量指标：RSI、MACD
- 波动率指标：布林带、ATR
- 成交量指标：VWMA

分析框架：
1. 趋势识别（上升/下降/横盘）
2. 支撑阻力位确定
3. 买卖信号识别
4. 风险收益比计算

输出要求：
- 明确的趋势判断
- 具体的进出场点位
- 技术指标背离分析
- 量价关系分析
"""
```

## ⚙️ 配置参数速查

### LLM配置
```python
"llm_provider": "openai" | "google" | "anthropic"
"deep_think_llm": "模型名称"  # 深度思考模型
"quick_think_llm": "模型名称"  # 快速思考模型
"backend_url": "API地址"
```

#### Google模型快速参考
```python
# 快速模型: gemini-2.0-flash-lite, gemini-2.0-flash ⭐, gemini-2.5-flash-preview-05-20
# 深度模型: gemini-2.0-flash ⭐, gemini-2.5-flash-preview-05-20, gemini-2.5-pro-preview-06-05

# Google API设置
export GOOGLE_API_KEY="your_key_here"
```

### 辩论配置
```python
"max_debate_rounds": 1-5        # 辩论轮数
"max_risk_discuss_rounds": 1-3  # 风险讨论轮数
"max_recur_limit": 100          # 递归限制
```

### 工具配置
```python
"online_tools": True | False    # 是否使用在线工具
"data_cache_dir": "缓存目录路径"
"results_dir": "结果输出目录"
```

### 缓存配置
```python
# 在cache_manager.py中
'us_stock_data': {'ttl_hours': 2}     # 美股缓存2小时
'china_stock_data': {'ttl_hours': 1}  # A股缓存1小时
```

## 🔧 常用命令

### 测试配置
```bash
# 运行基础测试
cd tests && python test_cache_manager.py

# 运行集成测试
cd tests && python test_integration.py

# 运行性能测试
cd tests && python test_performance.py
```

### 备份与恢复
```bash
# 备份配置文件
cp tradingagents/default_config.py tradingagents/default_config.py.backup

# 备份提示词文件
cp tradingagents/agents/trader/trader.py tradingagents/agents/trader/trader.py.backup

# 恢复文件
cp tradingagents/default_config.py.backup tradingagents/default_config.py
```

### Git管理
```bash
# 查看修改状态
git status

# 提交配置更改
git add tradingagents/default_config.py
git commit -m "feat: 更新LLM配置为Google Gemini"

# 提交提示词更改
git add tradingagents/agents/trader/trader.py
git commit -m "feat: 优化交易员提示词，增加风险控制"
```

## 🚨 注意事项

### ⚠️ 修改前必做
1. **备份文件**: 修改前务必备份原文件
2. **测试环境**: 在测试环境中验证修改效果
3. **版本控制**: 使用Git跟踪所有更改

### ⚠️ 常见错误
1. **忘记重启**: 修改配置后需要重启应用
2. **路径错误**: 确保文件路径正确
3. **语法错误**: Python语法必须正确
4. **编码问题**: 中文内容使用UTF-8编码

### ⚠️ 性能考虑
1. **提示词长度**: 避免过长的提示词（建议<4000 tokens）
2. **API调用频率**: 注意API调用限制
3. **缓存设置**: 合理设置缓存TTL时间

## 🆘 故障排除

### 问题：配置不生效
```python
# 解决方案：强制重新加载配置
from tradingagents.dataflows.config import reload_config
reload_config()
```

### 问题：中文显示乱码
```python
# 解决方案：确保文件编码为UTF-8
# 在文件开头添加编码声明
# -*- coding: utf-8 -*-
```

### 问题：API调用失败
```python
# 解决方案：检查API密钥和网络连接
import os
print("OpenAI API Key:", os.getenv("OPENAI_API_KEY", "未设置"))
print("Google API Key:", os.getenv("GOOGLE_API_KEY", "未设置"))
```

### 问题：内存使用过高
```python
# 解决方案：启用缓存清理
config["cache_settings"]["cache_size_limit_mb"] = 500  # 限制缓存大小
config["cache_settings"]["cache_cleanup_interval"] = 1800  # 30分钟清理一次
```

## 📞 获取帮助

1. **查看详细文档**: `docs/configuration_guide.md`
2. **运行测试**: `tests/` 目录下的测试文件
3. **查看示例**: `examples/` 目录（如果有）
4. **GitHub Issues**: 在项目仓库提交问题

---

💡 **提示**: 建议将此文档保存为书签，方便随时查阅！
