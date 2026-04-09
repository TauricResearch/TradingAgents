# Tool Execution Logs - 2026-04-09

## 1. Check average volume (batch)

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:21:55.929317
- **Tool:** `get_average_volume_batch`
- **Parameters:** `{'symbols': ['AA', 'ALB', 'AMAT', 'APA', 'AMD', 'OSCR', 'HMH', 'BETR', 'EJH', 'SCVL', 'FUL', 'XAGE', 'HUIZ', 'LPCN', 'VSCO', 'OTRK', 'AVGO', 'ADM', 'AKAM', 'ECAT', 'CGCT', 'BOT', 'RPAY', 'ANVS', 'GF', 'LCFY', 'MKZR', 'SWZ', 'XZO', 'NTIC', 'WDFC', 'NEOG', 'SLP', 'SMPL', 'EICCF', 'FGI', 'BYRN', 'AME', 'AEP', 'CSCO', 'BSX', 'AXP', 'COIN', 'EL', 'EIX', 'AMZN', 'BKR', 'CVNA', 'EBAY', 'ENTX', 'IV', 'ARAI', 'US', 'II', 'OECD', 'TSLA', 'DCA', 'UAE', 'WTI', 'EDIT', 'CAGR', 'RIP', 'REAL', 'NVO', 'HIMS', 'ALOT'], 'lookback_days': 10, 'curr_date': '2026-04-09', 'cache_key': 'default'}`
- **Output Length:** 11512 chars

### Output
```
{"AA": {"symbol": "AA", "average_volume": 6136468.2, "latest_volume": 1606582.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-09", "error": null}, "ALB": {"symbol": "ALB", "average_volume": 1484167.2, "latest_volume": 376672.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-09", "error": null}, "AMAT": {"symbol": "AMAT", "average_volume": 5560613.3, "latest_volume": 1063533.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-09", "error": null}, "APA": {"symbol": "APA", "average_volume": 10203094.1, "latest_volume": 1833741.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-09", "error": null}, "AMD": {"symbol": "AMD", "average_volume": 34062932.3, "latest_volume": 6871823.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-09", "error": null}, "AVGO": {"symbol": "AVGO", "average_volume": 21610082.5, "latest_volume": 4692525.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-09", "error": null}, "ADM": {"symbol": "ADM", "average_volume": 3348441.5, "latest_volume": 229715.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-09", "error": null}, "AKAM": {"symbol": "AKAM", "average_volume": 3875930.3, "latest_volume": 482503.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-09", "error": null}, "AME": {"symbol": "AME", "average_volume": 973870.3, "latest_volume": 148003.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-09", "error": null}, "AEP": {"symbol": "AEP", "average_volume": 2474561.7, "latest_volume": 256117.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-09", "error": null}, "CSCO": {"symbol": "CSCO", "average_volume": 18328638.9, "latest_volume": 3291389.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-09", "error": null}, "BSX": {"symbol": "BSX", "average_volume": 18162394.7, "latest_volume": 1444447.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-09", "error": null}, "AXP": {"symbol": "AXP", "average_volume": 2686720.9, "latest_volume": 249809.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-09", "error": null}, "COIN": {"symbol": "COIN", "average_volume": 9052861.7, "latest_volume": 2146117.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-09", "error": null}, "EL": {"symbol": "EL", "average_volume": 4970711.1, "latest_volume": 289811.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-09", "error": null}, "EIX": {"symbol": "EIX", "average_volume": 2904030.4, "latest_volume": 333904.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-09", "error": null}, "AMZN": {"symbol": "AMZN", "average_volume": 40128011.3, "latest_volume": 11699913.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-09", "error": null}, "BKR": {"symbol": "BKR", "average_volume": 7315936.6, "latest_volume": 928466.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-09", "error": null}, "CVNA": {"symbol": "CVNA", "average_volume": 2694010.4, "latest_volume": 624904.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-09", "error": null}, "EBAY": {"symbol": "EBAY", "average_volume": 3900246.8, "latest_volume": 365968.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-09", "error": null}, "TSLA": {"symbol": "TSLA", "average_volume": 64956663.9, "latest_volume": 16072339.0, "lookback_days": 10, "source": "cache", "cache_date": "2026-04-09", "error": null}, "OSCR": {"symbol": "OSCR", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-09", "error": "No volume data found"}, "HMH": {"symbol": "HMH", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-09", "error": "No volume data found"}, "BETR": {"symbol": "BETR", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-09", "error": "No volume data found"}, "EJH": {"symbol": "EJH", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-09", "error": "No volume data found"}, "SCVL": {"symbol": "SCVL", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-09", "error": "No volume data found"}, "FUL": {"symbol": "FUL", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-09", "error": "No volume data found"}, "XAGE": {"symbol": "XAGE", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-09", "error": "No volume data found"}, "HUIZ": {"symbol": "HUIZ", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-09", "error": "No volume data found"}, "LPCN": {"symbol": "LPCN", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-09", "error": "No volume data found"}, "VSCO": {"symbol": "VSCO", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-09", "error": "No volume data found"}, "OTRK": {"symbol": "OTRK", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-09", "error": "No volume data found"}, "ECAT": {"symbol": "ECAT", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-09", "error": "No volume data found"}, "CGCT": {"symbol": "CGCT", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-09", "error": "No volume data found"}, "BOT": {"symbol": "BOT", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-09", "error": "No volume data found"}, "RPAY": {"symbol": "RPAY", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-09", "error": "No volume data found"}, "ANVS": {"symbol": "ANVS", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-09", "error": "No volume data found"}, "GF": {"symbol": "GF", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-09", "error": "No volume data found"}, "LCFY": {"symbol": "LCFY", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-09", "error": "No volume data found"}, "MKZR": {"symbol": "MKZR", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-09", "error": "No volume data found"}, "SWZ": {"symbol": "SWZ", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-09", "error": "No volume data found"}, "XZO": {"symbol": "XZO", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-09", "error": "No volume data found"}, "NTIC": {"symbol": "NTIC", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-09", "error": "No volume data found"}, "WDFC": {"symbol": "WDFC", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-09", "error": "No volume data found"}, "NEOG": {"symbol": "NEOG", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-09", "error": "No volume data found"}, "SLP": {"symbol": "SLP", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-09", "error": "No volume data found"}, "SMPL": {"symbol": "SMPL", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-09", "error": "No volume data found"}, "EICCF": {"symbol": "EICCF", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-09", "error": "No volume data found"}, "FGI": {"symbol": "FGI", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-09", "error": "No volume data found"}, "BYRN": {"symbol": "BYRN", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-09", "error": "No volume data found"}, "ENTX": {"symbol": "ENTX", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-09", "error": "No volume data found"}, "IV": {"symbol": "IV", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-09", "error": "No volume data found"}, "ARAI": {"symbol": "ARAI", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-09", "error": "No volume data found"}, "US": {"symbol": "US", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-09", "error": "No volume data found"}, "II": {"symbol": "II", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-09", "error": "No volume data found"}, "OECD": {"symbol": "OECD", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-09", "error": "No volume data found"}, "DCA": {"symbol": "DCA", "average_volume": null, "latest_volume": null, "lookback_days": 10, "source": "download", "cache_date": "2026-04-09", "error": "No volume data found"}, "UAE": {"symbol": "UAE", "average_volume": null, "latest_volume": null, "lookback_days": 1... [truncated]
```

---

## 2. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:24:24.931382
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'ALB', 'curr_date': '2026-04-09'}`
- **Output Length:** 1517 chars

### Output
```
# Technical Analysis for ALB
**Date:** 2026-04-09
**Current Price:** $177.44

## Price Action
- **Daily Change:** +2.25%
- **5-Day Change:** -0.58%

## RSI (14)
- **Value:** 54.6 ↓
- **Signal:** Bullish

## MACD
- **MACD Line:** 2.200
- **Signal Line:** 1.794
- **Histogram:** 0.407 (Weakening ↓)
- **Signal:** Bullish

