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

The checked-in `config/german_equities.example.json` is a single-instrument template; the local default registry at `~/.tradingagents/german_equities.json` currently seeds 19 verified German issuers (SAP, Rheinmetall, Allianz, Mercedes-Benz Group, Deutsche Bank, adidas, Volkswagen, BASF, Bayer, Deutsche Telekom, E.ON, Continental, Heidelberg Materials, Munich Re, Infineon, …). For each, `news_feed_url` is `null` unless an official standardized RSS/Atom endpoint was verified for that issuer — in that state the provider reports "not configured" and the explicit chain falls back to Yahoo; it does not claim that the issuer had no news. Only HTTPS RSS/Atom URLs are accepted. The same entries carry the UReg identity used by `ureg_pdmr` (`ureg_query_name` + `ureg_entity_name`, both captured live, not inferred). For each new listing, record ISIN, WKN, venue MIC, currency and each source's own symbol; do not infer instrument identity from `.DE` alone.

This adapter reads configured RSS/Atom feed entries; it does not scrape logged-in websites or attempt to turn an IR page into a feed. Issuer feed discovery/configuration remains per-company work, and current prices/fundamentals remain on existing providers pending a representative German coverage pilot.

## Alpha Vantage price fallback

`core_stock_apis` defaults to `yfinance,alpha_vantage`: Yahoo remains primary and Alpha Vantage is tried only when Yahoo reports no usable data or is unavailable. A requested latest Yahoo bar with no `Close` is now rejected to let the configured secondary provider supply a complete bar instead of presenting an earlier session as current. The TradingAgents wrapper reads `ALPHA_VANTAGE_API_KEY` from the active Hermes profile's `.env` and passes it only to the child process; it is not included in wrapper output, reports, or provenance.

The adapter first requests `TIME_SERIES_DAILY_ADJUSTED`. If Alpha Vantage explicitly reports that endpoint requires a premium entitlement, it retries with `TIME_SERIES_DAILY` and labels the result as **unadjusted**; dividends and splits are not reflected in that close series. A genuine rate-limit response does not trigger this entitlement fallback. The free daily-series response is limited to the latest 100 trading observations; older/full-history requests may still require premium access. If Yahoo returns a valid response, Alpha Vantage is not queried. For RHM, the native Alpha Vantage symbol verified through `SYMBOL_SEARCH` is `RHM.DEX` (XETRA, EUR); map that provider-specific symbol before choosing Alpha Vantage explicitly as the primary.

Because the provider does not label whether the latest daily bar is final, an unadjusted same-day bar can be incomplete during the exchange session. Do not treat it as a settled close or merge it silently with Yahoo history. Check the last observation date and session status before using it for an as-of analysis.

## Yahoo Finance / yfinance for RHM.DE

The existing Yahoo adapter supplies OHLCV history, profile fundamentals, annual/quarterly statements, technical indicators, dividends/splits, and best-effort news/insider data. The profile report additionally surfaces Yahoo's quote currency and market timestamp (UTC), shares outstanding, revenue growth, operating cash flow, cash/debt, and the available analyst consensus: mean target, the **low/high target spread with the band around the mean in percent**, median target, Yahoo's text rating, recommendation key, and covering-analyst headcount. These are live `Ticker.info` fields, not historical snapshots; the adapter withholds them for past-as-of runs. Treat analyst fields as vendor estimates, not verified forecasts, and preserve currency and timestamp. The spread block is emitted only when Yahoo supplies a mean plus at least one bound or a headcount, and it is labelled as dispersion among covering analysts — not a range of price scenarios and not per-house targets. The block stays absent (never "None") for instruments Yahoo has no consensus for.

