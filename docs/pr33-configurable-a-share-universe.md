# PR33: Configurable A-share Research Universe

This increment adds a server-side research settings layer without changing the
legacy TradingAgents graph. Open `/settings` from the local cockpit to manage:

- concept-based watchlist sectors, initially **Game** and **AI**;
- concept-name keywords plus explicit symbol includes and excludes;
- a preferred market-data provider; and
- named, extensible research lookback periods from 1 to 3650 days.

## Tushare-first discovery

Universe discovery reads the current listed A-share catalog from `stock_basic`,
then tries the Tushare Pro `ths_index` and `ths_member` concept endpoints. It
falls back to `concept` and `concept_detail` for accounts that expose the older
concept interface. Endpoint permission errors are returned as visible settings
page errors and never clear the existing watchlist.

The default rules match game and AI-related concept names. They are deliberately
editable because vendor concept taxonomies change. Perfect World (`002624`) and
Century Huatong (`002602`) are explicit default game includes so the existing
research focus remains present if a vendor renames its concept.

Synchronization is additive: discovered company names and sector ids are merged
into `watchlist.json`; existing manual entries are preserved. The main watchlist
board displays the saved sectors. Shanghai, Shenzhen, and Beijing exchange
members are recognized, and automatic research continues to prefer Tushare Pro
for these six-digit symbols.

## API

- `GET /settings` — standalone configuration page.
- `GET /api/research-settings` — settings and credential readiness only.
- `PUT /api/research-settings` — validate and save settings.
- `POST /api/universe-preview` — discover without mutating the watchlist.
- `POST /api/universe-sync` — discover and add/merge watchlist entries.

Credentials are never part of the settings model or responses. `TUSHARE_TOKEN`
is read only inside the server process. Single-stock and batch research requests
inherit the configured provider and default lookback when a caller omits them;
the cockpit sends the selected period explicitly.