## Moving Averages
- **50 SMA:** $171.43 (+3.5% from price)
- **200 SMA:** $118.80 (+49.4% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $186.46
- **Middle:** $171.06
- **Lower:** $155.65
- **Band Position:** 71%
- **Bandwidth:** 18.0% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $9.06 (5.1% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $163.85 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 45.7
- **%D:** 56.1
- **Signal:** Bearish

## ADX (Trend Strength)
- **ADX:** 6.5 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $173.40 (+2.3% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 145.7M
- **5-Day Trend:** Rising ↑
- **Signal:** BULLISH DIVERGENCE ⚡ (accumulation)

## VWAP (20-period)
- **VWAP:** $170.84
- **Current vs VWAP:** +3.9%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $205.49
- **Recent Low:** $154.69
- **Next Resistance:** $180.09 (50.0%)
- **Next Support:** $174.10 (61.8%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 3. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:24:25.205406
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'ALB'}`
- **Output Length:** 719 chars

### Output
```
# Insider Transactions for ALB
# Data retrieved on: 2026-04-09 14:24:25

## Summary
- **Insider Sentiment:** BEARISH ⚠️ (significant insider selling)
- **Award/Grant:** 1 transactions
- **Gift:** 1 transactions
- **Sale:** 1 transactions
- **Total Sales Value:** $2,012,688
- **Largest Sale (3mo):** 2026-03-10 | MASTERS JERRY KENT JR. (Chief Executive Officer) | 11783 shares | $2012688.0 | Ownership: D

## Transaction Details

Start Date,Insider,Position,Transaction,Shares,Value,Ownership
2026-04-01,WOLFF ALEJANDRO DANIEL,Director,Award/Grant,25,0.0,D
2026-03-12,MASTERS JERRY KENT JR.,Chief Executive Officer,Gift,30716,5000258.0,D
2026-03-10,MASTERS JERRY KENT JR.,Chief Executive Officer,Sale,11783,2012688.0,D

```

---

## 4. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:24:25.478763
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
- **Timestamp:** 2026-04-09T14:24:25.905168
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'ALB', 'num_expirations': 3, 'curr_date': '2026-04-09'}`
- **Output Length:** 670 chars

### Output
```
## Options Activity for ALB

**Available Expirations:** 13 dates
**Analyzing:** 2026-04-10, 2026-04-17, 2026-04-24

### Summary
| Metric | Calls | Puts | Put/Call Ratio |
|--------|-------|------|----------------|
| Volume | 912 | 811 | 0.889 |
| Open Interest | 8,147 | 11,518 | 1.414 |

### Sentiment Analysis
- **Volume P/C Ratio:** Neutral
- **OI P/C Ratio:** Bearish positioning

### Unusual Activity (High Volume vs Open Interest)
| Type | Expiry | Strike | Volume | OI | Vol/OI | IV |
|------|--------|--------|--------|----|---------|----|---|
| CALL | 2026-04-10 | $202.5 | 102 | 107 | 0.95x | 130.2% |
| PUT | 2026-04-17 | $175.0 | 110 | 133 | 0.83x | 52.2% |

```

---

## 6. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:24:29.188475
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'HMH', 'curr_date': '2026-04-09'}`
- **Output Length:** 1539 chars

### Output
```
# Technical Analysis for HMH
**Date:** 2026-04-09
**Current Price:** $16.89

## Price Action
- **Daily Change:** -7.45%
- **5-Day Change:** +0.00%

## RSI (14)
- **Value:** 0.0 ↓
- **Signal:** OVERSOLD ⚡

## MACD
- **MACD Line:** -0.099
- **Signal Line:** -0.043
- **Histogram:** -0.055 (Strengthening ↑)
- **Signal:** BEARISH CROSSOVER ⚠️

## Moving Averages
- **50 SMA:** $18.37 (-8.0% from price)
- **200 SMA:** $18.37 (-8.0% from price)
- **Trend:** Downtrend

## Bollinger Bands (20,2)
- **Upper:** $20.18
- **Middle:** $18.37
- **Lower:** $16.55
- **Band Position:** 9%
- **Bandwidth:** 19.7% (volatility indicator)
- **Signal:** Near lower band

## ATR (Volatility)
- **ATR:** $1.45 (8.6% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $14.72 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 29.2
- **%D:** 38.2
- **Signal:** Bearish

## ADX (Trend Strength)
- **ADX:** 90.9 (Weakening ↓)
- **Interpretation:** VERY STRONG TREND ⚡

## 20 EMA
- **Value:** $18.26 (-7.5% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** -4.2M
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $18.73
- **Current vs VWAP:** -9.8%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $20.00
- **Recent Low:** $16.32
- **Next Resistance:** $17.11 (78.6%)
- **Next Support:** $16.32 (100% (Low))

## Summary
- **Key Signals:** RSI oversold, Below 50 SMA

```

---

## 7. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:24:29.428596
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'HMH'}`
- **Output Length:** 51 chars

### Output
```
No insider transactions data found for symbol 'HMH'
```

---

## 8. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:24:29.691796
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'HMH'}`
- **Output Length:** 43 chars

### Output
```
No recommendation trends data found for HMH
```

---

## 9. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:24:29.752461
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'HMH', 'num_expirations': 3, 'curr_date': '2026-04-09'}`
- **Output Length:** 33 chars

### Output
```
No options data available for HMH
```

---

## 10. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:24:32.805286
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'SCVL', 'curr_date': '2026-04-09'}`
- **Output Length:** 1539 chars

### Output
```
# Technical Analysis for SCVL
**Date:** 2026-04-09
**Current Price:** $16.80

## Price Action
- **Daily Change:** +5.07%
- **5-Day Change:** +6.93%

## RSI (14)
- **Value:** 45.6 ↑
- **Signal:** Bearish

## MACD
- **MACD Line:** -0.770
- **Signal Line:** -0.807
- **Histogram:** 0.036 (Weakening ↓)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $18.57 (-9.5% from price)
- **200 SMA:** $19.19 (-12.5% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $18.71
- **Middle:** $16.81
- **Lower:** $14.90
- **Band Position:** 50%
- **Bandwidth:** 22.7% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $0.92 (5.5% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $15.43 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 45.0
- **%D:** 32.1
- **Signal:** Bullish crossover ⚡

## ADX (Trend Strength)
- **ADX:** 13.4 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $16.88 (-0.5% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** 1.8M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $16.59
- **Current vs VWAP:** +1.3%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $21.38
- **Recent Low:** $14.88
- **Next Resistance:** $17.36 (61.8%)
- **Next Support:** $16.27 (78.6%)

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 11. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:24:33.148283
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'SCVL'}`
- **Output Length:** 516 chars

### Output
```
# Insider Transactions for SCVL
# Data retrieved on: 2026-04-09 14:24:33

## Summary
- **Insider Sentiment:** BULLISH ⚡ (more buying than selling)
- **Purchase:** 1 transactions
- **Total Purchases Value:** $500,030
- **Largest Purchase (3mo):** 2026-04-02 | JACKSON WILLIAM KERRY (Chief Financial Officer) | 31000 shares | $500030 | Ownership: D

## Transaction Details

Start Date,Insider,Position,Transaction,Shares,Value,Ownership
2026-04-02,JACKSON WILLIAM KERRY,Chief Financial Officer,Purchase,31000,500030,D

```

---

## 12. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:24:33.404537
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'SCVL'}`
- **Output Length:** 707 chars

### Output
```
## Analyst Recommendation Trends for SCVL

### 2026-04-01
- **Strong Buy**: 2
- **Buy**: 4
- **Hold**: 3
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 9

**Sentiment**: 66.7% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 2
- **Buy**: 4
- **Hold**: 3
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 9

**Sentiment**: 66.7% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 0
- **Buy**: 0
- **Hold**: 5
- **Sell**: 1
- **Strong Sell**: 2
- **Total Analysts**: 8

**Sentiment**: 0.0% Bullish, 37.5% Bearish

### 2026-01-01
- **Strong Buy**: 0
- **Buy**: 0
- **Hold**: 5
- **Sell**: 1
- **Strong Sell**: 2
- **Total Analysts**: 8

**Sentiment**: 0.0% Bullish, 37.5% Bearish


```

---

## 13. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:24:33.817260
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'SCVL', 'num_expirations': 3, 'curr_date': '2026-04-09'}`
- **Output Length:** 441 chars

### Output
```
## Options Activity for SCVL

**Available Expirations:** 4 dates
**Analyzing:** 2026-04-17, 2026-05-15, 2026-06-18

### Summary
| Metric | Calls | Puts | Put/Call Ratio |
|--------|-------|------|----------------|
| Volume | 2,028 | 134 | 0.066 |
| Open Interest | 325 | 812 | 2.498 |

### Sentiment Analysis
- **Volume P/C Ratio:** Bullish (more call volume)
- **OI P/C Ratio:** Bearish positioning

*No unusual options activity detected.*

```

---

## 14. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:24:35.608543
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'FUL', 'curr_date': '2026-04-09'}`
- **Output Length:** 1539 chars

### Output
```
# Technical Analysis for FUL
**Date:** 2026-04-09
**Current Price:** $62.78

## Price Action
- **Daily Change:** +8.65%
- **5-Day Change:** +0.48%

## RSI (14)
- **Value:** 59.5 ↓
- **Signal:** Bullish

## MACD
- **MACD Line:** 0.114
- **Signal Line:** -0.777
- **Histogram:** 0.891 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $60.92 (+3.0% from price)
- **200 SMA:** $59.69 (+5.2% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $64.28
- **Middle:** $56.44
- **Lower:** $48.60
- **Band Position:** 90%
- **Bandwidth:** 27.8% (volatility indicator)
- **Signal:** Near upper band

## ATR (Volatility)
- **ATR:** $2.62 (4.2% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $58.86 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 73.2
- **%D:** 72.5
- **Signal:** Bullish crossover ⚡

## ADX (Trend Strength)
- **ADX:** 11.9 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $58.64 (+7.1% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** -3.3M
- **5-Day Trend:** Falling ↓
- **Signal:** BEARISH DIVERGENCE ⚠️ (distribution)

## VWAP (20-period)
- **VWAP:** $56.69
- **Current vs VWAP:** +10.7%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $68.63
- **Recent Low:** $48.71
- **Next Resistance:** $63.93 (23.6%)
- **Next Support:** $61.02 (38.2%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 15. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:24:35.906823
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'FUL'}`
- **Output Length:** 515 chars

### Output
```
# Insider Transactions for FUL
# Data retrieved on: 2026-04-09 14:24:35

## Summary
- **Insider Sentiment:** BULLISH ⚡ (more buying than selling)
- **Purchase:** 1 transactions
- **Total Purchases Value:** $295,104
- **Largest Purchase (3mo):** 2026-04-07 | MASTIN CELESTE BEEKS (Chief Executive Officer) | 5170 shares | $295104.0 | Ownership: I

## Transaction Details

Start Date,Insider,Position,Transaction,Shares,Value,Ownership
2026-04-07,MASTIN CELESTE BEEKS,Chief Executive Officer,Purchase,5170,295104.0,I

```

---

## 16. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:24:36.150472
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'FUL'}`
- **Output Length:** 710 chars

### Output
```
## Analyst Recommendation Trends for FUL

### 2026-04-01
- **Strong Buy**: 3
- **Buy**: 5
- **Hold**: 2
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 11

**Sentiment**: 72.7% Bullish, 9.1% Bearish

### 2026-03-01
- **Strong Buy**: 3
- **Buy**: 4
- **Hold**: 3
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 11

**Sentiment**: 63.6% Bullish, 9.1% Bearish

### 2026-02-01
- **Strong Buy**: 3
- **Buy**: 4
- **Hold**: 3
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 11

**Sentiment**: 63.6% Bullish, 9.1% Bearish

### 2026-01-01
- **Strong Buy**: 3
- **Buy**: 4
- **Hold**: 3
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 11

**Sentiment**: 63.6% Bullish, 9.1% Bearish


```

---

## 17. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:24:36.436657
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'FUL', 'num_expirations': 3, 'curr_date': '2026-04-09'}`
- **Output Length:** 621 chars

### Output
```
## Options Activity for FUL

**Available Expirations:** 4 dates
**Analyzing:** 2026-04-17, 2026-05-15, 2026-08-21

### Summary
| Metric | Calls | Puts | Put/Call Ratio |
|--------|-------|------|----------------|
| Volume | 26 | 337 | 12.962 |
| Open Interest | 175 | 734 | 4.194 |

### Sentiment Analysis
- **Volume P/C Ratio:** Bearish (more put volume)
- **OI P/C Ratio:** Bearish positioning

### Unusual Activity (High Volume vs Open Interest)
| Type | Expiry | Strike | Volume | OI | Vol/OI | IV |
|------|--------|--------|--------|----|---------|----|---|
| PUT | 2026-04-17 | $50.0 | 240 | 172 | 1.4x | 195.1% |

```

---

## 18. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:24:38.909081
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'OTRK', 'curr_date': '2026-04-09'}`
- **Output Length:** 1454 chars

### Output
```
# Technical Analysis for OTRK
**Date:** 2026-04-09
**Current Price:** $0.00

## Price Action
- **Daily Change:** +0.00%
- **5-Day Change:** +0.00%

## RSI (14)
- **Value:** 59.9 ↓
- **Signal:** Bullish

## MACD
- **MACD Line:** 0.000
- **Signal Line:** 0.000
- **Histogram:** 0.000 (Weakening ↓)
- **Signal:** Bullish

## Moving Averages
- **50 SMA:** $0.00 (+44.9% from price)
- **200 SMA:** $0.00 (+44.9% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $0.00
- **Middle:** $0.00
- **Lower:** $0.00
- **Band Position:** 74%
- **Bandwidth:** 136.8% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $0.00 (8.3% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $0.00 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 42.7
- **%D:** 66.6
- **Signal:** Bearish

## ADX (Trend Strength)
- **ADX:** 100.0 (Weakening ↓)
- **Interpretation:** VERY STRONG TREND ⚡

## 20 EMA
- **Value:** $0.00 (+19.6% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 1.2K
- **5-Day Trend:** Falling ↓
- **Signal:** Neutral

## VWAP (20-period)
- **VWAP:** $0.00
- **Current vs VWAP:** +13.4%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $0.00
- **Recent Low:** $0.00
- **Next Resistance:** $0.00 (78.6%)
- **Next Support:** $0.00 (100% (Low))

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 19. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:24:39.311054
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'OTRK'}`
- **Output Length:** 52 chars

### Output
```
No insider transactions data found for symbol 'OTRK'
```

---

## 20. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:24:39.541749
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

## 21. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:24:39.698528
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'OTRK', 'num_expirations': 3, 'curr_date': '2026-04-09'}`
- **Output Length:** 34 chars

### Output
```
No options data available for OTRK
```

---

## 22. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:24:42.604565
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'AKAM', 'curr_date': '2026-04-09'}`
- **Output Length:** 1548 chars

### Output
```
# Technical Analysis for AKAM
**Date:** 2026-04-09
**Current Price:** $116.00

## Price Action
- **Daily Change:** +1.85%
- **5-Day Change:** +0.22%

## RSI (14)
- **Value:** 59.3 ↓
- **Signal:** Bullish

## MACD
- **MACD Line:** 3.466
- **Signal Line:** 3.671
- **Histogram:** -0.205 (Strengthening ↑)
- **Signal:** BEARISH CROSSOVER ⚠️

## Moving Averages
- **50 SMA:** $104.83 (+10.7% from price)
- **200 SMA:** $86.84 (+33.6% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $121.03
- **Middle:** $112.17
- **Lower:** $103.30
- **Band Position:** 72%
- **Bandwidth:** 15.8% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $4.85 (4.2% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $108.73 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 55.1
- **%D:** 58.4
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 19.0 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $112.04 (+3.5% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 91.2M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $112.12
- **Current vs VWAP:** +3.5%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $121.12
- **Recent Low:** $90.88
- **Next Resistance:** $121.12 (0.0% (High))
- **Next Support:** $113.98 (23.6%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 23. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:24:42.842849
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'AKAM'}`
- **Output Length:** 789 chars

### Output
```
# Insider Transactions for AKAM
# Data retrieved on: 2026-04-09 14:24:42

## Summary
- **Insider Sentiment:** BEARISH ⚠️ (significant insider selling)
- **Sale:** 5 transactions
- **Unknown:** 1 transactions
- **Total Sales Value:** $5,791,065
- **Largest Sale (3mo):** 2026-03-12 | KARON ADAM M (Officer) | 17000 shares | $1826249.0 | Ownership: D

## Transaction Details

Start Date,Insider,Position,Transaction,Shares,Value,Ownership
2026-03-16,JOSEPH PAUL C,Officer,Sale,5000,531256.0,D
2026-03-16,AHOLA AARON,General Counsel,Sale,4500,478216.0,I
2026-03-12,HOWELL LAURA,Officer,Unknown,322,,D
2026-03-12,KARON ADAM M,Officer,Sale,17000,1826249.0,D
2026-03-11,WILLIAMS ANTHONY P,Officer,Sale,15000,1564419.0,D
2026-03-10,MCGOWAN EDWARD J,Chief Financial Officer,Sale,13745,1390925.0,D

```

---

## 24. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:24:43.083702
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'AKAM'}`
- **Output Length:** 719 chars

### Output
```
## Analyst Recommendation Trends for AKAM

### 2026-04-01
- **Strong Buy**: 7
- **Buy**: 13
- **Hold**: 11
- **Sell**: 2
- **Strong Sell**: 0
- **Total Analysts**: 33

**Sentiment**: 60.6% Bullish, 6.1% Bearish

### 2026-03-01
- **Strong Buy**: 7
- **Buy**: 13
- **Hold**: 11
- **Sell**: 2
- **Strong Sell**: 0
- **Total Analysts**: 33

**Sentiment**: 60.6% Bullish, 6.1% Bearish

### 2026-02-01
- **Strong Buy**: 7
- **Buy**: 13
- **Hold**: 11
- **Sell**: 2
- **Strong Sell**: 0
- **Total Analysts**: 33

**Sentiment**: 60.6% Bullish, 6.1% Bearish

### 2026-01-01
- **Strong Buy**: 7
- **Buy**: 12
- **Hold**: 10
- **Sell**: 3
- **Strong Sell**: 0
- **Total Analysts**: 32

**Sentiment**: 59.4% Bullish, 9.4% Bearish


```

---

## 25. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:24:43.550786
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'AKAM', 'num_expirations': 3, 'curr_date': '2026-04-09'}`
- **Output Length:** 426 chars

### Output
```
## Options Activity for AKAM

**Available Expirations:** 16 dates
**Analyzing:** 2026-04-10, 2026-04-17, 2026-04-24

### Summary
| Metric | Calls | Puts | Put/Call Ratio |
|--------|-------|------|----------------|
| Volume | 382 | 277 | 0.725 |
| Open Interest | 10,185 | 9,259 | 0.909 |

### Sentiment Analysis
- **Volume P/C Ratio:** Neutral
- **OI P/C Ratio:** Neutral positioning

*No unusual options activity detected.*

```

---

## 26. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:24:47.279625
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'CGCT', 'curr_date': '2026-04-09'}`
- **Output Length:** 1502 chars

### Output
```
# Technical Analysis for CGCT
**Date:** 2026-04-09
**Current Price:** $10.27

## Price Action
- **Daily Change:** -0.05%
- **5-Day Change:** -0.34%

## RSI (14)
- **Value:** 49.4 ↓
- **Signal:** Bearish

## MACD
- **MACD Line:** 0.000
- **Signal Line:** -0.003
- **Histogram:** 0.003 (Weakening ↓)
- **Signal:** Bullish

## Moving Averages
- **50 SMA:** $10.28 (-0.1% from price)
- **200 SMA:** $10.15 (+1.2% from price)
- **Trend:** Downtrend

## Bollinger Bands (20,2)
- **Upper:** $10.29
- **Middle:** $10.26
- **Lower:** $10.23
- **Band Position:** 55%
- **Bandwidth:** 0.6% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $0.03 (0.3% of price)
- **Level:** Low volatility
- **Suggested Stop-Loss:** $10.22 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 47.6
- **%D:** 50.1
- **Signal:** Bearish crossover ⚠️

## ADX (Trend Strength)
- **ADX:** 34.9 (Strengthening ↑)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $10.27 (-0.0% from price)
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

## 27. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:24:47.550273
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'CGCT'}`
- **Output Length:** 52 chars

### Output
```
No insider transactions data found for symbol 'CGCT'
```

---

## 28. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:24:47.777176
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'CGCT'}`
- **Output Length:** 44 chars

### Output
```
No recommendation trends data found for CGCT
```

---

## 29. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:24:47.838461
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'CGCT', 'num_expirations': 3, 'curr_date': '2026-04-09'}`
- **Output Length:** 34 chars

### Output
```
No options data available for CGCT
```

---

## 30. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:24:51.196157
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'GF', 'curr_date': '2026-04-09'}`
- **Output Length:** 1531 chars

### Output
```
# Technical Analysis for GF
**Date:** 2026-04-09
**Current Price:** $11.10

## Price Action
- **Daily Change:** +5.61%
- **5-Day Change:** +6.02%

## RSI (14)
- **Value:** 56.4 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** -0.204
- **Signal Line:** -0.310
- **Histogram:** 0.106 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $11.37 (-2.4% from price)
- **200 SMA:** $11.39 (-2.5% from price)
- **Trend:** STRONG DOWNTREND ⚠️ (DEATH CROSS ⚠️)

## Bollinger Bands (20,2)
- **Upper:** $11.22
- **Middle:** $10.56
- **Lower:** $9.90
- **Band Position:** 91%
- **Bandwidth:** 12.5% (volatility indicator)
- **Signal:** Near upper band

## ATR (Volatility)
- **ATR:** $0.35 (3.1% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $10.58 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 62.5
- **%D:** 52.9
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 26.9 (Weakening ↓)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $10.68 (+3.9% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 710.8K
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $10.57
- **Current vs VWAP:** +5.0%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $12.39
- **Recent Low:** $9.98
- **Next Resistance:** $11.18 (50.0%)
- **Next Support:** $10.90 (61.8%)

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 31. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:24:51.430983
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'GF'}`
- **Output Length:** 1586 chars

### Output
```
# Insider Transactions for GF
# Data retrieved on: 2026-04-09 14:24:51

## Summary
- **Insider Sentiment:** BULLISH ⚡ (more buying than selling)
- **Purchase:** 9 transactions
- **Total Purchases Value:** $2,982,502
- **Largest Purchase (3mo):** 2026-04-06 | SABA CAPITAL MANAGEMENT, L.P. (Beneficial Owner of more than 10% of a Class of Security) | 140564 shares | $1494195 | Ownership: I

## Transaction Details

Start Date,Insider,Position,Transaction,Shares,Value,Ownership
2026-04-06,"SABA CAPITAL MANAGEMENT, L.P.",Beneficial Owner of more than 10% of a Class of Security,Purchase,140564,1494195,I
2026-04-02,"SABA CAPITAL MANAGEMENT, L.P.",Beneficial Owner of more than 10% of a Class of Security,Purchase,73863,777721,I
2026-03-31,"SABA CAPITAL MANAGEMENT, L.P.",Beneficial Owner of more than 10% of a Class of Security,Purchase,5888,60588,I
2026-03-26,"SABA CAPITAL MANAGEMENT, L.P.",Beneficial Owner of more than 10% of a Class of Security,Purchase,3158,32243,I
2026-03-23,"SABA CAPITAL MANAGEMENT, L.P.",Beneficial Owner of more than 10% of a Class of Security,Purchase,27269,287688,I
2026-03-20,"SABA CAPITAL MANAGEMENT, L.P.",Beneficial Owner of more than 10% of a Class of Security,Purchase,4087,41647,I
2026-03-18,"SABA CAPITAL MANAGEMENT, L.P.",Beneficial Owner of more than 10% of a Class of Security,Purchase,15597,169071,I
2026-03-12,"SABA CAPITAL MANAGEMENT, L.P.",Beneficial Owner of more than 10% of a Class of Security,Purchase,224,2419,I
2026-03-10,"SABA CAPITAL MANAGEMENT, L.P.",Beneficial Owner of more than 10% of a Class of Security,Purchase,10631,116930,I

```

---

## 32. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:24:51.694743
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'GF'}`
- **Output Length:** 42 chars

### Output
```
No recommendation trends data found for GF
```

---

## 33. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:24:51.756004
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'GF', 'num_expirations': 3, 'curr_date': '2026-04-09'}`
- **Output Length:** 32 chars

### Output
```
No options data available for GF
```

---

## 34. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:24:55.675411
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'SWZ', 'curr_date': '2026-04-09'}`
- **Output Length:** 1530 chars

### Output
```
# Technical Analysis for SWZ
**Date:** 2026-04-09
**Current Price:** $6.01

## Price Action
- **Daily Change:** +0.67%
- **5-Day Change:** +1.18%

## RSI (14)
- **Value:** 53.1 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** -0.021
- **Signal Line:** -0.032
- **Histogram:** 0.010 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $6.02 (-0.1% from price)
- **200 SMA:** $6.09 (-1.3% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $6.05
- **Middle:** $5.96
- **Lower:** $5.87
- **Band Position:** 77%
- **Bandwidth:** 3.0% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $0.07 (1.1% of price)
- **Level:** Low volatility
- **Suggested Stop-Loss:** $5.91 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 39.7
- **%D:** 32.5
- **Signal:** Bullish crossover ⚡

## ADX (Trend Strength)
- **ADX:** 12.4 (Strengthening ↑)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $5.97 (+0.7% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** -412.9K
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $5.96
- **Current vs VWAP:** +0.8%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $6.21
- **Recent Low:** $5.87
- **Next Resistance:** $6.04 (50.0%)
- **Next Support:** $6.00 (61.8%)

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 35. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:24:55.944199
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'SWZ'}`
- **Output Length:** 51 chars

### Output
```
No insider transactions data found for symbol 'SWZ'
```

---

## 36. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:24:56.193825
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'SWZ'}`
- **Output Length:** 43 chars

### Output
```
No recommendation trends data found for SWZ
```

---

## 37. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:24:56.319339
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'SWZ', 'num_expirations': 3, 'curr_date': '2026-04-09'}`
- **Output Length:** 33 chars

### Output
```
No options data available for SWZ
```

---

## 38. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:00.452787
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'WDFC', 'curr_date': '2026-04-09'}`
- **Output Length:** 1513 chars

### Output
```
# Technical Analysis for WDFC
**Date:** 2026-04-09
**Current Price:** $219.32

