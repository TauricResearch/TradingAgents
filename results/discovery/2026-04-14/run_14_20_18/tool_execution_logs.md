# Tool Execution Logs - 2026-04-14

## 1. Check average volume (batch)

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:21:09.782753
- **Tool:** `get_average_volume_batch`
- **Parameters:** `{'symbols': ['ALB', 'AA', 'AMAT', 'APA', 'AMD', 'APH', 'COE', 'BETR', 'CHPT', 'XAGE', 'ABX', 'ACHC', 'AI', 'ARCT', 'ANAB', 'AVGO', 'ADM', 'AME', 'BAC', 'SMC', 'MESO', 'HYMC', 'SG', 'CGCT', 'HTO', 'BOT', 'RPAY', 'GF', 'MNR', 'ACET', 'WKSP', 'CNXC', 'FROPX', 'FRBBX', 'TER', 'NFLX', 'GS', 'ADI', 'HOVR', 'WFC', 'THCH', 'JNJ', 'KMX', 'JPM', 'EQBK', 'BLK', 'DTST', 'SURG', 'AAPL', 'AMZN', 'AMT', 'CSCO', 'COIN', 'BSX', 'AKAM', 'AXP', 'CARR', 'CRM', 'RKLB', 'MDAI', 'OBAI', 'IV', 'OPEN'], 'lookback_days': 10, 'curr_date': '2026-04-14', 'cache_key': 'default'}`
- **Output Length:** 10899 chars

### Output
```
{"ALB": {"symbol": "ALB", "average_volume": 1557867.5, "latest_volume": 355075.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-14", "error": null}, "AA": {"symbol": "AA", "average_volume": 5377772.2, "latest_volume": 669322.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-14", "error": null}, "AMAT": {"symbol": "AMAT", "average_volume": 5076602.3, "latest_volume": 1009623.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-14", "error": null}, "APA": {"symbol": "APA", "average_volume": 9073694.2, "latest_volume": 1400042.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-14", "error": null}, "AMD": {"symbol": "AMD", "average_volume": 30757993.3, "latest_volume": 6879633.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-14", "error": null}, "APH": {"symbol": "APH", "average_volume": 6474509.6, "latest_volume": 1420296.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-14", "error": null}, "AVGO": {"symbol": "AVGO", "average_volume": 22043500.1, "latest_volume": 6405001.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-14", "error": null}, "ADM": {"symbol": "ADM", "average_volume": 2854898.8, "latest_volume": 244588.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-14", "error": null}, "AME": {"symbol": "AME", "average_volume": 970992.1, "latest_volume": 67021.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-14", "error": null}, "BAC": {"symbol": "BAC", "average_volume": 29409193.4, "latest_volume": 6033434.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-14", "error": null}, "TER": {"symbol": "TER", "average_volume": 2910372.0, "latest_volume": 544720.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-14", "error": null}, "NFLX": {"symbol": "NFLX", "average_volume": 30763224.3, "latest_volume": 6008143.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-14", "error": null}, "GS": {"symbol": "GS", "average_volume": 1981993.8, "latest_volume": 553738.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-14", "error": null}, "JNJ": {"symbol": "JNJ", "average_volume": 6408551.3, "latest_volume": 2650613.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-14", "error": null}, "KMX": {"symbol": "KMX", "average_volume": 3375477.6, "latest_volume": 3500576.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-14", "error": null}, "JPM": {"symbol": "JPM", "average_volume": 8048682.2, "latest_volume": 3042422.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-14", "error": null}, "BLK": {"symbol": "BLK", "average_volume": 678019.6, "latest_volume": 341996.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-14", "error": null}, "AAPL": {"symbol": "AAPL", "average_volume": 35551528.7, "latest_volume": 7447987.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-14", "error": null}, "AMZN": {"symbol": "AMZN", "average_volume": 42061772.0, "latest_volume": 15154420.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-14", "error": null}, "AMT": {"symbol": "AMT", "average_volume": 3068733.7, "latest_volume": 676537.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-14", "error": null}, "CSCO": {"symbol": "CSCO", "average_volume": 16608447.2, "latest_volume": 2417872.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-14", "error": null}, "COIN": {"symbol": "COIN", "average_volume": 8429062.7, "latest_volume": 3312227.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-14", "error": null}, "BSX": {"symbol": "BSX", "average_volume": 14925863.8, "latest_volume": 1819938.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-14", "error": null}, "AKAM": {"symbol": "AKAM", "average_volume": 5196952.5, "latest_volume": 1577525.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-14", "error": null}, "AXP": {"symbol": "AXP", "average_volume": 2401293.7, "latest_volume": 314537.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-14", "error": null}, "CARR": {"symbol": "CARR", "average_volume": 5416146.3, "latest_volume": 566363.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-14", "error": null}, "CRM": {"symbol": "CRM", "average_volume": 12834930.9, "latest_volume": 2449009.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-14", "error": null}, "OPEN": {"symbol": "OPEN", "average_volume": 24526766.0, "latest_volume": 6413460.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-14", "error": null}, "COE": {"symbol": "COE", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-14", "error": "No volume data found"}, "BETR": {"symbol": "BETR", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-14", "error": "No volume data found"}, "CHPT": {"symbol": "CHPT", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-14", "error": "No volume data found"}, "XAGE": {"symbol": "XAGE", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-14", "error": "No volume data found"}, "ABX": {"symbol": "ABX", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-14", "error": "No volume data found"}, "ACHC": {"symbol": "ACHC", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-14", "error": "No volume data found"}, "AI": {"symbol": "AI", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-14", "error": "No volume data found"}, "ARCT": {"symbol": "ARCT", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-14", "error": "No volume data found"}, "ANAB": {"symbol": "ANAB", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-14", "error": "No volume data found"}, "SMC": {"symbol": "SMC", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-14", "error": "No volume data found"}, "MESO": {"symbol": "MESO", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-14", "error": "No volume data found"}, "HYMC": {"symbol": "HYMC", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-14", "error": "No volume data found"}, "SG": {"symbol": "SG", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-14", "error": "No volume data found"}, "CGCT": {"symbol": "CGCT", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-14", "error": "No volume data found"}, "HTO": {"symbol": "HTO", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-14", "error": "No volume data found"}, "BOT": {"symbol": "BOT", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-14", "error": "No volume data found"}, "RPAY": {"symbol": "RPAY", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-14", "error": "No volume data found"}, "GF": {"symbol": "GF", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-14", "error": "No volume data found"}, "MNR": {"symbol": "MNR", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-14", "error": "No volume data found"}, "ACET": {"symbol": "ACET", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-14", "error": "No volume data found"}, "WKSP": {"symbol": "WKSP", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-14", "error": "No volume data found"}, "CNXC": {"symbol": "CNXC", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-14", "error": "No volume data found"}, "FROPX": {"symbol": "FROPX", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-14", "error": "No volume data found"}, "FRBBX": {"symbol": "FRBBX", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-14", "error": "No volume data found"}, "ADI": {"symbol": "ADI", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-14", "error": "No volume data found"}, "HOVR": {"symbol": "HOVR", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-14", "error": "No volume data found"}, "WFC": {"symbol": "WFC", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-14", "error": "No volume data found"}, "THCH": {"symbol": "THCH", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-14", "error": "No volume data found"}, "EQBK": {"symbol": "EQBK", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-14", "error": "No volume data found"}, "DTST": {"symbol": "DTST", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-14", "error": "No volume data ... [truncated]
```

---

## 2. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:29.029458
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'ALB', 'curr_date': '2026-04-14'}`
- **Output Length:** 1558 chars

### Output
```
# Technical Analysis for ALB
**Date:** 2026-04-14
**Current Price:** $185.43

## Price Action
- **Daily Change:** +6.79%
- **5-Day Change:** +6.86%

