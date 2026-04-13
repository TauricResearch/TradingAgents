# Tool Execution Logs - 2026-04-13

## 1. Check average volume (batch)

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:16:22.327593
- **Tool:** `get_average_volume_batch`
- **Parameters:** `{'symbols': ['ALB', 'APA', 'AA', 'AMAT', 'AMD', 'APH', 'COE', 'OSCR', 'BETR', 'FUL', 'XAGE', 'HUIZ', 'GAM', 'ABX', 'BATL', 'ACHC', 'AI', 'ARCT', 'AVGO', 'ADM', 'AME', 'MESO', 'CGCT', 'BOT', 'GF', 'LCFY', 'MKZR', 'XZO', 'NKE', 'KYN', 'NMM', 'CTGO', 'AIRS', 'ADI', 'TMUS', 'VZ', 'MSFT', 'AMZN', 'COF', 'NVDA', 'TXN', 'AVT', 'ALOT', 'OTRK', 'GAME', 'ABVC', 'FBK', 'FAST', 'WINT', 'PPSI', 'GS', 'IVDA', 'IS', 'BAC', 'AAPL', 'BSX', 'CSCO', 'COIN', 'AXP', 'CARR', 'CI'], 'lookback_days': 10, 'curr_date': '2026-04-13', 'cache_key': 'default'}`
- **Output Length:** 10580 chars

### Output
```
{"ALB": {"symbol": "ALB", "average_volume": 1507938.5, "latest_volume": 698285.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-13", "error": null}, "APA": {"symbol": "APA", "average_volume": 9580029.1, "latest_volume": 1226391.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-13", "error": null}, "AA": {"symbol": "AA", "average_volume": 6345279.5, "latest_volume": 626295.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-13", "error": null}, "AMAT": {"symbol": "AMAT", "average_volume": 5192681.3, "latest_volume": 849113.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-13", "error": null}, "AMD": {"symbol": "AMD", "average_volume": 32484818.5, "latest_volume": 5886285.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-13", "error": null}, "APH": {"symbol": "APH", "average_volume": 6466532.3, "latest_volume": 802923.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-13", "error": null}, "AVGO": {"symbol": "AVGO", "average_volume": 22226354.1, "latest_volume": 4287641.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-13", "error": null}, "ADM": {"symbol": "ADM", "average_volume": 2992212.7, "latest_volume": 218327.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-13", "error": null}, "AME": {"symbol": "AME", "average_volume": 977026.4, "latest_volume": 58764.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-13", "error": null}, "NKE": {"symbol": "NKE", "average_volume": 37961730.6, "latest_volume": 3979206.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-13", "error": null}, "MSFT": {"symbol": "MSFT", "average_volume": 27995836.7, "latest_volume": 7272667.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-13", "error": null}, "AMZN": {"symbol": "AMZN", "average_volume": 41885602.2, "latest_volume": 9164522.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-13", "error": null}, "COF": {"symbol": "COF", "average_volume": 3888237.0, "latest_volume": 385570.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-13", "error": null}, "NVDA": {"symbol": "NVDA", "average_volume": 141890077.6, "latest_volume": 31457376.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-13", "error": null}, "FAST": {"symbol": "FAST", "average_volume": 6917092.0, "latest_volume": 2619020.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-13", "error": null}, "GS": {"symbol": "GS", "average_volume": 1815917.9, "latest_volume": 1507079.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-13", "error": null}, "BAC": {"symbol": "BAC", "average_volume": 30775010.0, "latest_volume": 4132600.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-13", "error": null}, "AAPL": {"symbol": "AAPL", "average_volume": 35792933.1, "latest_volume": 5644431.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-13", "error": null}, "BSX": {"symbol": "BSX", "average_volume": 18000476.7, "latest_volume": 1331067.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-13", "error": null}, "CSCO": {"symbol": "CSCO", "average_volume": 17262244.8, "latest_volume": 4647548.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-13", "error": null}, "COIN": {"symbol": "COIN", "average_volume": 8756146.1, "latest_volume": 2188861.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-13", "error": null}, "AXP": {"symbol": "AXP", "average_volume": 2523157.5, "latest_volume": 262675.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-13", "error": null}, "CARR": {"symbol": "CARR", "average_volume": 5347004.3, "latest_volume": 796543.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-13", "error": null}, "CI": {"symbol": "CI", "average_volume": 1148170.1, "latest_volume": 74101.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-13", "error": null}, "COE": {"symbol": "COE", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-13", "error": "No volume data found"}, "OSCR": {"symbol": "OSCR", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-13", "error": "No volume data found"}, "BETR": {"symbol": "BETR", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-13", "error": "No volume data found"}, "FUL": {"symbol": "FUL", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-13", "error": "No volume data found"}, "XAGE": {"symbol": "XAGE", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-13", "error": "No volume data found"}, "HUIZ": {"symbol": "HUIZ", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-13", "error": "No volume data found"}, "GAM": {"symbol": "GAM", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-13", "error": "No volume data found"}, "ABX": {"symbol": "ABX", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-13", "error": "No volume data found"}, "BATL": {"symbol": "BATL", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-13", "error": "No volume data found"}, "ACHC": {"symbol": "ACHC", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-13", "error": "No volume data found"}, "AI": {"symbol": "AI", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-13", "error": "No volume data found"}, "ARCT": {"symbol": "ARCT", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-13", "error": "No volume data found"}, "MESO": {"symbol": "MESO", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-13", "error": "No volume data found"}, "CGCT": {"symbol": "CGCT", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-13", "error": "No volume data found"}, "BOT": {"symbol": "BOT", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-13", "error": "No volume data found"}, "GF": {"symbol": "GF", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-13", "error": "No volume data found"}, "LCFY": {"symbol": "LCFY", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-13", "error": "No volume data found"}, "MKZR": {"symbol": "MKZR", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-13", "error": "No volume data found"}, "XZO": {"symbol": "XZO", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-13", "error": "No volume data found"}, "KYN": {"symbol": "KYN", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-13", "error": "No volume data found"}, "NMM": {"symbol": "NMM", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-13", "error": "No volume data found"}, "CTGO": {"symbol": "CTGO", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-13", "error": "No volume data found"}, "AIRS": {"symbol": "AIRS", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-13", "error": "No volume data found"}, "ADI": {"symbol": "ADI", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-13", "error": "No volume data found"}, "TMUS": {"symbol": "TMUS", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-13", "error": "No volume data found"}, "VZ": {"symbol": "VZ", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-13", "error": "No volume data found"}, "TXN": {"symbol": "TXN", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-13", "error": "No volume data found"}, "AVT": {"symbol": "AVT", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-13", "error": "No volume data found"}, "ALOT": {"symbol": "ALOT", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-13", "error": "No volume data found"}, "OTRK": {"symbol": "OTRK", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-13", "error": "No volume data found"}, "GAME": {"symbol": "GAME", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-13", "error": "No volume data found"}, "ABVC": {"symbol": "ABVC", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-13", "error": "No volume data found"}, "FBK": {"symbol": "FBK", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-13", "error": "No volume data found"}, "WINT": {"symbol": "WINT", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": ... [truncated]
```

---

## 2. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:42.292315
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'ALB', 'curr_date': '2026-04-13'}`
- **Output Length:** 1541 chars

### Output
```
# Technical Analysis for ALB
**Date:** 2026-04-13
**Current Price:** $173.64

## Price Action
- **Daily Change:** +0.75%
- **5-Day Change:** +0.35%

## RSI (14)
- **Value:** 51.0 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 1.641
- **Signal Line:** 1.771
- **Histogram:** -0.130 (Strengthening ↑)
- **Signal:** BEARISH CROSSOVER ⚠️