## Price Action
- **Daily Change:** +3.23%
- **5-Day Change:** +6.67%

## RSI (14)
- **Value:** 52.3 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** -5.018
- **Signal Line:** -5.907
- **Histogram:** 0.889 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $228.49 (-4.0% from price)
- **200 SMA:** $211.45 (+3.7% from price)
- **Trend:** Downtrend

## Bollinger Bands (20,2)
- **Upper:** $231.62
- **Middle:** $214.67
- **Lower:** $197.72
- **Band Position:** 64%
- **Bandwidth:** 15.8% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $7.15 (3.3% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $208.59 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 63.3
- **%D:** 42.6
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 22.2 (Weakening ↓)
- **Interpretation:** Trending

## 20 EMA
- **Value:** $215.32 (+1.9% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 23.7K
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $213.63
- **Current vs VWAP:** +2.7%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $253.24
- **Recent Low:** $200.00
- **Next Resistance:** $220.34 (61.8%)
- **Next Support:** $211.39 (78.6%)

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 39. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:00.774758
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'WDFC'}`
- **Output Length:** 60 chars

### Output
```
No insider transactions found for WDFC in the last 3 months.
```

---

## 40. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:01.017315
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'WDFC'}`
- **Output Length:** 707 chars

### Output
```
## Analyst Recommendation Trends for WDFC

### 2026-04-01
- **Strong Buy**: 3
- **Buy**: 4
- **Hold**: 2
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 9

**Sentiment**: 77.8% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 3
- **Buy**: 4
- **Hold**: 2
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 9

**Sentiment**: 77.8% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 3
- **Buy**: 4
- **Hold**: 2
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 9

**Sentiment**: 77.8% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 3
- **Buy**: 4
- **Hold**: 2
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 9

**Sentiment**: 77.8% Bullish, 0.0% Bearish


```

---

## 41. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:01.343432
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'WDFC', 'num_expirations': 3, 'curr_date': '2026-04-09'}`
- **Output Length:** 438 chars

### Output
```
## Options Activity for WDFC

**Available Expirations:** 4 dates
**Analyzing:** 2026-04-17, 2026-05-15, 2026-08-21

### Summary
| Metric | Calls | Puts | Put/Call Ratio |
|--------|-------|------|----------------|
| Volume | 189 | 279 | 1.476 |
| Open Interest | 478 | 553 | 1.157 |

### Sentiment Analysis
- **Volume P/C Ratio:** Bearish (more put volume)
- **OI P/C Ratio:** Neutral positioning

*No unusual options activity detected.*

```

---

## 42. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:03.198635
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'SLP', 'curr_date': '2026-04-09'}`
- **Output Length:** 1551 chars

### Output
```
# Technical Analysis for SLP
**Date:** 2026-04-09
**Current Price:** $13.00

## Price Action
- **Daily Change:** +2.77%
- **5-Day Change:** +8.70%

## RSI (14)
- **Value:** 60.3 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** -0.146
- **Signal Line:** -0.393
- **Histogram:** 0.247 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $12.93 (+0.5% from price)
- **200 SMA:** $15.59 (-16.6% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $12.88
- **Middle:** $11.98
- **Lower:** $11.09
- **Band Position:** 107%
- **Bandwidth:** 14.9% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $0.58 (4.5% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $12.13 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 83.5
- **%D:** 70.7
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 17.3 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $12.18 (+6.8% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** -8.8M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $12.04
- **Current vs VWAP:** +8.0%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $20.43
- **Recent Low:** $11.09
- **Next Resistance:** $13.09 (78.6%)
- **Next Support:** $11.09 (100% (Low))

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 43. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:03.475578
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'SLP'}`
- **Output Length:** 59 chars

### Output
```
No insider transactions found for SLP in the last 3 months.
```

---

## 44. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:03.722460
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'SLP'}`
- **Output Length:** 710 chars

### Output
```
## Analyst Recommendation Trends for SLP

### 2026-04-01
- **Strong Buy**: 3
- **Buy**: 3
- **Hold**: 5
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 11

**Sentiment**: 54.5% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 3
- **Buy**: 3
- **Hold**: 5
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 11

**Sentiment**: 54.5% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 3
- **Buy**: 3
- **Hold**: 5
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 11

**Sentiment**: 54.5% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 4
- **Buy**: 3
- **Hold**: 4
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 11

**Sentiment**: 63.6% Bullish, 0.0% Bearish


```

---

## 45. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:04.005242
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'SLP', 'num_expirations': 3, 'curr_date': '2026-04-09'}`
- **Output Length:** 437 chars

### Output
```
## Options Activity for SLP

**Available Expirations:** 4 dates
**Analyzing:** 2026-04-17, 2026-05-15, 2026-06-18

### Summary
| Metric | Calls | Puts | Put/Call Ratio |
|--------|-------|------|----------------|
| Volume | 63 | 33 | 0.524 |
| Open Interest | 3,213 | 85 | 0.026 |

### Sentiment Analysis
- **Volume P/C Ratio:** Bullish (more call volume)
- **OI P/C Ratio:** Bullish positioning

*No unusual options activity detected.*

```

---

## 46. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:07.507657
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'AME', 'curr_date': '2026-04-09'}`
- **Output Length:** 1566 chars

### Output
```
# Technical Analysis for AME
**Date:** 2026-04-09
**Current Price:** $230.49

## Price Action
- **Daily Change:** +5.85%
- **5-Day Change:** +5.42%

