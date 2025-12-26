import yfinance as yf
from datetime import datetime

# Check multiple gold tickers
tickers = ['GC=F', 'GLD', 'XAUUSD=X']
print(f'Checking gold prices as of {datetime.now().strftime("%Y-%m-%d %H:%M")}')
print('='*50)

for ticker in tickers:
    try:
        data = yf.Ticker(ticker)
        hist = data.history(period='5d')
        if not hist.empty:
            latest = hist['Close'].iloc[-1]
            print(f'{ticker}: ${latest:.2f}')
    except Exception as e:
        print(f'{ticker}: Error - {e}')
