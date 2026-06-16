---
type: architecture
tags:
  - opencloude-agent
  - paper-portfolio
---

# Paper Portfolio

[[PaperPortfolio]] symuluje portfel bez realnych transakcji.

## Stan początkowy

- `cash_usd = 10_000.0`
- `positions = {}`

## Operacje

### `simulate_buy(ticker, quantity, price)`

- Sprawdza, czy cena jest dodatnia.
- Ogranicza zakup do dostępnej gotówki.
- Zmniejsza gotówkę.
- Zwiększa pozycję.

### `simulate_sell(ticker, quantity, price)`

- Zmniejsza pozycję.
- Zwiększa gotówkę.
- Zwraca przychód ze sprzedaży.

### `to_dict(latest_prices=None)`

Zwraca:

- `cash_usd`
- `positions`
- `equity_usd`
- `total_value_usd`

## Linki

- [[PaperPortfolio]]
- [[Agent Loop]]
- [[Risk Evaluation]]
- [[Reporting and Persistence]]