## RSI (14)
- **Value:** 63.7 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** -0.771
- **Signal Line:** -2.599
- **Histogram:** 1.828 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $224.43 (+2.7% from price)
- **200 SMA:** $199.28 (+15.7% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $225.80
- **Middle:** $215.46
- **Lower:** $205.12
- **Band Position:** 123%
- **Bandwidth:** 9.6% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $6.01 (2.6% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $221.47 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 77.5
- **%D:** 63.4
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 19.4 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $218.47 (+5.5% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 8.7M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $215.65
- **Current vs VWAP:** +6.9%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $241.67
- **Recent Low:** $207.32
- **Next Resistance:** $233.56 (23.6%)
- **Next Support:** $228.55 (38.2%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 47. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:07.749436
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'AME'}`
- **Output Length:** 1629 chars

### Output
```
# Insider Transactions for AME
# Data retrieved on: 2026-04-09 14:25:07

## Summary
- **Insider Sentiment:** BEARISH ⚠️ (significant insider selling)
- **Award/Grant:** 15 transactions
- **Unknown:** 2 transactions
- **Sale:** 1 transactions
- **Total Sales Value:** $114,893
- **Largest Sale (3mo):** 2026-03-24 | AMATO THOMAS A (Director) | 530 shares | $114893.0 | Ownership: D

## Transaction Details

Start Date,Insider,Position,Transaction,Shares,Value,Ownership
2026-03-24,AMATO THOMAS A,Director,Sale,530,114893.0,D
2026-03-20,SPERANZA EMANUELA,Officer,Unknown,574,,D
2026-03-18,AMATO THOMAS A,Director,Award/Grant,950,202132.0,D
2026-03-18,ZAPICO NIMCRUT DAVID A.,Chief Executive Officer,Award/Grant,11930,2538346.0,D
2026-03-18,PURI DALIP,Chief Financial Officer,Award/Grant,3780,804271.0,D
2026-03-18,CONTI ANTHONY JAMES,Director,Award/Grant,950,202132.0,D
2026-03-18,CARPENTER TOD E,Director,Award/Grant,950,202132.0,D
2026-03-18,HARDIN JOHN WESLEY,Officer,Award/Grant,1360,289367.0,D
2026-03-18,SEAVERS DEAN,Director,Award/Grant,950,202132.0,D
2026-03-18,MCCLAIN GRETCHEN W,Director,Award/Grant,950,202132.0,D
2026-03-18,AMODEI ROBERT J.,Officer,Award/Grant,360,76597.0,D
2026-03-18,SPERANZA EMANUELA,Officer,Unknown,296,,D
2026-03-18,HERMANCE DAVID F.,Officer,Award/Grant,1240,263835.0,D
2026-03-18,STEFANY SUZANNE L.,Director,Award/Grant,950,202132.0,D
2026-03-18,CIAMPITTI TONY J.,Officer,Award/Grant,1300,276601.0,D
2026-03-18,MARECIC THOMAS C,Officer,Award/Grant,1240,263835.0,D
2026-03-18,OSCHER RONALD J,Officer,Award/Grant,1300,276601.0,D
2026-03-18,OBERTON KARLEEN MARIE,Director,Award/Grant,950,202132.0,D

```

---

## 48. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:08.005292
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

## 49. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:08.373465
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'AME', 'num_expirations': 3, 'curr_date': '2026-04-09'}`
- **Output Length:** 682 chars

### Output
```
## Options Activity for AME

**Available Expirations:** 6 dates
**Analyzing:** 2026-04-17, 2026-05-15, 2026-06-18

### Summary
| Metric | Calls | Puts | Put/Call Ratio |
|--------|-------|------|----------------|
| Volume | 343 | 894 | 2.606 |
| Open Interest | 4,572 | 2,824 | 0.618 |

### Sentiment Analysis
- **Volume P/C Ratio:** Bearish (more put volume)
- **OI P/C Ratio:** Bullish positioning

### Unusual Activity (High Volume vs Open Interest)
| Type | Expiry | Strike | Volume | OI | Vol/OI | IV |
|------|--------|--------|--------|----|---------|----|---|
| PUT | 2026-04-17 | $185.0 | 200 | 201 | 1.0x | 82.7% |
| PUT | 2026-05-15 | $220.0 | 600 | 602 | 1.0x | 36.0% |

```

---

## 50. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:11.618465
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'CSCO', 'curr_date': '2026-04-09'}`
- **Output Length:** 1566 chars

### Output
```
# Technical Analysis for CSCO
**Date:** 2026-04-09
**Current Price:** $83.70

## Price Action
- **Daily Change:** +3.74%
- **5-Day Change:** +7.99%

## RSI (14)
- **Value:** 63.8 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 0.652
- **Signal Line:** 0.255
- **Histogram:** 0.396 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $79.21 (+5.7% from price)
- **200 SMA:** $72.69 (+15.1% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $82.73
- **Middle:** $78.96
- **Lower:** $75.20
- **Band Position:** 113%
- **Bandwidth:** 9.5% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $2.11 (2.5% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $80.53 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 70.0
- **%D:** 55.7
- **Signal:** Bullish crossover ⚡

## ADX (Trend Strength)
- **ADX:** 11.5 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $79.37 (+5.5% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 403.2M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $78.72
- **Current vs VWAP:** +6.3%
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

## 51. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:11.955543
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'CSCO'}`
- **Output Length:** 972 chars

### Output
```
# Insider Transactions for CSCO
# Data retrieved on: 2026-04-09 14:25:11

## Summary
- **Insider Sentiment:** BEARISH ⚠️ (significant insider selling)
- **Sale:** 5 transactions
- **Award/Grant:** 4 transactions
- **Total Sales Value:** $1,442,844
- **Largest Sale (3mo):** 2026-03-17 | STAHLKOPF DEBORAH L (Officer) | 7981 shares | $634513 | Ownership: D

## Transaction Details

Start Date,Insider,Position,Transaction,Shares,Value,Ownership
2026-04-06,SHIMER PETER A,Director,Award/Grant,2333,0,D
2026-03-20,PATTERSON MARK,Chief Financial Officer,Sale,4892,381450,D
2026-03-18,TUSZIK OLIVER,Officer,Sale,3132,249746,D
2026-03-17,STAHLKOPF DEBORAH L,Officer,Sale,7981,634513,D
2026-03-16,JOHNSON KRISTINA MARY,Director,Award/Grant,383,30219,D
2026-03-16,WEIL KEVIN,Director,Award/Grant,383,30219,D
2026-03-16,TESSEL MARIANNA,Director,Award/Grant,383,30219,D
2026-03-12,SUBAIYA THIMAYA K,Officer,Sale,1744,134410,D
2026-03-11,WONG MARIA VICTORIA,Officer,Sale,551,42725,D

```

---

## 52. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:12.179255
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

## 53. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:12.664974
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'CSCO', 'num_expirations': 3, 'curr_date': '2026-04-09'}`
- **Output Length:** 1167 chars

### Output
```
## Options Activity for CSCO

**Available Expirations:** 17 dates
**Analyzing:** 2026-04-10, 2026-04-17, 2026-04-24

### Summary
| Metric | Calls | Puts | Put/Call Ratio |
|--------|-------|------|----------------|
| Volume | 38,209 | 9,608 | 0.251 |
| Open Interest | 116,829 | 117,653 | 1.007 |

### Sentiment Analysis
- **Volume P/C Ratio:** Bullish (more call volume)
- **OI P/C Ratio:** Neutral positioning

### Unusual Activity (High Volume vs Open Interest)
| Type | Expiry | Strike | Volume | OI | Vol/OI | IV |
|------|--------|--------|--------|----|---------|----|---|
| CALL | 2026-04-17 | $57.5 | 15,841 | 1 | 15841.0x | 177.5% |
| CALL | 2026-04-17 | $60.0 | 5,361 | 1 | 5361.0x | 157.3% |
| CALL | 2026-04-17 | $62.5 | 941 | 4 | 235.25x | 139.3% |
| CALL | 2026-04-17 | $40.0 | 317 | 5 | 63.4x | 298.2% |
| CALL | 2026-04-17 | $73.0 | 237 | 61 | 3.89x | 93.5% |
| CALL | 2026-04-10 | $88.0 | 299 | 81 | 3.69x | 36.7% |
| PUT | 2026-04-10 | $78.0 | 7,924 | 5,998 | 1.32x | 49.2% |
| PUT | 2026-04-24 | $80.0 | 296 | 294 | 1.01x | 31.8% |
| PUT | 2026-04-10 | $73.0 | 171 | 266 | 0.64x | 79.7% |
| CALL | 2026-04-10 | $85.0 | 326 | 641 | 0.51x | 44.8% |

```

---

## 54. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:14.252150
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'BSX', 'curr_date': '2026-04-09'}`
- **Output Length:** 1531 chars

### Output
```
# Technical Analysis for BSX
**Date:** 2026-04-09
**Current Price:** $62.56

## Price Action
- **Daily Change:** +1.13%
- **5-Day Change:** +0.90%

## RSI (14)
- **Value:** 29.6 ↑
- **Signal:** OVERSOLD ⚡

## MACD
- **MACD Line:** -3.418
- **Signal Line:** -3.190
- **Histogram:** -0.228 (Weakening ↓)
- **Signal:** Bearish

## Moving Averages
- **50 SMA:** $73.74 (-15.2% from price)
- **200 SMA:** $93.62 (-33.2% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $74.34
- **Middle:** $67.16
- **Lower:** $59.99
- **Band Position:** 18%
- **Bandwidth:** 21.4% (volatility indicator)
- **Signal:** Near lower band

## ATR (Volatility)
- **ATR:** $2.15 (3.4% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $59.33 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 14.9
- **%D:** 18.1
- **Signal:** OVERSOLD ⚡

## ADX (Trend Strength)
- **ADX:** 49.6 (Strengthening ↑)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $66.81 (-6.4% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** -297.3M
- **5-Day Trend:** Falling ↓
- **Signal:** BEARISH DIVERGENCE ⚠️ (distribution)

## VWAP (20-period)
- **VWAP:** $66.34
- **Current vs VWAP:** -5.7%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $94.46
- **Recent Low:** $60.90
- **Next Resistance:** $68.08 (78.6%)
- **Next Support:** $60.90 (100% (Low))

## Summary
- **Key Signals:** RSI oversold, Below 50 SMA

```

---

## 55. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:14.498204
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'BSX'}`
- **Output Length:** 59 chars

### Output
```
No insider transactions found for BSX in the last 3 months.
```

---

## 56. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:14.751248
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'BSX'}`
- **Output Length:** 718 chars

### Output
```
## Analyst Recommendation Trends for BSX

### 2026-04-01
- **Strong Buy**: 13
- **Buy**: 25
- **Hold**: 3
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 41

**Sentiment**: 92.7% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 14
- **Buy**: 23
- **Hold**: 3
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 40

**Sentiment**: 92.5% Bullish, 0.0% Bearish

### 2026-02-01
- **Strong Buy**: 15
- **Buy**: 22
- **Hold**: 3
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 40

**Sentiment**: 92.5% Bullish, 0.0% Bearish

### 2026-01-01
- **Strong Buy**: 15
- **Buy**: 21
- **Hold**: 4
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 40

**Sentiment**: 90.0% Bullish, 0.0% Bearish


```

---

## 57. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:15.146809
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'BSX', 'num_expirations': 3, 'curr_date': '2026-04-09'}`
- **Output Length:** 927 chars

### Output
```
## Options Activity for BSX

**Available Expirations:** 17 dates
**Analyzing:** 2026-04-10, 2026-04-17, 2026-04-24

### Summary
| Metric | Calls | Puts | Put/Call Ratio |
|--------|-------|------|----------------|
| Volume | 2,100 | 4,164 | 1.983 |
| Open Interest | 152,121 | 30,738 | 0.202 |

### Sentiment Analysis
- **Volume P/C Ratio:** Bearish (more put volume)
- **OI P/C Ratio:** Bullish positioning

### Unusual Activity (High Volume vs Open Interest)
| Type | Expiry | Strike | Volume | OI | Vol/OI | IV |
|------|--------|--------|--------|----|---------|----|---|
| PUT | 2026-04-17 | $85.0 | 2,050 | 37 | 55.41x | 96.9% |
| PUT | 2026-04-17 | $90.0 | 1,123 | 36 | 31.19x | 110.9% |
| CALL | 2026-04-10 | $69.0 | 114 | 105 | 1.09x | 136.7% |
| CALL | 2026-04-17 | $73.5 | 380 | 357 | 1.06x | 58.2% |
| PUT | 2026-04-24 | $71.0 | 169 | 198 | 0.85x | 55.5% |
| CALL | 2026-04-17 | $65.0 | 296 | 568 | 0.52x | 52.6% |

```

---

## 58. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:18.225746
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'COIN', 'curr_date': '2026-04-09'}`
- **Output Length:** 1529 chars

### Output
```
# Technical Analysis for COIN
**Date:** 2026-04-09
**Current Price:** $175.09

## Price Action
- **Daily Change:** -0.05%
- **5-Day Change:** +1.21%

## RSI (14)
- **Value:** 44.7 ↑
- **Signal:** Bearish

## MACD
- **MACD Line:** -5.109
- **Signal Line:** -4.072
- **Histogram:** -1.038 (Weakening ↓)
- **Signal:** Bearish

## Moving Averages
- **50 SMA:** $181.24 (-3.4% from price)
- **200 SMA:** $278.67 (-37.2% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $215.76
- **Middle:** $185.29
- **Lower:** $154.82
- **Band Position:** 33%
- **Bandwidth:** 32.9% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $11.60 (6.6% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $157.69 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 42.2
- **%D:** 33.1
- **Signal:** Bearish

## ADX (Trend Strength)
- **ADX:** 15.5 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $180.32 (-2.9% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** -66.0M
- **5-Day Trend:** Falling ↓
- **Signal:** BEARISH DIVERGENCE ⚠️ (distribution)

## VWAP (20-period)
- **VWAP:** $186.78
- **Current vs VWAP:** -6.3%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $214.39
- **Recent Low:** $139.36
- **Next Resistance:** $176.88 (50.0%)
- **Next Support:** $168.02 (61.8%)

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 59. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:18.631118
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'COIN'}`
- **Output Length:** 494 chars

### Output
```
# Insider Transactions for COIN
# Data retrieved on: 2026-04-09 14:25:18

## Summary
- **Insider Sentiment:** BEARISH ⚠️ (significant insider selling)
- **Sale:** 1 transactions
- **Total Sales Value:** $2,005,934
- **Largest Sale (3mo):** 2026-03-16 | HAAS ALESIA J (Chief Financial Officer) | 9950 shares | $2005934.0 | Ownership: D

## Transaction Details

Start Date,Insider,Position,Transaction,Shares,Value,Ownership
2026-03-16,HAAS ALESIA J,Chief Financial Officer,Sale,9950,2005934.0,D

```

---

## 60. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:18.861087
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

## 61. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:19.420818
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'COIN', 'num_expirations': 3, 'curr_date': '2026-04-09'}`
- **Output Length:** 1160 chars

### Output
```
## Options Activity for COIN

**Available Expirations:** 21 dates
**Analyzing:** 2026-04-10, 2026-04-17, 2026-04-24

### Summary
| Metric | Calls | Puts | Put/Call Ratio |
|--------|-------|------|----------------|
| Volume | 14,557 | 14,243 | 0.978 |
| Open Interest | 178,614 | 112,660 | 0.631 |

### Sentiment Analysis
- **Volume P/C Ratio:** Neutral
- **OI P/C Ratio:** Bullish positioning

### Unusual Activity (High Volume vs Open Interest)
| Type | Expiry | Strike | Volume | OI | Vol/OI | IV |
|------|--------|--------|--------|----|---------|----|---|
| CALL | 2026-04-24 | $175.0 | 1,072 | 206 | 5.2x | 77.2% |
| PUT | 2026-04-10 | $147.0 | 541 | 236 | 2.29x | 89.5% |
| PUT | 2026-04-10 | $134.0 | 352 | 269 | 1.31x | 160.0% |
| PUT | 2026-04-10 | $170.0 | 2,064 | 1,891 | 1.09x | 46.9% |
| CALL | 2026-04-24 | $167.5 | 190 | 183 | 1.04x | 80.7% |
| PUT | 2026-04-24 | $175.0 | 523 | 612 | 0.85x | 55.3% |
| PUT | 2026-04-24 | $190.0 | 227 | 273 | 0.83x | 53.3% |
| CALL | 2026-04-17 | $192.5 | 254 | 321 | 0.79x | 71.1% |
| CALL | 2026-04-17 | $175.0 | 1,600 | 2,075 | 0.77x | 77.5% |
| PUT | 2026-04-10 | $160.0 | 2,239 | 3,274 | 0.68x | 65.9% |

```

---

## 62. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:21.708435
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'EL', 'curr_date': '2026-04-09'}`
- **Output Length:** 1506 chars

### Output
```
# Technical Analysis for EL
**Date:** 2026-04-09
**Current Price:** $71.44

## Price Action
- **Daily Change:** +3.28%
- **5-Day Change:** +1.03%

## RSI (14)
- **Value:** 34.4 ↑
- **Signal:** Bearish

## MACD
- **MACD Line:** -7.748
- **Signal Line:** -8.124
- **Histogram:** 0.376 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $95.24 (-25.0% from price)
- **200 SMA:** $94.31 (-24.2% from price)
- **Trend:** Downtrend

## Bollinger Bands (20,2)
- **Upper:** $94.90
- **Middle:** $77.54
- **Lower:** $60.19
- **Band Position:** 32%
- **Bandwidth:** 44.8% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $4.25 (5.9% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $65.07 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 40.6
- **%D:** 26.2
- **Signal:** Bearish

## ADX (Trend Strength)
- **ADX:** 36.7 (Weakening ↓)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $77.76 (-8.1% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** 12.5M
- **5-Day Trend:** Falling ↓
- **Signal:** BEARISH DIVERGENCE ⚠️ (distribution)

## VWAP (20-period)
- **VWAP:** $76.35
- **Current vs VWAP:** -6.4%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $121.26
- **Recent Low:** $66.22
- **Next Resistance:** $78.00 (78.6%)
- **Next Support:** $66.22 (100% (Low))

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 63. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:21.972696
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'EL'}`
- **Output Length:** 58 chars

### Output
```
No insider transactions found for EL in the last 3 months.
```

---

## 64. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:22.259280
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'EL'}`
- **Output Length:** 717 chars

### Output
```
## Analyst Recommendation Trends for EL

### 2026-04-01
- **Strong Buy**: 7
- **Buy**: 10
- **Hold**: 16
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 34

**Sentiment**: 50.0% Bullish, 2.9% Bearish

### 2026-03-01
- **Strong Buy**: 7
- **Buy**: 11
- **Hold**: 16
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 35

**Sentiment**: 51.4% Bullish, 2.9% Bearish

### 2026-02-01
- **Strong Buy**: 6
- **Buy**: 12
- **Hold**: 16
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 35

**Sentiment**: 51.4% Bullish, 2.9% Bearish

### 2026-01-01
- **Strong Buy**: 5
- **Buy**: 12
- **Hold**: 17
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 35

**Sentiment**: 48.6% Bullish, 2.9% Bearish


```

---

## 65. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:22.676042
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'EL', 'num_expirations': 3, 'curr_date': '2026-04-09'}`
- **Output Length:** 1021 chars

### Output
```
## Options Activity for EL

**Available Expirations:** 15 dates
**Analyzing:** 2026-04-10, 2026-04-17, 2026-04-24

### Summary
| Metric | Calls | Puts | Put/Call Ratio |
|--------|-------|------|----------------|
| Volume | 3,036 | 3,035 | 1.0 |
| Open Interest | 35,625 | 15,760 | 0.442 |

### Sentiment Analysis
- **Volume P/C Ratio:** Neutral
- **OI P/C Ratio:** Bullish positioning

### Unusual Activity (High Volume vs Open Interest)
| Type | Expiry | Strike | Volume | OI | Vol/OI | IV |
|------|--------|--------|--------|----|---------|----|---|
| PUT | 2026-04-17 | $115.0 | 500 | 118 | 4.24x | 195.2% |
| CALL | 2026-04-10 | $68.5 | 1,501 | 438 | 3.43x | 99.0% |
| PUT | 2026-04-17 | $105.0 | 262 | 95 | 2.76x | 161.6% |
| PUT | 2026-04-17 | $110.0 | 260 | 174 | 1.49x | 175.6% |
| CALL | 2026-04-17 | $77.0 | 195 | 194 | 1.01x | 59.6% |
| CALL | 2026-04-17 | $78.0 | 114 | 130 | 0.88x | 62.5% |
| PUT | 2026-04-10 | $66.0 | 731 | 839 | 0.87x | 84.2% |
| CALL | 2026-04-17 | $77.5 | 192 | 242 | 0.79x | 60.7% |

```

---

## 66. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:25.773256
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'AMZN', 'curr_date': '2026-04-09'}`
- **Output Length:** 1562 chars

### Output
```
# Technical Analysis for AMZN
**Date:** 2026-04-09
**Current Price:** $221.25

## Price Action
- **Daily Change:** +3.50%
- **5-Day Change:** +5.07%

## RSI (14)
- **Value:** 60.7 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 0.106
- **Signal Line:** -1.502
- **Histogram:** 1.608 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $213.72 (+3.5% from price)
- **200 SMA:** $224.60 (-1.5% from price)
- **Trend:** Uptrend

## Bollinger Bands (20,2)
- **Upper:** $219.20
- **Middle:** $209.71
- **Lower:** $200.21
- **Band Position:** 111%
- **Bandwidth:** 9.1% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $6.23 (2.8% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $211.90 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 80.5
- **%D:** 68.1
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 11.1 (Strengthening ↑)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $210.87 (+4.9% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 458.0M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $209.64
- **Current vs VWAP:** +5.5%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $247.78
- **Recent Low:** $196.00
- **Next Resistance:** $221.89 (50.0%)
- **Next Support:** $215.78 (61.8%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 67. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:26.128355
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'AMZN'}`
- **Output Length:** 472 chars

### Output
```
# Insider Transactions for AMZN
# Data retrieved on: 2026-04-09 14:25:26

## Summary
- **Insider Sentiment:** BEARISH ⚠️ (significant insider selling)
- **Sale:** 1 transactions
- **Total Sales Value:** $210,500
- **Largest Sale (3mo):** 2026-04-01 | HERRINGTON DOUGLAS J (Officer) | 1000 shares | $210500.0 | Ownership: D

## Transaction Details

Start Date,Insider,Position,Transaction,Shares,Value,Ownership
2026-04-01,HERRINGTON DOUGLAS J,Officer,Sale,1000,210500.0,D

```

---

## 68. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:26.365997
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

## 69. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:26.777386
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'AMZN', 'num_expirations': 3, 'curr_date': '2026-04-09'}`
- **Output Length:** 1169 chars

### Output
```
## Options Activity for AMZN

**Available Expirations:** 25 dates
**Analyzing:** 2026-04-10, 2026-04-13, 2026-04-15

### Summary
| Metric | Calls | Puts | Put/Call Ratio |
|--------|-------|------|----------------|
| Volume | 61,968 | 29,806 | 0.481 |
| Open Interest | 147,754 | 124,806 | 0.845 |

### Sentiment Analysis
- **Volume P/C Ratio:** Bullish (more call volume)
- **OI P/C Ratio:** Neutral positioning

### Unusual Activity (High Volume vs Open Interest)
| Type | Expiry | Strike | Volume | OI | Vol/OI | IV |
|------|--------|--------|--------|----|---------|----|---|
| CALL | 2026-04-13 | $275.0 | 121 | 1 | 121.0x | 59.4% |
| PUT | 2026-04-10 | $222.5 | 9,180 | 987 | 9.3x | 26.5% |
| CALL | 2026-04-10 | $175.0 | 492 | 56 | 8.79x | 233.9% |
| PUT | 2026-04-13 | $225.0 | 543 | 63 | 8.62x | 23.7% |
| PUT | 2026-04-10 | $227.5 | 310 | 49 | 6.33x | 21.9% |
| CALL | 2026-04-10 | $170.0 | 195 | 32 | 6.09x | 259.2% |
| CALL | 2026-04-15 | $240.0 | 202 | 69 | 2.93x | 30.0% |
| CALL | 2026-04-13 | $235.0 | 291 | 105 | 2.77x | 27.9% |
| CALL | 2026-04-10 | $265.0 | 115 | 42 | 2.74x | 75.0% |
| CALL | 2026-04-10 | $227.5 | 14,218 | 8,943 | 1.59x | 30.4% |

```

---

## 70. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:28.647022
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'BKR', 'curr_date': '2026-04-09'}`
- **Output Length:** 1540 chars

### Output
```
# Technical Analysis for BKR
**Date:** 2026-04-09
**Current Price:** $63.16

## Price Action
- **Daily Change:** +3.12%
- **5-Day Change:** +4.67%

## RSI (14)
- **Value:** 59.8 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 0.605
- **Signal Line:** 0.540
- **Histogram:** 0.065 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $60.28 (+4.8% from price)
- **200 SMA:** $49.32 (+28.1% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $65.61
- **Middle:** $60.08
- **Lower:** $54.56
- **Band Position:** 78%
- **Bandwidth:** 18.4% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $2.05 (3.2% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $60.09 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 51.8
- **%D:** 49.1
- **Signal:** Bullish crossover ⚡

## ADX (Trend Strength)
- **ADX:** 14.4 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $60.92 (+3.7% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 324.5M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $59.64
- **Current vs VWAP:** +5.9%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $67.00
- **Recent Low:** $53.83
- **Next Resistance:** $63.89 (23.6%)
- **Next Support:** $61.97 (38.2%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 71. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:28.892218
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'BKR'}`
- **Output Length:** 757 chars

### Output
```
# Insider Transactions for BKR
# Data retrieved on: 2026-04-09 14:25:28

## Summary
- **Insider Sentiment:** BEARISH ⚠️ (significant insider selling)
- **Sale:** 3 transactions
- **Option Exercise:** 1 transactions
- **Total Sales Value:** $19,627,019
- **Largest Sale (3mo):** 2026-03-11 | SIMONELLI LORENZO (Chief Executive Officer) | 272594 shares | $16025801.0 | Ownership: D

## Transaction Details

Start Date,Insider,Position,Transaction,Shares,Value,Ownership
2026-03-16,BORRAS MARIA CLAUDIA,Officer,Sale,60626,3302298.0,D
2026-03-11,MAGNO MARIA GEORGIA,Officer,Sale,5063,298920.0,D
2026-03-11,SIMONELLI LORENZO,Chief Executive Officer,Sale,272594,16025801.0,D
2026-03-11,SIMONELLI LORENZO,Chief Executive Officer,Option Exercise,187344,6688181.0,D

```

---

## 72. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:29.143883
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'BKR'}`
- **Output Length:** 714 chars

### Output
```
## Analyst Recommendation Trends for BKR

### 2026-04-01
- **Strong Buy**: 7
- **Buy**: 15
- **Hold**: 3
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 26

**Sentiment**: 84.6% Bullish, 3.8% Bearish

### 2026-03-01
- **Strong Buy**: 7
- **Buy**: 15
- **Hold**: 3
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 26

**Sentiment**: 84.6% Bullish, 3.8% Bearish

### 2026-02-01
- **Strong Buy**: 7
- **Buy**: 14
- **Hold**: 3
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 25

**Sentiment**: 84.0% Bullish, 4.0% Bearish

### 2026-01-01
- **Strong Buy**: 7
- **Buy**: 14
- **Hold**: 4
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 26

**Sentiment**: 80.8% Bullish, 3.8% Bearish


```

---

## 73. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:29.470586
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'BKR', 'num_expirations': 3, 'curr_date': '2026-04-09'}`
- **Output Length:** 695 chars

### Output
```
## Options Activity for BKR

**Available Expirations:** 10 dates
**Analyzing:** 2026-04-17, 2026-05-15, 2026-06-18

### Summary
| Metric | Calls | Puts | Put/Call Ratio |
|--------|-------|------|----------------|
| Volume | 402 | 4,271 | 10.624 |
| Open Interest | 26,498 | 20,577 | 0.777 |

### Sentiment Analysis
- **Volume P/C Ratio:** Bearish (more put volume)
- **OI P/C Ratio:** Neutral positioning

### Unusual Activity (High Volume vs Open Interest)
| Type | Expiry | Strike | Volume | OI | Vol/OI | IV |
|------|--------|--------|--------|----|---------|----|---|
| PUT | 2026-05-15 | $55.0 | 1,706 | 106 | 16.09x | 44.8% |
| PUT | 2026-06-18 | $38.0 | 2,147 | 3,744 | 0.57x | 74.4% |

```

---

## 74. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:31.288809
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'CVNA', 'curr_date': '2026-04-09'}`
- **Output Length:** 1573 chars

### Output
```
# Technical Analysis for CVNA
**Date:** 2026-04-09
**Current Price:** $338.81

## Price Action
- **Daily Change:** +5.81%
- **5-Day Change:** +8.56%

## RSI (14)
- **Value:** 57.9 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** -4.027
- **Signal Line:** -10.582
- **Histogram:** 6.555 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $339.76 (-0.3% from price)
- **200 SMA:** $364.16 (-7.0% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $331.31
- **Middle:** $305.46
- **Lower:** $279.61
- **Band Position:** 115%
- **Bandwidth:** 16.9% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $21.07 (6.2% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $307.21 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 86.3
- **%D:** 78.8
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 18.3 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $314.76 (+7.6% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 20.3M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $303.06
- **Current vs VWAP:** +11.8%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $484.79
- **Recent Low:** $272.32
- **Next Resistance:** $353.48 (61.8%)
- **Next Support:** $317.79 (78.6%)

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 75. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:31.578288
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'CVNA'}`
- **Output Length:** 913 chars

### Output
```
# Insider Transactions for CVNA
# Data retrieved on: 2026-04-09 14:25:31

## Summary
- **Insider Sentiment:** BEARISH ⚠️ (significant insider selling)
- **Sale:** 3 transactions
- **Option Exercise:** 3 transactions
- **Total Sales Value:** $7,373,037
- **Largest Sale (3mo):** 2026-04-01 | JENKINS MARK W (Chief Financial Officer) | 12750 shares | $3956945.0 | Ownership: D

## Transaction Details

Start Date,Insider,Position,Transaction,Shares,Value,Ownership
2026-04-01,HUSTON BENJAMIN EDWARD,Chief Operating Officer,Sale,10000,3098592.0,D
2026-04-01,HUSTON BENJAMIN EDWARD,Chief Operating Officer,Option Exercise,10000,100700.0,D
2026-04-01,PALMER STEPHEN R,Officer,Sale,1000,317500.0,D
2026-04-01,JENKINS MARK W,Chief Financial Officer,Sale,12750,3956945.0,D
2026-04-01,JENKINS MARK W,Chief Financial Officer,Option Exercise,12750,223738.0,D
2026-03-12,PLATT IRA J,Director,Option Exercise,10000,150000.0,D

```

---

## 76. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:31.809146
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'CVNA'}`
- **Output Length:** 719 chars

### Output
```
## Analyst Recommendation Trends for CVNA

### 2026-04-01
- **Strong Buy**: 11
- **Buy**: 12
- **Hold**: 8
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 32

**Sentiment**: 71.9% Bullish, 3.1% Bearish

### 2026-03-01
- **Strong Buy**: 11
- **Buy**: 12
- **Hold**: 8
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 32

**Sentiment**: 71.9% Bullish, 3.1% Bearish

### 2026-02-01
- **Strong Buy**: 11
- **Buy**: 12
- **Hold**: 8
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 32

**Sentiment**: 71.9% Bullish, 3.1% Bearish

### 2026-01-01
- **Strong Buy**: 11
- **Buy**: 14
- **Hold**: 7
- **Sell**: 1
- **Strong Sell**: 0
- **Total Analysts**: 33

**Sentiment**: 75.8% Bullish, 3.0% Bearish


```

---

## 77. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:32.439449
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'CVNA', 'num_expirations': 3, 'curr_date': '2026-04-09'}`
- **Output Length:** 1171 chars

### Output
```
## Options Activity for CVNA

**Available Expirations:** 17 dates
**Analyzing:** 2026-04-10, 2026-04-17, 2026-04-24

### Summary
| Metric | Calls | Puts | Put/Call Ratio |
|--------|-------|------|----------------|
| Volume | 5,295 | 22,161 | 4.185 |
| Open Interest | 100,314 | 85,299 | 0.85 |

### Sentiment Analysis
- **Volume P/C Ratio:** Bearish (more put volume)
- **OI P/C Ratio:** Neutral positioning

### Unusual Activity (High Volume vs Open Interest)
| Type | Expiry | Strike | Volume | OI | Vol/OI | IV |
|------|--------|--------|--------|----|---------|----|---|
| PUT | 2026-04-24 | $230.0 | 13,056 | 6,294 | 2.07x | 95.8% |
| PUT | 2026-04-10 | $217.5 | 157 | 82 | 1.91x | 349.4% |
| CALL | 2026-04-24 | $365.0 | 103 | 68 | 1.51x | 69.2% |
| PUT | 2026-04-24 | $265.0 | 318 | 229 | 1.39x | 75.0% |
| PUT | 2026-04-10 | $320.0 | 182 | 174 | 1.05x | 61.2% |
| CALL | 2026-04-24 | $335.0 | 128 | 124 | 1.03x | 74.1% |
| PUT | 2026-04-24 | $250.0 | 4,172 | 4,100 | 1.02x | 84.3% |
| CALL | 2026-04-24 | $405.0 | 200 | 214 | 0.93x | 66.7% |
| PUT | 2026-04-24 | $150.0 | 470 | 583 | 0.81x | 137.5% |
| CALL | 2026-04-10 | $420.0 | 139 | 196 | 0.71x | 207.0% |

```

---

## 78. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:34.185184
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'EBAY', 'curr_date': '2026-04-09'}`
- **Output Length:** 1546 chars

### Output
```
# Technical Analysis for EBAY
**Date:** 2026-04-09
**Current Price:** $96.79

## Price Action
- **Daily Change:** +0.81%
- **5-Day Change:** +3.93%

## RSI (14)
- **Value:** 63.8 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** 1.659
- **Signal Line:** 0.955
- **Histogram:** 0.704 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $89.45 (+8.2% from price)
- **200 SMA:** $87.54 (+10.6% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $97.26
- **Middle:** $91.61
- **Lower:** $85.97
- **Band Position:** 96%
- **Bandwidth:** 12.3% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $2.94 (3.0% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $92.38 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 79.6
- **%D:** 68.8
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 30.5 (Strengthening ↑)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $92.08 (+5.1% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 104.6M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $91.49
- **Current vs VWAP:** +5.8%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $98.50
- **Recent Low:** $77.77
- **Next Resistance:** $98.50 (0.0% (High))
- **Next Support:** $93.61 (23.6%)

## Summary
- **Key Signals:** Above 50 SMA

```

---

## 79. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:34.426381
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'EBAY'}`
- **Output Length:** 1233 chars

### Output
```
# Insider Transactions for EBAY
# Data retrieved on: 2026-04-09 14:25:34

## Summary
- **Insider Sentiment:** BEARISH ⚠️ (significant insider selling)
- **Unknown:** 7 transactions
- **Sale:** 5 transactions
- **Total Sales Value:** $10,352,055
- **Largest Sale (3mo):** 2026-04-07 | IANNONE JAMES JOSEPH (Chief Executive Officer) | 42000 shares | $4078637.0 | Ownership: D

## Transaction Details

Start Date,Insider,Position,Transaction,Shares,Value,Ownership
2026-04-07,IANNONE JAMES JOSEPH,Chief Executive Officer,Sale,42000,4078637.0,D
2026-03-18,BOONE CORNELIUS,Officer,Sale,16685,1542334.0,D
2026-03-18,SWEETNAM JORDAN DOUGLAS BRADLEY,Officer,Sale,12978,1199684.0,D
2026-03-17,RAWASHDEH MAZEN,Chief Technology Officer,Sale,23167,2168200.0,D
2026-03-13,RAWASHDEH MAZEN,Chief Technology Officer,Unknown,96779,,D
2026-03-13,WELLINGTON SAMANTHA,Officer,Unknown,1880,,D
2026-03-13,BOONE CORNELIUS,Officer,Unknown,84961,,D
2026-03-13,SPENCER REBECCA,Officer,Unknown,3070,,D
2026-03-13,SWEETNAM JORDAN DOUGLAS BRADLEY,Officer,Unknown,104723,,D
2026-03-13,LOEGER JULIE ANNE,Officer,Unknown,107408,,D
2026-03-13,IANNONE JAMES JOSEPH,Chief Executive Officer,Unknown,364373,,D
2026-03-12,LOEGER JULIE ANNE,Officer,Sale,15000,1363200.0,D

```

---

## 80. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:34.670541
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'EBAY'}`
- **Output Length:** 719 chars

### Output
```
## Analyst Recommendation Trends for EBAY

### 2026-04-01
- **Strong Buy**: 4
- **Buy**: 11
- **Hold**: 25
- **Sell**: 0
- **Strong Sell**: 1
- **Total Analysts**: 41

**Sentiment**: 36.6% Bullish, 2.4% Bearish

### 2026-03-01
- **Strong Buy**: 4
- **Buy**: 11
- **Hold**: 25
- **Sell**: 0
- **Strong Sell**: 1
- **Total Analysts**: 41

**Sentiment**: 36.6% Bullish, 2.4% Bearish

### 2026-02-01
- **Strong Buy**: 4
- **Buy**: 11
- **Hold**: 24
- **Sell**: 1
- **Strong Sell**: 1
- **Total Analysts**: 41

**Sentiment**: 36.6% Bullish, 4.9% Bearish

### 2026-01-01
- **Strong Buy**: 4
- **Buy**: 11
- **Hold**: 23
- **Sell**: 1
- **Strong Sell**: 1
- **Total Analysts**: 40

**Sentiment**: 37.5% Bullish, 5.0% Bearish


```

---

## 81. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:35.106138
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'EBAY', 'num_expirations': 3, 'curr_date': '2026-04-09'}`
- **Output Length:** 1146 chars

### Output
```
## Options Activity for EBAY

**Available Expirations:** 15 dates
**Analyzing:** 2026-04-10, 2026-04-17, 2026-04-24

### Summary
| Metric | Calls | Puts | Put/Call Ratio |
|--------|-------|------|----------------|
| Volume | 1,124 | 8,578 | 7.632 |
| Open Interest | 15,844 | 17,215 | 1.087 |

### Sentiment Analysis
- **Volume P/C Ratio:** Bearish (more put volume)
- **OI P/C Ratio:** Neutral positioning

### Unusual Activity (High Volume vs Open Interest)
| Type | Expiry | Strike | Volume | OI | Vol/OI | IV |
|------|--------|--------|--------|----|---------|----|---|
| PUT | 2026-04-10 | $78.0 | 1,548 | 61 | 25.38x | 184.0% |
| PUT | 2026-04-10 | $79.0 | 1,528 | 82 | 18.63x | 174.6% |
| PUT | 2026-04-17 | $87.0 | 616 | 61 | 10.1x | 44.5% |
| PUT | 2026-04-17 | $86.0 | 289 | 43 | 6.72x | 54.9% |
| PUT | 2026-04-17 | $88.0 | 395 | 85 | 4.65x | 42.1% |
| PUT | 2026-04-10 | $87.0 | 388 | 92 | 4.22x | 100.6% |
| PUT | 2026-04-10 | $86.0 | 190 | 56 | 3.39x | 100.2% |
| PUT | 2026-04-10 | $88.0 | 236 | 74 | 3.19x | 91.2% |
| PUT | 2026-04-17 | $84.0 | 293 | 94 | 3.12x | 52.0% |
| PUT | 2026-04-17 | $79.0 | 147 | 61 | 2.41x | 69.9% |

```

---

## 82. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:40.906439
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'TSLA', 'curr_date': '2026-04-09'}`
- **Output Length:** 1541 chars

### Output
```
# Technical Analysis for TSLA
**Date:** 2026-04-09
**Current Price:** $343.25

## Price Action
- **Daily Change:** -0.98%
- **5-Day Change:** -9.97%

## RSI (14)
- **Value:** 33.7 ↓
- **Signal:** Bearish

## MACD
- **MACD Line:** -14.151
- **Signal Line:** -11.761
- **Histogram:** -2.390 (Strengthening ↑)
- **Signal:** BEARISH CROSSOVER ⚠️

## Moving Averages
- **50 SMA:** $397.66 (-13.7% from price)
- **200 SMA:** $397.33 (-13.6% from price)
- **Trend:** Downtrend

## Bollinger Bands (20,2)
- **Upper:** $413.15
- **Middle:** $376.26
- **Lower:** $339.37
- **Band Position:** 5%
- **Bandwidth:** 19.6% (volatility indicator)
- **Signal:** Near lower band

## ATR (Volatility)
- **ATR:** $15.59 (4.5% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $319.86 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 19.4
- **%D:** 24.7
- **Signal:** Bearish

## ADX (Trend Strength)
- **ADX:** 32.1 (Strengthening ↑)
- **Interpretation:** Strong trend

## 20 EMA
- **Value:** $372.86 (-7.9% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** 821.3M
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $375.78
- **Current vs VWAP:** -8.7%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $440.23
- **Recent Low:** $337.24
- **Next Resistance:** $359.28 (78.6%)
- **Next Support:** $337.24 (100% (Low))

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 83. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:41.190171
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'TSLA'}`
- **Output Length:** 675 chars

### Output
```
# Insider Transactions for TSLA
# Data retrieved on: 2026-04-09 14:25:41

## Summary
- **Insider Sentiment:** BEARISH ⚠️ (significant insider selling)
- **Option Exercise:** 2 transactions
- **Sale:** 1 transactions
- **Total Sales Value:** $9,273,888
- **Largest Sale (3mo):** 2026-03-30 | WILSON - THOMPSON KATHLEEN (Director) | 25809 shares | $9273888.0 | Ownership: D

## Transaction Details

Start Date,Insider,Position,Transaction,Shares,Value,Ownership
2026-03-31,ZHU XIAOTONG,Officer,Option Exercise,20000,411400.0,D
2026-03-30,WILSON - THOMPSON KATHLEEN,Director,Sale,25809,9273888.0,D
2026-03-30,WILSON - THOMPSON KATHLEEN,Director,Option Exercise,40000,599600.0,D

```

---

## 84. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:41.420379
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

## 85. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:41.887528
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'TSLA', 'num_expirations': 3, 'curr_date': '2026-04-09'}`
- **Output Length:** 1170 chars

### Output
```
## Options Activity for TSLA

