# Tool Execution Logs - 2026-04-16

## 1. Check average volume (batch)

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:09:22.876186
- **Tool:** `get_average_volume_batch`
- **Parameters:** `{'symbols': ['RVMD', 'BETR', 'NKE', 'CHPT', 'ABX', 'ACHC', 'AI', 'ARCT', 'ANAB', 'PAYC', 'CINF', 'CMCSA', 'CAR', 'ORCL', 'SVRE', 'SMC', 'MESO', 'SG', 'HTO', 'RPAY', 'GF', 'MNR', 'ACET', 'WKSP', 'CNXC', 'SVBL', 'FROPX', 'FRBBX', 'HOLX', 'EXAS', 'NI', 'AVB', 'SRE', 'SEE', 'EA', 'PYPL', 'COIN', 'AXP', 'COF', 'SYF', 'NVDA', 'TSLA', 'PLTR', 'SNDK', 'AMD', 'INTC', 'ABT', 'UBER', 'WMT', 'BAC', 'JPM', 'NFLX', 'AVGO', 'US', 'IV', 'AMS', 'CEPT', 'BIRD'], 'lookback_days': 10, 'curr_date': '2026-04-16', 'cache_key': 'default'}`
- **Output Length:** 10034 chars

### Output
```
{"NKE": {"symbol": "NKE", "average_volume": 39739853.9, "latest_volume": 31181739.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-16", "error": null}, "PAYC": {"symbol": "PAYC", "average_volume": 968747.0, "latest_volume": 684470.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-16", "error": null}, "CINF": {"symbol": "CINF", "average_volume": 592585.9, "latest_volume": 512259.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-16", "error": null}, "CMCSA": {"symbol": "CMCSA", "average_volume": 22943433.0, "latest_volume": 17022130.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-16", "error": null}, "ORCL": {"symbol": "ORCL", "average_volume": 29367750.4, "latest_volume": 39108504.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-16", "error": null}, "HOLX": {"symbol": "HOLX", "average_volume": 12273089.2, "latest_volume": 0.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-16", "error": null}, "EXAS": {"symbol": "EXAS", "average_volume": 3743537.9, "latest_volume": 0.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-16", "error": null}, "NI": {"symbol": "NI", "average_volume": 3137838.6, "latest_volume": 3936486.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-16", "error": null}, "AVB": {"symbol": "AVB", "average_volume": 879575.8, "latest_volume": 407758.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-16", "error": null}, "SRE": {"symbol": "SRE", "average_volume": 2877559.8, "latest_volume": 2769298.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-16", "error": null}, "SEE": {"symbol": "SEE", "average_volume": 3048100.0, "latest_volume": 0.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-16", "error": null}, "EA": {"symbol": "EA", "average_volume": 1519082.5, "latest_volume": 1163325.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-16", "error": null}, "PYPL": {"symbol": "PYPL", "average_volume": 13011948.7, "latest_volume": 12938087.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-16", "error": null}, "COIN": {"symbol": "COIN", "average_volume": 9073531.6, "latest_volume": 11413516.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-16", "error": null}, "AXP": {"symbol": "AXP", "average_volume": 2436000.3, "latest_volume": 1888303.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-16", "error": null}, "COF": {"symbol": "COF", "average_volume": 4092972.1, "latest_volume": 3211921.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-16", "error": null}, "SYF": {"symbol": "SYF", "average_volume": 2904120.0, "latest_volume": 1806500.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-16", "error": null}, "NVDA": {"symbol": "NVDA", "average_volume": 144848006.0, "latest_volume": 177529760.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-16", "error": null}, "TSLA": {"symbol": "TSLA", "average_volume": 71301637.2, "latest_volume": 113152672.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-16", "error": null}, "PLTR": {"symbol": "PLTR", "average_volume": 55872878.3, "latest_volume": 47901983.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-16", "error": null}, "AMD": {"symbol": "AMD", "average_volume": 30771630.6, "latest_volume": 23532806.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-16", "error": null}, "INTC": {"symbol": "INTC", "average_volume": 121145287.0, "latest_volume": 91456270.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-16", "error": null}, "ABT": {"symbol": "ABT", "average_volume": 9622234.0, "latest_volume": 12467440.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-16", "error": null}, "BAC": {"symbol": "BAC", "average_volume": 33338268.3, "latest_volume": 54186483.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-16", "error": null}, "JPM": {"symbol": "JPM", "average_volume": 8386134.2, "latest_volume": 7912942.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-16", "error": null}, "NFLX": {"symbol": "NFLX", "average_volume": 32356668.7, "latest_volume": 35620387.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-16", "error": null}, "AVGO": {"symbol": "AVGO", "average_volume": 23868599.1, "latest_volume": 29486791.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-16", "error": null}, "RVMD": {"symbol": "RVMD", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-16", "error": "No volume data found"}, "BETR": {"symbol": "BETR", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-16", "error": "No volume data found"}, "CHPT": {"symbol": "CHPT", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-16", "error": "No volume data found"}, "ABX": {"symbol": "ABX", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-16", "error": "No volume data found"}, "ACHC": {"symbol": "ACHC", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-16", "error": "No volume data found"}, "AI": {"symbol": "AI", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-16", "error": "No volume data found"}, "ARCT": {"symbol": "ARCT", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-16", "error": "No volume data found"}, "ANAB": {"symbol": "ANAB", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-16", "error": "No volume data found"}, "CAR": {"symbol": "CAR", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-16", "error": "No volume data found"}, "SVRE": {"symbol": "SVRE", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-16", "error": "No volume data found"}, "SMC": {"symbol": "SMC", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-16", "error": "No volume data found"}, "MESO": {"symbol": "MESO", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-16", "error": "No volume data found"}, "SG": {"symbol": "SG", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-16", "error": "No volume data found"}, "HTO": {"symbol": "HTO", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-16", "error": "No volume data found"}, "RPAY": {"symbol": "RPAY", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-16", "error": "No volume data found"}, "GF": {"symbol": "GF", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-16", "error": "No volume data found"}, "MNR": {"symbol": "MNR", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-16", "error": "No volume data found"}, "ACET": {"symbol": "ACET", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-16", "error": "No volume data found"}, "WKSP": {"symbol": "WKSP", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-16", "error": "No volume data found"}, "CNXC": {"symbol": "CNXC", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-16", "error": "No volume data found"}, "SVBL": {"symbol": "SVBL", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-16", "error": "No volume data found"}, "FROPX": {"symbol": "FROPX", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-16", "error": "No volume data found"}, "FRBBX": {"symbol": "FRBBX", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-16", "error": "No volume data found"}, "SNDK": {"symbol": "SNDK", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-16", "error": "No volume data found"}, "UBER": {"symbol": "UBER", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-16", "error": "No volume data found"}, "WMT": {"symbol": "WMT", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-16", "error": "No volume data found"}, "US": {"symbol": "US", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-16", "error": "No volume data found"}, "IV": {"symbol": "IV", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-16", "error": "No volume data found"}, "AMS": {"symbol": "AMS", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-16", "error": "No volume data found"}, "CEPT": {"symbol": "CEPT", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-16", "error": "No volume data found"}, "BIRD": {"symbol": "BIRD", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-16",... [truncated]
```

---

## 2. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:12.577582
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'RVMD', 'curr_date': '2026-04-16'}`
- **Output Length:** 1583 chars

### Output
```
# Technical Analysis for RVMD
**Date:** 2026-04-16
**Current Price:** $152.54

## Price Action
- **Daily Change:** +3.76%
- **5-Day Change:** +58.53%

## RSI (14)
- **Value:** 87.8 ↑
- **Signal:** OVERBOUGHT ⚠️

