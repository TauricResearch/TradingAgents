# Tool Execution Logs - 2026-04-11

## 1. Check average volume (batch)

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:38:31.090383
- **Tool:** `get_average_volume_batch`
- **Parameters:** `{'symbols': ['ALB', 'AA', 'APA', 'AMAT', 'AMD', 'OSCR', 'HMH', 'BETR', 'SCVL', 'FUL', 'XAGE', 'HUIZ', 'LPCN', 'VSCO', 'GAM', 'CMTV', 'APH', 'AVGO', 'ADM', 'AME', 'CGCT', 'BOT', 'GF', 'LCFY', 'MKZR', 'SWZ', 'XZO', 'NKE', 'TXN', 'T', 'EQIX', 'AMKR', 'FIS', 'C', 'JPM', 'CSCO', 'JBL', 'TIGO', 'MSFT', 'BAC', 'FRT', 'AMZN', 'COIN', 'BBY', 'BSX', 'CRWD', 'AXP', 'CI', 'CRM', 'DIS', 'AKAM', 'CVNA', 'IV', 'US', 'ALOT', 'OTRK', 'GAME', 'ABVC', 'FBK', 'FAST', 'WINT', 'PPSI', 'GS', 'IVDA', 'UK', 'CDS', 'UNH', 'LLM', 'MS', 'CIA', 'PN', 'CNCK', 'EPS', 'IBM', 'TLDR', 'LLY', 'POTUS', 'AKAN'], 'lookback_days': 10, 'curr_date': '2026-04-11', 'cache_key': 'default'}`
- **Output Length:** 13452 chars

### Output
```
{"ALB": {"symbol": "ALB", "average_volume": 1595330.0, "latest_volume": 1208200.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "AA": {"symbol": "AA", "average_volume": 6615520.0, "latest_volume": 3185100.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "APA": {"symbol": "APA", "average_volume": 10575160.0, "latest_volume": 4860000.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "AMAT": {"symbol": "AMAT", "average_volume": 5706250.0, "latest_volume": 6397400.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "AMD": {"symbol": "AMD", "average_volume": 34816850.0, "latest_volume": 36398600.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "APH": {"symbol": "APH", "average_volume": 7166820.0, "latest_volume": 9736500.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "AVGO": {"symbol": "AVGO", "average_volume": 24156980.0, "latest_volume": 29929600.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "ADM": {"symbol": "ADM", "average_volume": 3587940.0, "latest_volume": 2918500.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "AME": {"symbol": "AME", "average_volume": 1054490.0, "latest_volume": 966400.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "NKE": {"symbol": "NKE", "average_volume": 38871590.0, "latest_volume": 26014900.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "TXN": {"symbol": "TXN", "average_volume": 5404960.0, "latest_volume": 4265900.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "T": {"symbol": "T", "average_volume": 37851400.0, "latest_volume": 31985700.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "EQIX": {"symbol": "EQIX", "average_volume": 468410.0, "latest_volume": 342800.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "FIS": {"symbol": "FIS", "average_volume": 6970570.0, "latest_volume": 9180900.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "C": {"symbol": "C", "average_volume": 14070820.0, "latest_volume": 8953400.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "JPM": {"symbol": "JPM", "average_volume": 9073740.0, "latest_volume": 6067800.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "CSCO": {"symbol": "CSCO", "average_volume": 18853230.0, "latest_volume": 17568700.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "JBL": {"symbol": "JBL", "average_volume": 953870.0, "latest_volume": 1155800.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "MSFT": {"symbol": "MSFT", "average_volume": 31056910.0, "latest_volume": 28038000.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "BAC": {"symbol": "BAC", "average_volume": 34039940.0, "latest_volume": 25223900.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "FRT": {"symbol": "FRT", "average_volume": 1126240.0, "latest_volume": 2051700.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "AMZN": {"symbol": "AMZN", "average_volume": 46570130.0, "latest_volume": 56842200.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "COIN": {"symbol": "COIN", "average_volume": 9766250.0, "latest_volume": 7898800.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "BBY": {"symbol": "BBY", "average_volume": 3264290.0, "latest_volume": 2787600.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "BSX": {"symbol": "BSX", "average_volume": 19468620.0, "latest_volume": 14773000.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "CRWD": {"symbol": "CRWD", "average_volume": 4279790.0, "latest_volume": 8928400.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "AXP": {"symbol": "AXP", "average_volume": 2771990.0, "latest_volume": 1991300.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "CI": {"symbol": "CI", "average_volume": 1366920.0, "latest_volume": 906700.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "CRM": {"symbol": "CRM", "average_volume": 13501370.0, "latest_volume": 18076300.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "DIS": {"symbol": "DIS", "average_volume": 8903780.0, "latest_volume": 6356900.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "AKAM": {"symbol": "AKAM", "average_volume": 5260720.0, "latest_volume": 14265800.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "CVNA": {"symbol": "CVNA", "average_volume": 2761900.0, "latest_volume": 1921800.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "FAST": {"symbol": "FAST", "average_volume": 7226100.0, "latest_volume": 7285400.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "GS": {"symbol": "GS", "average_volume": 1875890.0, "latest_volume": 1639900.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "UNH": {"symbol": "UNH", "average_volume": 8935160.0, "latest_volume": 5206600.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "MS": {"symbol": "MS", "average_volume": 5984600.0, "latest_volume": 4237100.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "IBM": {"symbol": "IBM", "average_volume": 4251330.0, "latest_volume": 5864900.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "LLY": {"symbol": "LLY", "average_volume": 2901550.0, "latest_volume": 1957200.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-11", "error": null}, "OSCR": {"symbol": "OSCR", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-11", "error": "No volume data found"}, "HMH": {"symbol": "HMH", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-11", "error": "No volume data found"}, "BETR": {"symbol": "BETR", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-11", "error": "No volume data found"}, "SCVL": {"symbol": "SCVL", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-11", "error": "No volume data found"}, "FUL": {"symbol": "FUL", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-11", "error": "No volume data found"}, "XAGE": {"symbol": "XAGE", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-11", "error": "No volume data found"}, "HUIZ": {"symbol": "HUIZ", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-11", "error": "No volume data found"}, "LPCN": {"symbol": "LPCN", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-11", "error": "No volume data found"}, "VSCO": {"symbol": "VSCO", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-11", "error": "No volume data found"}, "GAM": {"symbol": "GAM", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-11", "error": "No volume data found"}, "CMTV": {"symbol": "CMTV", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-11", "error": "No volume data found"}, "CGCT": {"symbol": "CGCT", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-11", "error": "No volume data found"}, "BOT": {"symbol": "BOT", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-11", "error": "No volume data found"}, "GF": {"symbol": "GF", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-11", "error": "No volume data found"}, "LCFY": {"symbol": "LCFY", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-11", "error": "No volume data found"}, "MKZR": {"symbol": "MKZR", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-11", "error": "No volume data found"}, "SWZ": {"symbol": "SWZ", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-11", "error": "No volume data found"}, "XZO": {"symbol": "XZO", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-11", "error": "No volume data found"}, "AMKR": {"symbol": "AMKR", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-11", "error": "No volume data found"}, "TIGO": {"symbol": "TIGO", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-11", "error": "No volume data found"}, "IV": {"symbol": "IV", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "d... [truncated]
```