**Available Expirations:** 24 dates
**Analyzing:** 2026-04-10, 2026-04-13, 2026-04-15

### Summary
| Metric | Calls | Puts | Put/Call Ratio |
|--------|-------|------|----------------|
| Volume | 173,988 | 167,396 | 0.962 |
| Open Interest | 568,923 | 295,860 | 0.52 |

### Sentiment Analysis
- **Volume P/C Ratio:** Neutral
- **OI P/C Ratio:** Bullish positioning

### Unusual Activity (High Volume vs Open Interest)
| Type | Expiry | Strike | Volume | OI | Vol/OI | IV |
|------|--------|--------|--------|----|---------|----|---|
| CALL | 2026-04-15 | $295.0 | 108 | 5 | 21.6x | 61.1% |
| CALL | 2026-04-10 | $335.0 | 5,453 | 820 | 6.65x | 49.2% |
| CALL | 2026-04-10 | $345.0 | 19,440 | 3,594 | 5.41x | 47.8% |
| CALL | 2026-04-13 | $325.0 | 188 | 39 | 4.82x | 44.8% |
| CALL | 2026-04-10 | $342.5 | 8,186 | 1,709 | 4.79x | 48.4% |
| CALL | 2026-04-10 | $337.5 | 3,439 | 729 | 4.72x | 49.1% |
| PUT | 2026-04-10 | $342.5 | 18,257 | 4,057 | 4.5x | 46.9% |
| PUT | 2026-04-15 | $285.0 | 503 | 122 | 4.12x | 69.0% |
| PUT | 2026-04-10 | $337.5 | 15,094 | 4,015 | 3.76x | 48.7% |
| CALL | 2026-04-10 | $330.0 | 2,905 | 855 | 3.4x | 51.1% |

