# German equity data: Stage 1

This is a bounded first step, not a complete German securities master or a claim of broad market coverage.

## Live official macro providers

`get_macro_indicators` routes through `official_europe,fred` by default. The official adapter supports these friendly names:

| Indicator | Source | Coverage |
|---|---|---|
| `germany_hicp` (`germany_inflation`) | Eurostat `prc_hicp_minr` | Germany, HICP annual inflation rate |
| `euro_hicp` (`euro_area_hicp`) | Eurostat `prc_hicp_minr` | Euro area HICP annual inflation rate |
| `germany_unemployment` | Eurostat `une_rt_m` | Germany, seasonally adjusted unemployment rate |
| `germany_real_gdp` (`germany_gdp`) | Eurostat `namq_10_gdp` | Germany, seasonally adjusted real GDP level |
| `euro_real_gdp` | Eurostat `namq_10_gdp` | Euro area, seasonally adjusted real GDP level |
| `ecb_deposit_rate` (`ecb_deposit_facility_rate`) | ECB Data API `FM/B.U2.EUR.4F.KR.DFR.LEV` | ECB deposit facility rate |

Unknown indicators continue to the configured FRED provider. Returned reports name the official source, series/unit, analysis window, observation date and (for Eurostat) data-update time. Eurostat historical runs use the current API vintage; historical revisions are not reconstructed as-of the original run date. Observations later than the requested date are excluded.