## RSI (14)
- **Value:** 60.0 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 2.406
- **Signal Line:** 1.898
- **Histogram:** 0.508 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $170.91 (+8.5% from price)
- **200 SMA:** $120.57 (+53.8% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $187.81
- **Middle:** $173.16
- **Lower:** $158.51
- **Band Position:** 92%
- **Bandwidth:** 16.9% (volatility indicator)
- **Signal:** Near upper band

## ATR (Volatility)
- **ATR:** $9.46 (5.1% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $171.24 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 46.3
- **%D:** 43.8
- **Signal:** Bullish crossover ⚡

## ADX (Trend Strength)
- **ADX:** 9.4 (Strengthening ↑)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $174.49 (+6.3% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 151.4M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $173.19
- **Current vs VWAP:** +7.1%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $205.49
- **Recent Low:** $154.69
- **Next Resistance:** $186.08 (38.2%)
- **Next Support:** $180.09 (50.0%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 3. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:29.106941
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
- **Timestamp:** 2026-04-14T14:23:29.264777
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
- **Timestamp:** 2026-04-14T14:23:29.274915
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'ALB', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for ALB: Too Many Requests. Rate limited. Try after a while.
```

---

## 6. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:29.753114
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'AA', 'curr_date': '2026-04-14'}`
- **Output Length:** 1502 chars

### Output
```
# Technical Analysis for AA
**Date:** 2026-04-14
**Current Price:** $73.31

## Price Action
- **Daily Change:** +0.38%
- **5-Day Change:** +0.48%

## RSI (14)
- **Value:** 66.2 ↓
- **Signal:** Bullish

## MACD
- **MACD Line:** 3.267
- **Signal Line:** 2.229
- **Histogram:** 1.038 (Weakening ↓)
- **Signal:** Bullish

## Moving Averages
- **50 SMA:** $62.80 (+16.7% from price)
- **200 SMA:** $44.97 (+63.0% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $78.70
- **Middle:** $65.36
- **Lower:** $52.03
- **Band Position:** 80%
- **Bandwidth:** 40.8% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $3.60 (4.9% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $67.91 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 83.2
- **%D:** 83.4
- **Signal:** OVERBOUGHT ⚠️

## ADX (Trend Strength)
- **ADX:** 25.7 (Weakening ↓)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $67.38 (+8.8% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 52.1M
- **5-Day Trend:** Falling ↓
- **Signal:** BEARISH DIVERGENCE ⚠️ (distribution)

## VWAP (20-period)
- **VWAP:** $64.98
- **Current vs VWAP:** +12.8%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $75.70
- **Recent Low:** $54.95
- **Next Resistance:** $75.70 (0.0% (High))
- **Next Support:** $70.80 (23.6%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 7. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:30.020340
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'AA'}`
- **Output Length:** 97 chars

### Output
```
Error retrieving insider transactions for AA: Too Many Requests. Rate limited. Try after a while.
```

---

## 8. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:30.152913
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'AA'}`
- **Output Length:** 709 chars

### Output
```
## Analyst Recommendation Trends for AA

### 2026-04-01
- **Strong Buy**: 6
- **Buy**: 8
- **Hold**: 8
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 23

**Sentiment**: 60.9% Bullish, 4.3% Bearish

### 2026-03-01
- **Strong Buy**: 6
- **Buy**: 7
- **Hold**: 7
- **Sell**: 2
- **Strong Sell**: 0
- **Total Analysts**: 22

**Sentiment**: 59.1% Bullish, 9.1% Bearish

### 2026-02-01
- **Strong Buy**: 6
- **Buy**: 7
- **Hold**: 7
- **Sell**: 2
- **Strong Sell**: 0
- **Total Analysts**: 22

**Sentiment**: 59.1% Bullish, 9.1% Bearish

### 2026-01-01
- **Strong Buy**: 6
- **Buy**: 9
- **Hold**: 6
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 22

**Sentiment**: 68.2% Bullish, 4.5% Bearish


```

---

## 9. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:30.162415
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'AA', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 93 chars

### Output
```
Error retrieving options activity for AA: Too Many Requests. Rate limited. Try after a while.
```

---

## 10. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:30.671451
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'AMAT', 'curr_date': '2026-04-14'}`
- **Output Length:** 1538 chars

### Output
```
# Technical Analysis for AMAT
**Date:** 2026-04-14
**Current Price:** $395.73

## Price Action
- **Daily Change:** -0.94%
- **5-Day Change:** +11.69%

## RSI (14)
- **Value:** 64.3 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 10.750
- **Signal Line:** 5.291
- **Histogram:** 5.459 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $352.05 (+12.4% from price)
- **200 SMA:** $254.52 (+55.5% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $402.15
- **Middle:** $359.80
- **Lower:** $317.45
- **Band Position:** 92%
- **Bandwidth:** 23.5% (volatility indicator)
- **Signal:** Near upper band

## ATR (Volatility)
- **ATR:** $16.28 (4.1% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $371.31 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 82.8
- **%D:** 72.3
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 22.5 (Strengthening ↑)
- **Interpretation:** Trending

## 20 EMA
- **Value:** $364.66 (+8.5% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 223.7M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $358.89
- **Current vs VWAP:** +10.3%
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
- **Timestamp:** 2026-04-14T14:23:30.781517
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
- **Timestamp:** 2026-04-14T14:23:30.899588
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
- **Timestamp:** 2026-04-14T14:23:30.912031
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'AMAT', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for AMAT: Too Many Requests. Rate limited. Try after a while.
```

---

## 14. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:31.430939
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'APA', 'curr_date': '2026-04-14'}`
- **Output Length:** 1535 chars

### Output
```
# Technical Analysis for APA
**Date:** 2026-04-14
**Current Price:** $39.49

## Price Action
- **Daily Change:** +2.23%
- **5-Day Change:** -8.08%

## RSI (14)
- **Value:** 55.2 ↓
- **Signal:** Bullish

## MACD
- **MACD Line:** 1.833
- **Signal Line:** 2.587
- **Histogram:** -0.754 (Strengthening ↑)
- **Signal:** BEARISH CROSSOVER ⚠️

## Moving Averages
- **50 SMA:** $33.72 (+17.1% from price)
- **200 SMA:** $25.35 (+55.8% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $45.65
- **Middle:** $40.20
- **Lower:** $34.74
- **Band Position:** 44%
- **Bandwidth:** 27.1% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $2.05 (5.2% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $36.42 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 43.6
- **%D:** 48.9
- **Signal:** Bearish

## ADX (Trend Strength)
- **ADX:** 16.3 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $39.25 (+0.6% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 137.3M
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $40.17
- **Current vs VWAP:** -1.7%
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

## 15. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:31.507985
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'APA'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for APA: Too Many Requests. Rate limited. Try after a while.
```

---

## 16. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:31.616949
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

## 17. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:31.628453
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'APA', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for APA: Too Many Requests. Rate limited. Try after a while.
```

---

## 18. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:32.136218
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'AMD', 'curr_date': '2026-04-14'}`
- **Output Length:** 1592 chars

### Output
```
# Technical Analysis for AMD
**Date:** 2026-04-14
**Current Price:** $246.83

## Price Action
- **Daily Change:** +0.73%
- **5-Day Change:** +11.42%

## RSI (14)
- **Value:** 70.8 ↑
- **Signal:** OVERBOUGHT ⚠️

## MACD
- **MACD Line:** 8.984
- **Signal Line:** 4.176
- **Histogram:** 4.807 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $209.24 (+18.0% from price)
- **200 SMA:** $199.93 (+23.5% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $245.45
- **Middle:** $213.11
- **Lower:** $180.78
- **Band Position:** 102%
- **Bandwidth:** 30.3% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $9.87 (4.0% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $232.02 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 90.5
- **%D:** 82.8
- **Signal:** OVERBOUGHT ⚠️

## ADX (Trend Strength)
- **ADX:** 33.3 (Strengthening ↑)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $218.78 (+12.8% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 1219.4M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $212.24
- **Current vs VWAP:** +16.3%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $252.65
- **Recent Low:** $188.22
- **Next Resistance:** $252.65 (0.0% (High))
- **Next Support:** $237.44 (23.6%)

## Summary
- **Key Signals:** RSI overbought, Above 50 SMA

```

---

## 19. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:32.224519
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'AMD'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for AMD: Too Many Requests. Rate limited. Try after a while.
```

---

## 20. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:32.325327
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

## 21. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:32.336425
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'AMD', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for AMD: Too Many Requests. Rate limited. Try after a while.
```

---

## 22. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:32.743728
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'APH', 'curr_date': '2026-04-14'}`
- **Output Length:** 1570 chars

### Output
```
# Technical Analysis for APH
**Date:** 2026-04-14
**Current Price:** $145.27

## Price Action
- **Daily Change:** +3.21%
- **5-Day Change:** +13.16%

## RSI (14)
- **Value:** 63.8 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 0.556
- **Signal Line:** -1.984
- **Histogram:** 2.541 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $136.66 (+6.3% from price)
- **200 SMA:** $127.25 (+14.2% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $142.97
- **Middle:** $130.25
- **Lower:** $117.53
- **Band Position:** 109%
- **Bandwidth:** 19.5% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $5.89 (4.1% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $136.43 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 88.0
- **%D:** 75.1
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 14.4 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $132.95 (+9.3% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 252.7M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $130.70
- **Current vs VWAP:** +11.1%
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

## 23. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:32.851387
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'APH'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for APH: Too Many Requests. Rate limited. Try after a while.
```

---

## 24. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:32.953111
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

## 25. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:32.965926
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'APH', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for APH: Too Many Requests. Rate limited. Try after a while.
```

---

## 26. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:33.491056
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'COE', 'curr_date': '2026-04-14'}`
- **Output Length:** 1548 chars

### Output
```
# Technical Analysis for COE
**Date:** 2026-04-14
**Current Price:** $22.30

## Price Action
- **Daily Change:** +4.50%
- **5-Day Change:** +4.69%

## RSI (14)
- **Value:** 53.2 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** -0.430
- **Signal Line:** -0.962
- **Histogram:** 0.532 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $23.70 (-5.9% from price)
- **200 SMA:** $33.91 (-34.2% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $23.65
- **Middle:** $19.95
- **Lower:** $16.26
- **Band Position:** 82%
- **Bandwidth:** 37.1% (volatility indicator)
- **Signal:** Near upper band

## ATR (Volatility)
- **ATR:** $1.77 (7.9% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $19.65 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 72.6
- **%D:** 71.5
- **Signal:** Bullish crossover ⚡

## ADX (Trend Strength)
- **ADX:** 4.4 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $21.32 (+4.6% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** -272.8K
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $20.08
- **Current vs VWAP:** +11.0%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $28.50
- **Recent Low:** $15.32
- **Next Resistance:** $23.46 (38.2%)
- **Next Support:** $21.91 (50.0%)

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 27. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:33.582266
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'COE'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for COE: Too Many Requests. Rate limited. Try after a while.
```

---

## 28. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:33.727883
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

## 29. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:33.736835
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'COE', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for COE: Too Many Requests. Rate limited. Try after a while.
```

---

## 30. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:34.492165
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'BETR', 'curr_date': '2026-04-14'}`
- **Output Length:** 1485 chars

### Output
```
# Technical Analysis for BETR
**Date:** 2026-04-14
**Current Price:** $35.08

## Price Action
- **Daily Change:** +7.11%
- **5-Day Change:** -21.77%

## RSI (14)
- **Value:** 51.7 ↓
- **Signal:** Bullish

## MACD
- **MACD Line:** 0.967
- **Signal Line:** 0.952
- **Histogram:** 0.015 (Weakening ↓)
- **Signal:** Bullish

## Moving Averages
- **50 SMA:** $31.91 (+10.0% from price)
- **200 SMA:** $35.83 (-2.1% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $41.76
- **Middle:** $32.95
- **Lower:** $24.14
- **Band Position:** 62%
- **Bandwidth:** 53.5% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $4.01 (11.4% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $29.07 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 33.6
- **%D:** 48.8
- **Signal:** Bearish

## ADX (Trend Strength)
- **ADX:** 24.6 (Weakening ↓)
- **Interpretation:** Trending

## 20 EMA
- **Value:** $34.27 (+2.4% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 3.9M
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $33.37
- **Current vs VWAP:** +5.1%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $45.59
- **Recent Low:** $25.11
- **Next Resistance:** $35.35 (50.0%)
- **Next Support:** $32.93 (61.8%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 31. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:34.576351
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
- **Timestamp:** 2026-04-14T14:23:34.687197
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
- **Timestamp:** 2026-04-14T14:23:34.696361
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'BETR', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for BETR: Too Many Requests. Rate limited. Try after a while.
```

---

## 34. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:35.111731
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'CHPT', 'curr_date': '2026-04-14'}`
- **Output Length:** 1521 chars

### Output
```
# Technical Analysis for CHPT
**Date:** 2026-04-14
**Current Price:** $5.43

## Price Action
- **Daily Change:** +6.68%
- **5-Day Change:** +11.27%

## RSI (14)
- **Value:** 53.2 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** -0.173
- **Signal Line:** -0.256
- **Histogram:** 0.083 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $5.64 (-3.7% from price)
- **200 SMA:** $8.96 (-39.4% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $5.68
- **Middle:** $5.11
- **Lower:** $4.55
- **Band Position:** 78%
- **Bandwidth:** 22.2% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $0.33 (6.1% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $4.93 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 75.4
- **%D:** 58.4
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 11.7 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $5.19 (+4.6% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** -15.3M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $5.11
- **Current vs VWAP:** +6.2%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $6.76
- **Recent Low:** $4.44
- **Next Resistance:** $5.60 (50.0%)
- **Next Support:** $5.33 (61.8%)

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 35. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:35.188781
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'CHPT'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for CHPT: Too Many Requests. Rate limited. Try after a while.
```

---

## 36. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:35.294753
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'CHPT'}`
- **Output Length:** 715 chars

### Output
```
## Analyst Recommendation Trends for CHPT

### 2026-04-01
- **Strong Buy**: 0
- **Buy**: 1
- **Hold**: 10
- **Sell**: 2
- **Strong Sell**: 2
- **Total Analysts**: 15

**Sentiment**: 6.7% Bullish, 26.7% Bearish

### 2026-03-01
- **Strong Buy**: 0
- **Buy**: 1
- **Hold**: 10
- **Sell**: 3
- **Strong Sell**: 2
- **Total Analysts**: 16

**Sentiment**: 6.2% Bullish, 31.2% Bearish

### 2026-02-01
- **Strong Buy**: 0
- **Buy**: 1
- **Hold**: 10
- **Sell**: 3
- **Strong Sell**: 2
- **Total Analysts**: 16

**Sentiment**: 6.2% Bullish, 31.2% Bearish

### 2026-01-01
- **Strong Buy**: 0
- **Buy**: 1
- **Hold**: 10
- **Sell**: 3
- **Strong Sell**: 2
- **Total Analysts**: 16

**Sentiment**: 6.2% Bullish, 31.2% Bearish


```

---

## 37. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:35.303456
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'CHPT', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for CHPT: Too Many Requests. Rate limited. Try after a while.
```

---

## 38. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:35.705618
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'XAGE', 'curr_date': '2026-04-14'}`
- **Output Length:** 1548 chars

### Output
```
# Technical Analysis for XAGE
**Date:** 2026-04-14
**Current Price:** $0.50

## Price Action
- **Daily Change:** +41.43%
- **5-Day Change:** +78.06%

## RSI (14)
- **Value:** 68.5 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 0.010
- **Signal Line:** 0.001
- **Histogram:** 0.009 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $0.31 (+57.2% from price)
- **200 SMA:** $1.13 (-56.2% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $0.48
- **Middle:** $0.35
- **Lower:** $0.23
- **Band Position:** 107%
- **Bandwidth:** 71.3% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $0.05 (10.6% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $0.42 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 61.9
- **%D:** 43.9
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 15.9 (Strengthening ↑)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $0.34 (+47.1% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 102.3M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $0.34
- **Current vs VWAP:** +47.3%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $0.52
- **Recent Low:** $0.23
- **Next Resistance:** $0.52 (0.0% (High))
- **Next Support:** $0.45 (23.6%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 39. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:35.808780
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'XAGE'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for XAGE: Too Many Requests. Rate limited. Try after a while.
```

---

## 40. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:35.921998
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'XAGE'}`
- **Output Length:** 44 chars

### Output
```
No recommendation trends data found for XAGE
```

---

## 41. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:35.940319
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'XAGE', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for XAGE: Too Many Requests. Rate limited. Try after a while.
```

---

## 42. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:36.366193
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'ABX', 'curr_date': '2026-04-14'}`
- **Output Length:** 1477 chars

### Output
```
# Technical Analysis for ABX
**Date:** 2026-04-14
**Current Price:** $8.56

## Price Action
- **Daily Change:** +5.42%
- **5-Day Change:** +6.34%

## RSI (14)
- **Value:** 49.3 ↑
- **Signal:** Bearish

## MACD
- **MACD Line:** -0.239
- **Signal Line:** -0.220
- **Histogram:** -0.019 (Weakening ↓)
- **Signal:** Bearish

## Moving Averages
- **50 SMA:** $8.72 (-1.8% from price)
- **200 SMA:** $6.96 (+23.1% from price)
- **Trend:** Downtrend

## Bollinger Bands (20,2)
- **Upper:** $9.97
- **Middle:** $8.63
- **Lower:** $7.28
- **Band Position:** 47%
- **Bandwidth:** 31.1% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $0.52 (6.1% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $7.77 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 64.2
- **%D:** 46.6
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 31.3 (Weakening ↓)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $8.52 (+0.4% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** -1.8M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $8.71
- **Current vs VWAP:** -1.7%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $10.53
- **Recent Low:** $7.18
- **Next Resistance:** $8.86 (50.0%)
- **Next Support:** $8.46 (61.8%)

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 43. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:36.452394
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
- **Timestamp:** 2026-04-14T14:23:36.556192
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
- **Timestamp:** 2026-04-14T14:23:36.569537
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'ABX', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for ABX: Too Many Requests. Rate limited. Try after a while.
```

---

## 46. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:36.957698
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'ACHC', 'curr_date': '2026-04-14'}`
- **Output Length:** 1555 chars

### Output
```
# Technical Analysis for ACHC
**Date:** 2026-04-14
**Current Price:** $26.55

## Price Action
- **Daily Change:** +2.35%
- **5-Day Change:** +4.57%

## RSI (14)
- **Value:** 65.8 ↓
- **Signal:** Bullish

## MACD
- **MACD Line:** 1.345
- **Signal Line:** 1.232
- **Histogram:** 0.113 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $20.98 (+26.6% from price)
- **200 SMA:** $20.07 (+32.3% from price)
- **Trend:** STRONG UPTREND ⚡ (GOLDEN CROSS ⚡)

## Bollinger Bands (20,2)
- **Upper:** $26.98
- **Middle:** $24.12
- **Lower:** $21.27
- **Band Position:** 92%
- **Bandwidth:** 23.7% (volatility indicator)
- **Signal:** Near upper band

## ATR (Volatility)
- **ATR:** $1.29 (4.9% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $24.62 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 76.5
- **%D:** 77.8
- **Signal:** Bearish crossover ⚠️

## ADX (Trend Strength)
- **ADX:** 32.1 (Strengthening ↑)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $24.39 (+8.9% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 75.2M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $24.11
- **Current vs VWAP:** +10.1%
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

## 47. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:37.034432
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'ACHC'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for ACHC: Too Many Requests. Rate limited. Try after a while.
```

---

## 48. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:37.148441
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

## 49. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:37.157082
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'ACHC', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for ACHC: Too Many Requests. Rate limited. Try after a while.
```

---

## 50. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:37.498678
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'AI', 'curr_date': '2026-04-14'}`
- **Output Length:** 1504 chars

### Output
```
# Technical Analysis for AI
**Date:** 2026-04-14
**Current Price:** $8.47

## Price Action
- **Daily Change:** +2.29%
- **5-Day Change:** -2.98%

## RSI (14)
- **Value:** 44.2 ↓
- **Signal:** Bearish

## MACD
- **MACD Line:** -0.268
- **Signal Line:** -0.368
- **Histogram:** 0.100 (Weakening ↓)
- **Signal:** Bullish

## Moving Averages
- **50 SMA:** $9.40 (-9.9% from price)
- **200 SMA:** $15.77 (-46.3% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $9.09
- **Middle:** $8.48
- **Lower:** $7.88
- **Band Position:** 49%
- **Bandwidth:** 14.3% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $0.49 (5.8% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $7.73 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 51.5
- **%D:** 58.0
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 14.8 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $8.63 (-1.9% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** -133.7M
- **5-Day Trend:** Rising ↑
- **Signal:** BULLISH DIVERGENCE ⚡ (accumulation)

## VWAP (20-period)
- **VWAP:** $8.46
- **Current vs VWAP:** +0.2%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $12.06
- **Recent Low:** $7.68
- **Next Resistance:** $8.61 (78.6%)
- **Next Support:** $7.68 (100% (Low))

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 51. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:37.587721
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
- **Timestamp:** 2026-04-14T14:23:37.715291
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
- **Timestamp:** 2026-04-14T14:23:37.729962
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'AI', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 93 chars

### Output
```
Error retrieving options activity for AI: Too Many Requests. Rate limited. Try after a while.
```

---

## 54. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:38.154440
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'ARCT', 'curr_date': '2026-04-14'}`
- **Output Length:** 1492 chars

### Output
```
# Technical Analysis for ARCT
**Date:** 2026-04-14
**Current Price:** $8.46

## Price Action
- **Daily Change:** +1.20%
- **5-Day Change:** -0.59%

## RSI (14)
- **Value:** 64.5 ↓
- **Signal:** Bullish

## MACD
- **MACD Line:** 0.317
- **Signal Line:** 0.166
- **Histogram:** 0.150 (Weakening ↓)
- **Signal:** Bullish

## Moving Averages
- **50 SMA:** $7.49 (+12.9% from price)
- **200 SMA:** $11.36 (-25.5% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $8.97
- **Middle:** $7.41
- **Lower:** $5.84
- **Band Position:** 84%
- **Bandwidth:** 42.3% (volatility indicator)
- **Signal:** Near upper band

## ATR (Volatility)
- **ATR:** $0.49 (5.8% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $7.73 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 72.1
- **%D:** 74.1
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 30.7 (Strengthening ↑)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $7.76 (+9.1% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** -14.3M
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $7.33
- **Current vs VWAP:** +15.4%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $9.08
- **Recent Low:** $6.36
- **Next Resistance:** $9.08 (0.0% (High))
- **Next Support:** $8.44 (23.6%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 55. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:38.265716
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'ARCT'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for ARCT: Too Many Requests. Rate limited. Try after a while.
```

---

## 56. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:38.395462
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'ARCT'}`
- **Output Length:** 712 chars

### Output
```
## Analyst Recommendation Trends for ARCT

### 2026-04-01
- **Strong Buy**: 5
- **Buy**: 10
- **Hold**: 4
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 19

**Sentiment**: 78.9% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 5
- **Buy**: 9
- **Hold**: 4
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 18

**Sentiment**: 77.8% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 5
- **Buy**: 9
- **Hold**: 4
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 18

**Sentiment**: 77.8% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 5
- **Buy**: 8
- **Hold**: 4
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 17

**Sentiment**: 76.5% Bullish, 0.0% Bearish


```

---

## 57. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:38.404414
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'ARCT', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for ARCT: Too Many Requests. Rate limited. Try after a while.
```

---

## 58. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:38.799519
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'ANAB', 'curr_date': '2026-04-14'}`
- **Output Length:** 1525 chars

### Output
```
# Technical Analysis for ANAB
**Date:** 2026-04-14
**Current Price:** $68.73

## Price Action
- **Daily Change:** -1.95%
- **5-Day Change:** +10.62%

## RSI (14)
- **Value:** 63.7 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 2.320
- **Signal Line:** 1.603
- **Histogram:** 0.718 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $58.18 (+18.1% from price)
- **200 SMA:** $39.13 (+75.7% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $71.87
- **Middle:** $63.01
- **Lower:** $54.15
- **Band Position:** 82%
- **Bandwidth:** 28.1% (volatility indicator)
- **Signal:** Near upper band

## ATR (Volatility)
- **ATR:** $4.11 (6.0% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $62.57 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 79.4
- **%D:** 68.0
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 35.7 (Strengthening ↑)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $62.86 (+9.3% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 15.4M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $62.17
- **Current vs VWAP:** +10.5%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $73.30
- **Recent Low:** $44.75
- **Next Resistance:** $73.30 (0.0% (High))
- **Next Support:** $66.56 (23.6%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 59. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:38.870108
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'ANAB'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for ANAB: Too Many Requests. Rate limited. Try after a while.
```

---

## 60. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:38.979881
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'ANAB'}`
- **Output Length:** 714 chars

### Output
```
## Analyst Recommendation Trends for ANAB

### 2026-04-01
- **Strong Buy**: 7
- **Buy**: 10
- **Hold**: 2
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 19

**Sentiment**: 89.5% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 7
- **Buy**: 10
- **Hold**: 2
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 19

**Sentiment**: 89.5% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 7
- **Buy**: 10
- **Hold**: 2
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 19

**Sentiment**: 89.5% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 7
- **Buy**: 9
- **Hold**: 3
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 19

**Sentiment**: 84.2% Bullish, 0.0% Bearish


```

---

## 61. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:38.989008
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'ANAB', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for ANAB: Too Many Requests. Rate limited. Try after a while.
```

---

## 62. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:39.397428
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'AVGO', 'curr_date': '2026-04-14'}`
- **Output Length:** 1584 chars

### Output
```
# Technical Analysis for AVGO
**Date:** 2026-04-14
**Current Price:** $379.75

## Price Action
- **Daily Change:** +2.21%
- **5-Day Change:** +13.71%

## RSI (14)
- **Value:** 73.1 ↑
- **Signal:** OVERBOUGHT ⚠️

## MACD
- **MACD Line:** 9.261
- **Signal Line:** 1.287
- **Histogram:** 7.974 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $327.11 (+16.1% from price)
- **200 SMA:** $329.52 (+15.2% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $369.92
- **Middle:** $324.75
- **Lower:** $279.59
- **Band Position:** 111%
- **Bandwidth:** 27.8% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $13.28 (3.5% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $359.84 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 91.2
- **%D:** 80.3
- **Signal:** OVERBOUGHT ⚠️

## ADX (Trend Strength)
- **ADX:** 27.9 (Strengthening ↑)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $333.63 (+13.8% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 371.8M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $325.01
- **Current vs VWAP:** +16.8%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $380.86
- **Recent Low:** $289.96
- **Next Resistance:** $380.86 (0.0% (High))
- **Next Support:** $359.41 (23.6%)

## Summary
- **Key Signals:** RSI overbought, Above 50 SMA

```

---

## 63. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:39.500598
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'AVGO'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for AVGO: Too Many Requests. Rate limited. Try after a while.
```

---

## 64. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:39.599601
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

## 65. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:39.608451
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'AVGO', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for AVGO: Too Many Requests. Rate limited. Try after a while.
```

---

## 66. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:40.088409
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'ADM', 'curr_date': '2026-04-14'}`
- **Output Length:** 1534 chars

### Output
```
# Technical Analysis for ADM
**Date:** 2026-04-14
**Current Price:** $69.82

## Price Action
- **Daily Change:** +0.13%
- **5-Day Change:** -3.23%

## RSI (14)
- **Value:** 47.0 ↓
- **Signal:** Bearish

## MACD
- **MACD Line:** 0.528
- **Signal Line:** 0.922
- **Histogram:** -0.393 (Strengthening ↑)
- **Signal:** BEARISH CROSSOVER ⚠️

## Moving Averages
- **50 SMA:** $69.33 (+0.7% from price)
- **200 SMA:** $61.40 (+13.7% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $74.86
- **Middle:** $71.10
- **Lower:** $67.34
- **Band Position:** 33%
- **Bandwidth:** 10.6% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $2.29 (3.3% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $66.38 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 44.8
- **%D:** 56.6
- **Signal:** Bearish

## ADX (Trend Strength)
- **ADX:** 15.0 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $70.91 (-1.5% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** 11.8M
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $70.45
- **Current vs VWAP:** -0.9%
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

## 67. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:40.167811
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'ADM'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for ADM: Too Many Requests. Rate limited. Try after a while.
```

---

## 68. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:40.269702
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

## 69. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:40.303782
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'ADM', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for ADM: Too Many Requests. Rate limited. Try after a while.
```

---

## 70. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:40.759027
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'AME', 'curr_date': '2026-04-14'}`
- **Output Length:** 1555 chars

### Output
```
# Technical Analysis for AME
**Date:** 2026-04-14
**Current Price:** $234.47

## Price Action
- **Daily Change:** -0.19%
- **5-Day Change:** +7.68%

## RSI (14)
- **Value:** 66.5 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 2.418
- **Signal Line:** -0.526
- **Histogram:** 2.944 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $225.11 (+4.2% from price)
- **200 SMA:** $200.13 (+17.2% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $234.96
- **Middle:** $217.94
- **Lower:** $200.91
- **Band Position:** 99%
- **Bandwidth:** 15.6% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $5.68 (2.4% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $225.95 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 89.8
- **%D:** 80.7
- **Signal:** OVERBOUGHT ⚠️

## ADX (Trend Strength)
- **ADX:** 20.3 (Weakening ↓)
- **Interpretation:** Trending

## 20 EMA
- **Value:** $222.58 (+5.3% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 8.1M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $217.30
- **Current vs VWAP:** +7.9%
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

## 71. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:40.825171
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'AME'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for AME: Too Many Requests. Rate limited. Try after a while.
```

---

## 72. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:40.937568
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

## 73. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:40.946256
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'AME', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for AME: Too Many Requests. Rate limited. Try after a while.
```

---

## 74. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:41.440864
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'BAC', 'curr_date': '2026-04-14'}`
- **Output Length:** 1572 chars

### Output
```
# Technical Analysis for BAC
**Date:** 2026-04-14
**Current Price:** $53.35

## Price Action
- **Daily Change:** +1.54%
- **5-Day Change:** +6.11%

## RSI (14)
- **Value:** 70.2 ↑
- **Signal:** OVERBOUGHT ⚠️

## MACD
- **MACD Line:** 0.750
- **Signal Line:** 0.022
- **Histogram:** 0.728 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $50.54 (+5.6% from price)
- **200 SMA:** $50.56 (+5.5% from price)
- **Trend:** Uptrend (DEATH CROSS ⚠️)

## Bollinger Bands (20,2)
- **Upper:** $53.28
- **Middle:** $49.02
- **Lower:** $44.76
- **Band Position:** 101%
- **Bandwidth:** 17.4% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $1.26 (2.4% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $51.46 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 94.4
- **%D:** 88.6
- **Signal:** OVERBOUGHT ⚠️

## ADX (Trend Strength)
- **ADX:** 22.5 (Strengthening ↑)
- **Interpretation:** Trending

## 20 EMA
- **Value:** $50.09 (+6.5% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 1061.8M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $48.67
- **Current vs VWAP:** +9.6%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $56.55
- **Recent Low:** $46.12
- **Next Resistance:** $54.09 (23.6%)
- **Next Support:** $52.57 (38.2%)

## Summary
- **Key Signals:** RSI overbought, Above 50 SMA

```

---

## 75. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:41.519998
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'BAC'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for BAC: Too Many Requests. Rate limited. Try after a while.
```

---

## 76. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:41.630954
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

## 77. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:41.642769
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'BAC', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for BAC: Too Many Requests. Rate limited. Try after a while.
```

---

## 78. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:42.257310
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'SMC', 'curr_date': '2026-04-14'}`
- **Output Length:** 1522 chars

### Output
```
# Technical Analysis for SMC
**Date:** 2026-04-14
**Current Price:** $28.63

## Price Action
- **Daily Change:** -0.52%
- **5-Day Change:** -2.29%

## RSI (14)
- **Value:** 36.7 ↓
- **Signal:** Bearish

## MACD
- **MACD Line:** -0.406
- **Signal Line:** -0.076
- **Histogram:** -0.330 (Weakening ↓)
- **Signal:** Bearish

## Moving Averages
- **50 SMA:** $29.96 (-4.4% from price)
- **200 SMA:** $25.48 (+12.3% from price)
- **Trend:** Downtrend

## Bollinger Bands (20,2)
- **Upper:** $32.84
- **Middle:** $30.40
- **Lower:** $27.95
- **Band Position:** 14%
- **Bandwidth:** 16.1% (volatility indicator)
- **Signal:** Near lower band

## ATR (Volatility)
- **ATR:** $1.08 (3.8% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $27.01 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 10.1
- **%D:** 13.5
- **Signal:** OVERSOLD ⚡

## ADX (Trend Strength)
- **ADX:** 9.7 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $29.93 (-4.3% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** -2.6M
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $31.02
- **Current vs VWAP:** -7.7%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $33.50
- **Recent Low:** $27.40
- **Next Resistance:** $28.71 (78.6%)
- **Next Support:** $27.40 (100% (Low))

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 79. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:42.318958
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'SMC'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for SMC: Too Many Requests. Rate limited. Try after a while.
```

---

## 80. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:42.429089
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'SMC'}`
- **Output Length:** 706 chars

### Output
```
## Analyst Recommendation Trends for SMC

### 2026-04-01
- **Strong Buy**: 1
- **Buy**: 3
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 5

**Sentiment**: 80.0% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 1
- **Buy**: 3
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 5

**Sentiment**: 80.0% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 1
- **Buy**: 3
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 5

**Sentiment**: 80.0% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 1
- **Buy**: 3
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 5

**Sentiment**: 80.0% Bullish, 0.0% Bearish


```

---

## 81. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:42.437449
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'SMC', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for SMC: Too Many Requests. Rate limited. Try after a while.
```

---

## 82. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:42.893545
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'MESO', 'curr_date': '2026-04-14'}`
- **Output Length:** 1546 chars

### Output
```
# Technical Analysis for MESO
**Date:** 2026-04-14
**Current Price:** $14.70

## Price Action
- **Daily Change:** -2.00%
- **5-Day Change:** +7.38%

## RSI (14)
- **Value:** 47.7 ↑
- **Signal:** Bearish

## MACD
- **MACD Line:** -0.291
- **Signal Line:** -0.363
- **Histogram:** 0.072 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $15.66 (-6.1% from price)
- **200 SMA:** $16.01 (-8.2% from price)
- **Trend:** STRONG DOWNTREND ⚠️ (DEATH CROSS ⚠️)

## Bollinger Bands (20,2)
- **Upper:** $15.72
- **Middle:** $14.66
- **Lower:** $13.60
- **Band Position:** 52%
- **Bandwidth:** 14.5% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $0.80 (5.4% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $13.50 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 40.4
- **%D:** 37.1
- **Signal:** Bearish

## ADX (Trend Strength)
- **ADX:** 5.9 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $14.82 (-0.8% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** 5.9M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $14.64
- **Current vs VWAP:** +0.4%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $18.38
- **Recent Low:** $13.30
- **Next Resistance:** $15.24 (61.8%)
- **Next Support:** $14.39 (78.6%)

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 83. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:42.966605
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'MESO'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for MESO: Too Many Requests. Rate limited. Try after a while.
```

---

## 84. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:43.072030
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

## 85. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:43.394405
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'MESO', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for MESO: Too Many Requests. Rate limited. Try after a while.
```

---

## 86. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:44.090025
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'HYMC', 'curr_date': '2026-04-14'}`
- **Output Length:** 1535 chars

### Output
```
# Technical Analysis for HYMC
**Date:** 2026-04-14
**Current Price:** $39.56

## Price Action
- **Daily Change:** +5.49%
- **5-Day Change:** +8.18%

## RSI (14)
- **Value:** 54.8 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** -0.283
- **Signal Line:** -1.074
- **Histogram:** 0.791 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $38.79 (+2.0% from price)
- **200 SMA:** $18.29 (+116.3% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $41.43
- **Middle:** $35.20
- **Lower:** $28.97
- **Band Position:** 85%
- **Bandwidth:** 35.4% (volatility indicator)
- **Signal:** Near upper band

## ATR (Volatility)
- **ATR:** $4.06 (10.3% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $33.47 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 72.8
- **%D:** 68.9
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 6.2 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $36.83 (+7.4% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 109.7M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $34.33
- **Current vs VWAP:** +15.2%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $55.75
- **Recent Low:** $29.21
- **Next Resistance:** $42.48 (50.0%)
- **Next Support:** $39.35 (61.8%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 87. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:44.171207
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'HYMC'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for HYMC: Too Many Requests. Rate limited. Try after a while.
```

---

## 88. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:44.284898
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'HYMC'}`
- **Output Length:** 707 chars

### Output
```
## Analyst Recommendation Trends for HYMC

### 2026-04-01
- **Strong Buy**: 0
- **Buy**: 0
- **Hold**: 3
- **Sell**: 1
- **Strong Sell**: 2
- **Total Analysts**: 6

**Sentiment**: 0.0% Bullish, 50.0% Bearish

### 2026-03-01
- **Strong Buy**: 0
- **Buy**: 0
- **Hold**: 3
- **Sell**: 1
- **Strong Sell**: 2
- **Total Analysts**: 6

**Sentiment**: 0.0% Bullish, 50.0% Bearish

### 2026-02-01
- **Strong Buy**: 0
- **Buy**: 0
- **Hold**: 3
- **Sell**: 1
- **Strong Sell**: 2
- **Total Analysts**: 6

**Sentiment**: 0.0% Bullish, 50.0% Bearish

### 2026-01-01
- **Strong Buy**: 0
- **Buy**: 0
- **Hold**: 3
- **Sell**: 1
- **Strong Sell**: 2
- **Total Analysts**: 6

**Sentiment**: 0.0% Bullish, 50.0% Bearish


```

---

## 89. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:44.296545
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'HYMC', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for HYMC: Too Many Requests. Rate limited. Try after a while.
```

---

## 90. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:44.697647
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'SG', 'curr_date': '2026-04-14'}`
- **Output Length:** 1490 chars

### Output
```
# Technical Analysis for SG
**Date:** 2026-04-14
**Current Price:** $5.74

## Price Action
- **Daily Change:** -6.82%
- **5-Day Change:** +0.88%

## RSI (14)
- **Value:** 53.2 ↓
- **Signal:** Bullish

## MACD
- **MACD Line:** 0.047
- **Signal Line:** -0.056
- **Histogram:** 0.104 (Weakening ↓)
- **Signal:** Bullish

## Moving Averages
- **50 SMA:** $5.58 (+2.9% from price)
- **200 SMA:** $7.97 (-28.0% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $6.15
- **Middle:** $5.42
- **Lower:** $4.69
- **Band Position:** 72%
- **Bandwidth:** 26.8% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $0.41 (7.1% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $5.13 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 78.1
- **%D:** 74.4
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 18.5 (Strengthening ↑)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $5.54 (+3.6% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** -157.1M
- **5-Day Trend:** Falling ↓
- **Signal:** BEARISH DIVERGENCE ⚠️ (distribution)

## VWAP (20-period)
- **VWAP:** $5.41
- **Current vs VWAP:** +6.0%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $6.59
- **Recent Low:** $4.49
- **Next Resistance:** $5.79 (38.2%)
- **Next Support:** $5.54 (50.0%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 91. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:44.775629
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'SG'}`
- **Output Length:** 97 chars

### Output
```
Error retrieving insider transactions for SG: Too Many Requests. Rate limited. Try after a while.
```

---

## 92. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:44.879204
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'SG'}`
- **Output Length:** 713 chars

### Output
```
## Analyst Recommendation Trends for SG

### 2026-04-01
- **Strong Buy**: 5
- **Buy**: 5
- **Hold**: 13
- **Sell**: 2
- **Strong Sell**: 0
- **Total Analysts**: 25

**Sentiment**: 40.0% Bullish, 8.0% Bearish

### 2026-03-01
- **Strong Buy**: 6
- **Buy**: 5
- **Hold**: 10
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 22

**Sentiment**: 50.0% Bullish, 4.5% Bearish

### 2026-02-01
- **Strong Buy**: 5
- **Buy**: 5
- **Hold**: 11
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 22

**Sentiment**: 45.5% Bullish, 4.5% Bearish

### 2026-01-01
- **Strong Buy**: 5
- **Buy**: 6
- **Hold**: 10
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 22

**Sentiment**: 50.0% Bullish, 4.5% Bearish


```

---

## 93. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:44.888110
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'SG', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 93 chars

### Output
```
Error retrieving options activity for SG: Too Many Requests. Rate limited. Try after a while.
```

---

## 94. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:45.486428
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'CGCT', 'curr_date': '2026-04-14'}`
- **Output Length:** 1482 chars

### Output
```
# Technical Analysis for CGCT
**Date:** 2026-04-14
**Current Price:** $10.26

## Price Action
- **Daily Change:** +0.00%
- **5-Day Change:** -0.10%

## RSI (14)
- **Value:** 47.4 ↓
- **Signal:** Bearish

## MACD
- **MACD Line:** -0.001
- **Signal Line:** -0.001
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
- **%K:** 36.4
- **%D:** 43.2
- **Signal:** Bearish

## ADX (Trend Strength)
- **ADX:** 24.6 (Weakening ↓)
- **Interpretation:** Trending

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

## 95. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:45.566866
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'CGCT'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for CGCT: Too Many Requests. Rate limited. Try after a while.
```

---

## 96. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:45.667568
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'CGCT'}`
- **Output Length:** 44 chars

### Output
```
No recommendation trends data found for CGCT
```

---

## 97. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:45.676234
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'CGCT', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for CGCT: Too Many Requests. Rate limited. Try after a while.
```

---

## 98. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:46.144690
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'HTO', 'curr_date': '2026-04-14'}`
- **Output Length:** 1528 chars

### Output
```
# Technical Analysis for HTO
**Date:** 2026-04-14
**Current Price:** $58.21

## Price Action
- **Daily Change:** -2.45%
- **5-Day Change:** -0.95%

## RSI (14)
- **Value:** 53.1 ↓
- **Signal:** Bullish

## MACD
- **MACD Line:** 0.843
- **Signal Line:** 0.897
- **Histogram:** -0.054 (Strengthening ↑)
- **Signal:** BEARISH CROSSOVER ⚠️

## Moving Averages
- **50 SMA:** $56.05 (+3.9% from price)
- **200 SMA:** $50.46 (+15.4% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $60.26
- **Middle:** $58.04
- **Lower:** $55.82
- **Band Position:** 54%
- **Bandwidth:** 7.6% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $1.48 (2.5% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $55.99 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 66.1
- **%D:** 72.4
- **Signal:** Bearish crossover ⚠️

## ADX (Trend Strength)
- **ADX:** 20.4 (Weakening ↓)
- **Interpretation:** Trending

## 20 EMA
- **Value:** $58.11 (+0.2% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 6.4M
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $57.93
- **Current vs VWAP:** +0.5%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $60.18
- **Recent Low:** $50.69
- **Next Resistance:** $60.18 (0.0% (High))
- **Next Support:** $57.94 (23.6%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 99. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:46.278690
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'HTO'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for HTO: Too Many Requests. Rate limited. Try after a while.
```

---

## 100. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:46.384912
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'HTO'}`
- **Output Length:** 706 chars

### Output
```
## Analyst Recommendation Trends for HTO

### 2026-04-01
- **Strong Buy**: 4
- **Buy**: 4
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 9

**Sentiment**: 88.9% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 3
- **Buy**: 4
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 8

**Sentiment**: 87.5% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 4
- **Buy**: 3
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 8

**Sentiment**: 87.5% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 3
- **Buy**: 3
- **Hold**: 2
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 8

**Sentiment**: 75.0% Bullish, 0.0% Bearish


```

---

## 101. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:46.393790
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'HTO', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for HTO: Too Many Requests. Rate limited. Try after a while.
```

---

## 102. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:46.920386
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'RPAY', 'curr_date': '2026-04-14'}`
- **Output Length:** 1518 chars

### Output
```
# Technical Analysis for RPAY
**Date:** 2026-04-14
**Current Price:** $3.11

## Price Action
- **Daily Change:** +3.32%
- **5-Day Change:** +29.58%

## RSI (14)
- **Value:** 57.7 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** -0.030
- **Signal Line:** -0.078
- **Histogram:** 0.048 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $2.97 (+4.7% from price)
- **200 SMA:** $4.15 (-25.1% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $3.24
- **Middle:** $2.79
- **Lower:** $2.33
- **Band Position:** 86%
- **Bandwidth:** 32.5% (volatility indicator)
- **Signal:** Near upper band

## ATR (Volatility)
- **ATR:** $0.23 (7.3% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $2.77 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 63.4
- **%D:** 45.8
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 14.2 (Strengthening ↑)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $2.82 (+10.2% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** -12.2M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $2.73
- **Current vs VWAP:** +13.9%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $3.58
- **Recent Low:** $2.30
- **Next Resistance:** $3.28 (23.6%)
- **Next Support:** $3.09 (38.2%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 103. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:46.988237
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'RPAY'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for RPAY: Too Many Requests. Rate limited. Try after a while.
```

---

## 104. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:47.112019
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'RPAY'}`
- **Output Length:** 711 chars

### Output
```
## Analyst Recommendation Trends for RPAY

### 2026-04-01
- **Strong Buy**: 3
- **Buy**: 7
- **Hold**: 3
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 13

**Sentiment**: 76.9% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 3
- **Buy**: 7
- **Hold**: 3
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 13

**Sentiment**: 76.9% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 3
- **Buy**: 7
- **Hold**: 3
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 13

**Sentiment**: 76.9% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 3
- **Buy**: 7
- **Hold**: 3
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 13

**Sentiment**: 76.9% Bullish, 0.0% Bearish


```

---

## 105. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:47.121226
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'RPAY', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for RPAY: Too Many Requests. Rate limited. Try after a while.
```

---

## 106. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:48.095972
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'GF', 'curr_date': '2026-04-14'}`
- **Output Length:** 1543 chars

### Output
```
# Technical Analysis for GF
**Date:** 2026-04-14
**Current Price:** $11.35

## Price Action
- **Daily Change:** +0.27%
- **5-Day Change:** +7.99%

## RSI (14)
- **Value:** 60.7 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** -0.027
- **Signal Line:** -0.195
- **Histogram:** 0.168 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $11.32 (+0.3% from price)
- **200 SMA:** $11.38 (-0.3% from price)
- **Trend:** Uptrend (DEATH CROSS ⚠️)

## Bollinger Bands (20,2)
- **Upper:** $11.41
- **Middle:** $10.61
- **Lower:** $9.81
- **Band Position:** 96%
- **Bandwidth:** 15.1% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $0.35 (3.1% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $10.83 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 69.4
- **%D:** 63.1
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 32.8 (Strengthening ↑)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $10.84 (+4.7% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 1.0M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $10.77
- **Current vs VWAP:** +5.4%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $12.39
- **Recent Low:** $9.98
- **Next Resistance:** $11.47 (38.2%)
- **Next Support:** $11.18 (50.0%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 107. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:48.165991
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'GF'}`
- **Output Length:** 97 chars

### Output
```
Error retrieving insider transactions for GF: Too Many Requests. Rate limited. Try after a while.
```

---

## 108. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:48.268698
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'GF'}`
- **Output Length:** 42 chars

### Output
```
No recommendation trends data found for GF
```

---

## 109. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:48.278323
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'GF', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 93 chars

### Output
```
Error retrieving options activity for GF: Too Many Requests. Rate limited. Try after a while.
```

---

## 110. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:48.656778
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'MNR', 'curr_date': '2026-04-14'}`
- **Output Length:** 1491 chars

### Output
```
# Technical Analysis for MNR
**Date:** 2026-04-14
**Current Price:** $12.77

## Price Action
- **Daily Change:** +0.95%
- **5-Day Change:** +1.11%

## RSI (14)
- **Value:** 42.8 ↑
- **Signal:** Bearish

## MACD
- **MACD Line:** -0.091
- **Signal Line:** 0.137
- **Histogram:** -0.228 (Weakening ↓)
- **Signal:** Bearish

## Moving Averages
- **50 SMA:** $13.03 (-2.0% from price)
- **200 SMA:** $12.33 (+3.6% from price)
- **Trend:** Downtrend

## Bollinger Bands (20,2)
- **Upper:** $14.94
- **Middle:** $13.64
- **Lower:** $12.33
- **Band Position:** 17%
- **Bandwidth:** 19.2% (volatility indicator)
- **Signal:** Near lower band

## ATR (Volatility)
- **ATR:** $0.51 (4.0% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $12.00 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 23.8
- **%D:** 29.9
- **Signal:** Bearish

## ADX (Trend Strength)
- **ADX:** 24.8 (Strengthening ↑)
- **Interpretation:** Trending

## 20 EMA
- **Value:** $13.33 (-4.2% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** -8.4M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $12.98
- **Current vs VWAP:** -1.6%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $14.79
- **Recent Low:** $10.94
- **Next Resistance:** $12.87 (50.0%)
- **Next Support:** $12.41 (61.8%)

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 111. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:48.730468
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'MNR'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for MNR: Too Many Requests. Rate limited. Try after a while.
```

---

## 112. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:48.850602
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'MNR'}`
- **Output Length:** 710 chars

### Output
```
## Analyst Recommendation Trends for MNR

### 2026-04-01
- **Strong Buy**: 5
- **Buy**: 5
- **Hold**: 3
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 13

**Sentiment**: 76.9% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 5
- **Buy**: 6
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 12

**Sentiment**: 91.7% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 5
- **Buy**: 6
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 12

**Sentiment**: 91.7% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 5
- **Buy**: 6
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 12

**Sentiment**: 91.7% Bullish, 0.0% Bearish


```

---

## 113. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:48.861103
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'MNR', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for MNR: Too Many Requests. Rate limited. Try after a while.
```

---

## 114. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:49.283995
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'ACET', 'curr_date': '2026-04-14'}`
- **Output Length:** 1525 chars

### Output
```
# Technical Analysis for ACET
**Date:** 2026-04-14
**Current Price:** $6.35

## Price Action
- **Daily Change:** -6.07%
- **5-Day Change:** -1.24%

## RSI (14)
- **Value:** 41.2 ↑
- **Signal:** Bearish

## MACD
- **MACD Line:** -0.166
- **Signal Line:** -0.169
- **Histogram:** 0.003 (Weakening ↓)
- **Signal:** Bullish

## Moving Averages
- **50 SMA:** $7.06 (-10.1% from price)
- **200 SMA:** $10.01 (-36.6% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $7.32
- **Middle:** $6.76
- **Lower:** $6.21
- **Band Position:** 13%
- **Bandwidth:** 16.3% (volatility indicator)
- **Signal:** Near lower band

## ATR (Volatility)
- **ATR:** $0.44 (7.0% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $5.69 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 53.4
- **%D:** 58.1
- **Signal:** Bearish crossover ⚠️

## ADX (Trend Strength)
- **ADX:** 18.9 (Strengthening ↑)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $6.79 (-6.4% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** -2.8M
- **5-Day Trend:** Rising ↑
- **Signal:** BULLISH DIVERGENCE ⚡ (accumulation)

## VWAP (20-period)
- **VWAP:** $6.72
- **Current vs VWAP:** -5.6%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $8.50
- **Recent Low:** $6.01
- **Next Resistance:** $6.54 (78.6%)
- **Next Support:** $6.01 (100% (Low))

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 115. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:49.367074
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'ACET'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for ACET: Too Many Requests. Rate limited. Try after a while.
```

---

## 116. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:49.479513
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'ACET'}`
- **Output Length:** 711 chars

### Output
```
## Analyst Recommendation Trends for ACET

### 2026-04-01
- **Strong Buy**: 5
- **Buy**: 7
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 13

**Sentiment**: 92.3% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 5
- **Buy**: 7
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 13

**Sentiment**: 92.3% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 5
- **Buy**: 7
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 13

**Sentiment**: 92.3% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 5
- **Buy**: 7
- **Hold**: 1
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 13

**Sentiment**: 92.3% Bullish, 0.0% Bearish


```

---

## 117. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:49.489371
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'ACET', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for ACET: Too Many Requests. Rate limited. Try after a while.
```

---

## 118. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:49.975618
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'WKSP', 'curr_date': '2026-04-14'}`
- **Output Length:** 1520 chars

### Output
```
# Technical Analysis for WKSP
**Date:** 2026-04-14
**Current Price:** $0.94

## Price Action
- **Daily Change:** +10.12%
- **5-Day Change:** +0.11%

## RSI (14)
- **Value:** 35.3 ↑
- **Signal:** Bearish

## MACD
- **MACD Line:** -0.141
- **Signal Line:** -0.133
- **Histogram:** -0.008 (Weakening ↓)
- **Signal:** Bearish

## Moving Averages
- **50 SMA:** $1.34 (-30.1% from price)
- **200 SMA:** $2.59 (-63.9% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $1.49
- **Middle:** $1.12
- **Lower:** $0.75
- **Band Position:** 25%
- **Bandwidth:** 66.2% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $0.12 (13.2% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $0.75 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 21.9
- **%D:** 17.6
- **Signal:** Bullish crossover ⚡

## ADX (Trend Strength)
- **ADX:** 56.5 (Strengthening ↑)
- **Interpretation:** VERY STRONG TREND ⚡

## 20 EMA
- **Value:** $1.08 (-13.6% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** -4.1M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $1.19
- **Current vs VWAP:** -21.2%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $1.93
- **Recent Low:** $0.82
- **Next Resistance:** $1.06 (78.6%)
- **Next Support:** $0.82 (100% (Low))

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 119. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:50.053860
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'WKSP'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for WKSP: Too Many Requests. Rate limited. Try after a while.
```

---

## 120. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:50.156068
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'WKSP'}`
- **Output Length:** 707 chars

### Output
```
## Analyst Recommendation Trends for WKSP

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

## 121. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:50.164968
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'WKSP', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for WKSP: Too Many Requests. Rate limited. Try after a while.
```

---

## 122. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:50.547570
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'CNXC', 'curr_date': '2026-04-14'}`
- **Output Length:** 1529 chars

### Output
```
# Technical Analysis for CNXC
**Date:** 2026-04-14
**Current Price:** $27.86

## Price Action
- **Daily Change:** +6.66%
- **5-Day Change:** +0.61%

## RSI (14)
- **Value:** 45.4 ↑
- **Signal:** Bearish

## MACD
- **MACD Line:** -1.429
- **Signal Line:** -1.629
- **Histogram:** 0.200 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $31.82 (-12.4% from price)
- **200 SMA:** $42.25 (-34.1% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $33.56
- **Middle:** $28.53
- **Lower:** $23.51
- **Band Position:** 43%
- **Bandwidth:** 35.2% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $2.27 (8.1% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $24.45 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 51.1
- **%D:** 50.9
- **Signal:** Bullish crossover ⚡

## ADX (Trend Strength)
- **ADX:** 26.3 (Weakening ↓)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $28.58 (-2.5% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** 230.5K
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $28.03
- **Current vs VWAP:** -0.6%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $40.03
- **Recent Low:** $24.27
- **Next Resistance:** $30.29 (61.8%)
- **Next Support:** $27.64 (78.6%)

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 123. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:50.613809
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'CNXC'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for CNXC: Too Many Requests. Rate limited. Try after a while.
```

---

## 124. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:50.712030
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'CNXC'}`
- **Output Length:** 147 chars

### Output
```
Error fetching recommendation trends for CNXC: FinnhubAPIException(status_code: 429): API limit reached. Please try again later. Remaining Limit: 0
```

---

## 125. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:50.721131
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'CNXC', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for CNXC: Too Many Requests. Rate limited. Try after a while.
```

---

## 126. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:51.222242
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'FROPX', 'curr_date': '2026-04-14'}`
- **Output Length:** 1481 chars

### Output
```
# Technical Analysis for FROPX
**Date:** 2026-04-14
**Current Price:** $14.55

## Price Action
- **Daily Change:** -0.41%
- **5-Day Change:** +0.14%

## RSI (14)
- **Value:** 43.5 ↑
- **Signal:** Bearish

## MACD
- **MACD Line:** -0.047
- **Signal Line:** -0.079
- **Histogram:** 0.032 (Weakening ↓)
- **Signal:** Bullish

## Moving Averages
- **50 SMA:** $14.79 (-1.6% from price)
- **200 SMA:** $15.47 (-6.0% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $14.61
- **Middle:** $14.51
- **Lower:** $14.41
- **Band Position:** 69%
- **Bandwidth:** 1.4% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $0.03 (0.2% of price)
- **Level:** Low volatility
- **Suggested Stop-Loss:** $14.51 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 75.0
- **%D:** 74.2
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 14.7 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $14.56 (-0.1% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** 0.0K
- **5-Day Trend:** Falling ↓
- **Signal:** Neutral

## VWAP (20-period)
- **VWAP:** $nan
- **Current vs VWAP:** +nan%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $15.50
- **Recent Low:** $14.42
- **Next Resistance:** $14.65 (78.6%)
- **Next Support:** $14.42 (100% (Low))

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 127. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:51.344640
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'FROPX'}`
- **Output Length:** 100 chars

### Output
```
Error retrieving insider transactions for FROPX: Too Many Requests. Rate limited. Try after a while.
```

---

## 128. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:51.452372
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'FROPX'}`
- **Output Length:** 126 chars

### Output
```
Error fetching recommendation trends for FROPX: FinnhubAPIException(status_code: 403): You don't have access to this resource.
```

---

## 129. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:51.465713
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'FROPX', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 96 chars

### Output
```
Error retrieving options activity for FROPX: Too Many Requests. Rate limited. Try after a while.
```

---

## 130. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:51.919943
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'FRBBX', 'curr_date': '2026-04-14'}`
- **Output Length:** 1490 chars

### Output
```
# Technical Analysis for FRBBX
**Date:** 2026-04-14
**Current Price:** $21.47

## Price Action
- **Daily Change:** +0.05%
- **5-Day Change:** +0.14%

## RSI (14)
- **Value:** 53.5 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** -0.013
- **Signal Line:** -0.023
- **Histogram:** 0.010 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $21.51 (-0.2% from price)
- **200 SMA:** $21.13 (+1.6% from price)
- **Trend:** Downtrend

## Bollinger Bands (20,2)
- **Upper:** $21.49
- **Middle:** $21.42
- **Lower:** $21.35
- **Band Position:** 89%
- **Bandwidth:** 0.6% (volatility indicator)
- **Signal:** Near upper band

## ATR (Volatility)
- **ATR:** $0.01 (0.1% of price)
- **Level:** Low volatility
- **Suggested Stop-Loss:** $21.45 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 89.5
- **%D:** 85.0
- **Signal:** OVERBOUGHT ⚠️

## ADX (Trend Strength)
- **ADX:** 8.7 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $21.45 (+0.1% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 0.0K
- **5-Day Trend:** Falling ↓
- **Signal:** Neutral

## VWAP (20-period)
- **VWAP:** $nan
- **Current vs VWAP:** +nan%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $21.64
- **Recent Low:** $21.34
- **Next Resistance:** $21.49 (50.0%)
- **Next Support:** $21.45 (61.8%)

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 131. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:51.986875
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'FRBBX'}`
- **Output Length:** 100 chars

### Output
```
Error retrieving insider transactions for FRBBX: Too Many Requests. Rate limited. Try after a while.
```

---

## 132. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:52.103272
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'FRBBX'}`
- **Output Length:** 126 chars

### Output
```
Error fetching recommendation trends for FRBBX: FinnhubAPIException(status_code: 403): You don't have access to this resource.
```

---

## 133. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:52.112787
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'FRBBX', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 96 chars

### Output
```
Error retrieving options activity for FRBBX: Too Many Requests. Rate limited. Try after a while.
```

---

## 134. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:52.544458
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'TER', 'curr_date': '2026-04-14'}`
- **Output Length:** 1566 chars

### Output
```
# Technical Analysis for TER
**Date:** 2026-04-14
**Current Price:** $370.13

## Price Action
- **Daily Change:** +0.58%
- **5-Day Change:** +15.49%

## RSI (14)
- **Value:** 69.4 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 16.412
- **Signal Line:** 9.087
- **Histogram:** 7.326 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $307.75 (+20.3% from price)
- **200 SMA:** $189.73 (+95.1% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $371.22
- **Middle:** $316.12
- **Lower:** $261.03
- **Band Position:** 99%
- **Bandwidth:** 34.9% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $17.66 (4.8% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $343.64 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 91.4
- **%D:** 82.7
- **Signal:** OVERBOUGHT ⚠️

## ADX (Trend Strength)
- **ADX:** 22.2 (Strengthening ↑)
- **Interpretation:** Trending

## 20 EMA
- **Value:** $324.59 (+14.0% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 170.1M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $317.02
- **Current vs VWAP:** +16.8%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $373.00
- **Recent Low:** $238.70
- **Next Resistance:** $373.00 (0.0% (High))
- **Next Support:** $341.31 (23.6%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 135. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:52.609116
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'TER'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for TER: Too Many Requests. Rate limited. Try after a while.
```

---

## 136. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:52.722331
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'TER'}`
- **Output Length:** 146 chars

### Output
```
Error fetching recommendation trends for TER: FinnhubAPIException(status_code: 429): API limit reached. Please try again later. Remaining Limit: 0
```

---

## 137. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:52.731567
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'TER', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for TER: Too Many Requests. Rate limited. Try after a while.
```

---

## 138. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:53.208905
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'NFLX', 'curr_date': '2026-04-14'}`
- **Output Length:** 1571 chars

### Output
```
# Technical Analysis for NFLX
**Date:** 2026-04-14
**Current Price:** $103.16

## Price Action
- **Daily Change:** +0.15%
- **5-Day Change:** +4.39%

## RSI (14)
- **Value:** 72.9 ↑
- **Signal:** OVERBOUGHT ⚠️

## MACD
- **MACD Line:** 2.944
- **Signal Line:** 2.282
- **Histogram:** 0.662 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $90.10 (+14.5% from price)
- **200 SMA:** $106.41 (-3.1% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $103.70
- **Middle:** $95.99
- **Lower:** $88.28
- **Band Position:** 96%
- **Bandwidth:** 16.1% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $2.75 (2.7% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $99.04 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 88.9
- **%D:** 80.3
- **Signal:** OVERBOUGHT ⚠️

## ADX (Trend Strength)
- **ADX:** 47.8 (Strengthening ↑)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $97.04 (+6.3% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** -576.3M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $95.53
- **Current vs VWAP:** +8.0%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $103.67
- **Recent Low:** $75.01
- **Next Resistance:** $103.67 (0.0% (High))
- **Next Support:** $96.91 (23.6%)

## Summary
- **Key Signals:** RSI overbought, Above 50 SMA

```

---

## 139. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:53.364031
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'NFLX'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for NFLX: Too Many Requests. Rate limited. Try after a while.
```

---

## 140. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:53.471753
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'NFLX'}`
- **Output Length:** 147 chars

### Output
```
Error fetching recommendation trends for NFLX: FinnhubAPIException(status_code: 429): API limit reached. Please try again later. Remaining Limit: 0
```

---

## 141. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:53.484851
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'NFLX', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for NFLX: Too Many Requests. Rate limited. Try after a while.
```

---

## 142. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:53.955206
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'GS', 'curr_date': '2026-04-14'}`
- **Output Length:** 1534 chars

### Output
```
# Technical Analysis for GS
**Date:** 2026-04-14
**Current Price:** $890.79

## Price Action
- **Daily Change:** -1.87%
- **5-Day Change:** +3.08%

## RSI (14)
- **Value:** 59.2 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 11.572
- **Signal Line:** 0.875
- **Histogram:** 10.697 (Weakening ↓)
- **Signal:** Bullish

## Moving Averages
- **50 SMA:** $869.69 (+2.4% from price)
- **200 SMA:** $809.55 (+10.0% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $918.34
- **Middle:** $843.99
- **Lower:** $769.64
- **Band Position:** 81%
- **Bandwidth:** 17.6% (volatility indicator)
- **Signal:** Near upper band

## ATR (Volatility)
- **ATR:** $27.96 (3.1% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $848.84 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 83.3
- **%D:** 82.7
- **Signal:** OVERBOUGHT ⚠️

## ADX (Trend Strength)
- **ADX:** 9.1 (Strengthening ↑)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $861.57 (+3.4% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 59.8M
- **5-Day Trend:** Falling ↓
- **Signal:** BEARISH DIVERGENCE ⚠️ (distribution)

## VWAP (20-period)
- **VWAP:** $843.95
- **Current vs VWAP:** +5.6%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $963.32
- **Recent Low:** $780.50
- **Next Resistance:** $893.48 (38.2%)
- **Next Support:** $871.91 (50.0%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 143. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:54.035950
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'GS'}`
- **Output Length:** 97 chars

### Output
```
Error retrieving insider transactions for GS: Too Many Requests. Rate limited. Try after a while.
```

---

## 144. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:54.147003
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'GS'}`
- **Output Length:** 145 chars

### Output
```
Error fetching recommendation trends for GS: FinnhubAPIException(status_code: 429): API limit reached. Please try again later. Remaining Limit: 0
```

---

## 145. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:54.159536
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'GS', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 93 chars

### Output
```
Error retrieving options activity for GS: Too Many Requests. Rate limited. Try after a while.
```

---

## 146. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:54.642202
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'ADI', 'curr_date': '2026-04-14'}`
- **Output Length:** 1565 chars

### Output
```
# Technical Analysis for ADI
**Date:** 2026-04-14
**Current Price:** $350.01

## Price Action
- **Daily Change:** -0.04%
- **5-Day Change:** +6.90%

## RSI (14)
- **Value:** 66.9 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 6.392
- **Signal Line:** 1.752
- **Histogram:** 4.640 (Weakening ↓)
- **Signal:** Bullish

## Moving Averages
- **50 SMA:** $327.84 (+6.8% from price)
- **200 SMA:** $270.00 (+29.6% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $352.96
- **Middle:** $322.13
- **Lower:** $291.30
- **Band Position:** 95%
- **Bandwidth:** 19.1% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $9.85 (2.8% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $335.24 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 90.2
- **%D:** 84.2
- **Signal:** OVERBOUGHT ⚠️

## ADX (Trend Strength)
- **ADX:** 17.7 (Strengthening ↑)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $329.25 (+6.3% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 84.8M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $320.46
- **Current vs VWAP:** +9.2%
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

## 147. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:54.755607
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'ADI'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for ADI: Too Many Requests. Rate limited. Try after a while.
```

---

## 148. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:54.872633
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'ADI'}`
- **Output Length:** 146 chars

### Output
```
Error fetching recommendation trends for ADI: FinnhubAPIException(status_code: 429): API limit reached. Please try again later. Remaining Limit: 0
```

---

## 149. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:54.882149
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'ADI', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for ADI: Too Many Requests. Rate limited. Try after a while.
```

---

## 150. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:55.299157
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'HOVR', 'curr_date': '2026-04-14'}`
- **Output Length:** 1522 chars

### Output
```
# Technical Analysis for HOVR
**Date:** 2026-04-14
**Current Price:** $1.56

## Price Action
- **Daily Change:** -1.27%
- **5-Day Change:** +12.23%

## RSI (14)
- **Value:** 47.4 ↑
- **Signal:** Bearish

## MACD
- **MACD Line:** -0.080
- **Signal Line:** -0.103
- **Histogram:** 0.023 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $1.74 (-10.6% from price)
- **200 SMA:** $1.91 (-18.2% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $1.90
- **Middle:** $1.55
- **Lower:** $1.21
- **Band Position:** 51%
- **Bandwidth:** 44.7% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $0.15 (9.8% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $1.33 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 60.1
- **%D:** 51.6
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 15.2 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $1.57 (-0.5% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** -17.7M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $1.54
- **Current vs VWAP:** +1.6%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $2.13
- **Recent Low:** $1.25
- **Next Resistance:** $1.59 (61.8%)
- **Next Support:** $1.44 (78.6%)

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 151. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:55.364205
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'HOVR'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for HOVR: Too Many Requests. Rate limited. Try after a while.
```

---

## 152. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:55.464148
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'HOVR'}`
- **Output Length:** 147 chars

### Output
```
Error fetching recommendation trends for HOVR: FinnhubAPIException(status_code: 429): API limit reached. Please try again later. Remaining Limit: 0
```

---

## 153. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:55.472781
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'HOVR', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for HOVR: Too Many Requests. Rate limited. Try after a while.
```

---

## 154. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:55.967092
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'WFC', 'curr_date': '2026-04-14'}`
- **Output Length:** 1554 chars

### Output
```
# Technical Analysis for WFC
**Date:** 2026-04-14
**Current Price:** $86.64

## Price Action
- **Daily Change:** +1.45%
- **5-Day Change:** +5.98%

## RSI (14)
- **Value:** 65.7 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 0.946
- **Signal Line:** -0.266
- **Histogram:** 1.212 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $83.45 (+3.8% from price)
- **200 SMA:** $83.87 (+3.3% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $86.92
- **Middle:** $80.02
- **Lower:** $73.12
- **Band Position:** 98%
- **Bandwidth:** 17.3% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $2.20 (2.5% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $83.34 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 93.8
- **%D:** 88.3
- **Signal:** OVERBOUGHT ⚠️

## ADX (Trend Strength)
- **ADX:** 15.8 (Strengthening ↑)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $81.81 (+5.9% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 359.5M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $79.28
- **Current vs VWAP:** +9.3%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $95.09
- **Recent Low:** $74.03
- **Next Resistance:** $87.05 (38.2%)
- **Next Support:** $84.56 (50.0%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 155. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:56.061720
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'WFC'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for WFC: Too Many Requests. Rate limited. Try after a while.
```

---

## 156. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:56.164154
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'WFC'}`
- **Output Length:** 146 chars

### Output
```
Error fetching recommendation trends for WFC: FinnhubAPIException(status_code: 429): API limit reached. Please try again later. Remaining Limit: 0
```

---

## 157. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:56.174347
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'WFC', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for WFC: Too Many Requests. Rate limited. Try after a while.
```

---

## 158. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:56.736796
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'THCH', 'curr_date': '2026-04-14'}`
- **Output Length:** 1510 chars

### Output
```
# Technical Analysis for THCH
**Date:** 2026-04-14
**Current Price:** $2.16

## Price Action
- **Daily Change:** +6.40%
- **5-Day Change:** -1.82%

## RSI (14)
- **Value:** 54.4 ↓
- **Signal:** Bullish

## MACD
- **MACD Line:** 0.025
- **Signal Line:** 0.020
- **Histogram:** 0.006 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $2.00 (+8.2% from price)
- **200 SMA:** $2.43 (-11.1% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $2.29
- **Middle:** $2.09
- **Lower:** $1.89
- **Band Position:** 68%
- **Bandwidth:** 19.1% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $0.14 (6.5% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $1.95 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 58.8
- **%D:** 62.8
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 11.2 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $2.09 (+3.4% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** -36.7K
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $2.09
- **Current vs VWAP:** +3.5%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $2.42
- **Recent Low:** $1.68
- **Next Resistance:** $2.25 (23.6%)
- **Next Support:** $2.14 (38.2%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 159. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:56.813975
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'THCH'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for THCH: Too Many Requests. Rate limited. Try after a while.
```

---

## 160. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:56.907741
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'THCH'}`
- **Output Length:** 147 chars

### Output
```
Error fetching recommendation trends for THCH: FinnhubAPIException(status_code: 429): API limit reached. Please try again later. Remaining Limit: 0
```

---

## 161. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:56.917787
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'THCH', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for THCH: Too Many Requests. Rate limited. Try after a while.
```

---

## 162. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:57.452698
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'JNJ', 'curr_date': '2026-04-14'}`
- **Output Length:** 1539 chars

### Output
```
# Technical Analysis for JNJ
**Date:** 2026-04-14
**Current Price:** $237.96

## Price Action
- **Daily Change:** -0.21%
- **5-Day Change:** -0.19%

## RSI (14)
- **Value:** 45.6 ↓
- **Signal:** Bearish

## MACD
- **MACD Line:** 0.208
- **Signal Line:** 0.645
- **Histogram:** -0.437 (Strengthening ↑)
- **Signal:** BEARISH CROSSOVER ⚠️

## Moving Averages
- **50 SMA:** $240.47 (-1.0% from price)
- **200 SMA:** $199.37 (+19.4% from price)
- **Trend:** Downtrend

## Bollinger Bands (20,2)
- **Upper:** $245.46
- **Middle:** $239.72
- **Lower:** $233.98
- **Band Position:** 35%
- **Bandwidth:** 4.8% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $4.20 (1.8% of price)
- **Level:** Low volatility
- **Suggested Stop-Loss:** $231.66 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 42.1
- **%D:** 50.4
- **Signal:** Bearish

## ADX (Trend Strength)
- **ADX:** 16.4 (Strengthening ↑)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $240.24 (-0.9% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** 267.4M
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $239.49
- **Current vs VWAP:** -0.6%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $251.71
- **Recent Low:** $224.14
- **Next Resistance:** $241.18 (38.2%)
- **Next Support:** $237.92 (50.0%)

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 163. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:57.531321
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'JNJ'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for JNJ: Too Many Requests. Rate limited. Try after a while.
```

---

## 164. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:57.631926
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'JNJ'}`
- **Output Length:** 146 chars

### Output
```
Error fetching recommendation trends for JNJ: FinnhubAPIException(status_code: 429): API limit reached. Please try again later. Remaining Limit: 0
```

---

## 165. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:57.641365
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'JNJ', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for JNJ: Too Many Requests. Rate limited. Try after a while.
```

---

## 166. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:58.078410
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'KMX', 'curr_date': '2026-04-14'}`
- **Output Length:** 1558 chars

### Output
```
# Technical Analysis for KMX
**Date:** 2026-04-14
**Current Price:** $49.08

## Price Action
- **Daily Change:** +5.05%
- **5-Day Change:** +13.32%

## RSI (14)
- **Value:** 71.1 ↑
- **Signal:** OVERBOUGHT ⚠️

## MACD
- **MACD Line:** 0.927
- **Signal Line:** 0.109
- **Histogram:** 0.818 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $43.21 (+13.6% from price)
- **200 SMA:** $48.02 (+2.2% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $47.10
- **Middle:** $42.74
- **Lower:** $38.39
- **Band Position:** 123%
- **Bandwidth:** 20.4% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $1.98 (4.0% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $46.11 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 87.9
- **%D:** 74.7
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 20.1 (Strengthening ↑)
- **Interpretation:** Trending

## 20 EMA
- **Value:** $43.50 (+12.8% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** -48.1M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $43.02
- **Current vs VWAP:** +14.1%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $49.44
- **Recent Low:** $39.02
- **Next Resistance:** $49.44 (0.0% (High))
- **Next Support:** $46.98 (23.6%)

## Summary
- **Key Signals:** RSI overbought, Above 50 SMA

```

---

## 167. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:58.143911
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'KMX'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for KMX: Too Many Requests. Rate limited. Try after a while.
```

---

## 168. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:58.243383
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'KMX'}`
- **Output Length:** 146 chars

### Output
```
Error fetching recommendation trends for KMX: FinnhubAPIException(status_code: 429): API limit reached. Please try again later. Remaining Limit: 0
```

---

## 169. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:58.254183
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'KMX', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for KMX: Too Many Requests. Rate limited. Try after a while.
```

---

## 170. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:58.794634
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'JPM', 'curr_date': '2026-04-14'}`
- **Output Length:** 1573 chars

### Output
```
# Technical Analysis for JPM
**Date:** 2026-04-14
**Current Price:** $313.68

## Price Action
- **Daily Change:** +1.23%
- **5-Day Change:** +5.47%

## RSI (14)
- **Value:** 69.3 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 3.854
- **Signal Line:** 0.529
- **Histogram:** 3.325 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $298.21 (+5.2% from price)
- **200 SMA:** $300.33 (+4.4% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $313.03
- **Middle:** $293.48
- **Lower:** $273.92
- **Band Position:** 102%
- **Bandwidth:** 13.3% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $7.05 (2.2% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $303.11 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 93.6
- **%D:** 86.1
- **Signal:** OVERBOUGHT ⚠️

## ADX (Trend Strength)
- **ADX:** 19.6 (Strengthening ↑)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $297.79 (+5.3% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 138.5M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $292.03
- **Current vs VWAP:** +7.4%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $324.74
- **Recent Low:** $277.68
- **Next Resistance:** $324.74 (0.0% (High))
- **Next Support:** $313.63 (23.6%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 171. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:58.873206
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'JPM'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for JPM: Too Many Requests. Rate limited. Try after a while.
```

---

## 172. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:58.988713
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'JPM'}`
- **Output Length:** 146 chars

### Output
```
Error fetching recommendation trends for JPM: FinnhubAPIException(status_code: 429): API limit reached. Please try again later. Remaining Limit: 0
```

---

## 173. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:58.998674
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'JPM', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for JPM: Too Many Requests. Rate limited. Try after a while.
```

---

## 174. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:59.486421
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'EQBK', 'curr_date': '2026-04-14'}`
- **Output Length:** 1511 chars

### Output
```
# Technical Analysis for EQBK
**Date:** 2026-04-14
**Current Price:** $46.11

## Price Action
- **Daily Change:** -0.54%
- **5-Day Change:** +0.92%

## RSI (14)
- **Value:** 62.9 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 0.416
- **Signal Line:** 0.074
- **Histogram:** 0.342 (Weakening ↓)
- **Signal:** Bullish

## Moving Averages
- **50 SMA:** $45.13 (+2.2% from price)
- **200 SMA:** $42.63 (+8.2% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $46.76
- **Middle:** $44.45
- **Lower:** $42.13
- **Band Position:** 86%
- **Bandwidth:** 10.4% (volatility indicator)
- **Signal:** Near upper band

## ATR (Volatility)
- **ATR:** $1.03 (2.2% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $44.57 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 74.0
- **%D:** 76.4
- **Signal:** Bearish crossover ⚠️

## ADX (Trend Strength)
- **ADX:** 20.5 (Strengthening ↑)
- **Interpretation:** Trending

## 20 EMA
- **Value:** $45.00 (+2.5% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** -460.3K
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $44.34
- **Current vs VWAP:** +4.0%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $48.46
- **Recent Low:** $42.56
- **Next Resistance:** $46.21 (38.2%)
- **Next Support:** $45.51 (50.0%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 175. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:59.555638
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'EQBK'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for EQBK: Too Many Requests. Rate limited. Try after a while.
```

---

## 176. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:59.661714
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'EQBK'}`
- **Output Length:** 147 chars

### Output
```
Error fetching recommendation trends for EQBK: FinnhubAPIException(status_code: 429): API limit reached. Please try again later. Remaining Limit: 0
```

---

## 177. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:23:59.671961
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'EQBK', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for EQBK: Too Many Requests. Rate limited. Try after a while.
```

---

## 178. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:00.184488
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'BLK', 'curr_date': '2026-04-14'}`
- **Output Length:** 1566 chars

### Output
```
# Technical Analysis for BLK
**Date:** 2026-04-14
**Current Price:** $1023.65

## Price Action
- **Daily Change:** +2.44%
- **5-Day Change:** +6.80%

## RSI (14)
- **Value:** 60.4 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** -2.396
- **Signal Line:** -13.093
- **Histogram:** 10.698 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $1015.24 (+0.8% from price)
- **200 SMA:** $1073.86 (-4.7% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $1015.98
- **Middle:** $970.41
- **Lower:** $924.83
- **Band Position:** 108%
- **Bandwidth:** 9.4% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $28.80 (2.8% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $980.45 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 80.0
- **%D:** 67.4
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 11.0 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $982.68 (+4.2% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 8.4M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $969.94
- **Current vs VWAP:** +5.5%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $1122.82
- **Recent Low:** $917.39
- **Next Resistance:** $1044.35 (38.2%)
- **Next Support:** $1020.10 (50.0%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 179. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:00.256840
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'BLK'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for BLK: Too Many Requests. Rate limited. Try after a while.
```

---

## 180. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:00.361299
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'BLK'}`
- **Output Length:** 146 chars

### Output
```
Error fetching recommendation trends for BLK: FinnhubAPIException(status_code: 429): API limit reached. Please try again later. Remaining Limit: 0
```

---

## 181. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:00.370403
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'BLK', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for BLK: Too Many Requests. Rate limited. Try after a while.
```

---

## 182. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:00.755485
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'DTST', 'curr_date': '2026-04-14'}`
- **Output Length:** 1526 chars

### Output
```
# Technical Analysis for DTST
**Date:** 2026-04-14
**Current Price:** $4.22

## Price Action
- **Daily Change:** +5.50%
- **5-Day Change:** +9.90%

## RSI (14)
- **Value:** 57.6 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** -0.018
- **Signal Line:** -0.059
- **Histogram:** 0.041 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $4.14 (+2.0% from price)
- **200 SMA:** $4.37 (-3.5% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $4.18
- **Middle:** $3.94
- **Lower:** $3.70
- **Band Position:** 109%
- **Bandwidth:** 12.0% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $0.23 (5.5% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $3.87 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 63.2
- **%D:** 54.8
- **Signal:** Bullish crossover ⚡

## ADX (Trend Strength)
- **ADX:** 20.4 (Strengthening ↑)
- **Interpretation:** Trending

## 20 EMA
- **Value:** $3.98 (+6.0% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 12.4M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $3.95
- **Current vs VWAP:** +6.9%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $4.95
- **Recent Low:** $3.68
- **Next Resistance:** $4.31 (50.0%)
- **Next Support:** $4.17 (61.8%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 183. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:00.875444
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'DTST'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for DTST: Too Many Requests. Rate limited. Try after a while.
```

---

## 184. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:00.973017
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'DTST'}`
- **Output Length:** 147 chars

### Output
```
Error fetching recommendation trends for DTST: FinnhubAPIException(status_code: 429): API limit reached. Please try again later. Remaining Limit: 0
```

---

## 185. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:00.981915
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'DTST', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for DTST: Too Many Requests. Rate limited. Try after a while.
```

---

## 186. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:01.402185
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'SURG', 'curr_date': '2026-04-14'}`
- **Output Length:** 1530 chars

### Output
```
# Technical Analysis for SURG
**Date:** 2026-04-14
**Current Price:** $0.72

## Price Action
- **Daily Change:** +7.46%
- **5-Day Change:** +2.86%

## RSI (14)
- **Value:** 39.8 ↑
- **Signal:** Bearish

## MACD
- **MACD Line:** -0.059
- **Signal Line:** -0.060
- **Histogram:** 0.001 (Weakening ↓)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $0.85 (-15.0% from price)
- **200 SMA:** $2.03 (-64.6% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $0.92
- **Middle:** $0.77
- **Lower:** $0.62
- **Band Position:** 33%
- **Bandwidth:** 38.6% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $0.07 (9.8% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $0.61 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 25.5
- **%D:** 17.7
- **Signal:** Bullish crossover ⚡

## ADX (Trend Strength)
- **ADX:** 17.4 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $0.76 (-4.9% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** -8.8M
- **5-Day Trend:** Falling ↓
- **Signal:** BEARISH DIVERGENCE ⚠️ (distribution)

## VWAP (20-period)
- **VWAP:** $0.79
- **Current vs VWAP:** -8.5%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $1.21
- **Recent Low:** $0.65
- **Next Resistance:** $0.77 (78.6%)
- **Next Support:** $0.65 (100% (Low))

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 187. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:01.481495
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'SURG'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for SURG: Too Many Requests. Rate limited. Try after a while.
```

---

## 188. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:01.600759
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'SURG'}`
- **Output Length:** 147 chars

### Output
```
Error fetching recommendation trends for SURG: FinnhubAPIException(status_code: 429): API limit reached. Please try again later. Remaining Limit: 0
```

---

## 189. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:01.611576
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'SURG', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for SURG: Too Many Requests. Rate limited. Try after a while.
```

---

## 190. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:02.084404
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'AAPL', 'curr_date': '2026-04-14'}`
- **Output Length:** 1522 chars

### Output
```
# Technical Analysis for AAPL
**Date:** 2026-04-14
**Current Price:** $259.20

## Price Action
- **Daily Change:** -0.49%
- **5-Day Change:** +2.25%

## RSI (14)
- **Value:** 53.7 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 0.079
- **Signal Line:** -1.288
- **Histogram:** 1.367 (Weakening ↓)
- **Signal:** Bullish

## Moving Averages
- **50 SMA:** $260.87 (-0.6% from price)
- **200 SMA:** $250.60 (+3.4% from price)
- **Trend:** Downtrend

## Bollinger Bands (20,2)
- **Upper:** $262.20
- **Middle:** $253.74
- **Lower:** $245.28
- **Band Position:** 82%
- **Bandwidth:** 6.7% (volatility indicator)
- **Signal:** Near upper band

## ATR (Volatility)
- **ATR:** $5.75 (2.2% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $250.57 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 81.3
- **%D:** 75.5
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 10.9 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $256.39 (+1.1% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 1123.7M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $252.99
- **Current vs VWAP:** +2.5%
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

## 191. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:02.216260
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'AAPL'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for AAPL: Too Many Requests. Rate limited. Try after a while.
```

---

## 192. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:02.326402
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'AAPL'}`
- **Output Length:** 147 chars

### Output
```
Error fetching recommendation trends for AAPL: FinnhubAPIException(status_code: 429): API limit reached. Please try again later. Remaining Limit: 0
```

---

## 193. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:02.336393
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'AAPL', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for AAPL: Too Many Requests. Rate limited. Try after a while.
```

---

## 194. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:03.146990
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'AMZN', 'curr_date': '2026-04-14'}`
- **Output Length:** 1582 chars

### Output
```
# Technical Analysis for AMZN
**Date:** 2026-04-14
**Current Price:** $239.89

## Price Action
- **Daily Change:** +0.63%
- **5-Day Change:** +12.22%

## RSI (14)
- **Value:** 72.2 ↑
- **Signal:** OVERBOUGHT ⚠️

## MACD
- **MACD Line:** 5.067
- **Signal Line:** 1.064
- **Histogram:** 4.003 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $213.37 (+12.4% from price)
- **200 SMA:** $225.00 (+6.6% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $236.22
- **Middle:** $213.81
- **Lower:** $191.40
- **Band Position:** 108%
- **Bandwidth:** 21.0% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $6.51 (2.7% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $230.12 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 92.5
- **%D:** 83.8
- **Signal:** OVERBOUGHT ⚠️

## ADX (Trend Strength)
- **ADX:** 28.1 (Strengthening ↑)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $217.78 (+10.2% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 666.2M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $214.22
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

## 195. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:03.236193
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'AMZN'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for AMZN: Too Many Requests. Rate limited. Try after a while.
```

---

## 196. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:03.341879
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'AMZN'}`
- **Output Length:** 147 chars

### Output
```
Error fetching recommendation trends for AMZN: FinnhubAPIException(status_code: 429): API limit reached. Please try again later. Remaining Limit: 0
```

---

## 197. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:03.351392
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'AMZN', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for AMZN: Too Many Requests. Rate limited. Try after a while.
```

---

## 198. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:03.824389
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'AMT', 'curr_date': '2026-04-14'}`
- **Output Length:** 1531 chars

### Output
```
# Technical Analysis for AMT
**Date:** 2026-04-14
**Current Price:** $180.94

## Price Action
- **Daily Change:** +0.92%
- **5-Day Change:** +3.94%

## RSI (14)
- **Value:** 55.3 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** -0.935
- **Signal Line:** -2.106
- **Histogram:** 1.171 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $180.68 (+0.1% from price)
- **200 SMA:** $188.31 (-3.9% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $186.64
- **Middle:** $175.84
- **Lower:** $165.04
- **Band Position:** 74%
- **Bandwidth:** 12.3% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $4.64 (2.6% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $173.97 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 79.8
- **%D:** 70.5
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 14.1 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $177.15 (+2.1% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 3.1M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $175.89
- **Current vs VWAP:** +2.9%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $195.45
- **Recent Low:** $165.08
- **Next Resistance:** $183.85 (38.2%)
- **Next Support:** $180.26 (50.0%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 199. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:03.890642
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'AMT'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for AMT: Too Many Requests. Rate limited. Try after a while.
```

---

## 200. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:03.990263
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'AMT'}`
- **Output Length:** 146 chars

### Output
```
Error fetching recommendation trends for AMT: FinnhubAPIException(status_code: 429): API limit reached. Please try again later. Remaining Limit: 0
```

---

## 201. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:03.999920
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'AMT', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for AMT: Too Many Requests. Rate limited. Try after a while.
```

---

## 202. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:04.439376
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'CSCO', 'curr_date': '2026-04-14'}`
- **Output Length:** 1520 chars

### Output
```
# Technical Analysis for CSCO
**Date:** 2026-04-14
**Current Price:** $82.35

## Price Action
- **Daily Change:** +0.16%
- **5-Day Change:** +2.07%

## RSI (14)
- **Value:** 58.7 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 1.022
- **Signal Line:** 0.600
- **Histogram:** 0.423 (Weakening ↓)
- **Signal:** Bullish

## Moving Averages
- **50 SMA:** $79.47 (+3.6% from price)
- **200 SMA:** $72.94 (+12.9% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $84.07
- **Middle:** $79.71
- **Lower:** $75.34
- **Band Position:** 80%
- **Bandwidth:** 11.0% (volatility indicator)
- **Signal:** Near upper band

## ATR (Volatility)
- **ATR:** $2.13 (2.6% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $79.16 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 73.0
- **%D:** 68.0
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 13.9 (Strengthening ↑)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $80.20 (+2.7% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 367.2M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $79.33
- **Current vs VWAP:** +3.8%
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

## 203. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:04.547756
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'CSCO'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for CSCO: Too Many Requests. Rate limited. Try after a while.
```

---

## 204. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:04.645142
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'CSCO'}`
- **Output Length:** 147 chars

### Output
```
Error fetching recommendation trends for CSCO: FinnhubAPIException(status_code: 429): API limit reached. Please try again later. Remaining Limit: 0
```

---

## 205. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:04.668476
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'CSCO', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for CSCO: Too Many Requests. Rate limited. Try after a while.
```

---

## 206. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:05.071746
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'COIN', 'curr_date': '2026-04-14'}`
- **Output Length:** 1550 chars

### Output
```
# Technical Analysis for COIN
**Date:** 2026-04-14
**Current Price:** $174.53

## Price Action
- **Daily Change:** +3.98%
- **5-Day Change:** -0.37%

## RSI (14)
- **Value:** 45.9 ↑
- **Signal:** Bearish

## MACD
- **MACD Line:** -5.204
- **Signal Line:** -4.711
- **Histogram:** -0.492 (Weakening ↓)
- **Signal:** Bearish

## Moving Averages
- **50 SMA:** $179.08 (-2.5% from price)
- **200 SMA:** $276.19 (-36.8% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $212.14
- **Middle:** $181.49
- **Lower:** $150.85
- **Band Position:** 39%
- **Bandwidth:** 33.8% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $11.20 (6.4% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $157.73 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 39.3
- **%D:** 36.8
- **Signal:** Bullish crossover ⚡

## ADX (Trend Strength)
- **ADX:** 12.3 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $177.81 (-1.8% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** -117.8M
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $183.32
- **Current vs VWAP:** -4.8%
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

## 207. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:05.152060
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'COIN'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for COIN: Too Many Requests. Rate limited. Try after a while.
```

---

## 208. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:05.265418
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'COIN'}`
- **Output Length:** 147 chars

### Output
```
Error fetching recommendation trends for COIN: FinnhubAPIException(status_code: 429): API limit reached. Please try again later. Remaining Limit: 0
```

---

## 209. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:05.274497
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'COIN', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for COIN: Too Many Requests. Rate limited. Try after a while.
```

---

## 210. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:05.699965
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'BSX', 'curr_date': '2026-04-14'}`
- **Output Length:** 1531 chars

### Output
```
# Technical Analysis for BSX
**Date:** 2026-04-14
**Current Price:** $63.18

## Price Action
- **Daily Change:** +2.25%
- **5-Day Change:** +2.13%

## RSI (14)
- **Value:** 36.0 ↑
- **Signal:** Bearish

## MACD
- **MACD Line:** -3.194
- **Signal Line:** -3.255
- **Histogram:** 0.061 (Weakening ↓)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $71.87 (-12.1% from price)
- **200 SMA:** $92.99 (-32.1% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $73.92
- **Middle:** $66.11
- **Lower:** $58.30
- **Band Position:** 31%
- **Bandwidth:** 23.6% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $2.03 (3.2% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $60.13 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 34.4
- **%D:** 22.2
- **Signal:** Bullish crossover ⚡

## ADX (Trend Strength)
- **ADX:** 45.2 (Weakening ↓)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $65.60 (-3.7% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** -293.9M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $65.45
- **Current vs VWAP:** -3.5%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $94.25
- **Recent Low:** $60.59
- **Next Resistance:** $67.79 (78.6%)
- **Next Support:** $60.59 (100% (Low))

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 211. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:05.776730
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'BSX'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for BSX: Too Many Requests. Rate limited. Try after a while.
```

---

## 212. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:05.876629
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'BSX'}`
- **Output Length:** 146 chars

### Output
```
Error fetching recommendation trends for BSX: FinnhubAPIException(status_code: 429): API limit reached. Please try again later. Remaining Limit: 0
```

---

## 213. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:05.887249
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'BSX', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for BSX: Too Many Requests. Rate limited. Try after a while.
```

---

## 214. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:06.335405
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'AKAM', 'curr_date': '2026-04-14'}`
- **Output Length:** 1549 chars

### Output
```
# Technical Analysis for AKAM
**Date:** 2026-04-14
**Current Price:** $94.94

## Price Action
- **Daily Change:** +3.93%
- **5-Day Change:** -16.64%

## RSI (14)
- **Value:** 36.6 ↓
- **Signal:** Bearish

## MACD
- **MACD Line:** -0.377
- **Signal Line:** 2.312
- **Histogram:** -2.688 (Strengthening ↑)
- **Signal:** BEARISH CROSSOVER ⚠️

## Moving Averages
- **50 SMA:** $104.65 (-9.3% from price)
- **200 SMA:** $87.13 (+9.0% from price)
- **Trend:** Downtrend

## Bollinger Bands (20,2)
- **Upper:** $125.38
- **Middle:** $110.98
- **Lower:** $96.59
- **Band Position:** -6%
- **Bandwidth:** 25.9% (volatility indicator)
- **Signal:** AT LOWER BAND - Potential bounce ⚡

## ATR (Volatility)
- **ATR:** $6.18 (6.5% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $85.67 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 25.8
- **%D:** 39.4
- **Signal:** Bearish

## ADX (Trend Strength)
- **ADX:** 28.8 (Strengthening ↑)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $108.44 (-12.4% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** 74.3M
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $109.77
- **Current vs VWAP:** -13.5%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $121.12
- **Recent Low:** $90.56
- **Next Resistance:** $97.10 (78.6%)
- **Next Support:** $90.56 (100% (Low))

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 215. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:06.441795
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'AKAM'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for AKAM: Too Many Requests. Rate limited. Try after a while.
```

---

## 216. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:06.543216
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'AKAM'}`
- **Output Length:** 147 chars

### Output
```
Error fetching recommendation trends for AKAM: FinnhubAPIException(status_code: 429): API limit reached. Please try again later. Remaining Limit: 0
```

---

## 217. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:06.554869
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'AKAM', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for AKAM: Too Many Requests. Rate limited. Try after a while.
```

---

## 218. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:07.032921
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'AXP', 'curr_date': '2026-04-14'}`
- **Output Length:** 1573 chars

### Output
```
# Technical Analysis for AXP
**Date:** 2026-04-14
**Current Price:** $323.82

## Price Action
- **Daily Change:** +3.29%
- **5-Day Change:** +5.47%

## RSI (14)
- **Value:** 62.7 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 0.295
- **Signal Line:** -3.794
- **Histogram:** 4.089 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $318.89 (+1.5% from price)
- **200 SMA:** $333.90 (-3.0% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $320.32
- **Middle:** $302.63
- **Lower:** $284.94
- **Band Position:** 110%
- **Bandwidth:** 11.7% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $8.72 (2.7% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $310.75 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 84.9
- **%D:** 78.7
- **Signal:** Bullish crossover ⚡

## ADX (Trend Strength)
- **ADX:** 16.6 (Strengthening ↑)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $308.25 (+5.1% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 26.6M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $301.33
- **Current vs VWAP:** +7.5%
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

## 219. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:07.115103
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'AXP'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for AXP: Too Many Requests. Rate limited. Try after a while.
```

---

## 220. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:07.216932
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'AXP'}`
- **Output Length:** 146 chars

### Output
```
Error fetching recommendation trends for AXP: FinnhubAPIException(status_code: 429): API limit reached. Please try again later. Remaining Limit: 0
```

---

## 221. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:07.227470
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'AXP', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for AXP: Too Many Requests. Rate limited. Try after a while.
```

---

## 222. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:07.671021
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'CARR', 'curr_date': '2026-04-14'}`
- **Output Length:** 1530 chars

### Output
```
# Technical Analysis for CARR
**Date:** 2026-04-14
**Current Price:** $64.32

## Price Action
- **Daily Change:** +1.55%
- **5-Day Change:** +16.02%

## RSI (14)
- **Value:** 67.2 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 0.484
- **Signal Line:** -0.546
- **Histogram:** 1.030 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $60.42 (+6.5% from price)
- **200 SMA:** $60.72 (+5.9% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $63.29
- **Middle:** $57.71
- **Lower:** $52.14
- **Band Position:** 109%
- **Bandwidth:** 19.3% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $2.09 (3.3% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $61.18 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 82.2
- **%D:** 64.6
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 23.7 (Strengthening ↑)
- **Interpretation:** Trending

## 20 EMA
- **Value:** $58.75 (+9.5% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** -62.5M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $57.80
- **Current vs VWAP:** +11.3%
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

## 223. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:07.748428
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'CARR'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for CARR: Too Many Requests. Rate limited. Try after a while.
```

---

## 224. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:07.852663
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'CARR'}`
- **Output Length:** 147 chars

### Output
```
Error fetching recommendation trends for CARR: FinnhubAPIException(status_code: 429): API limit reached. Please try again later. Remaining Limit: 0
```

---

## 225. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:07.862393
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'CARR', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for CARR: Too Many Requests. Rate limited. Try after a while.
```

---

## 226. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:08.310319
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'CRM', 'curr_date': '2026-04-14'}`
- **Output Length:** 1530 chars

### Output
```
# Technical Analysis for CRM
**Date:** 2026-04-14
**Current Price:** $172.82

## Price Action
- **Daily Change:** +4.76%
- **5-Day Change:** -5.31%

## RSI (14)
- **Value:** 38.0 ↓
- **Signal:** Bearish

## MACD
- **MACD Line:** -6.251
- **Signal Line:** -4.895
- **Histogram:** -1.356 (Weakening ↓)
- **Signal:** Bearish

## Moving Averages
- **50 SMA:** $189.69 (-8.9% from price)
- **200 SMA:** $233.69 (-26.0% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $202.57
- **Middle:** $184.68
- **Lower:** $166.79
- **Band Position:** 17%
- **Bandwidth:** 19.4% (volatility indicator)
- **Signal:** Near lower band

## ATR (Volatility)
- **ATR:** $7.56 (4.4% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $161.48 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 24.5
- **%D:** 25.2
- **Signal:** Bearish

## ADX (Trend Strength)
- **ADX:** 28.4 (Strengthening ↑)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $182.58 (-5.3% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** -26.7M
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $184.23
- **Current vs VWAP:** -6.2%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $216.35
- **Recent Low:** $163.52
- **Next Resistance:** $174.83 (78.6%)
- **Next Support:** $163.52 (100% (Low))

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 227. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:08.396789
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'CRM'}`
- **Output Length:** 98 chars

### Output
```
Error retrieving insider transactions for CRM: Too Many Requests. Rate limited. Try after a while.
```

---

## 228. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:08.504082
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'CRM'}`
- **Output Length:** 146 chars

### Output
```
Error fetching recommendation trends for CRM: FinnhubAPIException(status_code: 429): API limit reached. Please try again later. Remaining Limit: 0
```

---

## 229. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:08.514069
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'CRM', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 94 chars

### Output
```
Error retrieving options activity for CRM: Too Many Requests. Rate limited. Try after a while.
```

---

## 230. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:08.986080
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'RKLB', 'curr_date': '2026-04-14'}`
- **Output Length:** 1529 chars

### Output
```
# Technical Analysis for RKLB
**Date:** 2026-04-14
**Current Price:** $70.62

## Price Action
- **Daily Change:** +3.78%
- **5-Day Change:** +6.48%

## RSI (14)
- **Value:** 52.9 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** -0.727
- **Signal Line:** -1.374
- **Histogram:** 0.647 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $70.00 (+0.9% from price)
- **200 SMA:** $59.10 (+19.5% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $76.59
- **Middle:** $67.78
- **Lower:** $58.98
- **Band Position:** 66%
- **Bandwidth:** 26.0% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $5.46 (7.7% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $62.43 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 67.7
- **%D:** 58.9
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 4.0 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $67.90 (+4.0% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 781.0M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $68.27
- **Current vs VWAP:** +3.4%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $89.32
- **Recent Low:** $56.13
- **Next Resistance:** $72.73 (50.0%)
- **Next Support:** $68.81 (61.8%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 231. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:09.061723
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'RKLB'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for RKLB: Too Many Requests. Rate limited. Try after a while.
```

---

## 232. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:09.166057
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'RKLB'}`
- **Output Length:** 147 chars

### Output
```
Error fetching recommendation trends for RKLB: FinnhubAPIException(status_code: 429): API limit reached. Please try again later. Remaining Limit: 0
```

---

## 233. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:09.181591
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'RKLB', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for RKLB: Too Many Requests. Rate limited. Try after a while.
```

---

## 234. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:09.581740
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'MDAI', 'curr_date': '2026-04-14'}`
- **Output Length:** 1525 chars

### Output
```
# Technical Analysis for MDAI
**Date:** 2026-04-14
**Current Price:** $1.85

## Price Action
- **Daily Change:** +6.94%
- **5-Day Change:** +12.80%

## RSI (14)
- **Value:** 69.2 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 0.072
- **Signal Line:** 0.037
- **Histogram:** 0.036 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $1.50 (+23.0% from price)
- **200 SMA:** $1.90 (-2.7% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $1.87
- **Middle:** $1.53
- **Lower:** $1.20
- **Band Position:** 97%
- **Bandwidth:** 43.5% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $0.13 (6.9% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $1.66 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 83.1
- **%D:** 71.4
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 32.9 (Strengthening ↑)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $1.58 (+17.2% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** -8.4M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $1.44
- **Current vs VWAP:** +28.7%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $1.90
- **Recent Low:** $1.18
- **Next Resistance:** $1.90 (0.0% (High))
- **Next Support:** $1.73 (23.6%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 235. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:09.661735
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'MDAI'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for MDAI: Too Many Requests. Rate limited. Try after a while.
```

---

## 236. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:09.766268
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'MDAI'}`
- **Output Length:** 147 chars

### Output
```
Error fetching recommendation trends for MDAI: FinnhubAPIException(status_code: 429): API limit reached. Please try again later. Remaining Limit: 0
```

---

## 237. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:09.777346
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'MDAI', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for MDAI: Too Many Requests. Rate limited. Try after a while.
```

---

## 238. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:10.207397
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'OBAI', 'curr_date': '2026-04-14'}`
- **Output Length:** 1507 chars

### Output
```
# Technical Analysis for OBAI
**Date:** 2026-04-14
**Current Price:** $1.14

## Price Action
- **Daily Change:** -5.00%
- **5-Day Change:** -9.52%

## RSI (14)
- **Value:** 17.3 ↑
- **Signal:** OVERSOLD ⚡

## MACD
- **MACD Line:** -0.411
- **Signal Line:** -0.509
- **Histogram:** 0.098 (Weakening ↓)
- **Signal:** Bullish

## Moving Averages
- **50 SMA:** $3.89 (-70.7% from price)
- **200 SMA:** $3.89 (-70.7% from price)
- **Trend:** Downtrend

## Bollinger Bands (20,2)
- **Upper:** $1.87
- **Middle:** $1.41
- **Lower:** $0.95
- **Band Position:** 20%
- **Bandwidth:** 64.8% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $0.41 (36.4% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $0.52 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 21.1
- **%D:** 26.6
- **Signal:** Bearish

## ADX (Trend Strength)
- **ADX:** 43.7 (Weakening ↓)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $1.53 (-25.3% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** 24.1M
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $1.37
- **Current vs VWAP:** -17.0%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $38.50
- **Recent Low:** $1.05
- **Next Resistance:** $9.06 (78.6%)
- **Next Support:** $1.05 (100% (Low))

## Summary
- **Key Signals:** RSI oversold, Below 50 SMA

```

---

## 239. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:10.269996
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'OBAI'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for OBAI: Too Many Requests. Rate limited. Try after a while.
```

---

## 240. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:10.385092
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'OBAI'}`
- **Output Length:** 147 chars

### Output
```
Error fetching recommendation trends for OBAI: FinnhubAPIException(status_code: 429): API limit reached. Please try again later. Remaining Limit: 0
```

---

## 241. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:10.394526
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'OBAI', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for OBAI: Too Many Requests. Rate limited. Try after a while.
```

---

## 242. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:10.818401
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'OPEN', 'curr_date': '2026-04-14'}`
- **Output Length:** 1514 chars

### Output
```
# Technical Analysis for OPEN
**Date:** 2026-04-14
**Current Price:** $4.36

## Price Action
- **Daily Change:** +0.93%
- **5-Day Change:** -4.18%

## RSI (14)
- **Value:** 40.1 ↓
- **Signal:** Bearish

## MACD
- **MACD Line:** -0.195
- **Signal Line:** -0.150
- **Histogram:** -0.045 (Weakening ↓)
- **Signal:** Bearish

## Moving Averages
- **50 SMA:** $4.88 (-10.6% from price)
- **200 SMA:** $5.51 (-20.9% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $5.55
- **Middle:** $4.82
- **Lower:** $4.10
- **Band Position:** 18%
- **Bandwidth:** 29.9% (volatility indicator)
- **Signal:** Near lower band

## ATR (Volatility)
- **ATR:** $0.34 (7.8% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $3.85 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 17.4
- **%D:** 18.4
- **Signal:** OVERSOLD ⚡

## ADX (Trend Strength)
- **ADX:** 11.7 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $4.71 (-7.4% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** 6594.3M
- **5-Day Trend:** Rising ↑
- **Signal:** BULLISH DIVERGENCE ⚡ (accumulation)

## VWAP (20-period)
- **VWAP:** $4.89
- **Current vs VWAP:** -10.8%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $5.67
- **Recent Low:** $4.12
- **Next Resistance:** $4.45 (78.6%)
- **Next Support:** $4.12 (100% (Low))

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 243. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:10.884625
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'OPEN'}`
- **Output Length:** 99 chars

### Output
```
Error retrieving insider transactions for OPEN: Too Many Requests. Rate limited. Try after a while.
```

---

## 244. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:10.995010
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'OPEN'}`
- **Output Length:** 147 chars

### Output
```
Error fetching recommendation trends for OPEN: FinnhubAPIException(status_code: 429): API limit reached. Please try again later. Remaining Limit: 0
```

---

## 245. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-14T14:24:11.005438
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'OPEN', 'num_expirations': 3, 'curr_date': '2026-04-14'}`
- **Output Length:** 95 chars

### Output
```
Error retrieving options activity for OPEN: Too Many Requests. Rate limited. Try after a while.
```

---

## 246. Rank candidates

- **Type:** `llm`
- **Node:** ranker
- **Timestamp:** 2026-04-14T14:25:45.059458
- **Model:** `gemini-3-pro-preview`
- **Prompt Length:** 189582 chars
- **Output Length:** 2000 chars

### Prompt
```
You are a professional stock analyst selecting the best short-term trading opportunities from a pre-filtered candidate list.

CURRENT DATE: 2026-04-14

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
"Historical 1-day win rate: 38.6% (603 tracked)\nHistorical 7-day win rate: 42.2% (590 tracked)\nHistorical 30-day win rate: 35.4% (486 tracked)\n\nBest performing strategies (7-day):\n  - short_squeeze: 60.0% win rate, avg +2.1% return (10 samples)\n  - analyst_upgrade: 50.0% win rate, avg -0.7% return (32 samples)\n  - insider_buying: 46.5% win rate, avg -0.3% return (172 samples)\n\nWORST performing strategies (7-day) \u2014 penalize these heavily in scoring:\n  - pre_earnings_accumulation: 28.6% win rate, avg -1.9% return (7 samples)\n  - social_hype: 18.2% win rate, avg -4.6% return (22 samples)\n  - news_catalyst: 0.0% win rate, avg -8.4% return (8 samples)"

CANDIDATES FOR REVIEW:
### ALB (Priority: CRITICAL)
- **Strategy Match**: minervini
- **Sources**: minervini | **Confluence**: 1 source(s)
- **Quant Pre-Score**: 10/100 | **ML Win Probability**: N/A | **Altman Z-Score**: None | **Piotroski F-Score**: None
- **Price**: $186.02 | **Current Price (numeric)**: 186.02499389648438 | **Intraday**: -2.1% | **Avg Volume**: 1,557,868
- **Short Interest**: N/A
- **Discovery Context**: Minervini Stage 2: P>SMA50>SMA150>SMA200, +261% off 52w low, within 4% of 52w high, RS Rating 100/100
- **Business**: ALB - Business description not available.
- **News**: Moved in line with the broader sector volatility driven by the Strait of Hormuz blockade on April 13 and the subsequent diplomatic relief rally on April 14.

**Technical Analysis**:
# Technical Analysis for ALB
**Date:** 2026-04-14
**Current Price:** $185.43

## Price Action
- **Daily Change:** +6.79%
- **5-Day Change:** +6.86%

## RSI (14)
- **Value:** 60.0 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 2.406
- **Signal Line:** 1.898
- **Histogram:** 0.508 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $170.91 (+8.5% from price)
- **200 SMA:** $120.57 (+53.8% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $187.81
- **Middle:** $173.16
- **Lower:** $158.51
- **Band Position:** 92%
- **Bandwidth:** 16.9% (volatility indicator)
- **Signal:** Near upper band

## ATR (Volatility)
- **ATR:** $9.46 (5.1% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $171.24 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 46.3
- **%D:** 43.8
- **Signal:** Bullish crossover ⚡

## ADX (Trend Strength)
- **ADX:** 9.4 (Strengthening ↑)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $174.49 (+6.3% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 151.4M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $173.19
- **Current vs VWAP:** +7.1%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $205.49
- **Recent Low:** $154.69
- **Next Resistance:** $186.08 (38.2%)
- **Next Support:** $180.09 (50.0%)

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

**Upcoming Earnings**: Earnings in 22 days (2026-05-06): EPS Est $0.96, Rev Est $1,311,591,595

### AA (Priority: CRITICAL)
- **Strategy Match**: minervini
- **Sources**: minervini | **Confluence**: 1 source(s)
- **Quant Pre-Score**: 10/100 | **ML Win Probability**: N/A | **Altman Z-Score**: None | **Piotroski F-Score**: None
- **Price**: $72.18 | **Current Price (numeric)**: 72.17500305175781 | **Intraday**: +0.0% | **Avg Volume**: 5,377,772
- **Short Interest**: N/A
- **Discovery Context**: Minervini Stage 2: P>SMA50>SMA150>SMA200, +214% off 52w low, within 1% of 52w high, RS Rating 98/100
- **Business**: AA - Business description not available.
- **News**: Stock performance was primarily influenced by macroeconomic volatility and sector shifts following the Strait of Hormuz blockade and relief rally.

**Technical Analysis**:
# Technical Analysis for AA
**Date:** 2026-04-14
**Current Price:** $73.31

## Price Action
- **Daily Change:** +0.38%
- **5-Day Change:** +0.48%

## RSI (14)
- **Value:** 66.2 ↓
- **Signal:** Bullish

## MACD
- **MACD Line:** 3.267
- **Signal Line:** 2.229
- **Histogram:** 1.038 (Weakening ↓)
- **Signal:** Bullish

## Moving Averages
- **50 SMA:** $62.80 (+16.7% from price)
- **200 SMA:** $44.97 (+63.0% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $78.70
- **Middle:** $65.36
- **Lower:** $52.03
- **Band Position:** 80%
- **Bandwidth:** 40.8% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $3.60 (4.9% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $67.91 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 83.2
- **%D:** 83.4
- **Signal:** OVERBOUGHT ⚠️

## ADX (Trend Strength)
- **ADX:** 25.7 (Weakening ↓)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $67.38 (+8.8% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 52.1M
- **5-Day Trend:** Falling ↓
- **Signal:** BEARISH DIVERGENCE ⚠️ (distribution)

## VWAP (20-period)
- **VWAP:** $64.98
- **Current vs VWAP:** +12.8%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $75.70
- **Recent Low:** $54.95
- **Next Resistance:** $75.70 (0.0% (High))
- **Next Support:** $70.80 (23.6%)

## Summary
- **Key Signals:** Above 50 SMA


**Fundamentals**: N/A

**Insider Transactions**:
Error retrieving insider transactions for AA: Too Many Requests. Rate limited. Try after a while.

**Analyst Recommendations**:
## Analyst Recommendation Trends for AA

### 2026-04-01
- **Strong Buy**: 6
- **Buy**: 8
- **Hold**: 8
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 23

**Sent... [truncated]
```

### Output
```
{
  "rankings": [
    {
      "rank": 1,
      "ticker": "ALB",
      "company_name": "Albemarle Corporation",
      "current_price": 186.02,
      "strategy_match": "minervini",
      "final_score": 92,
      "confidence": 9,
      "risk_level": "moderate",
      "reason": "(1) Albemarle boasts a perfect Minervini RS Rating of 100/100, consolidating within 4% of its 52-week high with a 261% gain off its lows. (2) The timing is urgent as a recent MACD bullish crossover (histogram at 0.508) and rising OBV (151.4M) suggest an imminent breakout from this high-tight flag structure. (3) The risk/reward is favorable as it trades above its 50-day SMA of $170.91, providing a clear support level for a tight stop. (4) The primary risk is a potential rejection at resistance or macro volatility, especially given the high ATR of 5.1% ($9.46) which could trigger premature stop-outs.",
      "description": "Albemarle Corporation is a specialty chemicals manufacturing company highly focused on lithium and bromine."
    },
    {
      "rank": 2,
      "ticker": "AMAT",
      "company_name": "Applied Materials, Inc.",
      "current_price": 394.71,
      "strategy_match": "minervini",
      "final_score": 89,
      "confidence": 9,
      "risk_level": "moderate",
      "reason": "(1) Applied Materials exhibits a textbook Minervini Stage 2 setup with an RS Rating of 96/100 and price action within 1% of its 52-week high. (2) The immediate catalyst is the tech sector rebound coupled with a fresh MACD bullish crossover (histogram strengthening to 5.459) and rising volume (OBV at 223.7M). (3) The setup offers asymmetric upside, supported heavily by the 20-period EMA at $364.66 and strong institutional buying (price 10.3% above VWAP). (4) The primary risk is market-wide tech weakness or a false breakout at 52-week highs, making a strict stop below the 20 EMA prudent.",
      "description": "Applied Materials is a global leader in materials engineering solutions for the semiconductor and di
```

---

