# General
- Update untuk input coin base/quote BTCUSDT
- Perlu profile agent: current assets, current open orders, balance dalam USDT
- Outputnya tidak hanya BUY / SELL / HOLD, tapi dengan quantity juga, bentuk place order
- Explore demo account

# Per Agent
- Analyst
    - Market:
      1. Ganti get_stock_data to crypto related untuk get data coin for past n days candle per hari, kita pake Binance untuk demo account
      2. Ganti get_indicators: calculate mandiri dengan sebelumnya get_coin_data -> Binance
      3. Check prompt

    - Social
      1. Bisa pake OpenAI  as default
      2. update prompt to crypto related
      3. Next: Buat baru source news, 
      4. Greed & fear index
      5. Update prompt

    - News
      1. Use openAI for now
      2. Next ganti pake telegram
      3. Update prompt
    
    - Fundamental
      1. Pake Coingecko buat whitepaper, marketcap, fdv, global ranking, explore Coingecko
      2. Update prompt

- Researcher 
    - Update prompt

- Trader
    - Update prompt

- Risk
    - Update prompt