```

---

## 86. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:43.819523
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'UAE', 'curr_date': '2026-04-09'}`
- **Output Length:** 1558 chars

### Output
```
# Technical Analysis for UAE
**Date:** 2026-04-09
**Current Price:** $19.22

## Price Action
- **Daily Change:** +4.37%
- **5-Day Change:** +3.03%

## RSI (14)
- **Value:** 54.2 ↑
- **Signal:** Bullish

## MACD
- **MACD Line:** -0.304
- **Signal Line:** -0.493
- **Histogram:** 0.189 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $19.91 (-3.5% from price)
- **200 SMA:** $19.42 (-1.1% from price)
- **Trend:** Downtrend

## Bollinger Bands (20,2)
- **Upper:** $19.10
- **Middle:** $18.22
- **Lower:** $17.34
- **Band Position:** 107%
- **Bandwidth:** 9.6% (volatility indicator)
- **Signal:** AT UPPER BAND - Potential reversal ⚠️

## ATR (Volatility)
- **ATR:** $0.58 (3.0% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $18.35 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 60.3
- **%D:** 54.6
- **Signal:** Bullish crossover ⚡

## ADX (Trend Strength)
- **ADX:** 14.3 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $18.63 (+3.1% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** -2.5M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $18.27
- **Current vs VWAP:** +5.2%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $22.29
- **Recent Low:** $17.29
- **Next Resistance:** $19.79 (50.0%)
- **Next Support:** $19.20 (61.8%)

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 87. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:44.210945
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'UAE'}`
- **Output Length:** 51 chars