The integration uses public, keyless APIs: [Eurostat API](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-getting-started) and [ECB Data API](https://data.ecb.europa.eu/help/api/overview). It does not yet supply a German 10-year Bund yield series.

## Official issuer RSS/Atom feeds and instrument registry

`get_news` now tries `issuer_rss` before Yahoo. Add each instrument to `~/.tradingagents/german_equities.json` (or set `TRADINGAGENTS_ISSUER_REGISTRY` to another JSON file):

```json
{
  "schema_version": 1,
  "instruments": {
    "RHM.DE": {
      "issuer": "Rheinmetall AG",
      "isin": "DE0007030009",
      "wkn": "703000",
      "ticker": "RHM.DE",
      "mic": "XETR",
      "currency": "EUR",
      "yahoo_symbol": "RHM.DE",
      "alpha_vantage_symbol": "RHM.DEX",
      "official_ir_url": "https://www.rheinmetall.com/en/investor-relations/share/basic-information",
      "news_feed_url": null,
      "aliases": ["DE0007030009", "703000"]
    }
  }
}
```

The checked-in `config/german_equities.example.json` and local default registry currently seed Rheinmetall identity only. Its `news_feed_url` is deliberately `null`: no official standardized RSS/Atom endpoint was verified for this issuer. In that state the provider reports “not configured” and the explicit chain falls back to Yahoo; it does not claim that the issuer had no news. Only HTTPS RSS/Atom URLs are accepted. For each new listing, record ISIN, WKN, venue MIC, currency and each source's own symbol; do not infer instrument identity from `.DE` alone.

This adapter reads configured RSS/Atom feed entries; it does not scrape logged-in websites or attempt to turn an IR page into a feed. Issuer feed discovery/configuration remains per-company work, and current prices/fundamentals remain on existing providers pending a representative German coverage pilot.

## Alpha Vantage price fallback

`core_stock_apis` defaults to `yfinance,alpha_vantage`: Yahoo remains primary and Alpha Vantage is tried only when Yahoo reports no usable data or is unavailable. A requested latest Yahoo bar with no `Close` is now rejected to let the configured secondary provider supply a complete bar instead of presenting an earlier session as current. The TradingAgents wrapper reads `ALPHA_VANTAGE_API_KEY` from the active Hermes profile's `.env` and passes it only to the child process; it is not included in wrapper output, reports, or provenance.

The adapter first requests `TIME_SERIES_DAILY_ADJUSTED`. If Alpha Vantage explicitly reports that endpoint requires a premium entitlement, it retries with `TIME_SERIES_DAILY` and labels the result as **unadjusted**; dividends and splits are not reflected in that close series. A genuine rate-limit response does not trigger this entitlement fallback. The free daily-series response is limited to the latest 100 trading observations; older/full-history requests may still require premium access. If Yahoo returns a valid response, Alpha Vantage is not queried. For RHM, the native Alpha Vantage symbol verified through `SYMBOL_SEARCH` is `RHM.DEX` (XETRA, EUR); map that provider-specific symbol before choosing Alpha Vantage explicitly as the primary.

Because the provider does not label whether the latest daily bar is final, an unadjusted same-day bar can be incomplete during the exchange session. Do not treat it as a settled close or merge it silently with Yahoo history. Check the last observation date and session status before using it for an as-of analysis.

## Yahoo Finance / yfinance for RHM.DE

The existing Yahoo adapter supplies OHLCV history, profile fundamentals, annual/quarterly statements, technical indicators, dividends/splits, and best-effort news/insider data. The profile report additionally surfaces Yahoo's quote currency and market timestamp (UTC), shares outstanding, revenue growth, operating cash flow, cash/debt, and the available analyst consensus summary/mean target. These are live `Ticker.info` fields, not historical snapshots; the adapter withholds them for past-as-of runs. Treat analyst fields as vendor estimates, not verified forecasts, and preserve currency and timestamp.

A live RHM.DE probe showed the latest daily history bar can have OHLC/volume but a missing Close. We compared it to Yahoo's raw chart response: its daily timestamp represents the exchange-local session date, but the raw response itself had `close: null` and `adjclose: null` for that bar. Therefore the observed missing close is not caused by converting the timestamp to UTC. Indicator/history loading still excludes an unsettled bar; the routed stock-price fetch now rejects a missing requested final Close and tries Alpha Vantage, if configured. Do not replace a missing close with the current quote. yfinance's optional `repair=True` path was not verified in the project environment because its `scikit-learn` dependency is absent.

Yahoo news did not return articles tagged `RHM.DE` in the tested window. That is a Yahoo coverage gap, not evidence that Rheinmetall issued no news; the official issuer feed remains unconfigured.

## dpa and comdirect news

Die geprüften öffentlichen [dpa-Informationen](https://www.dpa.com/en) dokumentieren keine selbst bedienbare News-API, keinen MCP-Server und keinen Integrationsendpunkt. Behandle dpa-Inhalte daher als lizenzpflichtig/zugangsbeschränkt, bis Vertrieb oder Support unterstützte Lieferung (API/Feed/MCP, falls angeboten), Abdeckung, Zeitstempel, Archivtiefe, LLM-Verarbeitung, Speicherung und Weitergabe schriftlich bestätigt. Keine dpa-Zugangsdaten oder Inhalte wurden eingebunden.

Der [comdirect Informer](https://www.comdirect.de/inf/aktien/DE0007030009) zeigt eine öffentliche Rheinmetall-Unternehmensnews-Liste und eignet sich zur manuellen Gegenprüfung. Die öffentliche [comdirect REST-API](https://www.comdirect.de/cms/kontakt-zugaenge-api.html) dokumentiert Zugriff auf Kundenkonten, Depot und PostBox — keinen Wertpapier-News-Suchendpunkt — und erklärt ausdrücklich, dass es derzeit keine Schnittstelle für Wertpapierkurse gibt. Die [Nutzungsbedingungen](https://www.comdirect.de/cms/hilfe-service-nutzungsbedingungen.html) beschränken Webinformationen auf private Nutzung und nennen dpa-AFX sowie FactSet als Drittanbieter. Deshalb Informer nicht scrapen und Inhalte ohne schriftliche Erlaubnis bzw. unterstützte Schnittstelle nicht automatisiert/LLM-verarbeitet nutzen. Bei separat lizenzierter dpa-AFX-Nutzung auf Überschneidungen achten.

Für dpa oder comdirect ist keine News-Integration bzw. kein MCP konfiguriert. Für automatisierte unternehmensspezifische Meldungen ist der bestehende HTTPS-Issuer-RSS/Atom-Adapter vorzuziehen, wenn der Emittent einen dokumentierten Feed anbietet; lizenzierte allgemeine Nachrichten können getrennt bewertet werden, sobald Rechte und Schnittstelle geklärt sind.

## InvestingPro / WarrenAI

No Investing.com account data or credentials are read by this integration. A paid web subscription and an authenticated browser session do not by themselves establish API access or permission for automated collection. Use it as a manual comparison/research source until an official export/API and applicable use rights are verified. Do not store its login, session cookies, or private watchlist/portfolio data in the project or send holdings to external data providers.

## Tests

```bash
env -u PYTHONPATH .venv/bin/python -m unittest \
  tests.test_alpha_vantage_fallback_unittest \
  tests.test_european_official tests.test_issuer_rss \
  tests.test_official_source_routing -v
```