## Moving Averages
- **50 SMA:** $170.80 (+1.7% from price)
- **200 SMA:** $119.94 (+44.8% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $186.71
- **Middle:** $171.80
- **Lower:** $156.90
- **Band Position:** 56%
- **Bandwidth:** 17.4% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $8.98 (5.2% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $160.17 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 29.7
- **%D:** 42.5
- **Signal:** Bearish

## ADX (Trend Strength)
- **ADX:** 4.6 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $173.34 (+0.2% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 145.6M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $171.67
- **Current vs VWAP:** +1.1%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $205.49
- **Recent Low:** $154.69
- **Next Resistance:** $174.10 (61.8%)
- **Next Support:** $165.56 (78.6%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 3. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:42.449901
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'ALB'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for ALB: Too Many Requests. Rate limited. Try after a while.
```

---

## 4. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:42.709016
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'ALB'}`
- **Output Length:** 717 chars

### Output
```
## Analyst Recommendation Trends for ALB

### 2026-04-01
- **Strong Buy**: 7
- **Buy**: 11
- **Hold**: 11
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 29

**Sentiment**: 62.1% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 7
- **Buy**: 11
- **Hold**: 12
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 30

**Sentiment**: 60.0% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 6
- **Buy**: 11
- **Hold**: 13
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 31

**Sentiment**: 54.8% Bullish, 3.2% Bearish

### 2026-01-01
- **Strong Buy**: 5
- **Buy**: 7
- **Hold**: 18
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 31

**Sentiment**: 38.7% Bullish, 3.2% Bearish


```

---

## 5. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:42.751539
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'ALB', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for ALB: Too Many Requests. Rate limited. Try after a while.
```

---

## 6. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:43.675929
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'APA', 'curr_date': '2026-04-13'}`
- **Output Length:** 1514 chars

### Output
```
# Technical Analysis for APA
**Date:** 2026-04-13
**Current Price:** $38.63

## Price Action
- **Daily Change:** -0.87%
- **5-Day Change:** -10.20%

## RSI (14)
- **Value:** 52.2 ↓
- **Signal:** Bullish

## MACD
- **MACD Line:** 2.049
- **Signal Line:** 2.776
- **Histogram:** -0.727 (Strengthening ↑)
- **Signal:** BEARISH CROSSOVER ⚠️

## Moving Averages
- **50 SMA:** $33.45 (+15.5% from price)
- **200 SMA:** $25.24 (+53.1% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $45.97
- **Middle:** $39.95
- **Lower:** $33.92
- **Band Position:** 39%
- **Bandwidth:** 30.1% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $2.12 (5.5% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $35.46 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 41.7
- **%D:** 51.6
- **Signal:** Bearish

## ADX (Trend Strength)
- **ADX:** 22.0 (Weakening ↓)
- **Interpretation:** Trending

## 20 EMA
- **Value:** $39.23 (-1.5% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** 122.8M
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $39.99
- **Current vs VWAP:** -3.4%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $45.66
- **Recent Low:** $25.30
- **Next Resistance:** $40.86 (23.6%)
- **Next Support:** $37.88 (38.2%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 7. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:43.883679
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'APA'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for APA: Too Many Requests. Rate limited. Try after a while.
```

---

## 8. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:44.147499
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'APA'}`
- **Output Length:** 718 chars

### Output
```
## Analyst Recommendation Trends for APA

### 2026-04-01
- **Strong Buy**: 3
- **Buy**: 7
- **Hold**: 19
- **Sell**: 5
- **Strong Sell**: 0
- **Total Analysts**: 34

**Sentiment**: 29.4% Bullish, 14.7% Bearish

### 2026-03-01
- **Strong Buy**: 3
- **Buy**: 7
- **Hold**: 19
- **Sell**: 5
- **Strong Sell**: 0
- **Total Analysts**: 34

**Sentiment**: 29.4% Bullish, 14.7% Bearish

### 2026-02-01
- **Strong Buy**: 3
- **Buy**: 7
- **Hold**: 19
- **Sell**: 5
- **Strong Sell**: 0
- **Total Analysts**: 34

**Sentiment**: 29.4% Bullish, 14.7% Bearish

### 2026-01-01
- **Strong Buy**: 3
- **Buy**: 6
- **Hold**: 21
- **Sell**: 4
- **Strong Sell**: 0
- **Total Analysts**: 34

**Sentiment**: 26.5% Bullish, 11.8% Bearish


```

---

## 9. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:44.186362
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'APA', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for APA: Too Many Requests. Rate limited. Try after a while.
```

---

## 10. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:45.249783
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'AMAT', 'curr_date': '2026-04-13'}`
- **Output Length:** 1561 chars

### Output
```
# Technical Analysis for AMAT
**Date:** 2026-04-13
**Current Price:** $399.49

## Price Action
- **Daily Change:** +0.42%
- **5-Day Change:** +13.29%

## RSI (14)
- **Value:** 66.2 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 9.180
- **Signal Line:** 3.926
- **Histogram:** 5.254 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $350.95 (+13.8% from price)
- **200 SMA:** $253.45 (+57.6% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $396.61
- **Middle:** $357.09
- **Lower:** $317.58
- **Band Position:** 104%
- **Bandwidth:** 22.1% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $16.69 (4.2% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $374.45 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 81.3
- **%D:** 67.1
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 22.1 (Strengthening ↑)
- **Interpretation:** Trending

## 20 EMA
- **Value:** $361.39 (+10.5% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 224.0M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $356.76
- **Current vs VWAP:** +12.0%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $407.29
- **Recent Low:** $287.13
- **Next Resistance:** $407.29 (0.0% (High))
- **Next Support:** $378.93 (23.6%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 11. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:46.439539
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'AMAT'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for AMAT: Too Many Requests. Rate limited. Try after a while.
```

---

## 12. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:46.700124
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'AMAT'}`
- **Output Length:** 721 chars

### Output
```
## Analyst Recommendation Trends for AMAT

### 2026-04-01
- **Strong Buy**: 11
- **Buy**: 24
- **Hold**: 8
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 43

**Sentiment**: 81.4% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 11
- **Buy**: 24
- **Hold**: 8
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 43

**Sentiment**: 81.4% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 10
- **Buy**: 23
- **Hold**: 10
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 43

**Sentiment**: 76.7% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 10
- **Buy**: 17
- **Hold**: 13
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 40

**Sentiment**: 67.5% Bullish, 0.0% Bearish


```

---

## 13. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:46.749740
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'AMAT', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for AMAT: Too Many Requests. Rate limited. Try after a while.
```

---

## 14. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:47.662626
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'AMD', 'curr_date': '2026-04-13'}`
- **Output Length:** 1587 chars

### Output
```
# Technical Analysis for AMD
**Date:** 2026-04-13
**Current Price:** $245.04

## Price Action
- **Daily Change:** +3.55%
- **5-Day Change:** +11.29%

## RSI (14)
- **Value:** 70.1 ↑
- **Signal:** OVERBOUGHT ⚠️

## MACD
- **MACD Line:** 7.512
- **Signal Line:** 2.975
- **Histogram:** 4.538 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $209.35 (+17.0% from price)
- **200 SMA:** $199.41 (+22.9% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $239.73
- **Middle:** $210.44
- **Lower:** $181.15
- **Band Position:** 109%
- **Bandwidth:** 27.8% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $10.22 (4.2% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $229.70 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 88.3
- **%D:** 78.9
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 29.2 (Strengthening ↑)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $215.83 (+13.5% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 1147.0M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $210.44
- **Current vs VWAP:** +16.4%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $260.53
- **Recent Low:** $188.22
- **Next Resistance:** $260.53 (0.0% (High))
- **Next Support:** $243.46 (23.6%)

## Summary
- **Key Signals:** RSI overbought, Above 50 SMA

```

---

## 15. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:47.983794
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'AMD'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for AMD: Too Many Requests. Rate limited. Try after a while.
```

---

## 16. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:48.229865
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

## 17. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:48.277893
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'AMD', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for AMD: Too Many Requests. Rate limited. Try after a while.
```

---

## 18. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:49.230927
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'APH', 'curr_date': '2026-04-13'}`
- **Output Length:** 1570 chars

### Output
```
# Technical Analysis for APH
**Date:** 2026-04-13
**Current Price:** $140.75

## Price Action
- **Daily Change:** +2.23%
- **5-Day Change:** +11.27%

## RSI (14)
- **Value:** 59.9 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** -0.565
- **Signal Line:** -2.620
- **Histogram:** 2.055 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $136.74 (+2.9% from price)
- **200 SMA:** $127.01 (+10.8% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $140.41
- **Middle:** $129.67
- **Lower:** $118.93
- **Band Position:** 102%
- **Bandwidth:** 16.6% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $5.93 (4.2% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $131.86 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 82.2
- **%D:** 68.6
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 14.3 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $131.66 (+6.9% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 255.0M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $130.28
- **Current vs VWAP:** +8.0%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $153.75
- **Recent Low:** $118.24
- **Next Resistance:** $145.37 (23.6%)
- **Next Support:** $140.18 (38.2%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 19. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:49.396842
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'APH'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for APH: Too Many Requests. Rate limited. Try after a while.
```

---

## 20. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:49.626442
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'APH'}`
- **Output Length:** 714 chars

### Output
```
## Analyst Recommendation Trends for APH

### 2026-04-01
- **Strong Buy**: 5
- **Buy**: 15
- **Hold**: 4
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 24

**Sentiment**: 83.3% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 4
- **Buy**: 15
- **Hold**: 6
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 25

**Sentiment**: 76.0% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 4
- **Buy**: 15
- **Hold**: 6
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 25

**Sentiment**: 76.0% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 4
- **Buy**: 14
- **Hold**: 7
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 25

**Sentiment**: 72.0% Bullish, 0.0% Bearish


```

---

## 21. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:49.667787
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'APH', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for APH: Too Many Requests. Rate limited. Try after a while.
```

---

## 22. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:50.552572
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'COE', 'curr_date': '2026-04-13'}`
- **Output Length:** 1524 chars

### Output
```
# Technical Analysis for COE
**Date:** 2026-04-13
**Current Price:** $21.34

## Price Action
- **Daily Change:** -0.74%
- **5-Day Change:** -4.94%

## RSI (14)
- **Value:** 48.0 ↓
- **Signal:** Bearish

## MACD
- **MACD Line:** -0.573
- **Signal Line:** -1.095
- **Histogram:** 0.521 (Weakening ↓)
- **Signal:** Bullish

## Moving Averages
- **50 SMA:** $23.78 (-10.3% from price)
- **200 SMA:** $33.96 (-37.2% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $23.34
- **Middle:** $19.80
- **Lower:** $16.25
- **Band Position:** 72%
- **Bandwidth:** 35.8% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $1.82 (8.5% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $18.61 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 69.8
- **%D:** 70.9
- **Signal:** Bearish crossover ⚠️

## ADX (Trend Strength)
- **ADX:** 6.2 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $21.22 (+0.6% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** -268.2K
- **5-Day Trend:** Rising ↑
- **Signal:** BULLISH DIVERGENCE ⚡ (accumulation)

## VWAP (20-period)
- **VWAP:** $20.02
- **Current vs VWAP:** +6.6%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $28.50
- **Recent Low:** $15.32
- **Next Resistance:** $21.91 (50.0%)
- **Next Support:** $20.35 (61.8%)

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 23. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:50.714574
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'COE'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for COE: Too Many Requests. Rate limited. Try after a while.
```

---

## 24. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:50.936433
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'COE'}`
- **Output Length:** 706 chars

### Output
```
## Analyst Recommendation Trends for COE

### 2023-01-01
- **Strong Buy**: 0
- **Buy**: 0
- **Hold**: 3
- **Sell**: 4
- **Strong Sell**: 1
- **Total Analysts**: 8

**Sentiment**: 0.0% Bullish, 62.5% Bearish

### 2022-12-01
- **Strong Buy**: 0
- **Buy**: 0
- **Hold**: 3
- **Sell**: 4
- **Strong Sell**: 1
- **Total Analysts**: 8

**Sentiment**: 0.0% Bullish, 62.5% Bearish

### 2022-11-01
- **Strong Buy**: 0
- **Buy**: 0
- **Hold**: 3
- **Sell**: 4
- **Strong Sell**: 1
- **Total Analysts**: 8

**Sentiment**: 0.0% Bullish, 62.5% Bearish

### 2022-10-01
- **Strong Buy**: 0
- **Buy**: 0
- **Hold**: 3
- **Sell**: 4
- **Strong Sell**: 1
- **Total Analysts**: 8

**Sentiment**: 0.0% Bullish, 62.5% Bearish


```

---

## 25. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:50.978229
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'COE', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for COE: Too Many Requests. Rate limited. Try after a while.
```

---

## 26. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:51.873589
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'OSCR', 'curr_date': '2026-04-13'}`
- **Output Length:** 1518 chars

### Output
```
# Technical Analysis for OSCR
**Date:** 2026-04-13
**Current Price:** $14.45

## Price Action
- **Daily Change:** -0.62%
- **5-Day Change:** +13.24%

## RSI (14)
- **Value:** 62.6 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 0.111
- **Signal Line:** -0.254
- **Histogram:** 0.366 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $13.19 (+9.6% from price)
- **200 SMA:** $15.98 (-9.6% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $14.93
- **Middle:** $12.71
- **Lower:** $10.50
- **Band Position:** 89%
- **Bandwidth:** 34.8% (volatility indicator)
- **Signal:** Near upper band

## ATR (Volatility)
- **ATR:** $0.74 (5.1% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $13.34 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 82.5
- **%D:** 69.5
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 26.3 (Strengthening ↑)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $13.02 (+11.0% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** -163.4M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $12.78
- **Current vs VWAP:** +13.1%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $15.25
- **Recent Low:** $10.69
- **Next Resistance:** $15.25 (0.0% (High))
- **Next Support:** $14.17 (23.6%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 27. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:52.031361
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'OSCR'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for OSCR: Too Many Requests. Rate limited. Try after a while.
```

---

## 28. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:52.301320
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'OSCR'}`
- **Output Length:** 715 chars

### Output
```
## Analyst Recommendation Trends for OSCR

### 2026-04-01
- **Strong Buy**: 0
- **Buy**: 3
- **Hold**: 8
- **Sell**: 3
- **Strong Sell**: 3
- **Total Analysts**: 17

**Sentiment**: 17.6% Bullish, 35.3% Bearish

### 2026-03-01
- **Strong Buy**: 0
- **Buy**: 3
- **Hold**: 8
- **Sell**: 3
- **Strong Sell**: 3
- **Total Analysts**: 17

**Sentiment**: 17.6% Bullish, 35.3% Bearish

### 2026-02-01
- **Strong Buy**: 0
- **Buy**: 2
- **Hold**: 8
- **Sell**: 4
- **Strong Sell**: 3
- **Total Analysts**: 17

**Sentiment**: 11.8% Bullish, 41.2% Bearish

### 2026-01-01
- **Strong Buy**: 0
- **Buy**: 2
- **Hold**: 6
- **Sell**: 5
- **Strong Sell**: 3
- **Total Analysts**: 16

**Sentiment**: 12.5% Bullish, 50.0% Bearish


```

---

## 29. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:52.339438
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'OSCR', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for OSCR: Too Many Requests. Rate limited. Try after a while.
```

---

## 30. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:53.217807
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'BETR', 'curr_date': '2026-04-13'}`
- **Output Length:** 1489 chars

### Output
```
# Technical Analysis for BETR
**Date:** 2026-04-13
**Current Price:** $32.75

## Price Action
- **Daily Change:** +1.58%
- **5-Day Change:** -18.86%

## RSI (14)
- **Value:** 48.5 ↓
- **Signal:** Bearish

## MACD
- **MACD Line:** 1.026
- **Signal Line:** 0.949
- **Histogram:** 0.078 (Weakening ↓)
- **Signal:** Bullish

## Moving Averages
- **50 SMA:** $31.83 (+2.9% from price)
- **200 SMA:** $35.72 (-8.3% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $41.70
- **Middle:** $32.92
- **Lower:** $24.14
- **Band Position:** 49%
- **Bandwidth:** 53.3% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $4.13 (12.6% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $26.56 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 38.9
- **%D:** 56.5
- **Signal:** Bearish

## ADX (Trend Strength)
- **ADX:** 25.5 (Weakening ↓)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $34.19 (-4.2% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** 3.1M
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $33.41
- **Current vs VWAP:** -2.0%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $45.59
- **Recent Low:** $25.11
- **Next Resistance:** $32.93 (61.8%)
- **Next Support:** $29.49 (78.6%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 31. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:54.398210
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'BETR'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for BETR: Too Many Requests. Rate limited. Try after a while.
```

---

## 32. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:54.656574
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'BETR'}`
- **Output Length:** 707 chars

### Output
```
## Analyst Recommendation Trends for BETR

### 2026-04-01
- **Strong Buy**: 2
- **Buy**: 4
- **Hold**: 3
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 9

**Sentiment**: 66.7% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 0
- **Buy**: 0
- **Hold**: 4
- **Sell**: 1
- **Strong Sell**: 2
- **Total Analysts**: 7

**Sentiment**: 0.0% Bullish, 42.9% Bearish

### 2026-02-01
- **Strong Buy**: 0
- **Buy**: 0
- **Hold**: 4
- **Sell**: 1
- **Strong Sell**: 2
- **Total Analysts**: 7

**Sentiment**: 0.0% Bullish, 42.9% Bearish

### 2026-01-01
- **Strong Buy**: 0
- **Buy**: 0
- **Hold**: 4
- **Sell**: 1
- **Strong Sell**: 2
- **Total Analysts**: 7

**Sentiment**: 0.0% Bullish, 42.9% Bearish


```

---

## 33. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:54.698001
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'BETR', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for BETR: Too Many Requests. Rate limited. Try after a while.
```

---

## 34. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:55.928492
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'HUIZ', 'curr_date': '2026-04-13'}`
- **Output Length:** 1521 chars

### Output
```
# Technical Analysis for HUIZ
**Date:** 2026-04-13
**Current Price:** $1.56

## Price Action
- **Daily Change:** +6.12%
- **5-Day Change:** +4.70%

## RSI (14)
- **Value:** 46.0 ↑
- **Signal:** Bearish

## MACD
- **MACD Line:** -0.105
- **Signal Line:** -0.120
- **Histogram:** 0.015 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $1.81 (-13.7% from price)
- **200 SMA:** $2.65 (-41.2% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $1.91
- **Middle:** $1.59
- **Lower:** $1.27
- **Band Position:** 45%
- **Bandwidth:** 40.8% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $0.16 (10.5% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $1.31 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 59.9
- **%D:** 47.4
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 19.0 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $1.59 (-1.6% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** 25.3M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $1.52
- **Current vs VWAP:** +2.5%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $2.25
- **Recent Low:** $1.18
- **Next Resistance:** $1.59 (61.8%)
- **Next Support:** $1.41 (78.6%)

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 35. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:57.121406
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'HUIZ'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for HUIZ: Too Many Requests. Rate limited. Try after a while.
```

---

## 36. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:57.353979
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'HUIZ'}`
- **Output Length:** 707 chars

### Output
```
## Analyst Recommendation Trends for HUIZ

### 2026-04-01
- **Strong Buy**: 3
- **Buy**: 3
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 7

**Sentiment**: 85.7% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 3
- **Buy**: 3
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 7

**Sentiment**: 85.7% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 3
- **Buy**: 3
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 7

**Sentiment**: 85.7% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 3
- **Buy**: 3
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
- **Timestamp:** 2026-04-13T14:17:57.395874
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'HUIZ', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for HUIZ: Too Many Requests. Rate limited. Try after a while.
```

---

## 38. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:58.328675
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'GAM', 'curr_date': '2026-04-13'}`
- **Output Length:** 1557 chars

### Output
```
# Technical Analysis for GAM
**Date:** 2026-04-13
**Current Price:** $61.71

## Price Action
- **Daily Change:** +0.55%
- **5-Day Change:** +4.10%

## RSI (14)
- **Value:** 62.0 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 0.091
- **Signal Line:** -0.299
- **Histogram:** 0.390 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $60.44 (+2.1% from price)
- **200 SMA:** $56.88 (+8.5% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $61.86
- **Middle:** $59.43
- **Lower:** $57.01
- **Band Position:** 97%
- **Bandwidth:** 8.2% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $1.06 (1.7% of price)
- **Level:** Low volatility
- **Suggested Stop-Loss:** $60.12 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 81.7
- **%D:** 67.9
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 17.5 (Strengthening ↑)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $59.84 (+3.1% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 904.9K
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $59.59
- **Current vs VWAP:** +3.6%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $62.82
- **Recent Low:** $56.85
- **Next Resistance:** $62.82 (0.0% (High))
- **Next Support:** $61.41 (23.6%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 39. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:58.494237
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'GAM'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for GAM: Too Many Requests. Rate limited. Try after a while.
```

---

## 40. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:58.734262
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'GAM'}`
- **Output Length:** 43 chars

### Output
```
No recommendation trends data found for GAM
```

---

## 41. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:58.776106
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'GAM', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for GAM: Too Many Requests. Rate limited. Try after a while.
```

---

## 42. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:59.383170
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'ABX', 'curr_date': '2026-04-13'}`
- **Output Length:** 1482 chars

### Output
```
# Technical Analysis for ABX
**Date:** 2026-04-13
**Current Price:** $8.12

## Price Action
- **Daily Change:** +0.74%
- **5-Day Change:** +1.37%

## RSI (14)
- **Value:** 41.8 ↑
- **Signal:** Bearish

## MACD
- **MACD Line:** -0.278
- **Signal Line:** -0.215
- **Histogram:** -0.063 (Weakening ↓)
- **Signal:** Bearish

## Moving Averages
- **50 SMA:** $8.71 (-6.8% from price)
- **200 SMA:** $6.94 (+17.0% from price)
- **Trend:** Downtrend

## Bollinger Bands (20,2)
- **Upper:** $10.13
- **Middle:** $8.69
- **Lower:** $7.25
- **Band Position:** 30%
- **Bandwidth:** 33.2% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $0.52 (6.4% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $7.34 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 49.4
- **%D:** 37.9
- **Signal:** Bearish

## ADX (Trend Strength)
- **ADX:** 34.3 (Strengthening ↑)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $8.52 (-4.7% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** -1.2M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $8.80
- **Current vs VWAP:** -7.7%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $10.53
- **Recent Low:** $7.18
- **Next Resistance:** $8.46 (61.8%)
- **Next Support:** $7.89 (78.6%)

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 43. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:59.540250
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'ABX'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for ABX: Too Many Requests. Rate limited. Try after a while.
```

---

## 44. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:59.770104
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'ABX'}`
- **Output Length:** 706 chars

### Output
```
## Analyst Recommendation Trends for ABX

### 2026-04-01
- **Strong Buy**: 1
- **Buy**: 6
- **Hold**: 2
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 9

**Sentiment**: 77.8% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 1
- **Buy**: 7
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 9

**Sentiment**: 88.9% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 1
- **Buy**: 7
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 9

**Sentiment**: 88.9% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 1
- **Buy**: 7
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 9

**Sentiment**: 88.9% Bullish, 0.0% Bearish


```

---

## 45. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:17:59.807503
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'ABX', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for ABX: Too Many Requests. Rate limited. Try after a while.
```

---

## 46. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:00.443199
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'BATL', 'curr_date': '2026-04-13'}`
- **Output Length:** 1521 chars

### Output
```
# Technical Analysis for BATL
**Date:** 2026-04-13
**Current Price:** $3.20

## Price Action
- **Daily Change:** -10.86%
- **5-Day Change:** -24.53%

## RSI (14)
- **Value:** 36.9 ↓
- **Signal:** Bearish

## MACD
- **MACD Line:** -2.073
- **Signal Line:** -1.428
- **Histogram:** -0.644 (Weakening ↓)
- **Signal:** Bearish

## Moving Averages
- **50 SMA:** $8.19 (-60.9% from price)
- **200 SMA:** $2.98 (+7.2% from price)
- **Trend:** Downtrend

## Bollinger Bands (20,2)
- **Upper:** $17.08
- **Middle:** $7.82
- **Lower:** $-1.45
- **Band Position:** 25%
- **Bandwidth:** 237.0% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $2.24 (70.1% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $-0.16 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 9.8
- **%D:** 10.4
- **Signal:** OVERSOLD ⚡

## ADX (Trend Strength)
- **ADX:** 16.6 (Strengthening ↑)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $6.82 (-53.0% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** 592.5M
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $6.69
- **Current vs VWAP:** -52.2%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $29.70
- **Recent Low:** $2.33
- **Next Resistance:** $8.18 (78.6%)
- **Next Support:** $2.33 (100% (Low))

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 47. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:00.606442
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'BATL'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for BATL: Too Many Requests. Rate limited. Try after a while.
```

---

## 48. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:00.863877
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'BATL'}`
- **Output Length:** 707 chars

### Output
```
## Analyst Recommendation Trends for BATL

### 2024-01-01
- **Strong Buy**: 0
- **Buy**: 0
- **Hold**: 3
- **Sell**: 1
- **Strong Sell**: 2
- **Total Analysts**: 6

**Sentiment**: 0.0% Bullish, 50.0% Bearish

### 2023-12-01
- **Strong Buy**: 0
- **Buy**: 0
- **Hold**: 3
- **Sell**: 1
- **Strong Sell**: 2
- **Total Analysts**: 6

**Sentiment**: 0.0% Bullish, 50.0% Bearish

### 2023-11-01
- **Strong Buy**: 0
- **Buy**: 0
- **Hold**: 3
- **Sell**: 1
- **Strong Sell**: 2
- **Total Analysts**: 6

**Sentiment**: 0.0% Bullish, 50.0% Bearish

### 2023-10-01
- **Strong Buy**: 0
- **Buy**: 0
- **Hold**: 3
- **Sell**: 1
- **Strong Sell**: 2
- **Total Analysts**: 6

**Sentiment**: 0.0% Bullish, 50.0% Bearish


```

---

## 49. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:00.905885
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'BATL', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for BATL: Too Many Requests. Rate limited. Try after a while.
```

---

## 50. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:01.764483
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'AI', 'curr_date': '2026-04-13'}`
- **Output Length:** 1529 chars

### Output
```
# Technical Analysis for AI
**Date:** 2026-04-13
**Current Price:** $8.28

## Price Action
- **Daily Change:** -3.50%
- **5-Day Change:** -5.59%

## RSI (14)
- **Value:** 40.6 ↓
- **Signal:** Bearish

## MACD
- **MACD Line:** -0.284
- **Signal Line:** -0.393
- **Histogram:** 0.109 (Weakening ↓)
- **Signal:** Bullish

## Moving Averages
- **50 SMA:** $9.47 (-12.6% from price)
- **200 SMA:** $15.85 (-47.7% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $9.14
- **Middle:** $8.50
- **Lower:** $7.87
- **Band Position:** 32%
- **Bandwidth:** 14.9% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $0.48 (5.8% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $7.56 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 57.0
- **%D:** 61.3
- **Signal:** Bearish crossover ⚠️

## ADX (Trend Strength)
- **ADX:** 12.4 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $8.65 (-4.3% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** -134.0M
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $8.49
- **Current vs VWAP:** -2.5%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $12.81
- **Recent Low:** $7.68
- **Next Resistance:** $8.77 (78.6%)
- **Next Support:** $7.68 (100% (Low))

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 51. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:01.919369
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'AI'}`
- **Output Length:** 97 chars

### Output
```
Error retrieving insider transactions for AI: Too Many Requests. Rate limited. Try after a while.
```

---

## 52. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:02.172726
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'AI'}`
- **Output Length:** 713 chars

### Output
```
## Analyst Recommendation Trends for AI

### 2026-04-01
- **Strong Buy**: 1
- **Buy**: 1
- **Hold**: 10
- **Sell**: 8
- **Strong Sell**: 4
- **Total Analysts**: 24

**Sentiment**: 8.3% Bullish, 50.0% Bearish

### 2026-03-01
- **Strong Buy**: 1
- **Buy**: 1
- **Hold**: 10
- **Sell**: 8
- **Strong Sell**: 4
- **Total Analysts**: 24

**Sentiment**: 8.3% Bullish, 50.0% Bearish

### 2026-02-01
- **Strong Buy**: 1
- **Buy**: 2
- **Hold**: 9
- **Sell**: 8
- **Strong Sell**: 4
- **Total Analysts**: 24

**Sentiment**: 12.5% Bullish, 50.0% Bearish

### 2026-01-01
- **Strong Buy**: 1
- **Buy**: 2
- **Hold**: 9
- **Sell**: 8
- **Strong Sell**: 4
- **Total Analysts**: 24

**Sentiment**: 12.5% Bullish, 50.0% Bearish


```

---

## 53. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:02.214495
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'AI', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 93 chars

### Output
```
Error retrieving options activity for AI: Too Many Requests. Rate limited. Try after a while.
```

---

## 54. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:03.293249
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'AVGO', 'curr_date': '2026-04-13'}`
- **Output Length:** 1571 chars

### Output
```
# Technical Analysis for AVGO
**Date:** 2026-04-13
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
- **Value:** 378.1M
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

## 55. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:03.456862
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'AVGO'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for AVGO: Too Many Requests. Rate limited. Try after a while.
```

---

## 56. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:03.692813
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

## 57. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:03.733074
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'AVGO', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for AVGO: Too Many Requests. Rate limited. Try after a while.
```

---

## 58. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:04.629116
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'ADM', 'curr_date': '2026-04-13'}`
- **Output Length:** 1533 chars

### Output
```
# Technical Analysis for ADM
**Date:** 2026-04-13
**Current Price:** $69.73

## Price Action
- **Daily Change:** -0.88%
- **5-Day Change:** -4.97%

## RSI (14)
- **Value:** 46.6 ↓
- **Signal:** Bearish

## MACD
- **MACD Line:** 0.704
- **Signal Line:** 1.020
- **Histogram:** -0.316 (Strengthening ↑)
- **Signal:** BEARISH CROSSOVER ⚠️

## Moving Averages
- **50 SMA:** $69.26 (+0.7% from price)
- **200 SMA:** $61.30 (+13.7% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $74.94
- **Middle:** $71.21
- **Lower:** $67.48
- **Band Position:** 30%
- **Bandwidth:** 10.5% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $2.33 (3.3% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $66.24 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 50.2
- **%D:** 62.6
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 15.0 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $71.03 (-1.8% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** 4.5M
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $70.56
- **Current vs VWAP:** -1.2%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $74.19
- **Recent Low:** $61.93
- **Next Resistance:** $71.30 (23.6%)
- **Next Support:** $69.51 (38.2%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 59. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:04.798510
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'ADM'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for ADM: Too Many Requests. Rate limited. Try after a while.
```

---

## 60. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:05.040025
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'ADM'}`
- **Output Length:** 717 chars

### Output
```
## Analyst Recommendation Trends for ADM

### 2026-04-01
- **Strong Buy**: 0
- **Buy**: 2
- **Hold**: 10
- **Sell**: 7
- **Strong Sell**: 1
- **Total Analysts**: 20

**Sentiment**: 10.0% Bullish, 40.0% Bearish

### 2026-03-01
- **Strong Buy**: 0
- **Buy**: 2
- **Hold**: 10
- **Sell**: 7
- **Strong Sell**: 1
- **Total Analysts**: 20

**Sentiment**: 10.0% Bullish, 40.0% Bearish

### 2026-02-01
- **Strong Buy**: 0
- **Buy**: 2
- **Hold**: 10
- **Sell**: 7
- **Strong Sell**: 1
- **Total Analysts**: 20

**Sentiment**: 10.0% Bullish, 40.0% Bearish

### 2026-01-01
- **Strong Buy**: 0
- **Buy**: 2
- **Hold**: 9
- **Sell**: 7
- **Strong Sell**: 1
- **Total Analysts**: 19

**Sentiment**: 10.5% Bullish, 42.1% Bearish


```

---

## 61. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:05.080847
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'ADM', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for ADM: Too Many Requests. Rate limited. Try after a while.
```

---

## 62. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:06.030593
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'AME', 'curr_date': '2026-04-13'}`
- **Output Length:** 1551 chars

### Output
```
# Technical Analysis for AME
**Date:** 2026-04-13
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
- **Value:** 10.4M
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

## 63. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:06.197727
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'AME'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for AME: Too Many Requests. Rate limited. Try after a while.
```

---

## 64. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:06.431259
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

## 65. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:06.473106
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'AME', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for AME: Too Many Requests. Rate limited. Try after a while.
```

---

## 66. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:07.388872
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'MESO', 'curr_date': '2026-04-13'}`
- **Output Length:** 1558 chars

### Output
```
# Technical Analysis for MESO
**Date:** 2026-04-13
**Current Price:** $15.00

## Price Action
- **Daily Change:** +3.09%
- **5-Day Change:** +0.87%

## RSI (14)
- **Value:** 49.9 ↑
- **Signal:** Bearish

## MACD
- **MACD Line:** -0.317
- **Signal Line:** -0.380
- **Histogram:** 0.064 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $15.72 (-4.6% from price)
- **200 SMA:** $15.99 (-6.2% from price)
- **Trend:** STRONG DOWNTREND ⚠️ (DEATH CROSS ⚠️)

## Bollinger Bands (20,2)
- **Upper:** $15.72
- **Middle:** $14.65
- **Lower:** $13.59
- **Band Position:** 66%
- **Bandwidth:** 14.5% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $0.81 (5.4% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $13.79 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 38.7
- **%D:** 35.5
- **Signal:** Bullish crossover ⚡

## ADX (Trend Strength)
- **ADX:** 6.2 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $14.83 (+1.1% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 6.1M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $14.64
- **Current vs VWAP:** +2.5%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $18.49
- **Recent Low:** $13.30
- **Next Resistance:** $15.28 (61.8%)
- **Next Support:** $14.41 (78.6%)

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 67. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:08.575089
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'MESO'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for MESO: Too Many Requests. Rate limited. Try after a while.
```

---

## 68. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:08.810868
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'MESO'}`
- **Output Length:** 711 chars

### Output
```
## Analyst Recommendation Trends for MESO

### 2026-04-01
- **Strong Buy**: 2
- **Buy**: 7
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 10

**Sentiment**: 90.0% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 2
- **Buy**: 7
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 10

**Sentiment**: 90.0% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 2
- **Buy**: 7
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 10

**Sentiment**: 90.0% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 2
- **Buy**: 7
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 10

**Sentiment**: 90.0% Bullish, 0.0% Bearish


```

---

## 69. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:08.852930
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'MESO', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for MESO: Too Many Requests. Rate limited. Try after a while.
```

---

## 70. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:09.764373
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'CGCT', 'curr_date': '2026-04-13'}`
- **Output Length:** 1486 chars

### Output
```
# Technical Analysis for CGCT
**Date:** 2026-04-13
**Current Price:** $10.26

## Price Action
- **Daily Change:** -0.10%
- **5-Day Change:** -0.19%

## RSI (14)
- **Value:** 47.4 ↓
- **Signal:** Bearish

## MACD
- **MACD Line:** -0.000
- **Signal Line:** -0.002
- **Histogram:** 0.001 (Weakening ↓)
- **Signal:** Bullish

## Moving Averages
- **50 SMA:** $10.27 (-0.1% from price)
- **200 SMA:** $10.15 (+1.1% from price)
- **Trend:** Downtrend

## Bollinger Bands (20,2)
- **Upper:** $10.29
- **Middle:** $10.26
- **Lower:** $10.23
- **Band Position:** 47%
- **Bandwidth:** 0.6% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $0.03 (0.3% of price)
- **Level:** Low volatility
- **Suggested Stop-Loss:** $10.22 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 42.1
- **%D:** 46.6
- **Signal:** Bearish

## ADX (Trend Strength)
- **ADX:** 29.4 (Weakening ↓)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $10.27 (-0.1% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** 7.5M
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $10.27
- **Current vs VWAP:** -0.1%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $10.35
- **Recent Low:** $10.23
- **Next Resistance:** $10.28 (61.8%)
- **Next Support:** $10.26 (78.6%)

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 71. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:09.984858
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'CGCT'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for CGCT: Too Many Requests. Rate limited. Try after a while.
```

---

## 72. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:10.230068
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'CGCT'}`
- **Output Length:** 44 chars

### Output
```
No recommendation trends data found for CGCT
```

---

## 73. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:10.268276
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'CGCT', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for CGCT: Too Many Requests. Rate limited. Try after a while.
```

---

## 74. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:11.333305
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'GF', 'curr_date': '2026-04-13'}`
- **Output Length:** 1558 chars

### Output
```
# Technical Analysis for GF
**Date:** 2026-04-13
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
- **Value:** 969.2K
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

## 75. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:12.575735
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'GF'}`
- **Output Length:** 97 chars

### Output
```
Error retrieving insider transactions for GF: Too Many Requests. Rate limited. Try after a while.
```

---

## 76. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:12.809153
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'GF'}`
- **Output Length:** 42 chars

### Output
```
No recommendation trends data found for GF
```

---

## 77. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:12.847887
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'GF', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 93 chars

### Output
```
Error retrieving options activity for GF: Too Many Requests. Rate limited. Try after a while.
```

---

## 78. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:13.934990
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'MKZR', 'curr_date': '2026-04-13'}`
- **Output Length:** 1572 chars

### Output
```
# Technical Analysis for MKZR
**Date:** 2026-04-13
**Current Price:** $3.26

## Price Action
- **Daily Change:** -1.21%
- **5-Day Change:** -3.98%

## RSI (14)
- **Value:** 36.5 ↓
- **Signal:** Bearish

## MACD
- **MACD Line:** -0.126
- **Signal Line:** -0.094
- **Histogram:** -0.031 (Strengthening ↑)
- **Signal:** BEARISH CROSSOVER ⚠️

## Moving Averages
- **50 SMA:** $3.78 (-13.8% from price)
- **200 SMA:** $4.82 (-32.3% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $4.03
- **Middle:** $3.63
- **Lower:** $3.24
- **Band Position:** 3%
- **Bandwidth:** 22.0% (volatility indicator)
- **Signal:** AT LOWER BAND - Potential bounce ⚡

## ATR (Volatility)
- **ATR:** $0.25 (7.7% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $2.89 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 17.1
- **%D:** 22.4
- **Signal:** Bearish crossover ⚠️

## ADX (Trend Strength)
- **ADX:** 12.2 (Strengthening ↑)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $3.58 (-8.8% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** -44.6K
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $3.65
- **Current vs VWAP:** -10.7%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $4.70
- **Recent Low:** $3.25
- **Next Resistance:** $3.56 (78.6%)
- **Next Support:** $3.25 (100% (Low))

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 79. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:14.093742
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'MKZR'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for MKZR: Too Many Requests. Rate limited. Try after a while.
```

---

## 80. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:14.329884
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'MKZR'}`
- **Output Length:** 44 chars

### Output
```
No recommendation trends data found for MKZR
```

---

## 81. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:14.371462
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'MKZR', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for MKZR: Too Many Requests. Rate limited. Try after a while.
```

---

## 82. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:15.222227
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'XZO', 'curr_date': '2026-04-13'}`
- **Output Length:** 1520 chars

### Output
```
# Technical Analysis for XZO
**Date:** 2026-04-13
**Current Price:** $14.87

## Price Action
- **Daily Change:** -4.43%
- **5-Day Change:** +3.99%

## RSI (14)
- **Value:** 47.2 ↑
- **Signal:** Bearish

## MACD
- **MACD Line:** -0.304
- **Signal Line:** -0.498
- **Histogram:** 0.194 (Weakening ↓)
- **Signal:** Bullish

## Moving Averages
- **50 SMA:** $15.87 (-6.3% from price)
- **200 SMA:** $18.02 (-17.5% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $16.18
- **Middle:** $14.84
- **Lower:** $13.51
- **Band Position:** 51%
- **Bandwidth:** 18.0% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $0.83 (5.6% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $13.62 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 65.9
- **%D:** 59.3
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 14.8 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $14.96 (-0.6% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** -2.0M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $14.81
- **Current vs VWAP:** +0.4%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $21.25
- **Recent Low:** $13.31
- **Next Resistance:** $15.01 (78.6%)
- **Next Support:** $13.31 (100% (Low))

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 83. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:16.480662
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'XZO'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for XZO: Too Many Requests. Rate limited. Try after a while.
```

---

## 84. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:16.709506
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'XZO'}`
- **Output Length:** 706 chars

### Output
```
## Analyst Recommendation Trends for XZO

### 2026-04-01
- **Strong Buy**: 2
- **Buy**: 4
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 7

**Sentiment**: 85.7% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 2
- **Buy**: 4
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 7

**Sentiment**: 85.7% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 2
- **Buy**: 4
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 7

**Sentiment**: 85.7% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 2
- **Buy**: 4
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 7

**Sentiment**: 85.7% Bullish, 0.0% Bearish


```

---

## 85. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:16.753081
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'XZO', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for XZO: Too Many Requests. Rate limited. Try after a while.
```

---

## 86. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:17.682241
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'NKE', 'curr_date': '2026-04-13'}`
- **Output Length:** 1547 chars

### Output
```
# Technical Analysis for NKE
**Date:** 2026-04-13
**Current Price:** $42.62

## Price Action
- **Daily Change:** -3.14%
- **5-Day Change:** -3.20%

## RSI (14)
- **Value:** 22.8 ↑
- **Signal:** OVERSOLD ⚡

## MACD
- **MACD Line:** -4.037
- **Signal Line:** -3.474
- **Histogram:** -0.563 (Weakening ↓)
- **Signal:** Bearish

## Moving Averages
- **50 SMA:** $56.63 (-24.7% from price)
- **200 SMA:** $65.34 (-34.8% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $59.23
- **Middle:** $49.76
- **Lower:** $40.28
- **Band Position:** 12%
- **Bandwidth:** 38.1% (volatility indicator)
- **Signal:** Near lower band

## ATR (Volatility)
- **ATR:** $1.85 (4.3% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $39.84 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 7.9
- **%D:** 10.1
- **Signal:** OVERSOLD ⚡

## ADX (Trend Strength)
- **ADX:** 62.4 (Strengthening ↑)
- **Interpretation:** VERY STRONG TREND ⚡

## 20 EMA
- **Value:** $49.00 (-13.0% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** -341.4M
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $47.65
- **Current vs VWAP:** -10.6%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $68.04
- **Recent Low:** $42.36
- **Next Resistance:** $47.86 (78.6%)
- **Next Support:** $42.36 (100% (Low))

## Summary
- **Key Signals:** RSI oversold, Below 50 SMA

```

---

## 87. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:17.844291
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'NKE'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for NKE: Too Many Requests. Rate limited. Try after a while.
```

---

## 88. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:18.092224
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

## 89. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:18.134822
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'NKE', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for NKE: Too Many Requests. Rate limited. Try after a while.
```

---

## 90. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:19.041824
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'KYN', 'curr_date': '2026-04-13'}`
- **Output Length:** 1531 chars

### Output
```
# Technical Analysis for KYN
**Date:** 2026-04-13
**Current Price:** $13.85

## Price Action
- **Daily Change:** -0.43%
- **5-Day Change:** -0.43%

## RSI (14)
- **Value:** 46.9 ↓
- **Signal:** Bearish

## MACD
- **MACD Line:** 0.033
- **Signal Line:** 0.095
- **Histogram:** -0.062 (Strengthening ↑)
- **Signal:** BEARISH CROSSOVER ⚠️

## Moving Averages
- **50 SMA:** $13.79 (+0.4% from price)
- **200 SMA:** $12.25 (+13.1% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $14.41
- **Middle:** $14.05
- **Lower:** $13.69
- **Band Position:** 22%
- **Bandwidth:** 5.1% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $0.29 (2.1% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $13.41 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 28.5
- **%D:** 33.3
- **Signal:** Bearish

## ADX (Trend Strength)
- **ADX:** 6.1 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $13.98 (-0.9% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** 7.8M
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $14.08
- **Current vs VWAP:** -1.6%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $14.69
- **Recent Low:** $12.79
- **Next Resistance:** $13.96 (38.2%)
- **Next Support:** $13.74 (50.0%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 91. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:19.213505
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'KYN'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for KYN: Too Many Requests. Rate limited. Try after a while.
```

---

## 92. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:19.475312
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'KYN'}`
- **Output Length:** 43 chars

### Output
```
No recommendation trends data found for KYN
```

---

## 93. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:19.516463
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'KYN', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for KYN: Too Many Requests. Rate limited. Try after a while.
```

---

## 94. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:20.410324
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'NMM', 'curr_date': '2026-04-13'}`
- **Output Length:** 1527 chars

### Output
```
# Technical Analysis for NMM
**Date:** 2026-04-13
**Current Price:** $69.17

## Price Action
- **Daily Change:** -1.33%
- **5-Day Change:** -2.56%

## RSI (14)
- **Value:** 54.7 ↓
- **Signal:** Bullish

## MACD
- **MACD Line:** 1.412
- **Signal Line:** 1.120
- **Histogram:** 0.292 (Weakening ↓)
- **Signal:** Bullish

## Moving Averages
- **50 SMA:** $65.57 (+5.5% from price)
- **200 SMA:** $52.23 (+32.4% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $72.94
- **Middle:** $66.89
- **Lower:** $60.84
- **Band Position:** 69%
- **Bandwidth:** 18.1% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $2.75 (4.0% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $65.05 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 73.5
- **%D:** 74.7
- **Signal:** Bearish crossover ⚠️

## ADX (Trend Strength)
- **ADX:** 19.4 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $67.80 (+2.0% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 3.2M
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $66.75
- **Current vs VWAP:** +3.6%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $74.21
- **Recent Low:** $58.30
- **Next Resistance:** $70.46 (23.6%)
- **Next Support:** $68.13 (38.2%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 95. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:20.567152
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'NMM'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for NMM: Too Many Requests. Rate limited. Try after a while.
```

---

## 96. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:20.808477
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'NMM'}`
- **Output Length:** 706 chars

### Output
```
## Analyst Recommendation Trends for NMM

### 2026-04-01
- **Strong Buy**: 3
- **Buy**: 3
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 7

**Sentiment**: 85.7% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 3
- **Buy**: 3
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 7

**Sentiment**: 85.7% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 2
- **Buy**: 3
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 6

**Sentiment**: 83.3% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 2
- **Buy**: 3
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 6

**Sentiment**: 83.3% Bullish, 0.0% Bearish


```

---

## 97. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:20.857515
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'NMM', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for NMM: Too Many Requests. Rate limited. Try after a while.
```

---

## 98. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:22.174093
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'ADI', 'curr_date': '2026-04-13'}`
- **Output Length:** 1583 chars

### Output
```
# Technical Analysis for ADI
**Date:** 2026-04-13
**Current Price:** $350.14

## Price Action
- **Daily Change:** -0.35%
- **5-Day Change:** +6.96%

## RSI (14)
- **Value:** 67.0 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 5.266
- **Signal Line:** 0.592
- **Histogram:** 4.674 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $327.20 (+7.0% from price)
- **200 SMA:** $269.41 (+30.0% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $348.59
- **Middle:** $319.93
- **Lower:** $291.28
- **Band Position:** 103%
- **Bandwidth:** 17.9% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $10.13 (2.9% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $334.94 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 89.8
- **%D:** 81.2
- **Signal:** OVERBOUGHT ⚠️

## ADX (Trend Strength)
- **ADX:** 18.8 (Strengthening ↑)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $327.07 (+7.1% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 89.8M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $318.89
- **Current vs VWAP:** +9.8%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $362.07
- **Recent Low:** $300.56
- **Next Resistance:** $362.07 (0.0% (High))
- **Next Support:** $347.55 (23.6%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 99. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:22.405125
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'ADI'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for ADI: Too Many Requests. Rate limited. Try after a while.
```

---

## 100. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:22.646835
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'ADI'}`
- **Output Length:** 721 chars

### Output
```
## Analyst Recommendation Trends for ADI

### 2026-04-01
- **Strong Buy**: 12
- **Buy**: 21
- **Hold**: 8
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 41

**Sentiment**: 80.5% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 12
- **Buy**: 20
- **Hold**: 11
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 43

**Sentiment**: 74.4% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 12
- **Buy**: 18
- **Hold**: 13
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 43

**Sentiment**: 69.8% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 12
- **Buy**: 18
- **Hold**: 11
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 41

**Sentiment**: 73.2% Bullish, 0.0% Bearish


```

---

## 101. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:22.690670
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'ADI', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for ADI: Too Many Requests. Rate limited. Try after a while.
```

---

## 102. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:23.647943
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'TMUS', 'curr_date': '2026-04-13'}`
- **Output Length:** 1526 chars

### Output
```
# Technical Analysis for TMUS
**Date:** 2026-04-13
**Current Price:** $195.71

## Price Action
- **Daily Change:** -0.93%
- **5-Day Change:** -1.46%

## RSI (14)
- **Value:** 32.3 ↓
- **Signal:** Bearish

## MACD
- **MACD Line:** -3.684
- **Signal Line:** -1.995
- **Histogram:** -1.690 (Weakening ↓)
- **Signal:** Bearish

## Moving Averages
- **50 SMA:** $209.14 (-6.4% from price)
- **200 SMA:** $217.89 (-10.2% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $220.02
- **Middle:** $207.03
- **Lower:** $194.05
- **Band Position:** 6%
- **Bandwidth:** 12.5% (volatility indicator)
- **Signal:** Near lower band

## ATR (Volatility)
- **ATR:** $5.30 (2.7% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $187.76 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 11.4
- **%D:** 19.2
- **Signal:** OVERSOLD ⚡

## ADX (Trend Strength)
- **ADX:** 30.6 (Strengthening ↑)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $205.35 (-4.7% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** 6.9M
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $207.21
- **Current vs VWAP:** -5.6%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $223.67
- **Recent Low:** $185.36
- **Next Resistance:** $200.00 (61.8%)
- **Next Support:** $193.56 (78.6%)

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 103. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:23.805826
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'TMUS'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for TMUS: Too Many Requests. Rate limited. Try after a while.
```

---

## 104. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:24.048841
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'TMUS'}`
- **Output Length:** 719 chars

### Output
```
## Analyst Recommendation Trends for TMUS

### 2026-04-01
- **Strong Buy**: 6
- **Buy**: 21
- **Hold**: 10
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 37

**Sentiment**: 73.0% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 6
- **Buy**: 20
- **Hold**: 11
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 37

**Sentiment**: 70.3% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 6
- **Buy**: 19
- **Hold**: 12
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 37

**Sentiment**: 67.6% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 6
- **Buy**: 20
- **Hold**: 11
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 37

**Sentiment**: 70.3% Bullish, 0.0% Bearish


```

---

## 105. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:24.092202
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'TMUS', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for TMUS: Too Many Requests. Rate limited. Try after a while.
```

---

## 106. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:25.014582
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'VZ', 'curr_date': '2026-04-13'}`
- **Output Length:** 1554 chars

### Output
```
# Technical Analysis for VZ
**Date:** 2026-04-13
**Current Price:** $46.04

## Price Action
- **Daily Change:** -2.19%
- **5-Day Change:** -4.92%

## RSI (14)
- **Value:** 29.4 ↓
- **Signal:** OVERSOLD ⚡

## MACD
- **MACD Line:** -0.320
- **Signal Line:** 0.175
- **Histogram:** -0.495 (Strengthening ↑)
- **Signal:** BEARISH CROSSOVER ⚠️

## Moving Averages
- **50 SMA:** $48.30 (-4.7% from price)
- **200 SMA:** $42.08 (+9.4% from price)
- **Trend:** Downtrend

## Bollinger Bands (20,2)
- **Upper:** $51.33
- **Middle:** $48.99
- **Lower:** $46.64
- **Band Position:** -13%
- **Bandwidth:** 9.6% (volatility indicator)
- **Signal:** AT LOWER BAND - Potential bounce ⚡

## ATR (Volatility)
- **ATR:** $0.96 (2.1% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $44.60 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 11.5
- **%D:** 18.0
- **Signal:** OVERSOLD ⚡

## ADX (Trend Strength)
- **ADX:** 25.2 (Strengthening ↑)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $48.46 (-5.0% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** -3.7M
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $49.01
- **Current vs VWAP:** -6.1%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $50.91
- **Recent Low:** $38.89
- **Next Resistance:** $46.32 (38.2%)
- **Next Support:** $44.90 (50.0%)

## Summary
- **Key Signals:** RSI oversold, Below 50 SMA

```

---

## 107. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:25.175090
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'VZ'}`
- **Output Length:** 97 chars

### Output
```
Error retrieving insider transactions for VZ: Too Many Requests. Rate limited. Try after a while.
```

---

## 108. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:25.419426
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'VZ'}`
- **Output Length:** 717 chars

### Output
```
## Analyst Recommendation Trends for VZ

### 2026-04-01
- **Strong Buy**: 7
- **Buy**: 11
- **Hold**: 16
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 35

**Sentiment**: 51.4% Bullish, 2.9% Bearish

### 2026-03-01
- **Strong Buy**: 7
- **Buy**: 10
- **Hold**: 17
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 35

**Sentiment**: 48.6% Bullish, 2.9% Bearish

### 2026-02-01
- **Strong Buy**: 6
- **Buy**: 11
- **Hold**: 17
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 35

**Sentiment**: 48.6% Bullish, 2.9% Bearish

### 2026-01-01
- **Strong Buy**: 6
- **Buy**: 10
- **Hold**: 16
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 33

**Sentiment**: 48.5% Bullish, 3.0% Bearish


```

---

## 109. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:25.457736
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'VZ', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 93 chars

### Output
```
Error retrieving options activity for VZ: Too Many Requests. Rate limited. Try after a while.
```

---

## 110. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:26.518505
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'AMZN', 'curr_date': '2026-04-13'}`
- **Output Length:** 1572 chars

### Output
```
# Technical Analysis for AMZN
**Date:** 2026-04-13
**Current Price:** $238.38

## Price Action
- **Daily Change:** +2.02%
- **5-Day Change:** +12.03%

## RSI (14)
- **Value:** 71.5 ↑
- **Signal:** OVERBOUGHT ⚠️

## MACD
- **MACD Line:** 3.621
- **Signal Line:** 0.064
- **Histogram:** 3.558 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $213.40 (+11.7% from price)
- **200 SMA:** $224.86 (+6.0% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $231.06
- **Middle:** $212.20
- **Lower:** $193.33
- **Band Position:** 119%
- **Bandwidth:** 17.8% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $6.69 (2.8% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $228.35 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 89.5
- **%D:** 79.4
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 23.5 (Strengthening ↑)
- **Interpretation:** Trending

## 20 EMA
- **Value:** $215.46 (+10.6% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 579.7M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $212.82
- **Current vs VWAP:** +12.0%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $246.35
- **Recent Low:** $196.00
- **Next Resistance:** $246.35 (0.0% (High))
- **Next Support:** $234.47 (23.6%)

## Summary
- **Key Signals:** RSI overbought, Above 50 SMA

```

---

## 111. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:26.675334
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'AMZN'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for AMZN: Too Many Requests. Rate limited. Try after a while.
```

---

## 112. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:26.917760
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'AMZN'}`
- **Output Length:** 719 chars

### Output
```
## Analyst Recommendation Trends for AMZN

### 2026-04-01
- **Strong Buy**: 21
- **Buy**: 50
- **Hold**: 5
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 76

**Sentiment**: 93.4% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 21
- **Buy**: 50
- **Hold**: 5
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 76

**Sentiment**: 93.4% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 21
- **Buy**: 50
- **Hold**: 5
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 76

**Sentiment**: 93.4% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 21
- **Buy**: 52
- **Hold**: 4
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 77

**Sentiment**: 94.8% Bullish, 0.0% Bearish


```

---

## 113. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:26.955620
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'AMZN', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for AMZN: Too Many Requests. Rate limited. Try after a while.
```

---

## 114. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:28.882872
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'COF', 'curr_date': '2026-04-13'}`
- **Output Length:** 1570 chars

### Output
```
# Technical Analysis for COF
**Date:** 2026-04-13
**Current Price:** $193.00

## Price Action
- **Daily Change:** -0.89%
- **5-Day Change:** +4.77%

## RSI (14)
- **Value:** 55.3 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** -1.332
- **Signal Line:** -3.890
- **Histogram:** 2.558 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $196.05 (-1.6% from price)
- **200 SMA:** $214.65 (-10.1% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $193.21
- **Middle:** $183.50
- **Lower:** $173.78
- **Band Position:** 99%
- **Bandwidth:** 10.6% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $5.98 (3.1% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $184.03 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 76.8
- **%D:** 63.8
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 11.2 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $186.82 (+3.3% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 91.0M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $183.36
- **Current vs VWAP:** +5.3%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $226.85
- **Recent Low:** $174.98
- **Next Resistance:** $194.80 (61.8%)
- **Next Support:** $186.08 (78.6%)

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 115. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:29.046322
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'COF'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for COF: Too Many Requests. Rate limited. Try after a while.
```

---

## 116. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:29.295831
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

## 117. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:29.337297
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'COF', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for COF: Too Many Requests. Rate limited. Try after a while.
```

---

## 118. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:30.496056
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'TXN', 'curr_date': '2026-04-13'}`
- **Output Length:** 1552 chars

### Output
```
# Technical Analysis for TXN
**Date:** 2026-04-13
**Current Price:** $214.73

## Price Action
- **Daily Change:** -0.12%
- **5-Day Change:** +7.68%

## RSI (14)
- **Value:** 66.5 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 2.067
- **Signal Line:** -1.128
- **Histogram:** 3.194 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $206.66 (+3.9% from price)
- **200 SMA:** $188.55 (+13.9% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $212.44
- **Middle:** $195.94
- **Lower:** $179.45
- **Band Position:** 107%
- **Bandwidth:** 16.8% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $5.89 (2.7% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $205.89 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 90.7
- **%D:** 83.1
- **Signal:** OVERBOUGHT ⚠️

## ADX (Trend Strength)
- **ADX:** 20.1 (Weakening ↓)
- **Interpretation:** Trending

## 20 EMA
- **Value:** $200.42 (+7.1% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 12.6M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $195.10
- **Current vs VWAP:** +10.1%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $231.32
- **Recent Low:** $184.90
- **Next Resistance:** $220.36 (23.6%)
- **Next Support:** $213.59 (38.2%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 119. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:30.729919
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'TXN'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for TXN: Too Many Requests. Rate limited. Try after a while.
```

---

## 120. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:30.979708
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'TXN'}`
- **Output Length:** 722 chars

### Output
```
## Analyst Recommendation Trends for TXN

### 2026-04-01
- **Strong Buy**: 5
- **Buy**: 11
- **Hold**: 22
- **Sell**: 5
- **Strong Sell**: 1
- **Total Analysts**: 44

**Sentiment**: 36.4% Bullish, 13.6% Bearish

### 2026-03-01
- **Strong Buy**: 5
- **Buy**: 11
- **Hold**: 23
- **Sell**: 5
- **Strong Sell**: 1
- **Total Analysts**: 45

**Sentiment**: 35.6% Bullish, 13.3% Bearish

### 2026-02-01
- **Strong Buy**: 5
- **Buy**: 11
- **Hold**: 23
- **Sell**: 5
- **Strong Sell**: 1
- **Total Analysts**: 45

**Sentiment**: 35.6% Bullish, 13.3% Bearish

### 2026-01-01
- **Strong Buy**: 5
- **Buy**: 11
- **Hold**: 21
- **Sell**: 6
- **Strong Sell**: 1
- **Total Analysts**: 44

**Sentiment**: 36.4% Bullish, 15.9% Bearish


```

---

## 121. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:31.024782
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'TXN', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for TXN: Too Many Requests. Rate limited. Try after a while.
```

---

## 122. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:32.046210
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'AVT', 'curr_date': '2026-04-13'}`
- **Output Length:** 1568 chars

### Output
```
# Technical Analysis for AVT
**Date:** 2026-04-13
**Current Price:** $67.03

## Price Action
- **Daily Change:** +0.13%
- **5-Day Change:** +7.40%

## RSI (14)
- **Value:** 66.6 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 1.096
- **Signal Line:** 0.347
- **Histogram:** 0.748 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $63.12 (+6.2% from price)
- **200 SMA:** $53.82 (+24.5% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $66.66
- **Middle:** $61.61
- **Lower:** $56.56
- **Band Position:** 104%
- **Bandwidth:** 16.4% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $1.77 (2.6% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $64.37 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 90.5
- **%D:** 83.7
- **Signal:** OVERBOUGHT ⚠️

## ADX (Trend Strength)
- **ADX:** 19.8 (Strengthening ↑)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $62.77 (+6.8% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 4.8M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $61.48
- **Current vs VWAP:** +9.0%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $67.92
- **Recent Low:** $58.04
- **Next Resistance:** $67.92 (0.0% (High))
- **Next Support:** $65.58 (23.6%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 123. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:33.237075
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'AVT'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for AVT: Too Many Requests. Rate limited. Try after a while.
```

---

## 124. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:33.475433
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'AVT'}`
- **Output Length:** 146 chars

### Output
```
Error fetching recommendation trends for AVT: FinnhubAPIException(status_code: 429): API limit reached. Please try again later. Remaining Limit: 0
```

---

## 125. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:33.512566
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'AVT', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for AVT: Too Many Requests. Rate limited. Try after a while.
```

---

## 126. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:34.511540
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'ALOT', 'curr_date': '2026-04-13'}`
- **Output Length:** 1557 chars

### Output
```
# Technical Analysis for ALOT
**Date:** 2026-04-13
**Current Price:** $11.57

## Price Action
- **Daily Change:** -0.09%
- **5-Day Change:** +23.09%

## RSI (14)
- **Value:** 76.5 ↑
- **Signal:** OVERBOUGHT ⚠️

## MACD
- **MACD Line:** 0.533
- **Signal Line:** 0.225
- **Histogram:** 0.307 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $9.25 (+25.1% from price)
- **200 SMA:** $9.67 (+19.6% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $11.36
- **Middle:** $9.38
- **Lower:** $7.40
- **Band Position:** 105%
- **Bandwidth:** 42.3% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $0.51 (4.4% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $10.81 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 86.6
- **%D:** 75.6
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 45.6 (Strengthening ↑)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $9.75 (+18.7% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 553.4K
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $9.82
- **Current vs VWAP:** +17.8%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $11.63
- **Recent Low:** $8.29
- **Next Resistance:** $11.63 (0.0% (High))
- **Next Support:** $10.84 (23.6%)

## Summary
- **Key Signals:** RSI overbought, Above 50 SMA

```

---

## 127. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:34.745296
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'ALOT'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for ALOT: Too Many Requests. Rate limited. Try after a while.
```

---

## 128. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:34.987752
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'ALOT'}`
- **Output Length:** 147 chars

### Output
```
Error fetching recommendation trends for ALOT: FinnhubAPIException(status_code: 429): API limit reached. Please try again later. Remaining Limit: 0
```

---

## 129. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:35.030847
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'ALOT', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for ALOT: Too Many Requests. Rate limited. Try after a while.
```

---

## 130. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:35.853621
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'OTRK', 'curr_date': '2026-04-13'}`
- **Output Length:** 1471 chars

### Output
```
# Technical Analysis for OTRK
**Date:** 2026-04-13
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

## 131. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:37.081068
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'OTRK'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for OTRK: Too Many Requests. Rate limited. Try after a while.
```

---

## 132. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:37.328350
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'OTRK'}`
- **Output Length:** 147 chars

### Output
```
Error fetching recommendation trends for OTRK: FinnhubAPIException(status_code: 429): API limit reached. Please try again later. Remaining Limit: 0
```

---

## 133. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:37.370445
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'OTRK', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for OTRK: Too Many Requests. Rate limited. Try after a while.
```

---

## 134. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:38.272038
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'GAME', 'curr_date': '2026-04-13'}`
- **Output Length:** 1559 chars

### Output
```
# Technical Analysis for GAME
**Date:** 2026-04-13
**Current Price:** $0.37

## Price Action
- **Daily Change:** +14.55%
- **5-Day Change:** +45.10%

## RSI (14)
- **Value:** 70.3 ↑
- **Signal:** OVERBOUGHT ⚠️

## MACD
- **MACD Line:** -0.002
- **Signal Line:** -0.012
- **Histogram:** 0.011 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $0.30 (+24.1% from price)
- **200 SMA:** $0.63 (-41.4% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $0.34
- **Middle:** $0.28
- **Lower:** $0.22
- **Band Position:** 128%
- **Bandwidth:** 42.1% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $0.04 (10.5% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $0.31 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 46.5
- **%D:** 41.4
- **Signal:** Bullish crossover ⚡

## ADX (Trend Strength)
- **ADX:** 33.7 (Strengthening ↑)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $0.29 (+29.7% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 184.0M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $0.36
- **Current vs VWAP:** +4.2%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $0.46
- **Recent Low:** $0.23
- **Next Resistance:** $0.37 (38.2%)
- **Next Support:** $0.35 (50.0%)

## Summary
- **Key Signals:** RSI overbought, Above 50 SMA

```

---

## 135. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:38.456407
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'GAME'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for GAME: Too Many Requests. Rate limited. Try after a while.
```

---

## 136. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:38.681806
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'GAME'}`
- **Output Length:** 147 chars

### Output
```
Error fetching recommendation trends for GAME: FinnhubAPIException(status_code: 429): API limit reached. Please try again later. Remaining Limit: 0
```

---

## 137. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:38.723803
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'GAME', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for GAME: Too Many Requests. Rate limited. Try after a while.
```

---

## 138. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:39.639080
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'ABVC', 'curr_date': '2026-04-13'}`
- **Output Length:** 1509 chars

### Output
```
# Technical Analysis for ABVC
**Date:** 2026-04-13
**Current Price:** $1.43

## Price Action
- **Daily Change:** +0.00%
- **5-Day Change:** +2.88%

## RSI (14)
- **Value:** 57.3 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** -0.017
- **Signal Line:** -0.078
- **Histogram:** 0.061 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $1.44 (-0.4% from price)
- **200 SMA:** $2.44 (-41.3% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $1.55
- **Middle:** $1.22
- **Lower:** $0.88
- **Band Position:** 82%
- **Bandwidth:** 55.3% (volatility indicator)
- **Signal:** Near upper band

## ATR (Volatility)
- **ATR:** $0.16 (11.3% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $1.19 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 60.2
- **%D:** 52.5
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 33.6 (Strengthening ↑)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $1.28 (+11.5% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 6.0M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $1.32
- **Current vs VWAP:** +8.3%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $2.10
- **Recent Low:** $0.88
- **Next Resistance:** $1.49 (50.0%)
- **Next Support:** $1.35 (61.8%)

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 139. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:39.790561
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'ABVC'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for ABVC: Too Many Requests. Rate limited. Try after a while.
```

---

## 140. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:40.018386
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'ABVC'}`
- **Output Length:** 147 chars

### Output
```
Error fetching recommendation trends for ABVC: FinnhubAPIException(status_code: 429): API limit reached. Please try again later. Remaining Limit: 0
```

---

## 141. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:40.057178
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'ABVC', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for ABVC: Too Many Requests. Rate limited. Try after a while.
```

---

## 142. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:40.892502
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'FBK', 'curr_date': '2026-04-13'}`
- **Output Length:** 1516 chars

### Output
```
# Technical Analysis for FBK
**Date:** 2026-04-13
**Current Price:** $54.90

## Price Action
- **Daily Change:** -2.73%
- **5-Day Change:** +2.29%

## RSI (14)
- **Value:** 57.1 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 0.235
- **Signal Line:** -0.428
- **Histogram:** 0.663 (Weakening ↓)
- **Signal:** Bullish

## Moving Averages
- **50 SMA:** $55.18 (-0.5% from price)
- **200 SMA:** $53.83 (+2.0% from price)
- **Trend:** Downtrend

## Bollinger Bands (20,2)
- **Upper:** $55.88
- **Middle:** $52.55
- **Lower:** $49.22
- **Band Position:** 85%
- **Bandwidth:** 12.7% (volatility indicator)
- **Signal:** Near upper band

## ATR (Volatility)
- **ATR:** $1.42 (2.6% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $52.77 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 82.2
- **%D:** 82.4
- **Signal:** OVERBOUGHT ⚠️

## ADX (Trend Strength)
- **ADX:** 19.5 (Strengthening ↑)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $53.56 (+2.5% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 5.0M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $52.46
- **Current vs VWAP:** +4.6%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $62.13
- **Recent Low:** $49.24
- **Next Resistance:** $55.68 (50.0%)
- **Next Support:** $54.16 (61.8%)

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 143. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:41.091826
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'FBK'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for FBK: Too Many Requests. Rate limited. Try after a while.
```

---

## 144. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:41.345864
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'FBK'}`
- **Output Length:** 146 chars

### Output
```
Error fetching recommendation trends for FBK: FinnhubAPIException(status_code: 429): API limit reached. Please try again later. Remaining Limit: 0
```

---

## 145. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:41.383060
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'FBK', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for FBK: Too Many Requests. Rate limited. Try after a while.
```

---

## 146. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:42.459605
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'WINT', 'curr_date': '2026-04-13'}`
- **Output Length:** 1555 chars

### Output
```
# Technical Analysis for WINT
**Date:** 2026-04-13
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

## 147. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:42.620024
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'WINT'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for WINT: Too Many Requests. Rate limited. Try after a while.
```

---

## 148. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:42.855091
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

## 149. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:42.898879
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'WINT', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for WINT: Too Many Requests. Rate limited. Try after a while.
```

---

## 150. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:43.790939
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'PPSI', 'curr_date': '2026-04-13'}`
- **Output Length:** 1562 chars

### Output
```
# Technical Analysis for PPSI
**Date:** 2026-04-13
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

## 151. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:43.959141
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'PPSI'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for PPSI: Too Many Requests. Rate limited. Try after a while.
```

---

## 152. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:44.206275
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

## 153. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:44.248193
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'PPSI', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for PPSI: Too Many Requests. Rate limited. Try after a while.
```

---

## 154. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:45.162360
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'GS', 'curr_date': '2026-04-13'}`
- **Output Length:** 1578 chars

### Output
```
# Technical Analysis for GS
**Date:** 2026-04-13
**Current Price:** $907.80

## Price Action
- **Daily Change:** +0.45%
- **5-Day Change:** +4.82%

## RSI (14)
- **Value:** 65.4 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 10.531
- **Signal Line:** -1.799
- **Histogram:** 12.330 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $870.58 (+4.3% from price)
- **200 SMA:** $808.39 (+12.3% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $914.37
- **Middle:** $838.56
- **Lower:** $762.75
- **Band Position:** 96%
- **Bandwidth:** 18.1% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $26.85 (3.0% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $867.53 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 87.6
- **%D:** 82.4
- **Signal:** OVERBOUGHT ⚠️

## ADX (Trend Strength)
- **ADX:** 12.6 (Strengthening ↑)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $858.50 (+5.7% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 66.5M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $836.03
- **Current vs VWAP:** +8.6%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $963.32
- **Recent Low:** $780.50
- **Next Resistance:** $920.17 (23.6%)
- **Next Support:** $893.48 (38.2%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 155. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:45.315242
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'GS'}`
- **Output Length:** 97 chars

### Output
```
Error retrieving insider transactions for GS: Too Many Requests. Rate limited. Try after a while.
```

---

## 156. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:45.556516
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'GS'}`
- **Output Length:** 713 chars

### Output
```
## Analyst Recommendation Trends for GS

### 2026-04-01
- **Strong Buy**: 6
- **Buy**: 9
- **Hold**: 16
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 32

**Sentiment**: 46.9% Bullish, 3.1% Bearish

### 2026-03-01
- **Strong Buy**: 6
- **Buy**: 9
- **Hold**: 16
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 32

**Sentiment**: 46.9% Bullish, 3.1% Bearish

### 2026-02-01
- **Strong Buy**: 6
- **Buy**: 9
- **Hold**: 16
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 32

**Sentiment**: 46.9% Bullish, 3.1% Bearish

### 2026-01-01
- **Strong Buy**: 7
- **Buy**: 8
- **Hold**: 16
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 32

**Sentiment**: 46.9% Bullish, 3.1% Bearish


```

---

## 157. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:45.598361
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'GS', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 93 chars

### Output
```
Error retrieving options activity for GS: Too Many Requests. Rate limited. Try after a while.
```

---

## 158. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:46.462117
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'IVDA', 'curr_date': '2026-04-13'}`
- **Output Length:** 1500 chars

### Output
```
# Technical Analysis for IVDA
**Date:** 2026-04-13
**Current Price:** $0.26

## Price Action
- **Daily Change:** +0.00%
- **5-Day Change:** +0.00%

## RSI (14)
- **Value:** 35.4 ↑
- **Signal:** Bearish

## MACD
- **MACD Line:** -0.032
- **Signal Line:** -0.039
- **Histogram:** 0.007 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $0.35 (-25.7% from price)
- **200 SMA:** $1.14 (-77.3% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $0.33
- **Middle:** $0.28
- **Lower:** $0.23
- **Band Position:** 33%
- **Bandwidth:** 36.2% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $0.03 (12.9% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $0.21 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 50.4
- **%D:** 41.6
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 18.1 (Strengthening ↑)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $0.28 (-7.0% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** 458.6M
- **5-Day Trend:** Falling ↓
- **Signal:** Neutral

## VWAP (20-period)
- **VWAP:** $0.31
- **Current vs VWAP:** -15.3%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $0.96
- **Recent Low:** $0.22
- **Next Resistance:** $0.38 (78.6%)
- **Next Support:** $0.22 (100% (Low))

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 159. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:46.619438
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'IVDA'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for IVDA: Too Many Requests. Rate limited. Try after a while.
```

---

## 160. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:46.854798
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'IVDA'}`
- **Output Length:** 707 chars

### Output
```
## Analyst Recommendation Trends for IVDA

### 2025-01-01
- **Strong Buy**: 2
- **Buy**: 4
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 7

**Sentiment**: 85.7% Bullish, 0.0% Bearish

### 2024-12-01
- **Strong Buy**: 2
- **Buy**: 4
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 7

**Sentiment**: 85.7% Bullish, 0.0% Bearish

### 2024-11-01
- **Strong Buy**: 2
- **Buy**: 4
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 7

**Sentiment**: 85.7% Bullish, 0.0% Bearish

### 2024-10-01
- **Strong Buy**: 2
- **Buy**: 4
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 7

**Sentiment**: 85.7% Bullish, 0.0% Bearish


```

---

## 161. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:46.895399
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'IVDA', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for IVDA: Too Many Requests. Rate limited. Try after a while.
```

---

## 162. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:48.159927
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'AAPL', 'curr_date': '2026-04-13'}`
- **Output Length:** 1535 chars

### Output
```
# Technical Analysis for AAPL
**Date:** 2026-04-13
**Current Price:** $260.48

## Price Action
- **Daily Change:** -0.00%
- **5-Day Change:** +0.63%

## RSI (14)
- **Value:** 55.6 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** -0.161
- **Signal Line:** -1.630
- **Histogram:** 1.469 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $260.84 (-0.1% from price)
- **200 SMA:** $250.31 (+4.1% from price)
- **Trend:** Downtrend

## Bollinger Bands (20,2)
- **Upper:** $261.48
- **Middle:** $253.28
- **Lower:** $245.09
- **Band Position:** 94%
- **Bandwidth:** 6.5% (volatility indicator)
- **Signal:** Near upper band

## ATR (Volatility)
- **ATR:** $5.90 (2.3% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $251.63 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 81.0
- **%D:** 72.5
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 10.7 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $256.09 (+1.7% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 1204.3M
- **5-Day Trend:** Falling ↓
- **Signal:** BEARISH DIVERGENCE ⚠️ (distribution)

## VWAP (20-period)
- **VWAP:** $252.70
- **Current vs VWAP:** +3.1%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $280.65
- **Recent Low:** $245.51
- **Next Resistance:** $263.08 (50.0%)
- **Next Support:** $258.93 (61.8%)

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 163. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:48.314440
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'AAPL'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for AAPL: Too Many Requests. Rate limited. Try after a while.
```

---

## 164. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:48.544397
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'AAPL'}`
- **Output Length:** 723 chars

### Output
```
## Analyst Recommendation Trends for AAPL

### 2026-04-01
- **Strong Buy**: 14
- **Buy**: 23
- **Hold**: 15
- **Sell**: 2
- **Strong Sell**: 0
- **Total Analysts**: 54

**Sentiment**: 68.5% Bullish, 3.7% Bearish

### 2026-03-01
- **Strong Buy**: 14
- **Buy**: 22
- **Hold**: 16
- **Sell**: 2
- **Strong Sell**: 0
- **Total Analysts**: 54

**Sentiment**: 66.7% Bullish, 3.7% Bearish

### 2026-02-01
- **Strong Buy**: 14
- **Buy**: 21
- **Hold**: 17
- **Sell**: 2
- **Strong Sell**: 0
- **Total Analysts**: 54

**Sentiment**: 64.8% Bullish, 3.7% Bearish

### 2026-01-01
- **Strong Buy**: 14
- **Buy**: 21
- **Hold**: 16
- **Sell**: 2
- **Strong Sell**: 0
- **Total Analysts**: 53

**Sentiment**: 66.0% Bullish, 3.8% Bearish


```

---

## 165. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:48.582555
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'AAPL', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for AAPL: Too Many Requests. Rate limited. Try after a while.
```

---

## 166. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:50.756215
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'CSCO', 'curr_date': '2026-04-13'}`
- **Output Length:** 1516 chars

### Output
```
# Technical Analysis for CSCO
**Date:** 2026-04-13
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
- **Value:** 369.9M
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

## 167. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:50.991138
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'CSCO'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for CSCO: Too Many Requests. Rate limited. Try after a while.
```

---

## 168. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:51.241560
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

## 169. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:51.283512
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'CSCO', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for CSCO: Too Many Requests. Rate limited. Try after a while.
```

---

## 170. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:52.200645
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'COIN', 'curr_date': '2026-04-13'}`
- **Output Length:** 1537 chars

### Output
```
# Technical Analysis for COIN
**Date:** 2026-04-13
**Current Price:** $167.85

## Price Action
- **Daily Change:** -0.69%
- **5-Day Change:** -3.97%

## RSI (14)
- **Value:** 40.4 ↓
- **Signal:** Bearish

## MACD
- **MACD Line:** -5.613
- **Signal Line:** -4.588
- **Histogram:** -1.025 (Weakening ↓)
- **Signal:** Bearish

## Moving Averages
- **50 SMA:** $179.57 (-6.5% from price)
- **200 SMA:** $277.09 (-39.4% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $213.62
- **Middle:** $182.54
- **Lower:** $151.47
- **Band Position:** 26%
- **Bandwidth:** 34.0% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $11.24 (6.7% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $151.00 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 36.4
- **%D:** 35.6
- **Signal:** Bearish

## ADX (Trend Strength)
- **ADX:** 14.0 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $178.16 (-5.8% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** -87.6M
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $184.56
- **Current vs VWAP:** -9.1%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $213.50
- **Recent Low:** $139.36
- **Next Resistance:** $176.43 (50.0%)
- **Next Support:** $167.68 (61.8%)

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 171. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:52.349248
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'COIN'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for COIN: Too Many Requests. Rate limited. Try after a while.
```

---

## 172. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:52.579057
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

## 173. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:52.681924
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'COIN', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for COIN: Too Many Requests. Rate limited. Try after a while.
```

---

## 174. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:53.767044
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'CARR', 'curr_date': '2026-04-13'}`
- **Output Length:** 1526 chars

### Output
```
# Technical Analysis for CARR
**Date:** 2026-04-13
**Current Price:** $63.34

## Price Action
- **Daily Change:** +3.06%
- **5-Day Change:** +13.94%

## RSI (14)
- **Value:** 65.3 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 0.003
- **Signal Line:** -0.803
- **Histogram:** 0.807 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $60.32 (+5.0% from price)
- **200 SMA:** $60.76 (+4.2% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $61.97
- **Middle:** $57.28
- **Lower:** $52.59
- **Band Position:** 115%
- **Bandwidth:** 16.4% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $2.14 (3.4% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $60.14 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 73.9
- **%D:** 55.8
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 20.9 (Weakening ↓)
- **Interpretation:** Trending

## 20 EMA
- **Value:** $58.16 (+8.9% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** -65.0M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $57.43
- **Current vs VWAP:** +10.3%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $68.33
- **Recent Low:** $53.77
- **Next Resistance:** $64.89 (23.6%)
- **Next Support:** $62.77 (38.2%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 175. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:53.922130
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'CARR'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for CARR: Too Many Requests. Rate limited. Try after a while.
```

---

## 176. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:54.167959
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'CARR'}`
- **Output Length:** 719 chars

### Output
```
## Analyst Recommendation Trends for CARR

### 2026-04-01
- **Strong Buy**: 8
- **Buy**: 12
- **Hold**: 11
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 31

**Sentiment**: 64.5% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 8
- **Buy**: 12
- **Hold**: 11
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 31

**Sentiment**: 64.5% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 8
- **Buy**: 12
- **Hold**: 11
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 31

**Sentiment**: 64.5% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 8
- **Buy**: 12
- **Hold**: 11
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 31

**Sentiment**: 64.5% Bullish, 0.0% Bearish


```

---

## 177. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:54.208250
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'CARR', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for CARR: Too Many Requests. Rate limited. Try after a while.
```

---

## 178. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:55.125152
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'CI', 'curr_date': '2026-04-13'}`
- **Output Length:** 1529 chars

### Output
```
# Technical Analysis for CI
**Date:** 2026-04-13
**Current Price:** $271.25

## Price Action
- **Daily Change:** -2.59%
- **5-Day Change:** -1.61%

## RSI (14)
- **Value:** 49.9 ↓
- **Signal:** Bearish

## MACD
- **MACD Line:** 0.233
- **Signal Line:** -1.362
- **Histogram:** 1.596 (Weakening ↓)
- **Signal:** Bullish

## Moving Averages
- **50 SMA:** $275.34 (-1.5% from price)
- **200 SMA:** $282.22 (-3.9% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $279.26
- **Middle:** $268.11
- **Lower:** $256.96
- **Band Position:** 64%
- **Bandwidth:** 8.3% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $6.65 (2.5% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $261.28 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 77.6
- **%D:** 75.3
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 9.5 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $271.03 (+0.1% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** -19.8M
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $266.87
- **Current vs VWAP:** +1.6%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $296.17
- **Recent Low:** $257.85
- **Next Resistance:** $272.49 (61.8%)
- **Next Support:** $266.05 (78.6%)

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 179. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:55.272499
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'CI'}`
- **Output Length:** 97 chars

### Output
```
Error retrieving insider transactions for CI: Too Many Requests. Rate limited. Try after a while.
```

---

## 180. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:55.510626
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'CI'}`
- **Output Length:** 717 chars

### Output
```
## Analyst Recommendation Trends for CI

### 2026-04-01
- **Strong Buy**: 11
- **Buy**: 18
- **Hold**: 5
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 34

**Sentiment**: 85.3% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 10
- **Buy**: 17
- **Hold**: 6
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 33

**Sentiment**: 81.8% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 10
- **Buy**: 17
- **Hold**: 6
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 33

**Sentiment**: 81.8% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 10
- **Buy**: 17
- **Hold**: 6
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 33

**Sentiment**: 81.8% Bullish, 0.0% Bearish


```

---

## 181. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-13T14:18:55.548390
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'CI', 'num_expirations': 3, 'curr_date': '2026-04-13'}`
- **Output Length:** 93 chars

### Output
```
Error retrieving options activity for CI: Too Many Requests. Rate limited. Try after a while.
```

---

## 182. Rank candidates

- **Type:** `llm`
- **Node:** ranker
- **Timestamp:** 2026-04-13T14:20:09.623290
- **Model:** `gemini-3-pro-preview`
- **Prompt Length:** 147361 chars
- **Output Length:** 2000 chars

### Prompt
```
You are a professional stock analyst selecting the best short-term trading opportunities from a pre-filtered candidate list.

CURRENT DATE: 2026-04-13

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
- **news_catalyst**: Focus on the materiality of the news, whether it's already priced in (check intraday move), and the timeline of impact.
- **sector_rotation**: Focus on relative strength vs sector ETF, whether the stock is a laggard in an accelerating sector.
- **minervini**: Focus on the RS Rating (top 30% = RS>=70, top 10% = RS>=90) as the primary signal. Verify all 6 trend template conditions are met (price structure above rising SMAs). Strongest setups combine RS>=85 with price consolidating near highs (within 10-15% of 52w high) — these have minimal overhead supply. Penalize if RS Rating is borderline (70-75) without other confirming signals.
- **ml_signal**: Use the ML Win Probability as a strong quantitative signal. Scores above 65% deserve significant weight.

HISTORICAL INSIGHTS:
"Historical 1-day win rate: 38.6% (603 tracked)\nHistorical 7-day win rate: 41.9% (585 tracked)\nHistorical 30-day win rate: 34.7% (478 tracked)\n\nBest performing strategies (7-day):\n  - short_squeeze: 60.0% win rate, avg +2.1% return (10 samples)\n  - analyst_upgrade: 51.6% win rate, avg -0.6% return (31 samples)\n  - insider_buying: 45.9% win rate, avg -0.4% return (170 samples)\n\nWORST performing strategies (7-day) \u2014 penalize these heavily in scoring:\n  - pre_earnings_accumulation: 28.6% win rate, avg -1.9% return (7 samples)\n  - social_hype: 18.2% win rate, avg -4.6% return (22 samples)\n  - news_catalyst: 0.0% win rate, avg -8.4% return (8 samples)"

CANDIDATES FOR REVIEW:
### ALB (Priority: CRITICAL)
- **Strategy Match**: minervini
- **Sources**: minervini | **Confluence**: 1 source(s)
- **Quant Pre-Score**: 10/100 | **ML Win Probability**: N/A | **Altman Z-Score**: None | **Piotroski F-Score**: None
- **Price**: $185.76 | **Current Price (numeric)**: 185.75999450683594 | **Intraday**: +0.0% | **Avg Volume**: 1,507,938
- **Short Interest**: N/A
- **Discovery Context**: Minervini Stage 2: P>SMA50>SMA150>SMA200, +260% off 52w low, within 5% of 52w high, RS Rating 100/100
- **Business**: ALB - Business description not available.
- **News**: Albemarle finalized a $650 million cash tender offer for outstanding notes and is targeting $100M–$150M in cost improvements for 2026 to combat flat sales volumes.

**Technical Analysis**:
# Technical Analysis for ALB
**Date:** 2026-04-13
**Current Price:** $173.64

## Price Action
- **Daily Change:** +0.75%
- **5-Day Change:** +0.35%

## RSI (14)
- **Value:** 51.0 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 1.641
- **Signal Line:** 1.771
- **Histogram:** -0.130 (Strengthening ↑)
- **Signal:** BEARISH CROSSOVER ⚠️

## Moving Averages
- **50 SMA:** $170.80 (+1.7% from price)
- **200 SMA:** $119.94 (+44.8% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $186.71
- **Middle:** $171.80
- **Lower:** $156.90
- **Band Position:** 56%
- **Bandwidth:** 17.4% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $8.98 (5.2% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $160.17 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 29.7
- **%D:** 42.5
- **Signal:** Bearish

## ADX (Trend Strength)
- **ADX:** 4.6 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $173.34 (+0.2% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 145.6M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $171.67
- **Current vs VWAP:** +1.1%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $205.49
- **Recent Low:** $154.69
- **Next Resistance:** $174.10 (61.8%)
- **Next Support:** $165.56 (78.6%)

## Summary
- **Key Signals:** Above 50 SMA


**Fundamentals**: N/A

**Insider Transactions**:
Error retrieving insider transactions for ALB: Too Many Requests. Rate limited. Try after a while.

**Analyst Recommendations**:
## Analyst Recommendation Trends for ALB

### 2026-04-01
- **Strong Buy**: 7
- **Buy**: 11
- **Hold**: 11
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 29

**Sentiment**: 62.1% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 7
- **Buy**: 11
- **Hold**: 12
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 30

**Sentiment**: 60.0% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 6
- **Buy**: 11
- **Hold**: 13
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 31

**Sentiment**: 54.8% Bullish, 3.2% Bearish

### 2026-01-01
- **Strong Buy**: 5
- **Buy**: 7
- **Hold**: 18
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 31

**Sentiment**: 38.7% Bullish, 3.2% Bearish



**Options Activity**:
Error retrieving options activity for ALB: Too Many Requests. Rate limited. Try after a while.

**Upcoming Earnings**: Earnings in 23 days (2026-05-06): EPS Est $0.96, Rev Est $1,311,591,595

### APA (Priority: CRITICAL)
- **Strategy Match**: minervini
- **Sources**: minervini | **Confluence**: 1 source(s)
- **Quant Pre-Score**: 10/100 | **ML Win Probability**: N/A | **Altman Z-Score**: None | **Piotroski F-Score**: None
- **Price**: $39.31 | **Current Price (numeric)**: 39.310001373291016 | **Intraday**: +0.0% | **Avg Volume**: 9,580,029
- **Short Interest**: N/A
- **Discovery Context**: Minervini Stage 2: P>SMA50>SMA150>SMA200, +177% off 52w low, within 12% of 52w high, RS Rating 98/100
- **Business**: APA - Business description not available.
- **News**: No significant news found for this ticker.

**Technical Analysis**:
# Technical Analysis for APA
**Date:** 2026-04-13
**Current Price:** $38.63

## Price Action
- **Daily Change:** -0.87%
- **5-Day Change:** -10.20%

## RSI (14)
- **Value:** 52.2 ↓
- **Signal:** Bullish

## MACD
- **MACD Line:** 2.049
- **Signal Line:** 2.776
- **Histogram:** -0.727 (Strengthening ↑)
- **Signal:** BEARISH CROSSOVER ⚠️

## Moving Averages
- **50 SMA:** $33.45 (+15.5% from price)
- **200 SMA:** $25.24 (+53.1% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $45.97
- **Middle:** $39.95
- **Lower:** $33.92
- **Band Position:** 39%
- **Bandwidth:** 30.1% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $2.12 (5.5% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $35.46 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 41.7
- **%D:** 51.6
- **Signal:** Bearish

## ADX (Trend Strength)
- **ADX:** 22.0 (Weakening ↓)
- **Interpretation:** Trending

## 20 EMA
- **Value:** $39.23 (-1.5% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** 122.8M
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $39.99
- **Current vs VWAP:** -3.4%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $45.66
- **Recent Low:** $25.30
- **Next Resistance:** $40.86 (23.6%)
- **Next Support:** $37.88 (38.2%)

## Summary
- **Key Signals:** Above 50 SMA


**Fundamentals**: N/A

**Insider Transactions**:
Error retrieving insider transactions for APA: Too Many Requests. Rate limited. Try after a while.

**Analyst Recommendations**:
## Analyst Recommendation Trends for APA

### 2026-04-01
- **Strong Buy**: 3
- **Buy**: 7
- **Hold**: 19
- **Sell**: 5
- **Strong Sell**: 0
- **Total Analysts**: 34

**Sentiment**: 29.4% Bullish, 14.7% Bearish

### 2026-03-01
- **Strong Buy**: 3
- **Buy**: 7
- **Hold... [truncated]
```

### Output
```
{
  "rankings": [
    {
      "rank": 1,
      "ticker": "OSCR",
      "company_name": "OSCR",
      "current_price": 14.40999984741211,
      "strategy_match": "insider_buying",
      "final_score": 88,
      "confidence": 9,
      "risk_level": "moderate",
      "reason": "CEO Mark Bertolini aggressively purchased $11.9M in shares, signaling profound internal confidence in the company's trajectory. This insider accumulation arrives right after the CFO reaffirmed an optimistic 2026 outlook targeting 3.4 million enrollees and maiden GAAP profitability, giving the market a clear fundamental catalyst. Technically, the stock is in a solid uptrend trading 9.6% above its 50 SMA ($13.19) with a bullish MACD crossover (+0.366 histogram) indicating accelerating momentum. The key risk is its high historical volatility (ATR 5.1%), meaning broader market weakness could trigger sharp pullbacks.",
      "description": "OSCR - Business description not available."
    },
    {
      "rank": 2,
      "ticker": "ALB",
      "company_name": "ALB",
      "current_price": 185.75999450683594,
      "strategy_match": "minervini",
      "final_score": 85,
      "confidence": 8,
      "risk_level": "high",
      "reason": "ALB hits the top tier of Minervini criteria with a flawless 100/100 RS Rating and is trading within 5% of its 52-week high after an impressive 260% run off its lows. A recently announced $650M tender offer and corporate targeting of $100M-$150M in cost improvements provide immediate fundamental backing to this technical strength. The price structure remains solidly supported above its rising 50 SMA ($170.80) with a reasonable RSI of 51.0, leaving significant room for upside before becoming overbought. A high ATR (5.2%) and a recent bearish MACD crossover warn of potential short-term choppiness, which aggressive traders must manage.",
      "description": "ALB - Business description not available."
    },
    {
      "rank": 3,
      "ticker": "AMAT",
      "company_name"
```

---

