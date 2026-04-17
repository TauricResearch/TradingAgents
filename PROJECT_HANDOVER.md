# TradingAgents A股分析项目 - 交接文档

## 项目位置
```
/Users/chenshaojie/Downloads/autoresearch/TradingAgents/
```

## 环境配置

- **Python 版本**: 3.12 (非系统默认)
- **环境路径**: `env312/`
- **激活命令**: `source env312/bin/activate`

## 运行方式

### 方式1: 完整流程 (SEPA筛选 + TradingAgents分析)
```bash
cd /Users/chenshaojie/Downloads/autoresearch/TradingAgents
source env312/bin/activate
python sepa_v5.py
```

### 方式2: 单股分析
```bash
cd /Users/chenshaojie/Downloads/autoresearch/TradingAgents
source env312/bin/activate
python run_ningde.py   # 宁德时代
```

## 关键文件

| 文件 | 说明 |
|------|------|
| `sepa_v5.py` | SEPA筛选 + TradingAgents 工作流 |
| `run_ningde.py` | 宁德时代单股分析 |
| `run_312.py` | 贵州茅台分析 (原演示脚本) |

## 当前进度

- ✅ TradingAgents 部署完成
- ✅ Python 3.12 环境配置完成
- ✅ MiniMax API (Anthropic兼容) 配置完成
- ✅ SEPA筛选流程完成 (yfinance数据源)
- ⚠️ 只完成1只股票分析 (宁德时代)

## 当前发现

1. **SEPA筛选结果**: 5只基本面达标
   - 宁德时代 (300750.SZ): ROE=23.8%, 营收=36.6%, 利润=50.1%
   - 药明康德 (603259.SS): ROE=25.8%, 营收=18.2%, 利润=128.7%
   - 立讯精密 (002475.SZ): ROE=19.6%, 营收=31.0%, 利润=29.1%
   - 寒武纪 (688256.SS): ROE=23.8%, 营收=91.0%, 利润=61.7%
   - 澜起科技 (688008.SS): ROE=17.6%, 营收=31.0%, 利润=39.9%

2. **问题**: 这些股票目前都在均线下方（调整期），SEPA技术条件未通过

3. **TradingAgents运行缓慢**: 建议一次只分析1-2只股票

4. **akshare财务API已损坏**: 使用yfinance替代

## 宁德时代分析结果

**最终交易建议**: HOLD / WAIT FOR PULLBACK

| 指标 | 数值 | 信号 |
|------|------|------|
| 当前价格 | ¥397.00 | - |
| 50日均线 | ¥360.51 | 🟢 价格在线上 |
| 200日均线 | ¥329.40 | 🟢 均线之上 (强势) |
| RSI (14) | 70.14 | 🔴 超买 |
| MACD | 金叉看涨 | 🟢 强势 |
| ATR | 12.43 | 🟡 高波动 |

**建议**: 持有现有仓位 / 新资金等待回调至¥360-365再入场

## 建议任务

1. 继续分析剩余4只股票
2. 优化SEPA参数（中国市场更宽松的阈值）
3. 添加ST股和次新股过滤
4. 批量分析100+只股票

## API配置

- API Key: 从本地环境变量读取（不要提交到仓库）
- Base URL: `https://api.minimaxi.com/anthropic`
- Model: `MiniMax-M2.7-highspeed`