## MACD
- **MACD Line:** 8.970
- **Signal Line:** 2.666
- **Histogram:** 6.304 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $100.98 (+51.1% from price)
- **200 SMA:** $70.07 (+117.7% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $140.11
- **Middle:** $103.50
- **Lower:** $66.88
- **Band Position:** 117%
- **Bandwidth:** 70.8% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $6.69 (4.4% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $142.50 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 83.8
- **%D:** 70.4
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 49.5 (Strengthening ↑)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $109.49 (+39.3% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 76.8M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $120.49
- **Current vs VWAP:** +26.6%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $155.01
- **Recent Low:** $91.52
- **Next Resistance:** $155.01 (0.0% (High))
- **Next Support:** $140.03 (23.6%)

## Summary
- **Key Signals:** RSI overbought, Above 50 SMA

```

---

## 3. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:12.625678
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'RVMD'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for RVMD: Too Many Requests. Rate limited. Try after a while.
```

---

## 4. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:12.884466
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'RVMD'}`
- **Output Length:** 719 chars

### Output
```
## Analyst Recommendation Trends for RVMD

### 2026-04-01
- **Strong Buy**: 11
- **Buy**: 15
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 27

**Sentiment**: 96.3% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 11
- **Buy**: 15
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 27

**Sentiment**: 96.3% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 11
- **Buy**: 15
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 27

**Sentiment**: 96.3% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 11
- **Buy**: 15
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 27

**Sentiment**: 96.3% Bullish, 0.0% Bearish


```

---

## 5. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:12.908167
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'RVMD', 'num_expirations': 3, 'curr_date': '2026-04-16'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for RVMD: Too Many Requests. Rate limited. Try after a while.
```

---

## 6. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:13.610829
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'NKE', 'curr_date': '2026-04-16'}`
- **Output Length:** 1538 chars

### Output
```
# Technical Analysis for NKE
**Date:** 2026-04-16
**Current Price:** $45.44

## Price Action
- **Daily Change:** +2.81%
- **5-Day Change:** +3.27%

## RSI (14)
- **Value:** 36.2 ↑
- **Signal:** Bearish

## MACD
- **MACD Line:** -3.594
- **Signal Line:** -3.630
- **Histogram:** 0.036 (Weakening ↓)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $55.57 (-18.2% from price)
- **200 SMA:** $65.04 (-30.1% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $57.39
- **Middle:** $48.19
- **Lower:** $38.99
- **Band Position:** 35%
- **Bandwidth:** 38.2% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $1.75 (3.8% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $42.82 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 42.7
- **%D:** 22.8
- **Signal:** Bullish crossover ⚡

## ADX (Trend Strength)
- **ADX:** 51.0 (Weakening ↓)
- **Interpretation:** VERY STRONG TREND ⚡

## 20 EMA
- **Value:** $47.77 (-4.9% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** -271.4M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $46.72
- **Current vs VWAP:** -2.7%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $68.04
- **Recent Low:** $42.09
- **Next Resistance:** $47.64 (78.6%)
- **Next Support:** $42.09 (100% (Low))

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 7. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:13.658786
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'NKE'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for NKE: Too Many Requests. Rate limited. Try after a while.
```

---

## 8. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:13.936577
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'NKE'}`
- **Output Length:** 722 chars

### Output
```
## Analyst Recommendation Trends for NKE

### 2026-04-01
- **Strong Buy**: 11
- **Buy**: 16
- **Hold**: 14
- **Sell**: 2
- **Strong Sell**: 0
- **Total Analysts**: 43

**Sentiment**: 62.8% Bullish, 4.7% Bearish

### 2026-03-01
- **Strong Buy**: 11
- **Buy**: 15
- **Hold**: 16
- **Sell**: 2
- **Strong Sell**: 0
- **Total Analysts**: 44

**Sentiment**: 59.1% Bullish, 4.5% Bearish

### 2026-02-01
- **Strong Buy**: 11
- **Buy**: 15
- **Hold**: 16
- **Sell**: 2
- **Strong Sell**: 0
- **Total Analysts**: 44

**Sentiment**: 59.1% Bullish, 4.5% Bearish

### 2026-01-01
- **Strong Buy**: 11
- **Buy**: 15
- **Hold**: 15
- **Sell**: 2
- **Strong Sell**: 0
- **Total Analysts**: 43

**Sentiment**: 60.5% Bullish, 4.7% Bearish


```

---

## 9. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:13.959318
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'NKE', 'num_expirations': 3, 'curr_date': '2026-04-16'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for NKE: Too Many Requests. Rate limited. Try after a while.
```

---

## 10. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:14.532197
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'ACHC', 'curr_date': '2026-04-16'}`
- **Output Length:** 1502 chars

### Output
```
# Technical Analysis for ACHC
**Date:** 2026-04-16
**Current Price:** $26.61

## Price Action
- **Daily Change:** +0.19%
- **5-Day Change:** -2.17%

## RSI (14)
- **Value:** 66.1 ↓
- **Signal:** Bullish

## MACD
- **MACD Line:** 1.355
- **Signal Line:** 1.277
- **Histogram:** 0.078 (Weakening ↓)
- **Signal:** Bullish

## Moving Averages
- **50 SMA:** $21.51 (+23.7% from price)
- **200 SMA:** $20.11 (+32.3% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $27.59
- **Middle:** $24.46
- **Lower:** $21.32
- **Band Position:** 84%
- **Bandwidth:** 25.6% (volatility indicator)
- **Signal:** Near upper band

## ATR (Volatility)
- **ATR:** $1.20 (4.5% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $24.81 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 75.1
- **%D:** 76.4
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 33.6 (Strengthening ↑)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $24.79 (+7.3% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 77.4M
- **5-Day Trend:** Rising ↑
- **Signal:** BULLISH DIVERGENCE ⚡ (accumulation)

## VWAP (20-period)
- **VWAP:** $24.39
- **Current vs VWAP:** +9.1%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $27.99
- **Recent Low:** $12.91
- **Next Resistance:** $27.99 (0.0% (High))
- **Next Support:** $24.43 (23.6%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 11. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:14.583665
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'ACHC'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for ACHC: Too Many Requests. Rate limited. Try after a while.
```

---

## 12. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:14.851504
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'ACHC'}`
- **Output Length:** 711 chars

### Output
```
## Analyst Recommendation Trends for ACHC

### 2026-04-01
- **Strong Buy**: 3
- **Buy**: 9
- **Hold**: 7
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 20

**Sentiment**: 60.0% Bullish, 5.0% Bearish

### 2026-03-01
- **Strong Buy**: 3
- **Buy**: 9
- **Hold**: 7
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 20

**Sentiment**: 60.0% Bullish, 5.0% Bearish

### 2026-02-01
- **Strong Buy**: 3
- **Buy**: 9
- **Hold**: 7
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 20

**Sentiment**: 60.0% Bullish, 5.0% Bearish

### 2026-01-01
- **Strong Buy**: 4
- **Buy**: 9
- **Hold**: 6
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 20

**Sentiment**: 65.0% Bullish, 5.0% Bearish


```

---

## 13. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:14.876188
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'ACHC', 'num_expirations': 3, 'curr_date': '2026-04-16'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for ACHC: Too Many Requests. Rate limited. Try after a while.
```

---

## 14. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:15.660112
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'PAYC', 'curr_date': '2026-04-16'}`
- **Output Length:** 1557 chars

### Output
```
# Technical Analysis for PAYC
**Date:** 2026-04-16
**Current Price:** $123.64

## Price Action
- **Daily Change:** +3.17%
- **5-Day Change:** +7.66%

## RSI (14)
- **Value:** 51.3 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** -2.102
- **Signal Line:** -2.479
- **Histogram:** 0.377 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $124.31 (-0.5% from price)
- **200 SMA:** $176.00 (-29.7% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $128.03
- **Middle:** $121.12
- **Lower:** $114.20
- **Band Position:** 68%
- **Bandwidth:** 11.4% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $5.64 (4.6% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $115.18 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 56.4
- **%D:** 45.9
- **Signal:** Bullish crossover ⚡

## ADX (Trend Strength)
- **ADX:** 12.3 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $121.53 (+1.7% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 4.7M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $122.52
- **Current vs VWAP:** +0.9%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $138.86
- **Recent Low:** $104.61
- **Next Resistance:** $125.78 (38.2%)
- **Next Support:** $121.74 (50.0%)

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 15. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:15.707925
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'PAYC'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for PAYC: Too Many Requests. Rate limited. Try after a while.
```

---

## 16. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:15.975521
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'PAYC'}`
- **Output Length:** 715 chars

### Output
```
## Analyst Recommendation Trends for PAYC

### 2026-04-01
- **Strong Buy**: 5
- **Buy**: 7
- **Hold**: 16
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 28

**Sentiment**: 42.9% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 5
- **Buy**: 7
- **Hold**: 16
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 28

**Sentiment**: 42.9% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 5
- **Buy**: 7
- **Hold**: 16
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 28

**Sentiment**: 42.9% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 5
- **Buy**: 7
- **Hold**: 16
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 28

**Sentiment**: 42.9% Bullish, 0.0% Bearish


```

---

## 17. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:15.998468
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'PAYC', 'num_expirations': 3, 'curr_date': '2026-04-16'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for PAYC: Too Many Requests. Rate limited. Try after a while.
```

---

## 18. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:16.678370
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'CINF', 'curr_date': '2026-04-16'}`
- **Output Length:** 1526 chars

### Output
```
# Technical Analysis for CINF
**Date:** 2026-04-16
**Current Price:** $163.00

## Price Action
- **Daily Change:** -0.21%
- **5-Day Change:** -0.58%

## RSI (14)
- **Value:** 54.7 ↓
- **Signal:** Bullish

## MACD
- **MACD Line:** 0.418
- **Signal Line:** -0.323
- **Histogram:** 0.741 (Weakening ↓)
- **Signal:** Bullish

## Moving Averages
- **50 SMA:** $162.32 (+0.4% from price)
- **200 SMA:** $157.21 (+3.7% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $165.23
- **Middle:** $159.32
- **Lower:** $153.40
- **Band Position:** 81%
- **Bandwidth:** 7.4% (volatility indicator)
- **Signal:** Near upper band

## ATR (Volatility)
- **ATR:** $3.12 (1.9% of price)
- **Level:** Low volatility
- **Suggested Stop-Loss:** $158.32 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 74.6
- **%D:** 74.0
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 10.7 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $161.05 (+1.2% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 14.5M
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $158.96
- **Current vs VWAP:** +2.5%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $173.25
- **Recent Low:** $153.40
- **Next Resistance:** $163.32 (50.0%)
- **Next Support:** $160.98 (61.8%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 19. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:16.726582
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'CINF'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for CINF: Too Many Requests. Rate limited. Try after a while.
```

---

## 20. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:16.984035
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'CINF'}`
- **Output Length:** 711 chars

### Output
```
## Analyst Recommendation Trends for CINF

### 2026-04-01
- **Strong Buy**: 3
- **Buy**: 7
- **Hold**: 5
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 15

**Sentiment**: 66.7% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 3
- **Buy**: 7
- **Hold**: 5
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 15

**Sentiment**: 66.7% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 3
- **Buy**: 7
- **Hold**: 5
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 15

**Sentiment**: 66.7% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 3
- **Buy**: 7
- **Hold**: 5
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 15

**Sentiment**: 66.7% Bullish, 0.0% Bearish


```

---

## 21. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:17.007849
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'CINF', 'num_expirations': 3, 'curr_date': '2026-04-16'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for CINF: Too Many Requests. Rate limited. Try after a while.
```

---

## 22. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:17.731897
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'CMCSA', 'curr_date': '2026-04-16'}`
- **Output Length:** 1523 chars

### Output
```
# Technical Analysis for CMCSA
**Date:** 2026-04-16
**Current Price:** $28.30

## Price Action
- **Daily Change:** +0.57%
- **5-Day Change:** -0.04%

## RSI (14)
- **Value:** 44.8 ↑
- **Signal:** Bearish

## MACD
- **MACD Line:** -0.433
- **Signal Line:** -0.501
- **Histogram:** 0.068 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $29.78 (-5.0% from price)
- **200 SMA:** $28.64 (-1.2% from price)
- **Trend:** Downtrend

## Bollinger Bands (20,2)
- **Upper:** $28.91
- **Middle:** $28.25
- **Lower:** $27.59
- **Band Position:** 54%
- **Bandwidth:** 4.7% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $0.67 (2.4% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $27.30 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 56.7
- **%D:** 42.0
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 12.6 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $28.46 (-0.6% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** 315.7M
- **5-Day Trend:** Rising ↑
- **Signal:** BULLISH DIVERGENCE ⚡ (accumulation)

## VWAP (20-period)
- **VWAP:** $28.47
- **Current vs VWAP:** -0.6%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $32.48
- **Recent Low:** $27.48
- **Next Resistance:** $28.55 (78.6%)
- **Next Support:** $27.48 (100% (Low))

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 23. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:17.805378
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'CMCSA'}`
- **Output Length:** 100 chars

### Output
```
Error retrieving insider transactions for CMCSA: Too Many Requests. Rate limited. Try after a while.
```

---

## 24. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:18.043469
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'CMCSA'}`
- **Output Length:** 720 chars

### Output
```
## Analyst Recommendation Trends for CMCSA

### 2026-04-01
- **Strong Buy**: 5
- **Buy**: 10
- **Hold**: 21
- **Sell**: 3
- **Strong Sell**: 0
- **Total Analysts**: 39

**Sentiment**: 38.5% Bullish, 7.7% Bearish

### 2026-03-01
- **Strong Buy**: 5
- **Buy**: 10
- **Hold**: 21
- **Sell**: 3
- **Strong Sell**: 0
- **Total Analysts**: 39

**Sentiment**: 38.5% Bullish, 7.7% Bearish

### 2026-02-01
- **Strong Buy**: 5
- **Buy**: 10
- **Hold**: 22
- **Sell**: 2
- **Strong Sell**: 0
- **Total Analysts**: 39

**Sentiment**: 38.5% Bullish, 5.1% Bearish

### 2026-01-01
- **Strong Buy**: 5
- **Buy**: 11
- **Hold**: 23
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 40

**Sentiment**: 40.0% Bullish, 2.5% Bearish


```

---

## 25. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:18.060265
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'CMCSA', 'num_expirations': 3, 'curr_date': '2026-04-16'}`
- **Output Length:** 96 chars

### Output
```
Error retrieving options activity for CMCSA: Too Many Requests. Rate limited. Try after a while.
```

---

## 26. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:18.765183
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'ORCL', 'curr_date': '2026-04-16'}`
- **Output Length:** 1553 chars

### Output
```
# Technical Analysis for ORCL
**Date:** 2026-04-16
**Current Price:** $169.81

## Price Action
- **Daily Change:** +4.18%
- **5-Day Change:** +23.18%

## RSI (14)
- **Value:** 66.6 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 0.903
- **Signal Line:** -2.053
- **Histogram:** 2.956 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $150.06 (+13.2% from price)
- **200 SMA:** $214.45 (-20.8% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $164.60
- **Middle:** $147.73
- **Lower:** $130.87
- **Band Position:** 115%
- **Bandwidth:** 22.8% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $7.99 (4.7% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $157.83 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 72.5
- **%D:** 56.1
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 21.7 (Strengthening ↑)
- **Interpretation:** Trending

## 20 EMA
- **Value:** $150.01 (+13.2% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** -248.5M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $149.85
- **Current vs VWAP:** +13.3%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $172.56
- **Recent Low:** $134.57
- **Next Resistance:** $172.56 (0.0% (High))
- **Next Support:** $163.59 (23.6%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 27. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:18.818059
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'ORCL'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for ORCL: Too Many Requests. Rate limited. Try after a while.
```

---

## 28. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:19.069105
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'ORCL'}`
- **Output Length:** 723 chars

### Output
```
## Analyst Recommendation Trends for ORCL

### 2026-04-01
- **Strong Buy**: 16
- **Buy**: 24
- **Hold**: 10
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 51

**Sentiment**: 78.4% Bullish, 2.0% Bearish

### 2026-03-01
- **Strong Buy**: 16
- **Buy**: 22
- **Hold**: 11
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 50

**Sentiment**: 76.0% Bullish, 2.0% Bearish

### 2026-02-01
- **Strong Buy**: 15
- **Buy**: 23
- **Hold**: 11
- **Sell**: 2
- **Strong Sell**: 0
- **Total Analysts**: 51

**Sentiment**: 74.5% Bullish, 3.9% Bearish

### 2026-01-01
- **Strong Buy**: 15
- **Buy**: 22
- **Hold**: 12
- **Sell**: 2
- **Strong Sell**: 0
- **Total Analysts**: 51

**Sentiment**: 72.5% Bullish, 3.9% Bearish


```

---

## 29. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:19.094060
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'ORCL', 'num_expirations': 3, 'curr_date': '2026-04-16'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for ORCL: Too Many Requests. Rate limited. Try after a while.
```

---

## 30. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:25.991092
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'CNXC', 'curr_date': '2026-04-16'}`
- **Output Length:** 1543 chars

### Output
```
# Technical Analysis for CNXC
**Date:** 2026-04-16
**Current Price:** $28.81

## Price Action
- **Daily Change:** +1.87%
- **5-Day Change:** +1.09%

## RSI (14)
- **Value:** 48.6 ↑
- **Signal:** Bearish

## MACD
- **MACD Line:** -1.114
- **Signal Line:** -1.471
- **Histogram:** 0.357 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $31.42 (-8.3% from price)
- **200 SMA:** $42.02 (-31.4% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $32.40
- **Middle:** $28.15
- **Lower:** $23.89
- **Band Position:** 58%
- **Bandwidth:** 30.3% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $2.16 (7.5% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $25.56 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 62.0
- **%D:** 55.6
- **Signal:** Bullish crossover ⚡

## ADX (Trend Strength)
- **ADX:** 19.9 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $28.58 (+0.8% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 4.2M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $27.92
- **Current vs VWAP:** +3.2%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $40.03
- **Recent Low:** $24.27
- **Next Resistance:** $30.29 (61.8%)
- **Next Support:** $27.64 (78.6%)

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 31. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:26.039116
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'CNXC'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for CNXC: Too Many Requests. Rate limited. Try after a while.
```

---

## 32. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:26.297684
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'CNXC'}`
- **Output Length:** 711 chars

### Output
```
## Analyst Recommendation Trends for CNXC

### 2026-04-01
- **Strong Buy**: 4
- **Buy**: 4
- **Hold**: 3
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 11

**Sentiment**: 72.7% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 4
- **Buy**: 4
- **Hold**: 3
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 11

**Sentiment**: 72.7% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 4
- **Buy**: 4
- **Hold**: 3
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 11

**Sentiment**: 72.7% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 4
- **Buy**: 4
- **Hold**: 3
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 11

**Sentiment**: 72.7% Bullish, 0.0% Bearish


```

---

## 33. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:26.323839
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'CNXC', 'num_expirations': 3, 'curr_date': '2026-04-16'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for CNXC: Too Many Requests. Rate limited. Try after a while.
```

---

## 34. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:27.332281
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'NI', 'curr_date': '2026-04-16'}`
- **Output Length:** 1498 chars

### Output
```
# Technical Analysis for NI
**Date:** 2026-04-16
**Current Price:** $47.37

## Price Action
- **Daily Change:** +0.32%
- **5-Day Change:** -2.27%

## RSI (14)
- **Value:** 54.9 ↓
- **Signal:** Bullish

## MACD
- **MACD Line:** 0.410
- **Signal Line:** 0.394
- **Histogram:** 0.016 (Weakening ↓)
- **Signal:** Bullish

## Moving Averages
- **50 SMA:** $46.35 (+2.2% from price)
- **200 SMA:** $42.87 (+10.5% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $48.72
- **Middle:** $46.77
- **Lower:** $44.81
- **Band Position:** 65%
- **Bandwidth:** 8.4% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $0.86 (1.8% of price)
- **Level:** Low volatility
- **Suggested Stop-Loss:** $46.08 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 49.3
- **%D:** 64.3
- **Signal:** Bearish

## ADX (Trend Strength)
- **ADX:** 9.4 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $47.07 (+0.6% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 137.1M
- **5-Day Trend:** Rising ↑
- **Signal:** BULLISH DIVERGENCE ⚡ (accumulation)

## VWAP (20-period)
- **VWAP:** $46.74
- **Current vs VWAP:** +1.3%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $48.76
- **Recent Low:** $43.41
- **Next Resistance:** $47.50 (23.6%)
- **Next Support:** $46.72 (38.2%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 35. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:27.384526
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'NI'}`
- **Output Length:** 97 chars

### Output
```
Error retrieving insider transactions for NI: Too Many Requests. Rate limited. Try after a while.
```

---

## 36. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:27.654774
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'NI'}`
- **Output Length:** 713 chars

### Output
```
## Analyst Recommendation Trends for NI

### 2026-04-01
- **Strong Buy**: 8
- **Buy**: 12
- **Hold**: 4
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 24

**Sentiment**: 83.3% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 8
- **Buy**: 11
- **Hold**: 4
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 23

**Sentiment**: 82.6% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 8
- **Buy**: 12
- **Hold**: 3
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 23

**Sentiment**: 87.0% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 8
- **Buy**: 12
- **Hold**: 3
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 23

**Sentiment**: 87.0% Bullish, 0.0% Bearish


```

---

## 37. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:27.679249
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'NI', 'num_expirations': 3, 'curr_date': '2026-04-16'}`
- **Output Length:** 93 chars

### Output
```
Error retrieving options activity for NI: Too Many Requests. Rate limited. Try after a while.
```

---

## 38. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:28.336561
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'AVB', 'curr_date': '2026-04-16'}`
- **Output Length:** 1517 chars

### Output
```
# Technical Analysis for AVB
**Date:** 2026-04-16
**Current Price:** $171.29

## Price Action
- **Daily Change:** +0.17%
- **5-Day Change:** +1.65%

## RSI (14)
- **Value:** 60.4 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 0.226
- **Signal Line:** -1.022
- **Histogram:** 1.248 (Weakening ↓)
- **Signal:** Bullish

## Moving Averages
- **50 SMA:** $170.27 (+0.6% from price)
- **200 SMA:** $179.52 (-4.6% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $172.90
- **Middle:** $164.99
- **Lower:** $157.09
- **Band Position:** 90%
- **Bandwidth:** 9.6% (volatility indicator)
- **Signal:** Near upper band

## ATR (Volatility)
- **ATR:** $2.96 (1.7% of price)
- **Level:** Low volatility
- **Suggested Stop-Loss:** $166.85 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 92.3
- **%D:** 85.2
- **Signal:** OVERBOUGHT ⚠️

## ADX (Trend Strength)
- **ADX:** 8.3 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $167.69 (+2.1% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** -8.7M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $164.56
- **Current vs VWAP:** +4.1%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $179.37
- **Recent Low:** $158.58
- **Next Resistance:** $171.43 (38.2%)
- **Next Support:** $168.98 (50.0%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 39. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:28.385359
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'AVB'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for AVB: Too Many Requests. Rate limited. Try after a while.
```

---

## 40. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:28.619394
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'AVB'}`
- **Output Length:** 714 chars

### Output
```
## Analyst Recommendation Trends for AVB

### 2026-04-01
- **Strong Buy**: 3
- **Buy**: 6
- **Hold**: 18
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 27

**Sentiment**: 33.3% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 3
- **Buy**: 7
- **Hold**: 17
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 27

**Sentiment**: 37.0% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 3
- **Buy**: 8
- **Hold**: 16
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 27

**Sentiment**: 40.7% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 3
- **Buy**: 9
- **Hold**: 15
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 27

**Sentiment**: 44.4% Bullish, 0.0% Bearish


```

---

## 41. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:28.641900
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'AVB', 'num_expirations': 3, 'curr_date': '2026-04-16'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for AVB: Too Many Requests. Rate limited. Try after a while.
```

---

## 42. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:30.959145
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'SRE', 'curr_date': '2026-04-16'}`
- **Output Length:** 1534 chars

### Output
```
# Technical Analysis for SRE
**Date:** 2026-04-16
**Current Price:** $95.47

## Price Action
- **Daily Change:** -0.72%
- **5-Day Change:** -4.29%

## RSI (14)
- **Value:** 48.2 ↓
- **Signal:** Bearish

## MACD
- **MACD Line:** 1.005
- **Signal Line:** 1.342
- **Histogram:** -0.336 (Strengthening ↑)
- **Signal:** BEARISH CROSSOVER ⚠️

## Moving Averages
- **50 SMA:** $93.80 (+1.8% from price)
- **200 SMA:** $87.15 (+9.6% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $100.55
- **Middle:** $96.43
- **Lower:** $92.32
- **Band Position:** 38%
- **Bandwidth:** 8.5% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $2.00 (2.1% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $92.47 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 30.7
- **%D:** 51.8
- **Signal:** Bearish

## ADX (Trend Strength)
- **ADX:** 11.3 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $96.46 (-1.0% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** 99.1M
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $96.13
- **Current vs VWAP:** -0.7%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $101.04
- **Recent Low:** $85.04
- **Next Resistance:** $97.26 (23.6%)
- **Next Support:** $94.93 (38.2%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 43. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:31.010331
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'SRE'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for SRE: Too Many Requests. Rate limited. Try after a while.
```

---

## 44. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:31.276494
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'SRE'}`
- **Output Length:** 714 chars

### Output
```
## Analyst Recommendation Trends for SRE

### 2026-04-01
- **Strong Buy**: 6
- **Buy**: 11
- **Hold**: 6
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 23

**Sentiment**: 73.9% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 5
- **Buy**: 11
- **Hold**: 7
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 23

**Sentiment**: 69.6% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 5
- **Buy**: 10
- **Hold**: 7
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 22

**Sentiment**: 68.2% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 5
- **Buy**: 10
- **Hold**: 7
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 22

**Sentiment**: 68.2% Bullish, 0.0% Bearish


```

---

## 45. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:31.300528
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'SRE', 'num_expirations': 3, 'curr_date': '2026-04-16'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for SRE: Too Many Requests. Rate limited. Try after a while.
```

---

## 46. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:34.790533
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'EA', 'curr_date': '2026-04-16'}`
- **Output Length:** 1501 chars

### Output
```
# Technical Analysis for EA
**Date:** 2026-04-16
**Current Price:** $203.24

## Price Action
- **Daily Change:** +0.19%
- **5-Day Change:** +0.51%

## RSI (14)
- **Value:** 57.0 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 0.562
- **Signal Line:** 0.596
- **Histogram:** -0.034 (Weakening ↓)
- **Signal:** Bearish

## Moving Averages
- **50 SMA:** $201.12 (+1.1% from price)
- **200 SMA:** $189.81 (+7.1% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $204.86
- **Middle:** $202.51
- **Lower:** $200.16
- **Band Position:** 66%
- **Bandwidth:** 2.3% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $1.04 (0.5% of price)
- **Level:** Low volatility
- **Suggested Stop-Loss:** $201.68 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 47.1
- **%D:** 54.5
- **Signal:** Bearish

## ADX (Trend Strength)
- **ADX:** 20.9 (Weakening ↓)
- **Interpretation:** Trending

## 20 EMA
- **Value:** $202.51 (+0.4% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 48.5M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $202.21
- **Current vs VWAP:** +0.5%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $204.22
- **Recent Low:** $196.21
- **Next Resistance:** $204.22 (0.0% (High))
- **Next Support:** $202.33 (23.6%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 47. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:34.892572
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'EA'}`
- **Output Length:** 97 chars

### Output
```
Error retrieving insider transactions for EA: Too Many Requests. Rate limited. Try after a while.
```

---

## 48. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:35.151510
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'EA'}`
- **Output Length:** 713 chars

### Output
```
## Analyst Recommendation Trends for EA

### 2026-04-01
- **Strong Buy**: 5
- **Buy**: 6
- **Hold**: 21
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 32

**Sentiment**: 34.4% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 5
- **Buy**: 6
- **Hold**: 21
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 33

**Sentiment**: 33.3% Bullish, 3.0% Bearish

### 2026-02-01
- **Strong Buy**: 5
- **Buy**: 6
- **Hold**: 21
- **Sell**: 1
- **Strong Sell**: 1
- **Total Analysts**: 34

**Sentiment**: 32.4% Bullish, 5.9% Bearish

### 2026-01-01
- **Strong Buy**: 5
- **Buy**: 6
- **Hold**: 21
- **Sell**: 1
- **Strong Sell**: 1
- **Total Analysts**: 34

**Sentiment**: 32.4% Bullish, 5.9% Bearish


```

---

## 49. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:35.175042
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'EA', 'num_expirations': 3, 'curr_date': '2026-04-16'}`
- **Output Length:** 93 chars

### Output
```
Error retrieving options activity for EA: Too Many Requests. Rate limited. Try after a while.
```

---

## 50. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:35.829763
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'PYPL', 'curr_date': '2026-04-16'}`
- **Output Length:** 1558 chars

### Output
```
# Technical Analysis for PYPL
**Date:** 2026-04-16
**Current Price:** $49.57

## Price Action
- **Daily Change:** +3.34%
- **5-Day Change:** +7.81%

## RSI (14)
- **Value:** 65.4 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 0.554
- **Signal Line:** 0.033
- **Histogram:** 0.522 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $44.36 (+11.7% from price)
- **200 SMA:** $60.49 (-18.1% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $48.31
- **Middle:** $45.42
- **Lower:** $42.54
- **Band Position:** 122%
- **Bandwidth:** 12.7% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $1.54 (3.1% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $47.26 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 85.8
- **%D:** 76.0
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 17.2 (Strengthening ↑)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $46.03 (+7.7% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** -225.4M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $45.19
- **Current vs VWAP:** +9.7%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $49.76
- **Recent Low:** $38.34
- **Next Resistance:** $49.76 (0.0% (High))
- **Next Support:** $47.06 (23.6%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 51. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:35.879166
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'PYPL'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for PYPL: Too Many Requests. Rate limited. Try after a while.
```

---

## 52. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:36.135215
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'PYPL'}`
- **Output Length:** 719 chars

### Output
```
## Analyst Recommendation Trends for PYPL

### 2026-04-01
- **Strong Buy**: 4
- **Buy**: 12
- **Hold**: 30
- **Sell**: 4
- **Strong Sell**: 0
- **Total Analysts**: 50

**Sentiment**: 32.0% Bullish, 8.0% Bearish

### 2026-03-01
- **Strong Buy**: 4
- **Buy**: 11
- **Hold**: 32
- **Sell**: 4
- **Strong Sell**: 0
- **Total Analysts**: 51

**Sentiment**: 29.4% Bullish, 7.8% Bearish

### 2026-02-01
- **Strong Buy**: 5
- **Buy**: 15
- **Hold**: 26
- **Sell**: 4
- **Strong Sell**: 1
- **Total Analysts**: 51

**Sentiment**: 39.2% Bullish, 9.8% Bearish

### 2026-01-01
- **Strong Buy**: 6
- **Buy**: 15
- **Hold**: 25
- **Sell**: 3
- **Strong Sell**: 1
- **Total Analysts**: 50

**Sentiment**: 42.0% Bullish, 8.0% Bearish


```

---

## 53. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:36.158070
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'PYPL', 'num_expirations': 3, 'curr_date': '2026-04-16'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for PYPL: Too Many Requests. Rate limited. Try after a while.
```

---

## 54. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:38.835909
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'COIN', 'curr_date': '2026-04-16'}`
- **Output Length:** 1540 chars

### Output
```
# Technical Analysis for COIN
**Date:** 2026-04-16
**Current Price:** $195.90

## Price Action
- **Daily Change:** +6.23%
- **5-Day Change:** +15.90%

## RSI (14)
- **Value:** 59.2 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** -2.157
- **Signal Line:** -4.092
- **Histogram:** 1.935 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $179.03 (+9.4% from price)
- **200 SMA:** $274.45 (-28.6% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $206.27
- **Middle:** $179.83
- **Lower:** $153.39
- **Band Position:** 80%
- **Bandwidth:** 29.4% (volatility indicator)
- **Signal:** Near upper band

## ATR (Volatility)
- **ATR:** $11.42 (5.8% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $178.78 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 68.1
- **%D:** 50.9
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 11.8 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $180.10 (+8.8% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** -126.8M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $181.21
- **Current vs VWAP:** +8.1%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $213.50
- **Recent Low:** $139.36
- **Next Resistance:** $196.00 (23.6%)
- **Next Support:** $185.18 (38.2%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 55. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:38.887004
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'COIN'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for COIN: Too Many Requests. Rate limited. Try after a while.
```

---

## 56. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:39.171966
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'COIN'}`
- **Output Length:** 723 chars

### Output
```
## Analyst Recommendation Trends for COIN

### 2026-04-01
- **Strong Buy**: 11
- **Buy**: 17
- **Hold**: 13
- **Sell**: 0
- **Strong Sell**: 2
- **Total Analysts**: 43

**Sentiment**: 65.1% Bullish, 4.7% Bearish

### 2026-03-01
- **Strong Buy**: 11
- **Buy**: 18
- **Hold**: 12
- **Sell**: 0
- **Strong Sell**: 2
- **Total Analysts**: 43

**Sentiment**: 67.4% Bullish, 4.7% Bearish

### 2026-02-01
- **Strong Buy**: 11
- **Buy**: 19
- **Hold**: 12
- **Sell**: 0
- **Strong Sell**: 1
- **Total Analysts**: 43

**Sentiment**: 69.8% Bullish, 2.3% Bearish

### 2026-01-01
- **Strong Buy**: 10
- **Buy**: 17
- **Hold**: 14
- **Sell**: 0
- **Strong Sell**: 1
- **Total Analysts**: 42

**Sentiment**: 64.3% Bullish, 2.4% Bearish


```

---

## 57. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:39.195471
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'COIN', 'num_expirations': 3, 'curr_date': '2026-04-16'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for COIN: Too Many Requests. Rate limited. Try after a while.
```

---

## 58. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:39.865512
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'AXP', 'curr_date': '2026-04-16'}`
- **Output Length:** 1545 chars

### Output
```
# Technical Analysis for AXP
**Date:** 2026-04-16
**Current Price:** $329.06

## Price Action
- **Daily Change:** +0.64%
- **5-Day Change:** +3.55%

## RSI (14)
- **Value:** 66.0 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 2.869
- **Signal Line:** -1.589
- **Histogram:** 4.459 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $317.95 (+3.5% from price)
- **200 SMA:** $334.07 (-1.5% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $328.82
- **Middle:** $305.60
- **Lower:** $282.39
- **Band Position:** 101%
- **Bandwidth:** 15.2% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $8.25 (2.5% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $316.69 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 89.3
- **%D:** 84.3
- **Signal:** OVERBOUGHT ⚠️

## ADX (Trend Strength)
- **ADX:** 23.7 (Strengthening ↑)
- **Interpretation:** Trending

## 20 EMA
- **Value:** $311.84 (+5.5% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 25.1M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $303.31
- **Current vs VWAP:** +8.5%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $368.34
- **Recent Low:** $290.05
- **Next Resistance:** $329.19 (50.0%)
- **Next Support:** $319.96 (61.8%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 59. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:39.913372
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'AXP'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for AXP: Too Many Requests. Rate limited. Try after a while.
```

---

## 60. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:40.155225
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'AXP'}`
- **Output Length:** 718 chars

### Output
```
## Analyst Recommendation Trends for AXP

### 2026-04-01
- **Strong Buy**: 5
- **Buy**: 11
- **Hold**: 18
- **Sell**: 0
- **Strong Sell**: 1
- **Total Analysts**: 35

**Sentiment**: 45.7% Bullish, 2.9% Bearish

### 2026-03-01
- **Strong Buy**: 5
- **Buy**: 10
- **Hold**: 19
- **Sell**: 0
- **Strong Sell**: 1
- **Total Analysts**: 35

**Sentiment**: 42.9% Bullish, 2.9% Bearish

### 2026-02-01
- **Strong Buy**: 5
- **Buy**: 10
- **Hold**: 20
- **Sell**: 0
- **Strong Sell**: 1
- **Total Analysts**: 36

**Sentiment**: 41.7% Bullish, 2.8% Bearish

### 2026-01-01
- **Strong Buy**: 4
- **Buy**: 10
- **Hold**: 21
- **Sell**: 0
- **Strong Sell**: 1
- **Total Analysts**: 36

**Sentiment**: 38.9% Bullish, 2.8% Bearish


```

---

## 61. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:40.180648
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'AXP', 'num_expirations': 3, 'curr_date': '2026-04-16'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for AXP: Too Many Requests. Rate limited. Try after a while.
```

---

## 62. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:41.906281
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'COF', 'curr_date': '2026-04-16'}`
- **Output Length:** 1567 chars

### Output
```
# Technical Analysis for COF
**Date:** 2026-04-16
**Current Price:** $202.98

## Price Action
- **Daily Change:** +1.57%
- **5-Day Change:** +4.24%

## RSI (14)
- **Value:** 64.1 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 1.539
- **Signal Line:** -1.642
- **Histogram:** 3.181 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $194.87 (+4.2% from price)
- **200 SMA:** $214.53 (-5.4% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $201.62
- **Middle:** $186.32
- **Lower:** $171.01
- **Band Position:** 104%
- **Bandwidth:** 16.4% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $5.79 (2.9% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $194.29 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 90.4
- **%D:** 81.1
- **Signal:** OVERBOUGHT ⚠️

## ADX (Trend Strength)
- **ADX:** 17.3 (Strengthening ↑)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $190.32 (+6.7% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 92.4M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $185.48
- **Current vs VWAP:** +9.4%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $226.85
- **Recent Low:** $174.98
- **Next Resistance:** $207.04 (38.2%)
- **Next Support:** $200.92 (50.0%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 63. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:41.957717
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'COF'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for COF: Too Many Requests. Rate limited. Try after a while.
```

---

## 64. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:42.215745
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'COF'}`
- **Output Length:** 714 chars

### Output
```
## Analyst Recommendation Trends for COF

### 2026-04-01
- **Strong Buy**: 8
- **Buy**: 14
- **Hold**: 6
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 28

**Sentiment**: 78.6% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 8
- **Buy**: 14
- **Hold**: 6
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 28

**Sentiment**: 78.6% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 8
- **Buy**: 14
- **Hold**: 6
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 28

**Sentiment**: 78.6% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 8
- **Buy**: 14
- **Hold**: 6
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 28

**Sentiment**: 78.6% Bullish, 0.0% Bearish


```

---

## 65. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:42.241110
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'COF', 'num_expirations': 3, 'curr_date': '2026-04-16'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for COF: Too Many Requests. Rate limited. Try after a while.
```

---

## 66. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:48.097795
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'SYF', 'curr_date': '2026-04-16'}`
- **Output Length:** 1564 chars

### Output
```
# Technical Analysis for SYF
**Date:** 2026-04-16
**Current Price:** $75.99

## Price Action
- **Daily Change:** +0.58%
- **5-Day Change:** +4.83%

## RSI (14)
- **Value:** 73.7 ↑
- **Signal:** OVERBOUGHT ⚠️

## MACD
- **MACD Line:** 1.593
- **Signal Line:** 0.488
- **Histogram:** 1.105 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $69.71 (+9.0% from price)
- **200 SMA:** $73.34 (+3.6% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $75.91
- **Middle:** $69.08
- **Lower:** $62.25
- **Band Position:** 101%
- **Bandwidth:** 19.8% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $1.95 (2.6% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $73.07 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 93.5
- **%D:** 90.4
- **Signal:** OVERBOUGHT ⚠️

## ADX (Trend Strength)
- **ADX:** 27.0 (Strengthening ↑)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $70.49 (+7.8% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 63.9M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $68.42
- **Current vs VWAP:** +11.1%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $76.81
- **Recent Low:** $63.08
- **Next Resistance:** $76.81 (0.0% (High))
- **Next Support:** $73.57 (23.6%)

## Summary
- **Key Signals:** RSI overbought, Above 50 SMA

```

---

## 67. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:48.150789
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'SYF'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for SYF: Too Many Requests. Rate limited. Try after a while.
```

---

## 68. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:48.414778
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'SYF'}`
- **Output Length:** 714 chars

### Output
```
## Analyst Recommendation Trends for SYF

### 2026-04-01
- **Strong Buy**: 7
- **Buy**: 13
- **Hold**: 7
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 27

**Sentiment**: 74.1% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 7
- **Buy**: 13
- **Hold**: 7
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 27

**Sentiment**: 74.1% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 6
- **Buy**: 13
- **Hold**: 8
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 27

**Sentiment**: 70.4% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 5
- **Buy**: 13
- **Hold**: 9
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 27

**Sentiment**: 66.7% Bullish, 0.0% Bearish


```

---

## 69. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:49.452002
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'SYF', 'num_expirations': 3, 'curr_date': '2026-04-16'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for SYF: Too Many Requests. Rate limited. Try after a while.
```

---

## 70. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:50.043166
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'NVDA', 'curr_date': '2026-04-16'}`
- **Output Length:** 1585 chars

### Output
```
# Technical Analysis for NVDA
**Date:** 2026-04-16
**Current Price:** $198.87

## Price Action
- **Daily Change:** +1.20%
- **5-Day Change:** +8.13%

## RSI (14)
- **Value:** 69.8 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 3.135
- **Signal Line:** 0.220
- **Histogram:** 2.916 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $182.38 (+9.0% from price)
- **200 SMA:** $181.31 (+9.7% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $196.67
- **Middle:** $179.38
- **Lower:** $162.10
- **Band Position:** 106%
- **Bandwidth:** 19.3% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $5.36 (2.7% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $190.82 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 93.4
- **%D:** 86.5
- **Signal:** OVERBOUGHT ⚠️

## ADX (Trend Strength)
- **ADX:** 19.3 (Strengthening ↑)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $183.33 (+8.5% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 2758.0M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $178.65
- **Current vs VWAP:** +11.3%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $200.40
- **Recent Low:** $164.27
- **Next Resistance:** $200.40 (0.0% (High))
- **Next Support:** $191.87 (23.6%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 71. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:50.092131
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'NVDA'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for NVDA: Too Many Requests. Rate limited. Try after a while.
```

---

## 72. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:50.355611
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'NVDA'}`
- **Output Length:** 719 chars

### Output
```
## Analyst Recommendation Trends for NVDA

### 2026-04-01
- **Strong Buy**: 24
- **Buy**: 42
- **Hold**: 4
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 71

**Sentiment**: 93.0% Bullish, 1.4% Bearish

### 2026-03-01
- **Strong Buy**: 25
- **Buy**: 42
- **Hold**: 5
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 73

**Sentiment**: 91.8% Bullish, 1.4% Bearish

### 2026-02-01
- **Strong Buy**: 25
- **Buy**: 40
- **Hold**: 6
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 72

**Sentiment**: 90.3% Bullish, 1.4% Bearish

### 2026-01-01
- **Strong Buy**: 25
- **Buy**: 39
- **Hold**: 7
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 72

**Sentiment**: 88.9% Bullish, 1.4% Bearish


```

---

## 73. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:50.377502
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'NVDA', 'num_expirations': 3, 'curr_date': '2026-04-16'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for NVDA: Too Many Requests. Rate limited. Try after a while.
```

---

## 74. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:51.935844
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'TSLA', 'curr_date': '2026-04-16'}`
- **Output Length:** 1552 chars

### Output
```
# Technical Analysis for TSLA
**Date:** 2026-04-16
**Current Price:** $391.95

## Price Action
- **Daily Change:** +7.62%
- **5-Day Change:** +13.40%

## RSI (14)
- **Value:** 57.6 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** -8.910
- **Signal Line:** -12.089
- **Histogram:** 3.179 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $391.10 (+0.2% from price)
- **200 SMA:** $398.01 (-1.5% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $399.14
- **Middle:** $366.98
- **Lower:** $334.82
- **Band Position:** 89%
- **Bandwidth:** 17.5% (volatility indicator)
- **Signal:** Near upper band

## ATR (Volatility)
- **ATR:** $15.60 (4.0% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $368.55 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 56.0
- **%D:** 37.1
- **Signal:** Bullish crossover ⚡

## ADX (Trend Strength)
- **ADX:** 18.6 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $368.91 (+6.2% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 961.7M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $367.31
- **Current vs VWAP:** +6.7%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $436.35
- **Recent Low:** $337.24
- **Next Resistance:** $398.49 (38.2%)
- **Next Support:** $386.79 (50.0%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 75. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:51.986604
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'TSLA'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for TSLA: Too Many Requests. Rate limited. Try after a while.
```

---

## 76. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:52.254631
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'TSLA'}`
- **Output Length:** 723 chars

### Output
```
## Analyst Recommendation Trends for TSLA

### 2026-04-01
- **Strong Buy**: 9
- **Buy**: 20
- **Hold**: 21
- **Sell**: 8
- **Strong Sell**: 2
- **Total Analysts**: 60

**Sentiment**: 48.3% Bullish, 16.7% Bearish

### 2026-03-01
- **Strong Buy**: 8
- **Buy**: 20
- **Hold**: 21
- **Sell**: 8
- **Strong Sell**: 2
- **Total Analysts**: 59

**Sentiment**: 47.5% Bullish, 16.9% Bearish

### 2026-02-01
- **Strong Buy**: 8
- **Buy**: 19
- **Hold**: 21
- **Sell**: 8
- **Strong Sell**: 2
- **Total Analysts**: 58

**Sentiment**: 46.6% Bullish, 17.2% Bearish

### 2026-01-01
- **Strong Buy**: 7
- **Buy**: 20
- **Hold**: 21
- **Sell**: 9
- **Strong Sell**: 2
- **Total Analysts**: 59

**Sentiment**: 45.8% Bullish, 18.6% Bearish


```

---

## 77. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:52.287243
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'TSLA', 'num_expirations': 3, 'curr_date': '2026-04-16'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for TSLA: Too Many Requests. Rate limited. Try after a while.
```

---

## 78. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:52.897119
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'PLTR', 'curr_date': '2026-04-16'}`
- **Output Length:** 1544 chars

### Output
```
# Technical Analysis for PLTR
**Date:** 2026-04-16
**Current Price:** $142.15

## Price Action
- **Daily Change:** +4.75%
- **5-Day Change:** +8.94%

## RSI (14)
- **Value:** 48.4 ↑
- **Signal:** Bearish

## MACD
- **MACD Line:** -3.587
- **Signal Line:** -2.488
- **Histogram:** -1.098 (Weakening ↓)
- **Signal:** Bearish

## Moving Averages
- **50 SMA:** $143.61 (-1.0% from price)
- **200 SMA:** $164.12 (-13.4% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $163.31
- **Middle:** $145.33
- **Lower:** $127.35
- **Band Position:** 41%
- **Bandwidth:** 24.7% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $7.68 (5.4% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $130.63 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 39.2
- **%D:** 32.5
- **Signal:** Bullish crossover ⚡

## ADX (Trend Strength)
- **ADX:** 17.8 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $142.65 (-0.3% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** 337.0M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $143.06
- **Current vs VWAP:** -0.6%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $165.08
- **Recent Low:** $122.68
- **Next Resistance:** $143.88 (50.0%)
- **Next Support:** $138.88 (61.8%)

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 79. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:52.945264
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'PLTR'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for PLTR: Too Many Requests. Rate limited. Try after a while.
```

---

## 80. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:53.211679
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'PLTR'}`
- **Output Length:** 717 chars

### Output
```
## Analyst Recommendation Trends for PLTR

### 2026-04-01
- **Strong Buy**: 9
- **Buy**: 15
- **Hold**: 10
- **Sell**: 1
- **Strong Sell**: 1
- **Total Analysts**: 36

**Sentiment**: 66.7% Bullish, 5.6% Bearish

### 2026-03-01
- **Strong Buy**: 8
- **Buy**: 14
- **Hold**: 10
- **Sell**: 1
- **Strong Sell**: 1
- **Total Analysts**: 34

**Sentiment**: 64.7% Bullish, 5.9% Bearish

### 2026-02-01
- **Strong Buy**: 5
- **Buy**: 8
- **Hold**: 17
- **Sell**: 2
- **Strong Sell**: 1
- **Total Analysts**: 33

**Sentiment**: 39.4% Bullish, 9.1% Bearish

### 2026-01-01
- **Strong Buy**: 4
- **Buy**: 7
- **Hold**: 18
- **Sell**: 2
- **Strong Sell**: 1
- **Total Analysts**: 32

**Sentiment**: 34.4% Bullish, 9.4% Bearish


```

---

## 81. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:53.235751
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'PLTR', 'num_expirations': 3, 'curr_date': '2026-04-16'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for PLTR: Too Many Requests. Rate limited. Try after a while.
```

---

## 82. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:54.428339
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'SNDK', 'curr_date': '2026-04-16'}`
- **Output Length:** 1530 chars

### Output
```
# Technical Analysis for SNDK
**Date:** 2026-04-16
**Current Price:** $891.72

## Price Action
- **Daily Change:** -5.58%
- **5-Day Change:** +4.71%

## RSI (14)
- **Value:** 65.7 ↓
- **Signal:** Bullish

## MACD
- **MACD Line:** 71.698
- **Signal Line:** 48.456
- **Histogram:** 23.241 (Weakening ↓)
- **Signal:** Bullish

## Moving Averages
- **50 SMA:** $668.27 (+33.4% from price)
- **200 SMA:** $295.81 (+201.5% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $959.18
- **Middle:** $742.39
- **Lower:** $525.60
- **Band Position:** 84%
- **Bandwidth:** 58.4% (volatility indicator)
- **Signal:** Near upper band

## ATR (Volatility)
- **ATR:** $62.88 (7.1% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $797.40 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 87.3
- **%D:** 85.6
- **Signal:** OVERBOUGHT ⚠️

## ADX (Trend Strength)
- **ADX:** 35.7 (Strengthening ↑)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $765.79 (+16.4% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 427.9M
- **5-Day Trend:** Falling ↓
- **Signal:** BEARISH DIVERGENCE ⚠️ (distribution)

## VWAP (20-period)
- **VWAP:** $736.13
- **Current vs VWAP:** +21.1%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $965.00
- **Recent Low:** $517.00
- **Next Resistance:** $965.00 (0.0% (High))
- **Next Support:** $859.27 (23.6%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 83. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:54.478892
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'SNDK'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for SNDK: Too Many Requests. Rate limited. Try after a while.
```

---

## 84. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:54.746059
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'SNDK'}`
- **Output Length:** 715 chars

### Output
```
## Analyst Recommendation Trends for SNDK

### 2026-04-01
- **Strong Buy**: 8
- **Buy**: 13
- **Hold**: 5
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 26

**Sentiment**: 80.8% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 6
- **Buy**: 13
- **Hold**: 6
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 25

**Sentiment**: 76.0% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 7
- **Buy**: 13
- **Hold**: 8
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 28

**Sentiment**: 71.4% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 7
- **Buy**: 12
- **Hold**: 7
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 26

**Sentiment**: 73.1% Bullish, 0.0% Bearish


```

---

## 85. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:54.770425
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'SNDK', 'num_expirations': 3, 'curr_date': '2026-04-16'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for SNDK: Too Many Requests. Rate limited. Try after a while.
```

---

## 86. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:55.364099
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'AMD', 'curr_date': '2026-04-16'}`
- **Output Length:** 1591 chars

### Output
```
# Technical Analysis for AMD
**Date:** 2026-04-16
**Current Price:** $258.12

## Price Action
- **Daily Change:** +1.20%
- **5-Day Change:** +9.08%

## RSI (14)
- **Value:** 74.8 ↑
- **Signal:** OVERBOUGHT ⚠️

## MACD
- **MACD Line:** 12.151
- **Signal Line:** 6.814
- **Histogram:** 5.337 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $209.85 (+23.0% from price)
- **200 SMA:** $201.06 (+28.4% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $258.79
- **Middle:** $219.13
- **Lower:** $179.46
- **Band Position:** 99%
- **Bandwidth:** 36.2% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $9.61 (3.7% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $243.70 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 95.6
- **%D:** 89.4
- **Signal:** OVERBOUGHT ⚠️

## ADX (Trend Strength)
- **ADX:** 41.7 (Strengthening ↑)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $225.65 (+14.4% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 1188.8M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $216.48
- **Current vs VWAP:** +19.2%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $258.18
- **Recent Low:** $188.22
- **Next Resistance:** $258.18 (0.0% (High))
- **Next Support:** $241.67 (23.6%)

## Summary
- **Key Signals:** RSI overbought, Above 50 SMA

```

---

## 87. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:55.410657
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'AMD'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for AMD: Too Many Requests. Rate limited. Try after a while.
```

---

## 88. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:55.679570
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'AMD'}`
- **Output Length:** 722 chars

### Output
```
## Analyst Recommendation Trends for AMD

### 2026-04-01
- **Strong Buy**: 15
- **Buy**: 30
- **Hold**: 13
- **Sell**: 0
- **Strong Sell**: 1
- **Total Analysts**: 59

**Sentiment**: 76.3% Bullish, 1.7% Bearish

### 2026-03-01
- **Strong Buy**: 15
- **Buy**: 32
- **Hold**: 13
- **Sell**: 0
- **Strong Sell**: 1
- **Total Analysts**: 61

**Sentiment**: 77.0% Bullish, 1.6% Bearish

### 2026-02-01
- **Strong Buy**: 15
- **Buy**: 31
- **Hold**: 13
- **Sell**: 0
- **Strong Sell**: 1
- **Total Analysts**: 60

**Sentiment**: 76.7% Bullish, 1.7% Bearish

### 2026-01-01
- **Strong Buy**: 15
- **Buy**: 29
- **Hold**: 13
- **Sell**: 0
- **Strong Sell**: 1
- **Total Analysts**: 58

**Sentiment**: 75.9% Bullish, 1.7% Bearish


```

---

## 89. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:56.763450
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'AMD', 'num_expirations': 3, 'curr_date': '2026-04-16'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for AMD: Too Many Requests. Rate limited. Try after a while.
```

---

## 90. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:57.401193
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'INTC', 'curr_date': '2026-04-16'}`
- **Output Length:** 1547 chars

### Output
```
# Technical Analysis for INTC
**Date:** 2026-04-16
**Current Price:** $64.94

## Price Action
- **Daily Change:** +1.77%
- **5-Day Change:** +5.22%

## RSI (14)
- **Value:** 75.1 ↑
- **Signal:** OVERBOUGHT ⚠️

## MACD
- **MACD Line:** 4.953
- **Signal Line:** 3.005
- **Histogram:** 1.947 (Weakening ↓)
- **Signal:** Bullish

## Moving Averages
- **50 SMA:** $48.21 (+34.7% from price)
- **200 SMA:** $36.82 (+76.4% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $67.98
- **Middle:** $51.10
- **Lower:** $34.21
- **Band Position:** 91%
- **Bandwidth:** 66.1% (volatility indicator)
- **Signal:** Near upper band

## ATR (Volatility)
- **ATR:** $3.10 (4.8% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $60.29 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 93.9
- **%D:** 90.3
- **Signal:** OVERBOUGHT ⚠️

## ADX (Trend Strength)
- **ADX:** 55.8 (Strengthening ↑)
- **Interpretation:** VERY STRONG TREND ⚡

## 20 EMA
- **Value:** $54.10 (+20.0% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 3317.6M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $51.79
- **Current vs VWAP:** +25.4%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $65.84
- **Recent Low:** $40.63
- **Next Resistance:** $65.84 (0.0% (High))
- **Next Support:** $59.89 (23.6%)

## Summary
- **Key Signals:** RSI overbought, Above 50 SMA

```

---

## 91. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:57.734348
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'INTC'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for INTC: Too Many Requests. Rate limited. Try after a while.
```

---

## 92. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:57.993716
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'INTC'}`
- **Output Length:** 716 chars

### Output
```
## Analyst Recommendation Trends for INTC

### 2026-04-01
- **Strong Buy**: 4
- **Buy**: 9
- **Hold**: 35
- **Sell**: 3
- **Strong Sell**: 1
- **Total Analysts**: 52

**Sentiment**: 25.0% Bullish, 7.7% Bearish

### 2026-03-01
- **Strong Buy**: 4
- **Buy**: 9
- **Hold**: 36
- **Sell**: 3
- **Strong Sell**: 1
- **Total Analysts**: 53

**Sentiment**: 24.5% Bullish, 7.5% Bearish

### 2026-02-01
- **Strong Buy**: 4
- **Buy**: 9
- **Hold**: 34
- **Sell**: 4
- **Strong Sell**: 1
- **Total Analysts**: 52

**Sentiment**: 25.0% Bullish, 9.6% Bearish

### 2026-01-01
- **Strong Buy**: 2
- **Buy**: 4
- **Hold**: 34
- **Sell**: 6
- **Strong Sell**: 4
- **Total Analysts**: 50

**Sentiment**: 12.0% Bullish, 20.0% Bearish


```

---

## 93. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:11:58.113058
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'INTC', 'num_expirations': 3, 'curr_date': '2026-04-16'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for INTC: Too Many Requests. Rate limited. Try after a while.
```

---

## 94. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:12:00.163324
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'ABT', 'curr_date': '2026-04-16'}`
- **Output Length:** 1524 chars

### Output
```
# Technical Analysis for ABT
**Date:** 2026-04-16
**Current Price:** $101.56

## Price Action
- **Daily Change:** +0.50%
- **5-Day Change:** -1.13%

## RSI (14)
- **Value:** 37.3 ↑
- **Signal:** Bearish

## MACD
- **MACD Line:** -2.305
- **Signal Line:** -2.406
- **Histogram:** 0.101 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $108.49 (-6.4% from price)
- **200 SMA:** $122.29 (-17.0% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $107.59
- **Middle:** $103.36
- **Lower:** $99.13
- **Band Position:** 29%
- **Bandwidth:** 8.2% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $2.17 (2.1% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $98.30 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 40.5
- **%D:** 34.2
- **Signal:** Bearish

## ADX (Trend Strength)
- **ADX:** 40.9 (Weakening ↓)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $103.68 (-2.0% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** -185.5M
- **5-Day Trend:** Rising ↑
- **Signal:** BULLISH DIVERGENCE ⚡ (accumulation)

## VWAP (20-period)
- **VWAP:** $104.13
- **Current vs VWAP:** -2.5%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $116.82
- **Recent Low:** $99.05
- **Next Resistance:** $102.85 (78.6%)
- **Next Support:** $99.05 (100% (Low))

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 95. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:12:00.216051
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'ABT'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for ABT: Too Many Requests. Rate limited. Try after a while.
```

---

## 96. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:12:00.520396
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'ABT'}`
- **Output Length:** 721 chars

### Output
```
## Analyst Recommendation Trends for ABT

### 2026-04-01
- **Strong Buy**: 10
- **Buy**: 16
- **Hold**: 9
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 35

**Sentiment**: 74.3% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 10
- **Buy**: 15
- **Hold**: 10
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 35

**Sentiment**: 71.4% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 10
- **Buy**: 15
- **Hold**: 10
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 35

**Sentiment**: 71.4% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 10
- **Buy**: 14
- **Hold**: 11
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 35

**Sentiment**: 68.6% Bullish, 0.0% Bearish


```

---

## 97. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:12:00.545913
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'ABT', 'num_expirations': 3, 'curr_date': '2026-04-16'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for ABT: Too Many Requests. Rate limited. Try after a while.
```

---

## 98. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:12:01.808175
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'UBER', 'curr_date': '2026-04-16'}`
- **Output Length:** 1560 chars

### Output
```
# Technical Analysis for UBER
**Date:** 2026-04-16
**Current Price:** $77.28

## Price Action
- **Daily Change:** +5.99%
- **5-Day Change:** +7.62%

## RSI (14)
- **Value:** 61.7 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** -0.238
- **Signal Line:** -0.755
- **Histogram:** 0.517 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $73.38 (+5.3% from price)
- **200 SMA:** $86.31 (-10.5% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $76.87
- **Middle:** $72.63
- **Lower:** $68.39
- **Band Position:** 105%
- **Bandwidth:** 11.7% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $2.57 (3.3% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $73.43 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 62.0
- **%D:** 50.4
- **Signal:** Bullish crossover ⚡

## ADX (Trend Strength)
- **ADX:** 11.2 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $72.92 (+6.0% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** -79.1M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $72.80
- **Current vs VWAP:** +6.2%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $80.68
- **Recent Low:** $68.46
- **Next Resistance:** $77.80 (23.6%)
- **Next Support:** $76.01 (38.2%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 99. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:12:01.860386
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'UBER'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for UBER: Too Many Requests. Rate limited. Try after a while.
```

---

## 100. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:12:02.119426
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'UBER'}`
- **Output Length:** 720 chars

### Output
```
## Analyst Recommendation Trends for UBER

### 2026-04-01
- **Strong Buy**: 16
- **Buy**: 35
- **Hold**: 9
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 61

**Sentiment**: 83.6% Bullish, 1.6% Bearish

### 2026-03-01
- **Strong Buy**: 16
- **Buy**: 35
- **Hold**: 9
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 61

**Sentiment**: 83.6% Bullish, 1.6% Bearish

### 2026-02-01
- **Strong Buy**: 16
- **Buy**: 35
- **Hold**: 9
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 61

**Sentiment**: 83.6% Bullish, 1.6% Bearish

### 2026-01-01
- **Strong Buy**: 16
- **Buy**: 33
- **Hold**: 11
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 60

**Sentiment**: 81.7% Bullish, 0.0% Bearish


```

---

## 101. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:12:02.144667
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'UBER', 'num_expirations': 3, 'curr_date': '2026-04-16'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for UBER: Too Many Requests. Rate limited. Try after a while.
```

---

## 102. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:12:03.890166
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'WMT', 'curr_date': '2026-04-16'}`
- **Output Length:** 1525 chars

### Output
```
# Technical Analysis for WMT
**Date:** 2026-04-16
**Current Price:** $124.76

## Price Action
- **Daily Change:** -0.23%
- **5-Day Change:** -3.38%

## RSI (14)
- **Value:** 50.3 ↓
- **Signal:** Bullish

## MACD
- **MACD Line:** 0.495
- **Signal Line:** 0.391
- **Histogram:** 0.103 (Weakening ↓)
- **Signal:** Bullish

## Moving Averages
- **50 SMA:** $125.51 (-0.6% from price)
- **200 SMA:** $110.08 (+13.3% from price)
- **Trend:** Downtrend

## Bollinger Bands (20,2)
- **Upper:** $128.92
- **Middle:** $123.88
- **Lower:** $118.85
- **Band Position:** 59%
- **Bandwidth:** 8.1% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $2.84 (2.3% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $120.49 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 51.8
- **%D:** 61.7
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 11.3 (Strengthening ↑)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $124.85 (-0.1% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** 459.8M
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $123.14
- **Current vs VWAP:** +1.3%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $134.41
- **Recent Low:** $118.02
- **Next Resistance:** $126.22 (50.0%)
- **Next Support:** $124.28 (61.8%)

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 103. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:12:03.941122
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'WMT'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for WMT: Too Many Requests. Rate limited. Try after a while.
```

---

## 104. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:12:04.189923
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'WMT'}`
- **Output Length:** 718 chars

### Output
```
## Analyst Recommendation Trends for WMT

### 2026-04-01
- **Strong Buy**: 14
- **Buy**: 30
- **Hold**: 4
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 48

**Sentiment**: 91.7% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 14
- **Buy**: 31
- **Hold**: 4
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 49

**Sentiment**: 91.8% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 14
- **Buy**: 32
- **Hold**: 3
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 49

**Sentiment**: 93.9% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 15
- **Buy**: 31
- **Hold**: 2
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 48

**Sentiment**: 95.8% Bullish, 0.0% Bearish


```

---

## 105. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:12:04.213706
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'WMT', 'num_expirations': 3, 'curr_date': '2026-04-16'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for WMT: Too Many Requests. Rate limited. Try after a while.
```

---

## 106. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:12:04.925306
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'BAC', 'curr_date': '2026-04-16'}`
- **Output Length:** 1581 chars

### Output
```
# Technical Analysis for BAC
**Date:** 2026-04-16
**Current Price:** $54.32

## Price Action
- **Daily Change:** +1.82%
- **5-Day Change:** +3.05%

## RSI (14)
- **Value:** 73.5 ↑
- **Signal:** OVERBOUGHT ⚠️

## MACD
- **MACD Line:** 1.091
- **Signal Line:** 0.377
- **Histogram:** 0.714 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $50.56 (+7.4% from price)
- **200 SMA:** $50.63 (+7.3% from price)
- **Trend:** Uptrend (DEATH CROSS ⚠️)

## Bollinger Bands (20,2)
- **Upper:** $54.65
- **Middle:** $49.69
- **Lower:** $44.72
- **Band Position:** 97%
- **Bandwidth:** 20.0% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $1.28 (2.4% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $52.39 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 91.6
- **%D:** 91.0
- **Signal:** OVERBOUGHT ⚠️

## ADX (Trend Strength)
- **ADX:** 30.9 (Strengthening ↑)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $50.77 (+7.0% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 1051.5M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $49.45
- **Current vs VWAP:** +9.9%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $56.55
- **Recent Low:** $46.12
- **Next Resistance:** $56.55 (0.0% (High))
- **Next Support:** $54.09 (23.6%)

## Summary
- **Key Signals:** RSI overbought, Above 50 SMA

```

---

## 107. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:12:04.975111
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'BAC'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for BAC: Too Many Requests. Rate limited. Try after a while.
```

---

## 108. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:12:05.234990
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'BAC'}`
- **Output Length:** 714 chars

### Output
```
## Analyst Recommendation Trends for BAC

### 2026-04-01
- **Strong Buy**: 6
- **Buy**: 20
- **Hold**: 5
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 31

**Sentiment**: 83.9% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 5
- **Buy**: 19
- **Hold**: 6
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 30

**Sentiment**: 80.0% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 5
- **Buy**: 19
- **Hold**: 6
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 30

**Sentiment**: 80.0% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 6
- **Buy**: 18
- **Hold**: 5
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 29

**Sentiment**: 82.8% Bullish, 0.0% Bearish


```

---

## 109. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:12:05.259018
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'BAC', 'num_expirations': 3, 'curr_date': '2026-04-16'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for BAC: Too Many Requests. Rate limited. Try after a while.
```

---

## 110. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:12:07.746666
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'JPM', 'curr_date': '2026-04-16'}`
- **Output Length:** 1529 chars

### Output
```
# Technical Analysis for JPM
**Date:** 2026-04-16
**Current Price:** $305.93

## Price Action
- **Daily Change:** -1.67%
- **5-Day Change:** -1.42%

## RSI (14)
- **Value:** 58.3 ↓
- **Signal:** Bullish

## MACD
- **MACD Line:** 4.330
- **Signal Line:** 1.906
- **Histogram:** 2.424 (Weakening ↓)
- **Signal:** Bullish

## Moving Averages
- **50 SMA:** $298.33 (+2.5% from price)
- **200 SMA:** $300.59 (+1.8% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $316.50
- **Middle:** $295.82
- **Lower:** $275.14
- **Band Position:** 74%
- **Bandwidth:** 14.0% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $7.15 (2.3% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $295.20 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 84.2
- **%D:** 86.7
- **Signal:** OVERBOUGHT ⚠️

## ADX (Trend Strength)
- **ADX:** 19.9 (Strengthening ↑)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $299.71 (+2.1% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 105.1M
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $294.25
- **Current vs VWAP:** +4.0%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $324.74
- **Recent Low:** $277.68
- **Next Resistance:** $306.76 (38.2%)
- **Next Support:** $301.21 (50.0%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 111. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:12:07.794923
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'JPM'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for JPM: Too Many Requests. Rate limited. Try after a while.
```

---

## 112. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:12:08.037741
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'JPM'}`
- **Output Length:** 717 chars

### Output
```
## Analyst Recommendation Trends for JPM

### 2026-04-01
- **Strong Buy**: 3
- **Buy**: 16
- **Hold**: 13
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 32

**Sentiment**: 59.4% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 3
- **Buy**: 16
- **Hold**: 12
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 31

**Sentiment**: 61.3% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 3
- **Buy**: 16
- **Hold**: 10
- **Sell**: 1
- **Strong Sell**: 1
- **Total Analysts**: 31

**Sentiment**: 61.3% Bullish, 6.5% Bearish

### 2026-01-01
- **Strong Buy**: 4
- **Buy**: 15
- **Hold**: 9
- **Sell**: 1
- **Strong Sell**: 1
- **Total Analysts**: 30

**Sentiment**: 63.3% Bullish, 6.7% Bearish


```

---

## 113. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:12:08.062057
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'JPM', 'num_expirations': 3, 'curr_date': '2026-04-16'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for JPM: Too Many Requests. Rate limited. Try after a while.
```

---

## 114. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:12:10.824866
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'NFLX', 'curr_date': '2026-04-16'}`
- **Output Length:** 1582 chars

### Output
```
# Technical Analysis for NFLX
**Date:** 2026-04-16
**Current Price:** $107.71

## Price Action
- **Daily Change:** +1.35%
- **5-Day Change:** +5.55%

## RSI (14)
- **Value:** 79.0 ↑
- **Signal:** OVERBOUGHT ⚠️

## MACD
- **MACD Line:** 3.681
- **Signal Line:** 2.727
- **Histogram:** 0.954 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $91.05 (+18.3% from price)
- **200 SMA:** $106.17 (+1.5% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $107.40
- **Middle:** $97.21
- **Lower:** $87.03
- **Band Position:** 102%
- **Bandwidth:** 20.9% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $2.80 (2.6% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $103.50 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 94.2
- **%D:** 87.5
- **Signal:** OVERBOUGHT ⚠️

## ADX (Trend Strength)
- **ADX:** 54.8 (Strengthening ↑)
- **Interpretation:** VERY STRONG TREND ⚡

## 20 EMA
- **Value:** $98.85 (+9.0% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** -553.5M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $96.65
- **Current vs VWAP:** +11.4%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $107.85
- **Recent Low:** $75.01
- **Next Resistance:** $107.85 (0.0% (High))
- **Next Support:** $100.10 (23.6%)

## Summary
- **Key Signals:** RSI overbought, Above 50 SMA

```

---

## 115. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:12:10.871767
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'NFLX'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for NFLX: Too Many Requests. Rate limited. Try after a while.
```

---

## 116. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:12:11.131380
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'NFLX'}`
- **Output Length:** 723 chars

### Output
```
## Analyst Recommendation Trends for NFLX

### 2026-04-01
- **Strong Buy**: 16
- **Buy**: 29
- **Hold**: 14
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 59

**Sentiment**: 76.3% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 15
- **Buy**: 26
- **Hold**: 13
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 54

**Sentiment**: 75.9% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 14
- **Buy**: 23
- **Hold**: 14
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 52

**Sentiment**: 71.2% Bullish, 1.9% Bearish

### 2026-01-01
- **Strong Buy**: 14
- **Buy**: 23
- **Hold**: 13
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 51

**Sentiment**: 72.5% Bullish, 2.0% Bearish


```

---

## 117. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:12:12.182572
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'NFLX', 'num_expirations': 3, 'curr_date': '2026-04-16'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for NFLX: Too Many Requests. Rate limited. Try after a while.
```

---

## 118. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:12:13.907082
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'AVGO', 'curr_date': '2026-04-16'}`
- **Output Length:** 1585 chars

### Output
```
# Technical Analysis for AVGO
**Date:** 2026-04-16
**Current Price:** $396.72

## Price Action
- **Daily Change:** +4.19%
- **5-Day Change:** +11.78%

## RSI (14)
- **Value:** 77.0 ↑
- **Signal:** OVERBOUGHT ⚠️

## MACD
- **MACD Line:** 14.866
- **Signal Line:** 5.680
- **Histogram:** 9.186 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $329.44 (+20.4% from price)
- **200 SMA:** $330.73 (+20.0% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $391.40
- **Middle:** $331.39
- **Lower:** $271.37
- **Band Position:** 104%
- **Bandwidth:** 36.2% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $13.01 (3.3% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $377.21 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 95.5
- **%D:** 88.3
- **Signal:** OVERBOUGHT ⚠️

## ADX (Trend Strength)
- **ADX:** 35.0 (Strengthening ↑)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $343.70 (+15.4% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 467.8M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $332.06
- **Current vs VWAP:** +19.5%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $397.08
- **Recent Low:** $289.96
- **Next Resistance:** $397.08 (0.0% (High))
- **Next Support:** $371.80 (23.6%)

## Summary
- **Key Signals:** RSI overbought, Above 50 SMA

```

---

## 119. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:12:13.957984
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'AVGO'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for AVGO: Too Many Requests. Rate limited. Try after a while.
```

---

## 120. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:12:14.199314
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'AVGO'}`
- **Output Length:** 719 chars

### Output
```
## Analyst Recommendation Trends for AVGO

### 2026-04-01
- **Strong Buy**: 17
- **Buy**: 37
- **Hold**: 3
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 57

**Sentiment**: 94.7% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 17
- **Buy**: 38
- **Hold**: 3
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 58

**Sentiment**: 94.8% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 17
- **Buy**: 37
- **Hold**: 2
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 56

**Sentiment**: 96.4% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 17
- **Buy**: 36
- **Hold**: 3
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 56

**Sentiment**: 94.6% Bullish, 0.0% Bearish


```

---

## 121. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-16T03:12:14.226621
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'AVGO', 'num_expirations': 3, 'curr_date': '2026-04-16'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for AVGO: Too Many Requests. Rate limited. Try after a while.
```

---

## 122. Rank candidates

- **Type:** `llm`
- **Node:** ranker
- **Timestamp:** 2026-04-16T03:13:06.426531
- **Model:** `gemini-3-pro-preview`
- **Prompt Length:** 108633 chars
- **Output Length:** 2000 chars

### Prompt
```
You are a professional stock analyst selecting the best short-term trading opportunities from a pre-filtered candidate list.

CURRENT DATE: 2026-04-16

GOAL: Select UP TO 15 stocks with the highest probability of generating >5.0% returns within 1-7 days. If fewer than 15 candidates meet the quality bar, return only the ones that do. Quality over quantity — never pad the list with weak picks.

MINIMUM QUALITY BAR:
- Only include candidates where you have genuine conviction (final_score >= 65).
- If a candidate lacks a clear catalyst or has contradictory signals, SKIP it.
- It is better to return 5 excellent picks than 15 mediocre ones.

STRATEGY-SPECIFIC EVALUATION CRITERIA:
Each candidate was discovered by a specific scanner. Evaluate them using the criteria most relevant to their strategy:
- **insider_buying**: Focus on insider transaction SIZE relative to market cap, insider ROLE (CEO/CFO > Director), number of distinct insiders buying, and whether the stock is near support. Large cluster buys are strongest.
- **options_flow**: Focus on put/call ratio, absolute call VOLUME vs open interest, premium size, and whether flow aligns with the technical trend. Unusually low P/C ratios (<0.1) with high volume are strongest.
- **momentum / technical_breakout**: Focus on volume confirmation (>2x average), trend alignment (above key SMAs), and whether momentum is accelerating or fading. Avoid chasing extended moves (RSI >80).
- **earnings_play**: Focus on short interest (squeeze potential), pre-earnings accumulation signals, analyst estimate trends, and historical earnings surprise rate. Binary risk must be acknowledged.
- **social_dd**: Has shown 55% 30d win rate — strongest long-hold scanner. These setups combine social sentiment WITH technical confirmation (OBV, short interest, MACD). Score based on quality of technical/fundamental corroboration. A strong OBV + high short interest + bullish MACD warrants 65-75. DO NOT conflate with social_hype.
- **social_hype**: Treat as SPECULATIVE (14.3% 7d win rate, -4.84% avg 7d return). Require strong corroborating evidence. Pure social sentiment without data backing should score below 50.
- **short_squeeze**: Focus on short interest %, days to cover, cost to borrow, and whether a catalyst exists to trigger covering. High SI alone is not enough.
- **contrarian_value**: Focus on oversold technicals (RSI <30), fundamental support (earnings stability), and a clear reason why the selloff is overdone.
- **news_catalyst**: **AVOID by default** — 0% historical 7d win rate (-8.37% avg 7d return, n=8). Only score ≥55 if the catalyst is (1) not yet reflected in the intraday move, (2) mechanistic and specific (FDA decision, contract win, regulatory approval), NOT macroeconomic framing ('geopolitical tension', 'oil price', 'rate expectations'). Macro news_catalyst setups should score <50.
- **sector_rotation**: Focus on relative strength vs sector ETF, whether the stock is a laggard in an accelerating sector.
- **minervini**: Focus on the RS Rating (top 30% = RS>=70, top 10% = RS>=90) as the primary signal. Verify all 6 trend template conditions are met (price structure above rising SMAs). Strongest setups combine RS>=85 with price consolidating near highs (within 10-15% of 52w high) — these have minimal overhead supply. Penalize if RS Rating is borderline (70-75) without other confirming signals.
- **ml_signal**: Use the ML Win Probability as a strong quantitative signal. Scores above 65% deserve significant weight.

HISTORICAL INSIGHTS:
"Historical 1-day win rate: 39.2% (607 tracked)\nHistorical 7-day win rate: 44.4% (603 tracked)\nHistorical 30-day win rate: 36.7% (507 tracked)\n\nBest performing strategies (7-day):\n  - short_squeeze: 60.0% win rate, avg +2.1% return (10 samples)\n  - analyst_upgrade: 55.9% win rate, avg +0.2% return (34 samples)\n  - insider_buying: 47.7% win rate, avg -0.1% return (176 samples)\n\nWORST performing strategies (7-day) \u2014 penalize these heavily in scoring:\n  - pre_earnings_accumulation: 28.6% win rate, avg -1.9% return (7 samples)\n  - social_hype: 18.2% win rate, avg -4.1% return (22 samples)\n  - news_catalyst: 0.0% win rate, avg -9.1% return (8 samples)"

CANDIDATES FOR REVIEW:
### RVMD (Priority: LOW)
- **Strategy Match**: high_52w_breakout
- **Sources**: high_52w_breakout, technical_breakout | **Confluence**: 2 source(s)
- **Quant Pre-Score**: 20/100 | **ML Win Probability**: N/A | **Altman Z-Score**: None | **Piotroski F-Score**: None
- **Price**: $147.01 | **Current Price (numeric)**: 147.00999450683594 | **Intraday**: +7.9% | **Avg Volume**: None
- **Short Interest**: N/A
- **Discovery Context**: New 52-week high: closed at $147.01 (+7.5% above prior 52w high of $136.80) on 3.2x avg volume | Fresh crossing — first time at new high this week; Also: Breakout: closed +7.5% above 20d high on 3.2x volume | Near 52-week high | ⚠️ Recent move: +48.3% over 7d
- **Business**: RVMD - Business description not available.
- **News**: No significant news reported for the period between April 15 and April 16, 2026.

**Technical Analysis**:
# Technical Analysis for RVMD
**Date:** 2026-04-16
**Current Price:** $152.54

## Price Action
- **Daily Change:** +3.76%
- **5-Day Change:** +58.53%

## RSI (14)
- **Value:** 87.8 ↑
- **Signal:** OVERBOUGHT ⚠️

## MACD
- **MACD Line:** 8.970
- **Signal Line:** 2.666
- **Histogram:** 6.304 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $100.98 (+51.1% from price)
- **200 SMA:** $70.07 (+117.7% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $140.11
- **Middle:** $103.50
- **Lower:** $66.88
- **Band Position:** 117%
- **Bandwidth:** 70.8% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $6.69 (4.4% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $142.50 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 83.8
- **%D:** 70.4
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 49.5 (Strengthening ↑)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $109.49 (+39.3% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 76.8M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $120.49
- **Current vs VWAP:** +26.6%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $155.01
- **Recent Low:** $91.52
- **Next Resistance:** $155.01 (0.0% (High))
- **Next Support:** $140.03 (23.6%)

## Summary
- **Key Signals:** RSI overbought, Above 50 SMA


**Fundamentals**: N/A

**Insider Transactions**:
Error retrieving insider transactions for RVMD: Too Many Requests. Rate limited. Try after a while.

**Analyst Recommendations**:
## Analyst Recommendation Trends for RVMD

### 2026-04-01
- **Strong Buy**: 11
- **Buy**: 15
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 27

**Sentiment**: 96.3% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 11
- **Buy**: 15
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 27

**Sentiment**: 96.3% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 11
- **Buy**: 15
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 27

**Sentiment**: 96.3% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 11
- **Buy**: 15
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 27

**Sentiment**: 96.3% Bullish, 0.0% Bearish



**Options Activity**:
Error retrieving options activity for RVMD: Too Many Requests. Rate limited. Try after a while.

**Upcoming Earnings**: Earnings in 25 days (2026-05-11): EPS Est $-1.87, Rev Est $3,644,796

### NKE (Priority: CRITICAL)
- **Strategy Match**: insider_buying
- **Sources**: insider_buying | **Confluence**: 1 source(s)
- **Quant Pre-Score**: 10/100 | **ML Win Probability**: N/A | **Altman Z-Score**: None | **Piotroski F-Score**: None
- **Price**: $44.20 | **Current Price (numeric)**: 44.20000076293945 | **Intraday**: +3.0% | **Avg Volume**: 39,739,854
- **Short Interest**: N/A
- **Discovery Context**: Cluster: 3 insiders buying NKE. Largest: Dir Cook Timothy D purchased +$1,060,750
- **Business**: NKE - Business description not available.
- **News**: Nike shares received a boost following disclosure that CEO Elliott Hill and board member Tim Cook each purchased approximately $1 million in shares at $42.43. Despite the insider confidence, fundamental outlook remains cautious with low-single-digit revenue declines expected through fiscal 2026.

**Technical Analysis**:
# Technical Analysis for NKE
**Date:** 2026-04-16
**Current Price:** $45.44

## Price Action
- **Daily Change:** +2.81%
- **5-Day Change:** +3.27%

## RSI (14)
- **Value:** 36.2 ↑
- **Signal:** Bearish

## MACD
- **MACD Line:** -3.594
- **Signal Line:** -3.630
- **Histogram:** 0.036 (Weakening ↓)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $55.57 (-18.2% from price)
- **200 SMA:** $65.04 (-30.1% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $57.39
- **Middle:** $48.19
- **Lower:** $38.99
- **Band Position:** 35%
- **Bandwidth:** 38.2% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $1.75 (3.8% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $42.82 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 42.7
- **%D:** 22.8
- **Signal:** Bullish crossover ⚡

## ADX (Trend Strength)
- **ADX:** 51.0 (Weakening ↓)
- **Interpretation:** VERY STRONG TREND ⚡

## 20 EMA
- **Value:** $47.77 (-4.9% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** -271.4M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $46.72
- **Current vs VWAP:** -2.7%
- **Signal:** Price BELOW VWAP (institutional s... [truncated]
```

### Output
```
```json
{
  "rankings": [
    {
      "rank": 1,
      "ticker": "ACHC",
      "company_name": "Acadia Healthcare",
      "current_price": 26.56,
      "strategy_match": "short_squeeze",
      "final_score": 82,
      "confidence": 8,
      "risk_level": "high",
      "reason": "ACHC presents an extreme short squeeze setup with 42.1% of the float sold short and 6.5 days to cover. Technicals show resilient accumulation with a bullish OBV divergence and the price holding firmly above the 50 SMA of $21.51. While the stock faces fundamental risk due to recent analyst downgrades, the elevated short interest combined with an upward MACD trajectory makes this a prime candidate for a volatile short-covering squeeze. Failure to maintain support at the 20 EMA ($24.79) would invalidate the setup and signal a breakdown.",
      "description": "Acadia Healthcare operates a network of behavioral health facilities and services."
    },
    {
      "rank": 2,
      "ticker": "NKE",
      "company_name": "Nike Inc.",
      "current_price": 44.20,
      "strategy_match": "insider_buying",
      "final_score": 79,
      "confidence": 8,
      "risk_level": "moderate",
      "reason": "A powerful cluster of insider buying is driving this setup, highlighted by CEO Elliott Hill and Director Tim Cook purchasing approximately $1 million in shares each. With the RSI at an oversold 36.2 and a fresh bullish MACD crossover forming, technical indicators are aligning with strong fundamental conviction from leadership. This creates a compelling value reversion play off deep support levels as institutional accumulation begins. The primary risk is the overarching downtrend represented by the steep 200 SMA, meaning a strict stop-loss around $42.82 is essential.",
      "description": "Nike is a global leader in the design, marketing, and distribution of athletic footwear, apparel, equipment, and accessories."
    },
    {
      "rank": 3,
      "ticker": "UBER",
      "company_name": "Uber Technolog
```

---