**ETF profile (generic, keyless).** The same profile path also surfaces a fund-specific block — NAV, expense ratio (TER), YTD return, approximate AUM, inception date, distribution yield, legal type, category — for exchange-traded funds. Detection is generic: an instrument is treated as an ETF when Yahoo supplies a `navPrice` or labels it an exchange-traded fund, so it works for any listing without a hardcoded ticker list. For a plain equity those fields are null, so the block is absent (never "None"). Top holdings/positions are not provided by this vendor. A live SPY probe returned NAV/TER/AUM/inception; a live RHM.DE probe returned no ETF block.

A live RHM.DE probe showed the latest daily history bar can have OHLC/volume but a missing Close. We compared it to Yahoo's raw chart response: its daily timestamp represents the exchange-local session date, but the raw response itself had `close: null` and `adjclose: null` for that bar. Therefore the observed missing close is not caused by converting the timestamp to UTC. Indicator/history loading still excludes an unsettled bar; the routed stock-price fetch now rejects a missing requested final Close and tries Alpha Vantage, if configured. Do not replace a missing close with the current quote. yfinance's optional `repair=True` path was not verified in the project environment because its `scikit-learn` dependency is absent.

Yahoo news did not return articles tagged `RHM.DE` in the tested window. That is a Yahoo coverage gap, not evidence that Rheinmetall issued no news; the official issuer feed remains unconfigured.

## dpa and comdirect news

