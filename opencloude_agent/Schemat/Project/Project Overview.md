---
type: project
tags:
  - opencloude-agent
  - project
---

# Project Overview

## Cel

`opencloude_agent` to eksperymentalny, ciągły agent paper-tradingowy, który:

1. pobiera dane rynkowe dla listy tickerów,
2. wyznacza krótkoterminowe okazje inwestycyjne,
3. symuluje decyzje kupna/trzymania bez użycia realnego kapitału,
4. zapisuje wyniki w plikach Markdown i JSONL.

Projekt jest zaprojektowany jako mały pakiet Python, bez ciężkiego frameworka backendowego.

## Zakres

- Paper trading, nie realne transakcje.
- Monitorowanie tickerów z watchlisty.
- Skanowanie momentum i względnej siły.
- Prosta kontrola ryzyka oparta o koncentrację portfela.
- Raporty w `results/continuous/`.

## Główne komponenty

- [[OpenClaudeContinuousAgent]] — koordynuje jeden cykl i pętlę ciągłą.
- [[MarketWatcher]] — pobiera dane przez `yfinance`.
- [[OpportunityScanner]] — sortuje tickery po wyniku jakości.
- [[RiskGuard]] — klasyfikuje cykl jako `safe`, `watch` albo `blocked_by_risk`.
- [[PaperPortfolio]] — symuluje gotówkę, pozycje i wartość portfela.
- [[ReportWriter]] — zapisuje logi i podsumowania.

## Ważne założenia

- Domyślna watchlista: `AAPL,MSFT,NVDA,TSLA,SPY`.
- Domyślny interwał pętli: `3600` sekund.
- Domyślny budżet papierowy: `10 000 USD`.
- Domyślna liczba kandydatów: `3`.
- Dane rynkowe pochodzą z `yfinance`.

## Linki

- [[Repository Structure]]
- [[Agent Loop]]
- [[CLI Entry Points]]
- [[Configuration and Defaults]]