### Output
```
No insider transactions data found for symbol 'UAE'
```

---

## 88. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:44.434313
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'UAE'}`
- **Output Length:** 43 chars

### Output
```
No recommendation trends data found for UAE
```

---

## 89. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:44.840474
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'UAE', 'num_expirations': 3, 'curr_date': '2026-04-09'}`
- **Output Length:** 436 chars

### Output
```
## Options Activity for UAE

**Available Expirations:** 4 dates
**Analyzing:** 2026-04-17, 2026-05-15, 2026-07-17

### Summary
| Metric | Calls | Puts | Put/Call Ratio |
|--------|-------|------|----------------|
| Volume | 57 | 160 | 2.807 |
| Open Interest | 429 | 636 | 1.483 |

### Sentiment Analysis
- **Volume P/C Ratio:** Bearish (more put volume)
- **OI P/C Ratio:** Bearish positioning

*No unusual options activity detected.*

```

---

## 90. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:46.750740
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'CAGR', 'curr_date': '2026-04-09'}`
- **Output Length:** 1377 chars

### Output
```
# Technical Analysis for CAGR
**Date:** 2026-04-09
**Current Price:** $0.00

## Price Action
- **Daily Change:** +0.00%
- **5-Day Change:** +0.00%

## RSI (14)
- **Value:** 50.0 ↓
- **Signal:** Bearish

## MACD
- **MACD Line:** 0.000
- **Signal Line:** 0.000
- **Histogram:** 0.000 (Weakening ↓)
- **Signal:** Neutral

## Moving Averages
- **50 SMA:** $0.00 (0.0% from price)
- **200 SMA:** $0.00 (0.0% from price)
- **Trend:** Sideways

## Bollinger Bands (20,2)
- **Upper:** $0.00
- **Middle:** $0.00
- **Lower:** $0.00
- **Band Position:** 50%
- **Bandwidth:** 0.0% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $0.00 (0.0% of price)
- **Level:** Low volatility
- **Suggested Stop-Loss:** $0.00 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 0.0
- **%D:** 0.0
- **Signal:** OVERSOLD ⚡

## ADX (Trend Strength)
- **ADX:** nan (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $0.00 (+0.0% from price)
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
- **Recent High:** $0.00
- **Recent Low:** $0.00

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 91. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:47.047339
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'CAGR'}`
- **Output Length:** 52 chars

### Output
```
No insider transactions data found for symbol 'CAGR'
```

---

## 92. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:47.294316
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'CAGR'}`
- **Output Length:** 44 chars

### Output
```
No recommendation trends data found for CAGR
```

---

## 93. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:47.360583
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'CAGR', 'num_expirations': 3, 'curr_date': '2026-04-09'}`
- **Output Length:** 34 chars

### Output
```
No options data available for CAGR
```

---

## 94. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:50.669332
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'NVO', 'curr_date': '2026-04-09'}`
- **Output Length:** 1541 chars

### Output
```
# Technical Analysis for NVO
**Date:** 2026-04-09
**Current Price:** $37.61

## Price Action
- **Daily Change:** +1.90%
- **5-Day Change:** +3.10%

## RSI (14)
- **Value:** 49.5 ↑
- **Signal:** Bearish

## MACD
- **MACD Line:** -1.024
- **Signal Line:** -1.650
- **Histogram:** 0.625 (Strengthening ↑)
- **Signal:** BULLISH CROSSOVER ⚡

## Moving Averages
- **50 SMA:** $41.32 (-9.0% from price)
- **200 SMA:** $50.59 (-25.7% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $38.01
- **Middle:** $36.24
- **Lower:** $34.48
- **Band Position:** 89%
- **Bandwidth:** 9.7% (volatility indicator)
- **Signal:** Near upper band

## ATR (Volatility)
- **ATR:** $1.21 (3.2% of price)
- **Level:** Moderate volatility
- **Suggested Stop-Loss:** $35.79 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 77.5
- **%D:** 67.1
- **Signal:** Bullish

## ADX (Trend Strength)
- **ADX:** 12.9 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $36.94 (+1.8% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** -539.1M
- **5-Day Trend:** Rising ↑
- **Signal:** Confirmed uptrend (price & volume rising)

## VWAP (20-period)
- **VWAP:** $36.14
- **Current vs VWAP:** +4.1%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $61.24
- **Recent Low:** $34.58
- **Next Resistance:** $40.29 (78.6%)
- **Next Support:** $34.58 (100% (Low))

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 95. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:51.006829
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'NVO'}`
- **Output Length:** 51 chars

### Output
```
No insider transactions data found for symbol 'NVO'
```

---

## 96. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:51.242335
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'NVO'}`
- **Output Length:** 716 chars

### Output
```
## Analyst Recommendation Trends for NVO

### 2026-04-01
- **Strong Buy**: 5
- **Buy**: 7
- **Hold**: 23
- **Sell**: 1
- **Strong Sell**: 1
- **Total Analysts**: 37

**Sentiment**: 32.4% Bullish, 5.4% Bearish

### 2026-03-01
- **Strong Buy**: 5
- **Buy**: 8
- **Hold**: 19
- **Sell**: 2
- **Strong Sell**: 0
- **Total Analysts**: 34

**Sentiment**: 38.2% Bullish, 5.9% Bearish

### 2026-02-01
- **Strong Buy**: 6
- **Buy**: 12
- **Hold**: 13
- **Sell**: 2
- **Strong Sell**: 1
- **Total Analysts**: 34

**Sentiment**: 52.9% Bullish, 8.8% Bearish

### 2026-01-01
- **Strong Buy**: 5
- **Buy**: 13
- **Hold**: 11
- **Sell**: 2
- **Strong Sell**: 1
- **Total Analysts**: 32

**Sentiment**: 56.2% Bullish, 9.4% Bearish


```

---

## 97. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:51.669899
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'NVO', 'num_expirations': 3, 'curr_date': '2026-04-09'}`
- **Output Length:** 755 chars

### Output
```
## Options Activity for NVO

**Available Expirations:** 16 dates
**Analyzing:** 2026-04-10, 2026-04-17, 2026-04-24

### Summary
| Metric | Calls | Puts | Put/Call Ratio |
|--------|-------|------|----------------|
| Volume | 4,390 | 16,323 | 3.718 |
| Open Interest | 171,405 | 108,904 | 0.635 |

### Sentiment Analysis
- **Volume P/C Ratio:** Bearish (more put volume)
- **OI P/C Ratio:** Bullish positioning

### Unusual Activity (High Volume vs Open Interest)
| Type | Expiry | Strike | Volume | OI | Vol/OI | IV |
|------|--------|--------|--------|----|---------|----|---|
| PUT | 2026-04-17 | $65.0 | 10,000 | 1,250 | 8.0x | 175.8% |
| CALL | 2026-04-24 | $38.5 | 222 | 223 | 1.0x | 42.2% |
| PUT | 2026-04-17 | $37.5 | 875 | 1,100 | 0.8x | 40.8% |

```

---

## 98. Get technical indicators

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:53.409882
- **Tool:** `get_indicators`
- **Parameters:** `{'symbol': 'HIMS', 'curr_date': '2026-04-09'}`
- **Output Length:** 1524 chars

### Output
```
# Technical Analysis for HIMS
**Date:** 2026-04-09
**Current Price:** $19.39

## Price Action
- **Daily Change:** -0.56%
- **5-Day Change:** -2.27%

## RSI (14)
- **Value:** 44.8 ↓
- **Signal:** Bearish

## MACD
- **MACD Line:** -0.465
- **Signal Line:** -0.243
- **Histogram:** -0.223 (Weakening ↓)
- **Signal:** Bearish

## Moving Averages
- **50 SMA:** $20.53 (-5.5% from price)
- **200 SMA:** $39.16 (-50.5% from price)
- **Trend:** STRONG DOWNTREND ⚠️

## Bollinger Bands (20,2)
- **Upper:** $26.39
- **Middle:** $21.81
- **Lower:** $17.24
- **Band Position:** 23%
- **Bandwidth:** 41.9% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $1.79 (9.2% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $16.70 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 26.2
- **%D:** 24.1
- **Signal:** Bearish

## ADX (Trend Strength)
- **ADX:** 5.0 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $20.49 (-5.4% from price)
- **Signal:** Price BELOW 20 EMA (short-term bearish)

## OBV (On-Balance Volume)
- **Value:** -424.8M
- **5-Day Trend:** Falling ↓
- **Signal:** Confirmed downtrend (price & volume falling)

## VWAP (20-period)
- **VWAP:** $22.80
- **Current vs VWAP:** -14.9%
- **Signal:** Price BELOW VWAP (institutional selling)

## Fibonacci Levels (50-period)
- **Recent High:** $30.70
- **Recent Low:** $13.74
- **Next Resistance:** $20.22 (61.8%)
- **Next Support:** $17.37 (78.6%)

## Summary
- **Key Signals:** Below 50 SMA

```

---

## 99. Get insider transactions

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:53.721504
- **Tool:** `get_insider_transactions`
- **Parameters:** `{'ticker': 'HIMS'}`
- **Output Length:** 1473 chars