Die geprüften öffentlichen [dpa-Informationen](https://www.dpa.com/en) dokumentieren keine selbst bedienbare News-API, keinen MCP-Server und keinen Integrationsendpunkt. Behandle dpa-Inhalte daher als lizenzpflichtig/zugangsbeschränkt, bis Vertrieb oder Support unterstützte Lieferung (API/Feed/MCP, falls angeboten), Abdeckung, Zeitstempel, Archivtiefe, LLM-Verarbeitung, Speicherung und Weitergabe schriftlich bestätigt. Keine dpa-Zugangsdaten oder Inhalte wurden eingebunden.

Der [comdirect Informer](https://www.comdirect.de/inf/aktien/DE0007030009) zeigt eine öffentliche Rheinmetall-Unternehmensnews-Liste und eignet sich zur manuellen Gegenprüfung. Die öffentliche [comdirect REST-API](https://www.comdirect.de/cms/kontakt-zugaenge-api.html) dokumentiert Zugriff auf Kundenkonten, Depot und PostBox — keinen Wertpapier-News-Suchendpunkt — und erklärt ausdrücklich, dass es derzeit keine Schnittstelle für Wertpapierkurse gibt. Die [Nutzungsbedingungen](https://www.comdirect.de/cms/hilfe-service-nutzungsbedingungen.html) beschränken Webinformationen auf private Nutzung und nennen dpa-AFX sowie FactSet als Drittanbieter. Deshalb Informer nicht scrapen und Inhalte ohne schriftliche Erlaubnis bzw. unterstützte Schnittstelle nicht automatisiert/LLM-verarbeitet nutzen. Bei separat lizenzierter dpa-AFX-Nutzung auf Überschneidungen achten.

Für dpa oder comdirect ist keine News-Integration bzw. kein MCP konfiguriert. Für automatisierte unternehmensspezifische Meldungen ist der bestehende HTTPS-Issuer-RSS/Atom-Adapter vorzuziehen, wenn der Emittent einen dokumentierten Feed anbietet; lizenzierte allgemeine Nachrichten können getrennt bewertet werden, sobald Rechte und Schnittstelle geklärt sind.

## InvestingPro / WarrenAI

No Investing.com account data or credentials are read by this integration. A paid web subscription and an authenticated browser session do not by themselves establish API access or permission for automated collection. Use it as a manual comparison/research source until an official export/API and applicable use rights are verified. Do not store its login, session cookies, or private watchlist/portfolio data in the project or send holdings to external data providers.

## Known coverage gaps (honest limits)

Ticker-agnostic limits that remain after the adapters above; each is reported as a coverage gap in the run, never as "no news/no data":

| Input | Current state | Consequence |
|---|---|---|
| Per-house analyst targets + as-of date | Yahoo exposes only the aggregate (mean/median/low/high/headcount) plus the spread block; Finnhub's `stock/price-target` is plan-gated (403) and `stock/recommendation` is **403 for EU tickers** (verified: AAPL 200, SAP.DE/RHM.DE 403) | The agent sees dispersion but not *which* house moved; per-house calls (e.g. a downgrade) surface via news articles, not structured data |
| DE insider transactions (PDMR) | **Closed — keyless**: the `ureg_pdmr` vendor reads the Unternehmensregister capital-market search (category "Eigengeschäfte von Führungskräften", PDMR id 80) with plain `requests` (no browser/CDP). It is first in the `get_insider_transactions` chain and self-selects via the issuer registry; non-registry tickers fall through to Finnhub. See below | Structured Art. 19 MAR fields per person (position, LEI, ISIN, price/volume, dates, place) with per-emitter entity validation and point-in-time filter |
| Issuer first-party feed | `issuer_rss` is wired and authoritative when configured, but `news_feed_url` is `null` in the seed registry | Until an HTTPS feed is verified per instrument, `get_news` relies on Marketaux (EU disclosure coverage) and the optional news supplement |
| Fundamentals for EU issuers | SEC EDGAR does not serve EU filers; the statements chain falls to Yahoo's restated figures | DE fundamentals are single-vendor; reconciliation covers price data, not EU statements |
| ETF top holdings/positions | Yahoo's profile now surfaces NAV/TER/YTD/AUM/inception (generic, keyless) but **not** the holdings list | ETFs have a labelled profile block; holdings remain a manual/secondary cross-check |
| dpa / comdirect / InvestingPro | Reviewed: licensed or customer-account APIs, no self-serve endpoint | Not integrated; manual cross-check only (see above) |

## Tests

```bash
env -u PYTHONPATH .venv/bin/python -m unittest \
  tests.test_alpha_vantage_fallback_unittest \
  tests.test_european_official tests.test_issuer_rss \
  tests.test_official_source_routing tests.test_ureg_pdmr -v
```

Die `ureg_pdmr`-Tests laufen offline gegen echte UReg-Captures unter
`tests/fixtures/` (Suchseite SAP SE Seite 1 mit 30 Publikationszeilen, davon
exakt 18 PDMR/Category-80, plus deutsche und englische Detail-Fixtures derselben
Meldung) und gegen eine temporäre Registry (`tmp`-Datei, kein Netzwerk):
Extraktion/Category-Filter, Umlaut-Decode-Regressionsfall, Registry-Self-Gate
(inclusive Alias + case-insensitive), Point-in-time-Filter, Per-Emittent-Entity-
Filter, Abwesenheits-Pfade und Chain-Platzierung in `test_official_source_routing`.

## Open-source feasibility check (verified)

Ein Scan nach sicheren GitHub-Projekten, die diese Lücken ohne kostenpflichtige Abos
füllen würden, wurde gegen jede verbleibende Lücke geprüft:

| Lücke | Befund | Begründung |
|---|---|---|
| Pro-Haus-Kursziele + As-of-Datum | **Kein freies OSS** | Finnhub `stock/recommendation` ist für EU-Ticker plan-gesperrt / **403** (`AAPL`→200; `SAP.DE`, `RHM.DE`→403); kein tokenfreier Endpunkt liefert Haus-Ziele inkl. Datum |
| DE-Insider / PDMR strukturiert | **Geschlossen — kein OSS nötig** | Das Unternehmensregister selbst ist die freie Primärquelle; `ureg_pdmr` liest sie keyless per plain `requests` (Browser/CDP entbehrlich, live verifiziert). Finnhub bleibt **403 für EU-Ticker**, ist nur noch Fallback für Nicht-DE-Ticker |
| Issuer-First-Party-Feed | **Per-Listing-Arbeit** | Kein generischer Feed; RHM hat keinen verifizierten Feed; `issuer_rss` ist bereits generisch korrekt für jede Aktie mit dokumentiertem Feed |
| EU-Fundamentals | **Kein freies OSS** | SEC EDGAR = US-only; das XBRL-Register `filings.xbrl.org` enthält **keine deutschen Filings** (`country` stichprobenartig über ~6.500 Records geprüft → **DE=0**); daher helfen `brel` und `xbrl-filings-api` für DE-Aktien nicht |
| dpa / comdirect / InvestingPro | **Lizenziert/Konto** | Keine Selbstbedienungs-/freie API; manuelle Gegenprüfung bleibt |

**Eine echte Ausnahme (geschlossen):** ETF-Top-Holdings sind tokenfrei über
`yfinance.Ticker(...).funds_data.top_holdings` verfügbar — live verifiziert für
`EUNL.DE` und `IWDA.L` (Top-N-Holdings mit Name + Anteil), ohne Scraper und ohne
Paid-Abo; yfinance ist im Projekt bereits vorhanden.

## Free-tier check ("mit Anmeldung kostenfrei")

Auch mit **kostenloser Registrierung** schließt kein Anbieter die DE/EU-Lücken —
die Free-Tiers sind entweder US-only oder liefern für deutsche Symbole leer:

| Anbieter | Free-Tier-Befund | Für DE/EU-Lücke? |
|---|---|---|
| Alpha Vantage | `INCOME_STATEMENT`/`BALANCE_SHEET` für `SAP.DEX`/`RHM.DEX` → **leeres Objekt `{}`** (Key im Profil); Free-Limit nur ~25 req/Tag; Fundamentals laut Doku am stärksten für US-Ticker | Nein |
| Financial Modeling Prep | Analyst-Ratings/Kursziele nur über **TipRanks-Partnerschaft = Premium**; bezahlte Pläne laut Preisseite „US Coverage" | Nein |
| EODHD | Fundamentals nur im bezahlten Plan (§59/mo); Insider-Transactions explizit **Stocks _US_** | Nein |
| Finnhub | `stock/recommendation`, `price-target`, `insider-transactions` = Premium bzw. **403 für EU-Ticker** | Nein |
| Marketaux | Free = News-only; Market-Stats mit „entities per stat" erst ab Standard (§49); kein Haus-Kursziel/kein strukturierter PDMR | Nein |

Fazit: Die verbleibenden Lücken (Pro-Haus-Kursziele mit Datum, EU-Fundamentals) sind
Daten-Lizenz-/Region-Limits — ein kostenloses registriertes Konto hebt diese Sperren
bei keinem geprüften Anbieter auf. Der strukturierte DE-PDMR ist davon ausgenommen:
er kommt keyless aus dem Unternehmensregister (siehe `ureg_pdmr`-Sektion).

## Public / scrapeable source (verified)

Auf die Schließ-Frage „**Beides wäre dann Data-Aufwand, kein Abo**" wurden die drei
freien öffentlichen Quellen in der Reihenfolge **BaFin → EQS/DGAP → Bundesanzeiger** live geprüft
(2026-10-12). Ergebnis: **eine Lücke ist ohne Abo per Scrape tatsächlich schließbar —
die DE-Insider/PDMR-Lücke.**

**BaFin.** Die Seite „Eigengeschäfte von Führungskräften" liefert nur Metadaten/JSON-LD und
einen expliziten Verweis auf den **Primär-Speicherort: das Unternehmensregister**. Kein
selbst-bedienbarer CSV/XML/JSON-Download, keine öffentlicheSelf-Service-API.

**Unternehmensregister (Primärquelle).** `https://www.unternehmensregister.de` ist eine
Next.js-App mit `search-token`-Flow (`GET /api/search-token` → Session-Cookie → `/search`).
Die Suche in **Kapitalmarktinformationen** mit Filter „**Eigengeschäfte von Führungskräften**"
(`drilldownFilter=21`) liefert **strukturierte PDMR-Records** und je Record eine Detailseite
mit allen Art. 19 MAR-Feldern:

| Feld | Beispiel (live, SAP SE) |
|---|---|
| Person | Muhammad Alam |
| Position / Status | Vorstand |
| Emittent | SAP SE (LEI 529900D6BF99LW9R2E68) |
| ISIN | DE0007164600 |
| Art des Geschäfts | Veräußerung zur Begleichung von Steuern (Mitarbeiterbeteiligungsprogramm 'MOVE SAP') |
| Preis | 176,6431 EUR |
| Volumen | 34.485,73 EUR |
| Datum des Geschäfts | 11.09.2026 |
| Ort | INVEST BANCA – SYSTEMATIC INTERNALISER |
| Pflichtveröffentlichung | EQS Group AG, über Thomson Reuters/Bloomberg/vwd, am 14.09.2026 |

Verifiziert in einem echten (headless) Chromium und danach **reproduziert ohne Browser**:
der komplette Flow läuft mit plain `requests` (kein CDP/JS-Rendering nötig), weil die
Trefferliste das `elasticSearchDtos`-Array als RSC-Payload im SSR-HTML mitschickt und
die Detailseite einen stateless `GET /api/pub-html?payload=…`-Endpunkt bedient.
Der Vendor `ureg_pdmr` implementiert genau das (Token + `SEARCH_PARAMS`-Cookie →
`/de/suche` → RSC-Payload → `encryptedPayload` → `/api/pub-html`), ist keyless und
**ohne Browser/CDP** abrufbar. Rohdaten stammen aus EQS/DGAP-Meldungen an das Register —
lizenzfrei einsehbar.

## Unternehmensregister PDMR vendor (`ureg_pdmr`) — integrated

Die DE-Insider/Lücke ist **geschlossen**: `tradingagents/dataflows/vendors/ureg_pdmr.py`
liest die PDMR-Meldungen (Art. 19 MAR) keyless aus dem Unternehmensregister und steht
**an erster Stelle** der `get_insider_transactions`-Chain. Es ist bewusst *nur* für
deutsche Emittenten aktiv — pro Fall entschieden, nicht global:

**DE-Erkennung (Self-Gate).** Der Vendor dient nur Ticker, die in der
Issuer-Registry (`~/.tradingagents/german_equities.json`) mit einer UReg-Identität
gelistet sind. Jeder Eintrag trägt zwei Namen, getrennt nach Zweck:

- `ureg_query_name` — der Suchbegriff, der URegs fuzzy-Name-Matching zur richtigen
  Entität führt (nicht jeder Kurzname: „Siemens AG" → nur Energy-Töchter,
  „Siemens Aktiengesellschaft" → korrekt; „BMW" → 0,
  „Bayerische Motoren Werke Aktiengesellschaft" → korrekt; Holding „IFX" → 0,
  operative „Infineon Technologies AG" → alle 62 PDMR-Rows).
- `ureg_entity_name` — der exakte Name des Emittenten **im PDMR-Record**
  (`companyNameAtTimeOfPublication`), gegen den jede gefundene Zeile validiert wird.

Nicht in der Registry → `VendorNotConfiguredError` → Chain fällt zu Finnhub/Yahoo/
Alpha Vantage durch (US-Ticker wie AAPL bekommen damit unverändert die US-Quellen).
In der Registry, aber keine PDMR im Fenster → **terminale** Abwesenheits-Meldung mit
Quelle und letztem Datum — kein Fallback, weil das Register für die konfigurierte
Entität die autoritative Quelle ist („kein Eintrag" ≠ „insider-neutral").

**Abruf (plain `requests`, kein Browser).** `GET /api/search-token` →
`SEARCH_PARAMS`-Cookie (base64 der Suchparameter, inkl. `drilldownFilter=21`) →
`/de/suche` (SSR-HTML, Pagination `from/size=30`) → `elasticSearchDtos` aus dem
RSC-Payload per string-aware Bracket-Matching + `json.loads` (Umlaute bleiben intakt;
`unicode_escape` würde „Münchener" zu „MÃ¼nchener" korruptieren) → client-seitiger
Filter auf `publicationCategory.id==80` (PDMR) **und** `companyNameAtTimeOfPublication`
≈ `ureg_entity_name` (normalisiert: Umlaut-Fold, `ß→ss`, Casefold). **Wichtig:**
UReg mischt Kategorien pro Seite — Infineons PDMR-Rows liegen erst ab Seite 2,
daher endet die Paginierung nur bei fehlenden Zeilen *jeder* Kategorie, nicht bei
fehlenden PDMR-Zeilen. Details: stateless `GET /api/pub-html?payload=<encryptedPayload>`.

**Sprach-robust.** Das Register liefert dieselbe Meldung auf Deutsch *oder* Englisch
(pro Einreichung). Der Detail-Parser mappt normalisierte Labels beider Sprachen
(„a) Position/status" = „a) Position/Status", „Identification code" = „Kennung",
„Obligatory publication on" = „Pflichtveröffentlichung am"); Person- und
Emittenten-Name werden über ihre Abschnitts-Headings („Angaben zu der Person" /
„Information about the person") getrennt, nicht über Position.

**Point-in-time.** `disclosure_date` ist das Veröffentlichungsdatum
(`Pflichtveröffentlichung am`; live verifiziert identisch zur List-Zeile `sourceDate`)
und der Filter-Anchor für `as_of_date`. Alle Datumsformate (Detail `DD.MM.YYYY`,
Liste ISO) werden über `_to_iso_date` normalisiert.

**Live-Verifikation (2026-10-12):** `SAP.DE` → 25/40 Meldungen (alle Emittent „SAP SE",
DE+EN; Alam: 176,6431 EUR / 34.485,73 EUR / Geschäft 11.09.2026, ISIN DE0007164600,
LEI 529900D6BF99LW9R2E68); `IFX.DE` → 25/40 (alle „Infineon Technologies AG");
`as_of_date=2026-09-11` schließt spätere Meldungen korrekt aus; `AAPL` fällt an
Finnhub durch. Offline-Tests gegen echte Captures: `tests/test_ureg_pdmr.py`
(Suchseiten-Fixture mit 30 Zeilen, exakt 18 davon cat-80; DE- und EN-Detail-Fixtures
derselben Meldung).

**Bekannte Grenzen:** Paginierung deckt bis `MAX_PAGES=6` Seiten (180 Zeilen) ab,
Details pro Aufruf auf 25 gedeckelt (Ausgabe weist auf „showing 25 of N" hin);
die Suche ist fuzzy-namensbasiert, deshalb die doppelte Namenskodierung in der
Registry; Meldungen, die das Register nicht enthält (z. B. nicht-europäische
Meldewege), sind nicht abbildbar.

**EQS/DGAP.** `www.eqs-news.com`/`dgap.de` liefern an den geprüften Pfaden nur ein generisches
HTML-Doc, **kein öffentliches RSS/JSON** je Emittent an `…/rss/…`. Direkte Unternehmens-Feeds sind
nicht tokenfrei abrufbar; die Meldungen sind allerdings über das Unternehmensregister abgedeckt
(siehe oben).

**Bundesanzeiger.** `www.bundesanzeiger.de` nutzt dieselbe Publikations-Plattform wie das
Unternehmensregister; die Eigengeschäfte-Kategorie ist ebenfalls vorhanden.

**Fazit für die Lücken-Tabelle:**
- **DE-Insider/PDMR strukturiert** → **geschlossen** via `ureg_pdmr` (keyless,
  plain `requests`, keine Abo-/Browser-Abhängigkeit; Details in der
  `ureg_pdmr`-Sektion).
- Pro-Haus-Kursziele, Issuer-First-Party-Feed und EU-Fundamentals bleiben wie oben bestehen
  (kein freier Haus-Ziel-Endpunkt; Issuer-Feed per-Listing; DE-XBRL nicht im freien Register).

