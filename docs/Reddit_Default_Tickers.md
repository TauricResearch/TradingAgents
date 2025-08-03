# デフォルトTickerリスト定義

## 1. 人気テック銘柄
```python
POPULAR_TECH_TICKERS = [
    "AAPL",   # Apple
    "MSFT",   # Microsoft
    "NVDA",   # NVIDIA
    "GOOGL",  # Alphabet Class A
    "META",   # Meta Platforms
    "AMZN",   # Amazon
    "TSLA",   # Tesla
    "AMD",    # Advanced Micro Devices
    "INTC",   # Intel
    "NFLX",   # Netflix
    "AVGO",   # Broadcom
    "ORCL",   # Oracle
    "ADBE",   # Adobe
    "CRM",    # Salesforce
    "QCOM"    # Qualcomm
]
```

## 2. S&P500上位銘柄
```python
SP500_TOP_TICKERS = [
    "AAPL",   # Apple
    "MSFT",   # Microsoft
    "NVDA",   # NVIDIA
    "AMZN",   # Amazon
    "META",   # Meta Platforms
    "GOOGL",  # Alphabet Class A
    "GOOG",   # Alphabet Class C
    "BRK.B",  # Berkshire Hathaway Class B
    "LLY",    # Eli Lilly
    "AVGO",   # Broadcom
    "JPM",    # JPMorgan Chase
    "TSLA",   # Tesla
    "V",      # Visa
    "UNH",    # UnitedHealth
    "XOM",    # Exxon Mobil
    "MA",     # Mastercard
    "JNJ",    # Johnson & Johnson
    "WMT",    # Walmart
    "PG",     # Procter & Gamble
    "HD"      # Home Depot
]
```

## 3. 世界の主要株価指数
```python
GLOBAL_INDICES = [
    # 米国
    "SPY",    # S&P 500 ETF
    "QQQ",    # NASDAQ 100 ETF
    "DIA",    # Dow Jones ETF
    "IWM",    # Russell 2000 ETF
    
    # 日本
    "EWJ",    # iShares MSCI Japan ETF
    "NKY",    # Nikkei 225 (symbol varies by platform)
    "DXJ",    # WisdomTree Japan Hedged Equity
    "^N225",  # Nikkei 225 Index (Yahoo Finance)
    "NIKKEI", # Nikkei 225 (alternative symbol)
    
    # ヨーロッパ
    "EWG",    # iShares MSCI Germany ETF
    "EWQ",    # iShares MSCI France ETF
    "EWU",    # iShares MSCI UK ETF
    "FEZ",    # SPDR EURO STOXX 50 ETF
    
    # 新興国
    "EEM",    # iShares MSCI Emerging Markets ETF
    "FXI",    # iShares China Large-Cap ETF
    "INDA",   # iShares MSCI India ETF
    "EWZ",    # iShares MSCI Brazil ETF
    
    # セクター別
    "XLK",    # Technology Select Sector SPDR
    "XLF",    # Financial Select Sector SPDR
    "XLE",    # Energy Select Sector SPDR
    "XLV"     # Health Care Select Sector SPDR
]
```

## 4. 統合デフォルトリスト
```python
DEFAULT_TICKER_PRESETS = {
    "tech": POPULAR_TECH_TICKERS,
    "sp500": SP500_TOP_TICKERS,
    "indices": GLOBAL_INDICES,
    "all": list(set(POPULAR_TECH_TICKERS + SP500_TOP_TICKERS + GLOBAL_INDICES)),
    "quick": ["AAPL", "MSFT", "NVDA", "TSLA", "SPY"],  # クイックテスト用
}
```

## 使用例
```bash
# CLIでの選択
> Select ticker preset or enter custom:
1. Popular Tech Stocks (15 tickers)
2. S&P 500 Top 20
3. Global Indices (20 ETFs)
4. All Combined (50+ unique tickers)
5. Quick Test (5 tickers)
6. Custom (enter your own)

Select option (1-6): 
```