---

## 2. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:08.708200
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'XAGE', 'curr_date': '2026-04-11'}`
- **Output Length:** 1512 chars

### Output
```
# Technical Analysis for XAGE
**Date:** 2026-04-11
**Current Price:** $0.35

## Price Action
- **Daily Change:** +10.76%
- **5-Day Change:** +18.24%

## RSI (14)
- **Value:** 54.5 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** -0.005
- **Signal Line:** -0.001
- **Histogram:** -0.004 (Weakening ↓)
- **Signal:** Bearish

## Moving Averages
- **50 SMA:** $0.31 (+12.6% from price)
- **200 SMA:** $1.14 (-69.3% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $0.45
- **Middle:** $0.34
- **Lower:** $0.24
- **Band Position:** 52%
- **Bandwidth:** 61.5% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $0.04 (12.4% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $0.28 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 46.9
- **%D:** 34.9
- **Signal:** Bullish crossover ⚡

## ADX (Trend Strength)
- **ADX:** 9.7 (Strengthening ↑)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $0.32 (+9.4% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 102.4M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $0.33
- **Current vs VWAP:** +4.7%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $0.43
- **Recent Low:** $0.23
- **Next Resistance:** $0.35 (38.2%)
- **Next Support:** $0.33 (50.0%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 3. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:08.939252
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'XAGE'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for XAGE: Too Many Requests. Rate limited. Try after a while.
```

---

## 4. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:09.149014
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'XAGE'}`
- **Output Length:** 44 chars

### Output
```
No recommendation trends data found for XAGE
```

---

## 5. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:09.196461
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'XAGE', 'num_expirations': 3, 'curr_date': '2026-04-11'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for XAGE: Too Many Requests. Rate limited. Try after a while.
```

---

## 6. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:11.765082
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'AVGO', 'curr_date': '2026-04-11'}`
- **Output Length:** 1571 chars

### Output
```
# Technical Analysis for AVGO
**Date:** 2026-04-11
**Current Price:** $371.55

## Price Action
- **Daily Change:** +4.69%
- **5-Day Change:** +18.17%

## RSI (14)
- **Value:** 71.0 ↑
- **Signal:** OVERBOUGHT ⚠️

## MACD
- **MACD Line:** 6.034
- **Signal Line:** -0.706
- **Histogram:** 6.740 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $326.12 (+13.9% from price)
- **200 SMA:** $328.94 (+13.0% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $358.85
- **Middle:** $321.84
- **Lower:** $284.84
- **Band Position:** 117%
- **Bandwidth:** 23.0% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $13.42 (3.6% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $351.42 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 87.4
- **%D:** 74.8
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 24.5 (Weakening ↓)
- **Interpretation:** Trending

## 20 EMA
- **Value:** $328.78 (+13.0% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 356.1M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $322.75
- **Current vs VWAP:** +15.1%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $376.55
- **Recent Low:** $289.96
- **Next Resistance:** $376.55 (0.0% (High))
- **Next Support:** $356.11 (23.6%)

## Summary
- **Key Signals:** RSI overbought, Above 50 SMA

```

---

## 7. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:12.055057
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'AVGO'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for AVGO: Too Many Requests. Rate limited. Try after a while.
```

---

## 8. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:12.226410
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

## 9. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:12.302502
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'AVGO', 'num_expirations': 3, 'curr_date': '2026-04-11'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for AVGO: Too Many Requests. Rate limited. Try after a while.
```

---

## 10. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:13.903356
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'AME', 'curr_date': '2026-04-11'}`
- **Output Length:** 1550 chars

### Output
```
# Technical Analysis for AME
**Date:** 2026-04-11
**Current Price:** $234.91

## Price Action
- **Daily Change:** +0.61%
- **5-Day Change:** +7.55%

## RSI (14)
- **Value:** 67.3 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 1.606
- **Signal Line:** -1.262
- **Histogram:** 2.868 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $224.95 (+4.4% from price)
- **200 SMA:** $199.84 (+17.5% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $232.12
- **Middle:** $216.92
- **Lower:** $201.72
- **Band Position:** 109%
- **Bandwidth:** 14.0% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $5.84 (2.5% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $226.15 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 87.8
- **%D:** 76.1
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 20.3 (Weakening ↓)
- **Interpretation:** Trending

## 20 EMA
- **Value:** $221.33 (+6.1% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 9.4M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $216.55
- **Current vs VWAP:** +8.5%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $241.67
- **Recent Low:** $207.32
- **Next Resistance:** $241.67 (0.0% (High))
- **Next Support:** $233.56 (23.6%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 11. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:14.204964
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'AME'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for AME: Too Many Requests. Rate limited. Try after a while.
```

---

## 12. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:14.377264
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'AME'}`
- **Output Length:** 714 chars

### Output
```
## Analyst Recommendation Trends for AME

### 2026-04-01
- **Strong Buy**: 2
- **Buy**: 16
- **Hold**: 7
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 25

**Sentiment**: 72.0% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 2
- **Buy**: 15
- **Hold**: 7
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 24

**Sentiment**: 70.8% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 2
- **Buy**: 14
- **Hold**: 8
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 24

**Sentiment**: 66.7% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 3
- **Buy**: 12
- **Hold**: 8
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 23

**Sentiment**: 65.2% Bullish, 0.0% Bearish


```

---

## 13. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:14.424317
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'AME', 'num_expirations': 3, 'curr_date': '2026-04-11'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for AME: Too Many Requests. Rate limited. Try after a while.
```

---

## 14. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:15.966436
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'GF', 'curr_date': '2026-04-11'}`
- **Output Length:** 1558 chars

### Output
```
# Technical Analysis for GF
**Date:** 2026-04-11
**Current Price:** $11.32

## Price Action
- **Daily Change:** +1.43%
- **5-Day Change:** +6.39%

## RSI (14)
- **Value:** 60.2 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** -0.080
- **Signal Line:** -0.237
- **Histogram:** 0.157 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $11.33 (-0.1% from price)
- **200 SMA:** $11.38 (-0.6% from price)
- **Trend:** STRONG DOWNTREND ⚠️ (DEATH CROSS ⚠️)

## Bollinger Bands (20,2)
- **Upper:** $11.32
- **Middle:** $10.58
- **Lower:** $9.85
- **Band Position:** 100%
- **Bandwidth:** 13.9% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $0.35 (3.1% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $10.80 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 66.9
- **%D:** 59.9
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 31.2 (Strengthening ↑)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $10.78 (+5.0% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 964.4K
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $10.75
- **Current vs VWAP:** +5.3%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $12.39
- **Recent Low:** $9.98
- **Next Resistance:** $11.47 (38.2%)
- **Next Support:** $11.18 (50.0%)

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 15. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:16.183530
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'GF'}`
- **Output Length:** 97 chars

### Output
```
Error retrieving insider transactions for GF: Too Many Requests. Rate limited. Try after a while.
```

---

## 16. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:16.412863
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'GF'}`
- **Output Length:** 42 chars

### Output
```
No recommendation trends data found for GF
```

---

## 17. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:16.469720
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'GF', 'num_expirations': 3, 'curr_date': '2026-04-11'}`
- **Output Length:** 93 chars

### Output
```
Error retrieving options activity for GF: Too Many Requests. Rate limited. Try after a while.
```

---

## 18. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:20.182305
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'CSCO', 'curr_date': '2026-04-11'}`
- **Output Length:** 1516 chars

### Output
```
# Technical Analysis for CSCO
**Date:** 2026-04-11
**Current Price:** $82.22

## Price Action
- **Daily Change:** -1.14%
- **5-Day Change:** +2.21%

## RSI (14)
- **Value:** 58.3 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 0.956
- **Signal Line:** 0.494
- **Histogram:** 0.462 (Weakening ↓)
- **Signal:** Bullish

## Moving Averages
- **50 SMA:** $79.38 (+3.6% from price)
- **200 SMA:** $72.86 (+12.8% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $83.73
- **Middle:** $79.48
- **Lower:** $75.24
- **Band Position:** 82%
- **Bandwidth:** 10.7% (volatility indicator)
- **Signal:** Near upper band

## ATR (Volatility)
- **ATR:** $2.20 (2.7% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $78.91 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 73.1
- **%D:** 65.5
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 14.4 (Strengthening ↑)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $79.97 (+2.8% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 351.1M
- **5-Day Trend:** Falling ↓
- **Signal:** BEARISH DIVERGENCE ⚠️ (distribution)

## VWAP (20-period)
- **VWAP:** $79.16
- **Current vs VWAP:** +3.9%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $87.71
- **Recent Low:** $73.02
- **Next Resistance:** $84.25 (23.6%)
- **Next Support:** $82.10 (38.2%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 19. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:20.451469
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'CSCO'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for CSCO: Too Many Requests. Rate limited. Try after a while.
```

---

## 20. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:20.698471
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'CSCO'}`
- **Output Length:** 716 chars

### Output
```
## Analyst Recommendation Trends for CSCO

### 2026-04-01
- **Strong Buy**: 7
- **Buy**: 16
- **Hold**: 9
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 32

**Sentiment**: 71.9% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 7
- **Buy**: 15
- **Hold**: 9
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 31

**Sentiment**: 71.0% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 7
- **Buy**: 15
- **Hold**: 9
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 31

**Sentiment**: 71.0% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 7
- **Buy**: 13
- **Hold**: 11
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 31

**Sentiment**: 64.5% Bullish, 0.0% Bearish


```

---

## 21. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:20.774675
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'CSCO', 'num_expirations': 3, 'curr_date': '2026-04-11'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for CSCO: Too Many Requests. Rate limited. Try after a while.
```

---

## 22. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:22.865179
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'BAC', 'curr_date': '2026-04-11'}`
- **Output Length:** 1565 chars

### Output
```
# Technical Analysis for BAC
**Date:** 2026-04-11
**Current Price:** $52.54

## Price Action
- **Daily Change:** -0.32%
- **5-Day Change:** +4.95%

## RSI (14)
- **Value:** 67.2 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 0.543
- **Signal Line:** -0.160
- **Histogram:** 0.703 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $50.53 (+4.0% from price)
- **200 SMA:** $50.53 (+4.0% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $52.54
- **Middle:** $48.69
- **Lower:** $44.84
- **Band Position:** 100%
- **Bandwidth:** 15.8% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $1.24 (2.4% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $50.69 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 92.3
- **%D:** 85.8
- **Signal:** OVERBOUGHT ⚠️

## ADX (Trend Strength)
- **ADX:** 19.1 (Strengthening ↑)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $49.75 (+5.6% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 1044.2M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $48.42
- **Current vs VWAP:** +8.5%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $56.55
- **Recent Low:** $46.12
- **Next Resistance:** $52.57 (38.2%)
- **Next Support:** $51.34 (50.0%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 23. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:23.151123
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'BAC'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for BAC: Too Many Requests. Rate limited. Try after a while.
```

---

## 24. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:23.321104
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

## 25. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:23.397022
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'BAC', 'num_expirations': 3, 'curr_date': '2026-04-11'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for BAC: Too Many Requests. Rate limited. Try after a while.
```

---

## 26. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:26.229178
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'CRWD', 'curr_date': '2026-04-11'}`
- **Output Length:** 1566 chars

### Output
```
# Technical Analysis for CRWD
**Date:** 2026-04-11
**Current Price:** $379.02

## Price Action
- **Daily Change:** -3.97%
- **5-Day Change:** -4.91%

## RSI (14)
- **Value:** 41.3 ↓
- **Signal:** Bearish

## MACD
- **MACD Line:** -4.795
- **Signal Line:** -4.689
- **Histogram:** -0.107 (Weakening ↓)
- **Signal:** BEARISH CROSSOVER ⚠️

## Moving Averages
- **50 SMA:** $407.50 (-7.0% from price)
- **200 SMA:** $461.87 (-17.9% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $448.13
- **Middle:** $405.56
- **Lower:** $362.98
- **Band Position:** 19%
- **Bandwidth:** 21.0% (volatility indicator)
- **Signal:** Near lower band

## ATR (Volatility)
- **ATR:** $21.34 (5.6% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $347.01 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 45.4
- **%D:** 53.4
- **Signal:** Bearish crossover ⚠️

## ADX (Trend Strength)
- **ADX:** 13.1 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $402.89 (-5.9% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** -12.5M
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $403.82
- **Current vs VWAP:** -6.1%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $461.55
- **Recent Low:** $342.72
- **Next Resistance:** $388.11 (61.8%)
- **Next Support:** $368.15 (78.6%)

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 27. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:26.469588
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'CRWD'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for CRWD: Too Many Requests. Rate limited. Try after a while.
```

---

## 28. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:26.638960
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'CRWD'}`
- **Output Length:** 723 chars

### Output
```
## Analyst Recommendation Trends for CRWD

### 2026-04-01
- **Strong Buy**: 13
- **Buy**: 33
- **Hold**: 14
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 61

**Sentiment**: 75.4% Bullish, 1.6% Bearish

### 2026-03-01
- **Strong Buy**: 11
- **Buy**: 30
- **Hold**: 17
- **Sell**: 1
- **Strong Sell**: 1
- **Total Analysts**: 60

**Sentiment**: 68.3% Bullish, 3.3% Bearish

### 2026-02-01
- **Strong Buy**: 11
- **Buy**: 28
- **Hold**: 19
- **Sell**: 1
- **Strong Sell**: 1
- **Total Analysts**: 60

**Sentiment**: 65.0% Bullish, 3.3% Bearish

### 2026-01-01
- **Strong Buy**: 11
- **Buy**: 28
- **Hold**: 19
- **Sell**: 1
- **Strong Sell**: 1
- **Total Analysts**: 60

**Sentiment**: 65.0% Bullish, 3.3% Bearish


```

---

## 29. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:26.699572
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'CRWD', 'num_expirations': 3, 'curr_date': '2026-04-11'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for CRWD: Too Many Requests. Rate limited. Try after a while.
```

---

## 30. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:28.267900
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'CRM', 'curr_date': '2026-04-11'}`
- **Output Length:** 1588 chars

### Output
```
# Technical Analysis for CRM
**Date:** 2026-04-11
**Current Price:** $164.96

## Price Action
- **Daily Change:** -3.45%
- **5-Day Change:** -10.62%

## RSI (14)
- **Value:** 28.0 ↓
- **Signal:** OVERSOLD ⚡

## MACD
- **MACD Line:** -6.149
- **Signal Line:** -4.556
- **Histogram:** -1.593 (Strengthening ↑)
- **Signal:** BEARISH CROSSOVER ⚠️

## Moving Averages
- **50 SMA:** $190.51 (-13.4% from price)
- **200 SMA:** $234.15 (-29.6% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $202.94
- **Middle:** $185.66
- **Lower:** $168.37
- **Band Position:** -10%
- **Bandwidth:** 18.6% (volatility indicator)
- **Signal:** AT LOWER BAND - Potential bounce ⚡

## ATR (Volatility)
- **ATR:** $7.50 (4.5% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $153.72 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 18.1
- **%D:** 25.6
- **Signal:** Bearish

## ADX (Trend Strength)
- **ADX:** 25.6 (Strengthening ↑)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $183.60 (-10.2% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** -55.8M
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $185.42
- **Current vs VWAP:** -11.0%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $216.74
- **Recent Low:** $163.52
- **Next Resistance:** $174.91 (78.6%)
- **Next Support:** $163.52 (100% (Low))

## Summary
- **Key Signals:** RSI oversold, Below 50 SMA

```

---

## 31. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:28.529601
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'CRM'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for CRM: Too Many Requests. Rate limited. Try after a while.
```

---

## 32. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:28.686169
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'CRM'}`
- **Output Length:** 722 chars

### Output
```
## Analyst Recommendation Trends for CRM

### 2026-04-01
- **Strong Buy**: 14
- **Buy**: 30
- **Hold**: 13
- **Sell**: 0
- **Strong Sell**: 1
- **Total Analysts**: 58

**Sentiment**: 75.9% Bullish, 1.7% Bearish

### 2026-03-01
- **Strong Buy**: 14
- **Buy**: 30
- **Hold**: 13
- **Sell**: 0
- **Strong Sell**: 1
- **Total Analysts**: 58

**Sentiment**: 75.9% Bullish, 1.7% Bearish

### 2026-02-01
- **Strong Buy**: 15
- **Buy**: 29
- **Hold**: 13
- **Sell**: 0
- **Strong Sell**: 1
- **Total Analysts**: 58

**Sentiment**: 75.9% Bullish, 1.7% Bearish

### 2026-01-01
- **Strong Buy**: 15
- **Buy**: 30
- **Hold**: 13
- **Sell**: 0
- **Strong Sell**: 1
- **Total Analysts**: 59

**Sentiment**: 76.3% Bullish, 1.7% Bearish


```

---

## 33. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:28.757385
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'CRM', 'num_expirations': 3, 'curr_date': '2026-04-11'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for CRM: Too Many Requests. Rate limited. Try after a while.
```

---

## 34. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:31.638923
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'OTRK', 'curr_date': '2026-04-11'}`
- **Output Length:** 1471 chars

### Output
```
# Technical Analysis for OTRK
**Date:** 2026-04-11
**Current Price:** $0.00

## Price Action
- **Daily Change:** -50.00%
- **5-Day Change:** -50.00%

## RSI (14)
- **Value:** 39.6 ↓
- **Signal:** Bearish

## MACD
- **MACD Line:** 0.000
- **Signal Line:** 0.000
- **Histogram:** -0.000 (Weakening ↓)
- **Signal:** BEARISH CROSSOVER ⚠️

## Moving Averages
- **50 SMA:** $0.00 (-28.6% from price)
- **200 SMA:** $0.00 (-27.8% from price)
- **Trend:** Downtrend

## Bollinger Bands (20,2)
- **Upper:** $0.00
- **Middle:** $0.00
- **Lower:** $0.00
- **Band Position:** 23%
- **Bandwidth:** 131.7% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $0.00 (21.5% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $0.00 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 19.0
- **%D:** 42.2
- **Signal:** Bearish

## ADX (Trend Strength)
- **ADX:** 73.6 (Weakening ↓)
- **Interpretation:** VERY STRONG TREND ⚡

## 20 EMA
- **Value:** $0.00 (-38.9% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** 0.9K
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $0.00
- **Current vs VWAP:** -43.2%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $0.00
- **Recent Low:** $0.00
- **Next Resistance:** $0.00 (78.6%)

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 35. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:31.890999
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'OTRK'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for OTRK: Too Many Requests. Rate limited. Try after a while.
```

---

## 36. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:32.078454
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'OTRK'}`
- **Output Length:** 707 chars

### Output
```
## Analyst Recommendation Trends for OTRK

### 2025-12-01
- **Strong Buy**: 2
- **Buy**: 4
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 7

**Sentiment**: 85.7% Bullish, 0.0% Bearish

### 2025-11-01
- **Strong Buy**: 2
- **Buy**: 4
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 7

**Sentiment**: 85.7% Bullish, 0.0% Bearish

### 2025-10-01
- **Strong Buy**: 2
- **Buy**: 4
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 7

**Sentiment**: 85.7% Bullish, 0.0% Bearish

### 2025-09-01
- **Strong Buy**: 2
- **Buy**: 4
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 7

**Sentiment**: 85.7% Bullish, 0.0% Bearish


```

---

## 37. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:32.154412
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'OTRK', 'num_expirations': 3, 'curr_date': '2026-04-11'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for OTRK: Too Many Requests. Rate limited. Try after a while.
```

---

## 38. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:34.425725
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'WINT', 'curr_date': '2026-04-11'}`
- **Output Length:** 1555 chars

### Output
```
# Technical Analysis for WINT
**Date:** 2026-04-11
**Current Price:** $0.02

## Price Action
- **Daily Change:** +0.00%
- **5-Day Change:** +100.00%

## RSI (14)
- **Value:** 72.2 ↑
- **Signal:** OVERBOUGHT ⚠️

## MACD
- **MACD Line:** 0.001
- **Signal Line:** -0.000
- **Histogram:** 0.001 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $0.01 (+75.4% from price)
- **200 SMA:** $0.18 (-88.9% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $0.02
- **Middle:** $0.01
- **Lower:** $0.00
- **Band Position:** 108%
- **Bandwidth:** 127.4% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $0.01 (26.1% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $0.01 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 55.6
- **%D:** 26.0
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 93.0 (Strengthening ↑)
- **Interpretation:** VERY STRONG TREND ⚡

## 20 EMA
- **Value:** $0.01 (+64.1% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 363.8M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $0.01
- **Current vs VWAP:** +44.1%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $0.03
- **Recent Low:** $0.01
- **Next Resistance:** $0.02 (38.2%)
- **Next Support:** $0.02 (61.8%)

## Summary
- **Key Signals:** RSI overbought, Above 50 SMA

```

---

## 39. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:34.695339
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'WINT'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for WINT: Too Many Requests. Rate limited. Try after a while.
```

---

## 40. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:35.046156
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'WINT'}`
- **Output Length:** 707 chars

### Output
```
## Analyst Recommendation Trends for WINT

### 2025-04-01
- **Strong Buy**: 0
- **Buy**: 0
- **Hold**: 3
- **Sell**: 1
- **Strong Sell**: 2
- **Total Analysts**: 6

**Sentiment**: 0.0% Bullish, 50.0% Bearish

### 2025-03-01
- **Strong Buy**: 0
- **Buy**: 0
- **Hold**: 3
- **Sell**: 1
- **Strong Sell**: 2
- **Total Analysts**: 6

**Sentiment**: 0.0% Bullish, 50.0% Bearish

### 2025-02-01
- **Strong Buy**: 0
- **Buy**: 0
- **Hold**: 3
- **Sell**: 1
- **Strong Sell**: 2
- **Total Analysts**: 6

**Sentiment**: 0.0% Bullish, 50.0% Bearish

### 2025-01-01
- **Strong Buy**: 0
- **Buy**: 0
- **Hold**: 3
- **Sell**: 1
- **Strong Sell**: 2
- **Total Analysts**: 6

**Sentiment**: 0.0% Bullish, 50.0% Bearish


```

---

## 41. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:35.117252
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'WINT', 'num_expirations': 3, 'curr_date': '2026-04-11'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for WINT: Too Many Requests. Rate limited. Try after a while.
```

---

## 42. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:36.287609
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'PPSI', 'curr_date': '2026-04-11'}`
- **Output Length:** 1562 chars

### Output
```
# Technical Analysis for PPSI
**Date:** 2026-04-11
**Current Price:** $2.37

## Price Action
- **Daily Change:** -5.20%
- **5-Day Change:** -28.61%

## RSI (14)
- **Value:** 25.6 ↓
- **Signal:** OVERSOLD ⚡

## MACD
- **MACD Line:** -0.219
- **Signal Line:** -0.162
- **Histogram:** -0.057 (Strengthening ↑)
- **Signal:** BEARISH CROSSOVER ⚠️

## Moving Averages
- **50 SMA:** $3.62 (-34.5% from price)
- **200 SMA:** $3.88 (-39.0% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $3.80
- **Middle:** $3.23
- **Lower:** $2.65
- **Band Position:** -25%
- **Bandwidth:** 35.5% (volatility indicator)
- **Signal:** AT LOWER BAND - Potential bounce ⚡

## ATR (Volatility)
- **ATR:** $0.27 (11.6% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $1.96 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 24.0
- **%D:** 35.7
- **Signal:** Bearish

## ADX (Trend Strength)
- **ADX:** 29.9 (Strengthening ↑)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $3.20 (-25.9% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** 94.4M
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $3.05
- **Current vs VWAP:** -22.2%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $4.86
- **Recent Low:** $2.36
- **Next Resistance:** $2.89 (78.6%)
- **Next Support:** $2.36 (100% (Low))

## Summary
- **Key Signals:** RSI oversold, Below 50 SMA

```

---

## 43. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:36.555897
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'PPSI'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for PPSI: Too Many Requests. Rate limited. Try after a while.
```

---

## 44. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:36.720306
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'PPSI'}`
- **Output Length:** 707 chars

### Output
```
## Analyst Recommendation Trends for PPSI

### 2026-04-01
- **Strong Buy**: 2
- **Buy**: 5
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 8

**Sentiment**: 87.5% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 2
- **Buy**: 5
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 8

**Sentiment**: 87.5% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 2
- **Buy**: 5
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 8

**Sentiment**: 87.5% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 2
- **Buy**: 5
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 8

**Sentiment**: 87.5% Bullish, 0.0% Bearish


```

---

## 45. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-11T13:40:36.782319
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'PPSI', 'num_expirations': 3, 'curr_date': '2026-04-11'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for PPSI: Too Many Requests. Rate limited. Try after a while.
```

---

## 46. Rank candidates

- **Type:** `llm`
- **Node:** ranker
- **Timestamp:** 2026-04-11T13:41:48.242008
- **Model:** `gemini-3-pro-preview`
- **Prompt Length:** 40838 chars
- **Output Length:** 2000 chars

### Prompt
```
You are a professional stock analyst selecting the best short-term trading opportunities from a pre-filtered candidate list.

CURRENT DATE: 2026-04-11

GOAL: Select UP TO 15 stocks with the highest probability of generating >5.0% returns within 1-7 days. If fewer than 15 candidates meet the quality bar, return only the ones that do. Quality over quantity — never pad the list with weak picks.

MINIMUM QUALITY BAR:
- Only include candidates where you have genuine conviction (final_score >= 55).
- If a candidate lacks a clear catalyst or has contradictory signals, SKIP it.
- It is better to return 5 excellent picks than 15 mediocre ones.

STRATEGY-SPECIFIC EVALUATION CRITERIA:
Each candidate was discovered by a specific scanner. Evaluate them using the criteria most relevant to their strategy:
- **insider_buying**: Focus on insider transaction SIZE relative to market cap, insider ROLE (CEO/CFO > Director), number of distinct insiders buying, and whether the stock is near support. Large cluster buys are strongest.
- **options_flow**: Focus on put/call ratio, absolute call VOLUME vs open interest, premium size, and whether flow aligns with the technical trend. Unusually low P/C ratios (<0.1) with high volume are strongest.
- **momentum / technical_breakout**: Focus on volume confirmation (>2x average), trend alignment (above key SMAs), and whether momentum is accelerating or fading. Avoid chasing extended moves (RSI >80).
- **earnings_play**: Focus on short interest (squeeze potential), pre-earnings accumulation signals, analyst estimate trends, and historical earnings surprise rate. Binary risk must be acknowledged.
- **social_dd / social_hype**: Treat as SPECULATIVE. Require corroborating technical or fundamental evidence. Pure social sentiment without data backing should score low.
- **short_squeeze**: Focus on short interest %, days to cover, cost to borrow, and whether a catalyst exists to trigger covering. High SI alone is not enough.
- **contrarian_value**: Focus on oversold technicals (RSI <30), fundamental support (earnings stability), and a clear reason why the selloff is overdone.
- **news_catalyst**: Focus on the materiality of the news, whether it's already priced in (check intraday move), and the timeline of impact.
- **sector_rotation**: Focus on relative strength vs sector ETF, whether the stock is a laggard in an accelerating sector.
- **minervini**: Focus on the RS Rating (top 30% = RS>=70, top 10% = RS>=90) as the primary signal. Verify all 6 trend template conditions are met (price structure above rising SMAs). Strongest setups combine RS>=85 with price consolidating near highs (within 10-15% of 52w high) — these have minimal overhead supply. Penalize if RS Rating is borderline (70-75) without other confirming signals.
- **ml_signal**: Use the ML Win Probability as a strong quantitative signal. Scores above 65% deserve significant weight.

HISTORICAL INSIGHTS:
"Historical 1-day win rate: 38.6% (603 tracked)\nHistorical 7-day win rate: 42.2% (564 tracked)\nHistorical 30-day win rate: 33.8% (464 tracked)\n\nBest performing strategies (7-day):\n  - short_squeeze: 60.0% win rate (10 samples)\n  - analyst_upgrade: 48.0% win rate (25 samples)\n  - insider_buying: 46.3% win rate (164 samples)"

CANDIDATES FOR REVIEW:
### XAGE (Priority: CRITICAL)
- **Strategy Match**: insider_buying
- **Sources**: insider_buying | **Confluence**: 1 source(s)
- **Quant Pre-Score**: 10/100 | **ML Win Probability**: N/A | **Altman Z-Score**: None | **Piotroski F-Score**: None
- **Price**: $0.35 | **Current Price (numeric)**: 0.3499999940395355 | **Intraday**: +0.0% | **Avg Volume**: None
- **Short Interest**: N/A
- **Discovery Context**: CEO, 10% Ajjarapu J. Ram purchased +$200,000 of XAGE
- **Business**: XAGE - Business description not available.
- **News**: No company-specific news stories were reported for this ticker on April 10-11, 2026.

**Technical Analysis**:
# Technical Analysis for XAGE
**Date:** 2026-04-11
**Current Price:** $0.35

## Price Action
- **Daily Change:** +10.76%
- **5-Day Change:** +18.24%

## RSI (14)
- **Value:** 54.5 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** -0.005
- **Signal Line:** -0.001
- **Histogram:** -0.004 (Weakening ↓)
- **Signal:** Bearish

## Moving Averages
- **50 SMA:** $0.31 (+12.6% from price)
- **200 SMA:** $1.14 (-69.3% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $0.45
- **Middle:** $0.34
- **Lower:** $0.24
- **Band Position:** 52%
- **Bandwidth:** 61.5% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $0.04 (12.4% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $0.28 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 46.9
- **%D:** 34.9
- **Signal:** Bullish crossover ⚡

## ADX (Trend Strength)
- **ADX:** 9.7 (Strengthening ↑)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $0.32 (+9.4% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 102.4M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $0.33
- **Current vs VWAP:** +4.7%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $0.43
- **Recent Low:** $0.23
- **Next Resistance:** $0.35 (38.2%)
- **Next Support:** $0.33 (50.0%)

## Summary
- **Key Signals:** Above 50 SMA


**Fundamentals**: N/A

**Insider Transactions**:
Error retrieving insider transactions for XAGE: Too Many Requests. Rate limited. Try after a while.

**Analyst Recommendations**:
No recommendation trends data found for XAGE

**Options Activity**:
Error retrieving options activity for XAGE: Too Many Requests. Rate limited. Try after a while.

**Upcoming Earnings**: No upcoming earnings within 30 days

### AVGO (Priority: HIGH)
- **Strategy Match**: minervini
- **Sources**: minervini, options_flow | **Confluence**: 2 source(s)
- **Quant Pre-Score**: 20/100 | **ML Win Probability**: N/A | **Altman Z-Score**: None | **Piotroski F-Score**: None
- **Price**: $371.55 | **Current Price (numeric)**: 371.54998779296875 | **Intraday**: +0.0% | **Avg Volume**: 24,156,980
- **Short Interest**: N/A
- **Discovery Context**: Minervini Stage 2: P>SMA50>SMA150>SMA200, +125% off 52w low, within 10% of 52w high, RS Rating 88/100; Also: Unusual options: 3 strikes across 3 exp, P/C=999.00 (bearish), 0 unusual calls / 3 unusual puts
- **Business**: AVGO - Business description not available.
- **News**: Broadcom shares climbed 5% on April 10 after announcing a long-term TPU supply deal with Google and Anthropic and a new $10 billion share repurchase program.

**Technical Analysis**:
# Technical Analysis for AVGO
**Date:** 2026-04-11
**Current Price:** $371.55

## Price Action
- **Daily Change:** +4.69%
- **5-Day Change:** +18.17%

## RSI (14)
- **Value:** 71.0 ↑
- **Signal:** OVERBOUGHT ⚠️

## MACD
- **MACD Line:** 6.034
- **Signal Line:** -0.706
- **Histogram:** 6.740 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $326.12 (+13.9% from price)
- **200 SMA:** $328.94 (+13.0% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $358.85
- **Middle:** $321.84
- **Lower:** $284.84
- **Band Position:** 117%
- **Bandwidth:** 23.0% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $13.42 (3.6% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $351.42 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 87.4
- **%D:** 74.8
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 24.5 (Weakening ↓)
- **Interpretation:** Trending

## 20 EMA
- **Value:** $328.78 (+13.0% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 356.1M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $322.75
- **Current vs VWAP:** +15.1%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $376.55
- **Recent Low:** $289.96
- **Next Resistance:** $376.55 (0.0% (High))
- **Next Support:** $356.11 (23.6%)

## Summary
- **Key Signals:** RSI overbought, Above 50 SMA


**Fundamentals**: N/A

**Insider Transactions**:
Error retrieving insider transactions for AVGO: Too Many Requests. Rate limited. Try after a while.

**Analyst Recommendations**:
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



**Options Activity**:
Error retrieving options activity for AVGO: Too Many Requests. Rate limited. Try after a while.

**Upcoming Earnings**: No upcoming earnings within 30 days

### AME (Priority: HIGH)
- **Strategy Match**: minervini
- **Sources**: minervini | **Confluence**: 1 source(s)
- **Quant Pre-Score**: 10/100 | **ML Win Probability**: N/A | **Altman Z-Score**: None | **Piotroski F-Score**: None
- **Price**: $234.91 | **Current Price (numeric)**: 234.91000366210938 | **Intraday**: +0.0% | **Avg Volume**: 1,054,490
- **Short Interest**: N/A
- **Discovery Context**: Minervini Stage 2: P>SMA50>SMA150>SMA200, +52% off 52w low, within 3% of 52w high, RS Rating 82/100
- **Business**: AME - Business description not available.
- **News**: No company-specific news stories were reported for this... [truncated]
```

### Output
```
{
  "rankings": [
    {
      "rank": 1,
      "ticker": "AVGO",
      "company_name": "Broadcom",
      "current_price": 371.54998779296875,
      "strategy_match": "minervini",
      "final_score": 85,
      "confidence": 8,
      "risk_level": "moderate",
      "reason": "The stock has a massive fundamental catalyst driven by a new $10 billion share repurchase program and a long-term TPU supply deal with Google and Anthropic. The news triggered an immediate 4.69% daily jump, signaling the start of a momentum expansion perfectly aligned with its technical breakout. The setup provides strong risk/reward with the price up 125% off its 52-week low, an elite RS Rating of 88/100, and trading 13.9% above its 50-day SMA. The key risk is that short-term technicals show an overbought RSI of 71.0, and unusual options flow revealed a bearish P/C ratio of 999.00 with 3 unusual puts, suggesting potential near-term hedging or volatility.",
      "description": "Broadcom is a global technology leader expanding its AI footprint through major TPU supply agreements."
    },
    {
      "rank": 2,
      "ticker": "BAC",
      "company_name": "Bank of America",
      "current_price": 52.540000915527344,
      "strategy_match": "minervini",
      "final_score": 65,
      "confidence": 6,
      "risk_level": "high",
      "reason": "BAC is experiencing strong sector rotation and sympathy momentum following JPM's robust results, further validated by management confirming a 10% year-to-date jump in investment banking revenue. Institutional accumulation is actively confirming the move, evidenced by a rising 5-day On-Balance Volume (OBV) trend and a fresh MACD bullish crossover. The technical structure is highly supportive, with the stock maintaining a Minervini Stage 2 uptrend, an RS Rating of 78/100, and trading 4.0% above its 50-day SMA. The most significant risk is the binary earnings event in just 4 days, compounded by an overbought Stochastic reading of 92.3 that could trigger pre-ea
```

---