### Output
```
# Insider Transactions for HIMS
# Data retrieved on: 2026-04-09 14:25:53

## Summary
- **Insider Sentiment:** BEARISH ⚠️ (significant insider selling)
- **Unknown:** 8 transactions
- **Sale:** 5 transactions
- **Option Exercise:** 2 transactions
- **Total Sales Value:** $2,955,860
- **Largest Sale (3mo):** 2026-03-17 | CHI MICHAEL Y (Chief Operating Officer) | 97289 shares | $2402065.0 | Ownership: D

## Transaction Details

Start Date,Insider,Position,Transaction,Shares,Value,Ownership
2026-04-06,OKUPE OLUYEMI,Chief Financial Officer,Sale,3975,79409.0,D
2026-04-06,OKUPE OLUYEMI,Chief Financial Officer,Option Exercise,3975,19915.0,D
2026-03-20,OKUPE OLUYEMI,Chief Financial Officer,Sale,9217,219067.0,D
2026-03-20,OKUPE OLUYEMI,Chief Financial Officer,Option Exercise,4489,22490.0,D
2026-03-17,CHI MICHAEL Y,Chief Operating Officer,Sale,97289,2402065.0,D
2026-03-17,BOUGHTON SOLEIL,Officer,Sale,4812,118808.0,D
2026-03-17,BECKLUND IRENE,Officer,Sale,5529,136511.0,D
2026-03-13,OKUPE OLUYEMI,Chief Financial Officer,Unknown,105200,,D
2026-03-13,PENDARVIS CHRISTIANE,Director,Unknown,15211,,D
2026-03-13,CHI MICHAEL Y,Chief Operating Officer,Unknown,72108,,D
2026-03-13,DUDUM ANDREW,Chief Executive Officer,Unknown,164369,,D
2026-03-13,CARROLL PATRICK HARRISON,Officer and Director,Unknown,16522,,D
2026-03-13,BOUGHTON SOLEIL,Officer,Unknown,41421,,D
2026-03-13,BECKLUND IRENE,Officer,Unknown,17987,,D
2026-03-13,AUTOR DEBORAH M,Officer and Director,Unknown,32919,,D

```

---

## 100. Get recommendations

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:53.949230
- **Tool:** `get_recommendation_trends`
- **Parameters:** `{'ticker': 'HIMS'}`
- **Output Length:** 715 chars

### Output
```
## Analyst Recommendation Trends for HIMS

### 2026-04-01
- **Strong Buy**: 2
- **Buy**: 7
- **Hold**: 13
- **Sell**: 0
- **Strong Sell**: 0
- **Total Analysts**: 22

**Sentiment**: 40.9% Bullish, 0.0% Bearish

### 2026-03-01
- **Strong Buy**: 0
- **Buy**: 2
- **Hold**: 14
- **Sell**: 2
- **Strong Sell**: 3
- **Total Analysts**: 21

**Sentiment**: 9.5% Bullish, 23.8% Bearish

### 2026-02-01
- **Strong Buy**: 3
- **Buy**: 5
- **Hold**: 12
- **Sell**: 1
- **Strong Sell**: 1
- **Total Analysts**: 22

**Sentiment**: 36.4% Bullish, 9.1% Bearish

### 2026-01-01
- **Strong Buy**: 3
- **Buy**: 5
- **Hold**: 11
- **Sell**: 1
- **Strong Sell**: 1
- **Total Analysts**: 21

**Sentiment**: 38.1% Bullish, 9.5% Bearish


```

---

## 101. Get options activity

- **Type:** `tool`
- **Node:** filter
- **Timestamp:** 2026-04-09T14:25:54.355982
- **Tool:** `get_options_activity`
- **Parameters:** `{'ticker': 'HIMS', 'num_expirations': 3, 'curr_date': '2026-04-09'}`
- **Output Length:** 869 chars

### Output
```
## Options Activity for HIMS

**Available Expirations:** 17 dates
**Analyzing:** 2026-04-10, 2026-04-17, 2026-04-24

### Summary
| Metric | Calls | Puts | Put/Call Ratio |
|--------|-------|------|----------------|
| Volume | 5,744 | 3,065 | 0.534 |
| Open Interest | 240,965 | 105,584 | 0.438 |

### Sentiment Analysis
- **Volume P/C Ratio:** Bullish (more call volume)
- **OI P/C Ratio:** Bullish positioning

### Unusual Activity (High Volume vs Open Interest)
| Type | Expiry | Strike | Volume | OI | Vol/OI | IV |
|------|--------|--------|--------|----|---------|----|---|
| PUT | 2026-04-24 | $19.5 | 404 | 375 | 1.08x | 79.7% |
| CALL | 2026-04-10 | $16.0 | 185 | 174 | 1.06x | 248.4% |
| PUT | 2026-04-24 | $15.5 | 137 | 132 | 1.04x | 93.8% |
| CALL | 2026-04-10 | $15.0 | 188 | 204 | 0.92x | 305.5% |
| PUT | 2026-04-10 | $16.5 | 119 | 228 | 0.52x | 123.4% |

```

---

## 102. Rank candidates

- **Type:** `llm`
- **Node:** ranker
- **Timestamp:** 2026-04-09T14:26:51.260585
- **Model:** `gemini-3-pro-preview`
- **Prompt Length:** 143456 chars
- **Output Length:** 2000 chars

### Prompt
```
You are a professional stock analyst selecting the best short-term trading opportunities from a pre-filtered candidate list.

CURRENT DATE: 2026-04-09

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
"Historical 1-day win rate: 38.1% (596 tracked)\nHistorical 7-day win rate: 42.2% (554 tracked)\nHistorical 30-day win rate: 33.9% (448 tracked)\n\nBest performing strategies (7-day):\n  - short_squeeze: 60.0% win rate (10 samples)\n  - analyst_upgrade: 48.0% win rate (25 samples)\n  - options_flow: 46.1% win rate (89 samples)"

CANDIDATES FOR REVIEW:
### ALB (Priority: CRITICAL)
- **Strategy Match**: minervini
- **Sources**: minervini | **Confluence**: 1 source(s)
- **Quant Pre-Score**: 10/100 | **ML Win Probability**: N/A | **Altman Z-Score**: 2.66 | **Piotroski F-Score**: 5
- **Price**: $172.76 | **Current Price (numeric)**: 172.7550048828125 | **Intraday**: -2.1% | **Avg Volume**: 1,484,167
- **Short Interest**: 0.0%
- **Discovery Context**: Minervini Stage 2: P>SMA50>SMA150>SMA200, +235% off 52w low, within 12% of 52w high, RS Rating 98/100
- **Business**: Albemarle Corporation provides energy storage solutions worldwide. It operates through three segments: Energy Storage, Specialties, and Ketjen. The Energy Storage segment offers lithium compounds, including lithium carbonate, lithium hydroxide, and lithium chloride for use in lithium batteries used in consumer electronics and electric vehicles, power grids and solar panels, high performance greases, specialty glass used in consumer appliances and electronics. The Specialties segment provides bromine and highly specialized lithium solutions for various industries, such as energy, mobility, connectivity, and health comprising fire safety compounds; bromine-based specialty chemicals products, including elemental bromine, alkyl bromides, inorganic bromides, brominated powdered activated carbon, and various bromine fine chemicals; lithium specialties, such as butyllithium and lithium aluminum hydride; cesium products for the chemical and pharmaceutical industries; and zirconium, barium, and titanium products for pyrotechnical applications that include airbag initiators. This segment also provides organic synthesis processes in the areas of steroid chemistry and vitamins, and various life science applications, as well as intermediates in the pharmaceutical industry; technical services, including handling and use of reactive lithium products; and recycling services for lithium-containing by-products. The Ketjen segment offers clean fuels technologies, including hydroprocessing catalysts together with isomerization and akylation catalysts; fluidized catalytic cracking catalysts and additives; and performance catalyst solutions comprising organometallics and curatives. It serves grid storage, automotive, aerospace, conventional energy, electronics, construction, agriculture and food, pharmaceuticals and medical device industries. Albemarle Corporation was founded in 1887 and is headquartered in Charlotte, North Carolina.
- **News**: 

**Technical Analysis**:
# Technical Analysis for ALB
**Date:** 2026-04-09
**Current Price:** $177.44

## Price Action
- **Daily Change:** +2.25%
- **5-Day Change:** -0.58%

## RSI (14)
- **Value:** 54.6 ↓
- **Signal:** Bullish

## MACD
- **MACD Line:** 2.200
- **Signal Line:** 1.794
- **Histogram:** 0.407 (Weakening ↓)
- **Signal:** Bullish

## Moving Averages
- **50 SMA:** $171.43 (+3.5% from price)
- **200 SMA:** $118.80 (+49.4% from price)
- **Trend:** STRONG UPTREND ⚡

## Bollinger Bands (20,2)
- **Upper:** $186.46
- **Middle:** $171.06
- **Lower:** $155.65
- **Band Position:** 71%
- **Bandwidth:** 18.0% (volatility indicator)
- **Signal:** Within bands

## ATR (Volatility)
- **ATR:** $9.06 (5.1% of price)
- **Level:** HIGH VOLATILITY ⚠️
- **Suggested Stop-Loss:** $163.85 (1.5x ATR)

## Stochastic (14,3,3)
- **%K:** 45.7
- **%D:** 56.1
- **Signal:** Bearish

## ADX (Trend Strength)
- **ADX:** 6.5 (Weakening ↓)
- **Interpretation:** WEAK/NO TREND (range-bound) ⚠️

## 20 EMA
- **Value:** $173.40 (+2.3% from price)
- **Signal:** Price ABOVE 20 EMA (short-term bullish)

## OBV (On-Balance Volume)
- **Value:** 145.7M
- **5-Day Trend:** Rising ↑
- **Signal:** BULLISH DIVERGENCE ⚡ (accumulation)

## VWAP (20-period)
- **VWAP:** $170.84
- **Current vs VWAP:** +3.9%
- **Signal:** Price ABOVE VWAP (institutional buying)

## Fibonacci Levels (50-period)
- **Recent High:** $205.49
- **Recent Low:** $154.69
- **Next Resistance:** $180.09 (50.0%)
- **Next Support:** $174.10 (61.8%)

## Summary
- **Key Signals:** Above 50 SMA


**Fundamentals**: Sector: Basic Materials | Industry: Specialty Chemicals | Valuation: Cap: $20.37B, Fwd P/E: 19.99, P/B: 2.79, P/S: 3.96 | Growth: Rev Growth: 15.9% | Profitability: Profit Margin: -9.9%, Oper Margin: 2.3%, ROE: -4.7%, ROA: 0.3% | Dividend: 91.0% yield | Financial Health: Current Ratio: 2.23, D/E: 33.95 | Analyst Target: $189 | EPS: $-5.77 | Beta: 1.43 | 52W Range: $50.85 - $206.00

**Insider Transactions**:
# Insider Transactions for ALB
# Data retrieved on: 2026-04-09 14:24:25

## Summary
- **Insider Sentiment:** BEARISH ⚠️ (significant insider selling)
- **Award/Grant:** 1 transactions
- **Gift:** 1 transactions
- **Sale:** 1 transactions
- **Total Sales Value:** $2,012,688
- **Largest Sale (3mo):** 2026-03-10 | MASTERS JERRY KENT JR. (Chief Executive Officer) | 11783 shares | $2012688.0 | Ownership: D

## Transaction Details

Start Date,Insider,Position,Transaction,Shares,Value,Ownership
2026-04-01,WOLFF ALEJANDRO DANIEL,Director,Award/Grant,25,0.0,D
2026-03-12,MASTERS JERRY KENT JR.,Chief Executive Officer,Gift,30716,5000258.0,D
2026-03-10,MASTERS JERRY KENT JR.,Chief Executive Officer,Sale,11783,2012688.0,D


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
## Options Activity for ALB

**Available Expirations:** 13 dates
**Analyzing:** 2026-04-10, 2026-04-17, 2026-04-24

### Summary
| Metric | Calls | Puts | Put/Call Ratio |
|--------|-------|------|----------------|
| Volume | 912 | 811 | 0.889 |
| Open Interest | 8,147 | 11,518 | 1.414 |

### Sentiment Analysis
- **Volume P/C Ratio:** Neutral
- **OI P/C Ratio:** Bearish positioning

### Unusual Activity (High Volume vs Open Interest)
| Type | Expiry | Strike | Volume | OI | Vol/OI | IV |
|------|--------|--------|--------|----|---------|----|---|
| CALL | 2026-04-10 | $202.5 | 102 | 107 | 0.95x | 130.2% |
| PUT | 2026-04-17 | $175.0 | 110 | 133 | 0.83x | 52.2% |


**Upcoming Earnings**: Earnings in 27 days (2026-05-06): EPS Est $0.96, Rev Est $1,311,591,595

### HMH... [truncated]
```

### Output
```
{
  "rankings": [
    {
      "rank": 1,
      "ticker": "CSCO",
      "company_name": "Cisco Systems, Inc.",
      "current_price": 83.42,
      "strategy_match": "options_flow",
      "final_score": 85,
      "confidence": 8,
      "risk_level": "low",
      "reason": "Exceptional bullish options activity with a volume put/call ratio of 0.251 and 7 unusual call strikes detected against just 3 puts. Short-term momentum is accelerating with a fresh MACD Bullish Crossover and the price crossing above both the 20 EMA and 50 SMA ($79.21). The stock is in a confirmed strong uptrend with rising On-Balance Volume (403.2M), making this a high-probability continuation setup. Volatility is moderate (ATR 2.5%), which could limit the explosive potential, and the stock is hovering near the upper Bollinger Band, risking a mild short-term pullback.",
      "description": "Global technology leader specializing in networking, security, and cloud computing solutions."
    },
    {
      "rank": 2,
      "ticker": "HMH",
      "company_name": "HMH Holding Inc.",
      "current_price": 17.26,
      "strategy_match": "insider_buying",
      "final_score": 82,
      "confidence": 8,
      "risk_level": "high",
      "reason": "A strong insider cluster buy featuring 4 distinct insiders, led by CFO Thomas McGee's massive $1,000,000 purchase. The stock is severely oversold with an RSI of 0.0, indicating immediate short-term exhaustion of the recent downtrend. High volatility (ATR 8.6%) provides ample room for a >5% upside snapback, supported by absolute downside protection implied by the executive buying. The primary risk is the current technical downtrend; if the stock breaks below the recent low of $16.32, the oversold bounce thesis could be invalidated.",
      "description": "Provider of offshore and onshore oil and gas drilling equipment and systems."
    },
    {
      "rank": 3,
      "ticker": "SCVL",
      "company_name": "Shoe Carnival, Inc.",
      "current_price": 16.90,
      
```

---

