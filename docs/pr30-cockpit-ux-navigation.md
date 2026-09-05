# PR30: Cockpit UX Navigation

## Purpose

PR30 reorganizes the local research cockpit around user tasks instead of
rendering every available artifact in one continuous page. It changes only the
HTML, CSS, and browser interaction layer in `cockpit.py`; APIs, artifact
contracts, research jobs, risk rules, and legacy TradingAgents code are
unchanged.

## Five views

- **Research overview**: price summary, opportunity radar, recent changes, data
  health, chart, company profile, watchlist, and collapsed readiness details.
- **Game business**: operating entities, catalysts, product matrix, and exact
  company-linked approvals.
- **Financial valuation**: latest valuation, financial health, historical
  valuation range, financial quality, and disclosed trends.
- **Research report**: structured research, company events, archived runs,
  report coverage, and a collapsed full Markdown report.
- **Decision review**: manual decision draft, deterministic risk result,
  backtest, and decision journal.

The selected symbol and view are stored in the query string, for example
`?symbol=002602&view=financials`. Reloading the page preserves that context.

## Command hierarchy

The header keeps two frequent commands visible:

- update every saved watchlist symbol;
- research the currently selected symbol.

Add, remove, and local-cache reload actions live in the watchlist management
menu. Removing a symbol requires confirmation. Disabled decision-journal
actions explain which prerequisite is missing.

## Readability and performance

- Primary navigation and common labels are Chinese-first.
- Common status values are translated at render time without changing backend
  enum values.
- Market values and financial statements use `亿元` / `万元` formatting.
- Valuation values are rounded consistently.
- Research readiness and full report content start collapsed.
- Full Markdown is fetched only when its disclosure is opened.

## Responsive behavior

Desktop views use two columns only for comparable content. At narrower widths,
sections become single-column, command controls form a stable grid, and the
view tabs scroll horizontally. Tables retain their own horizontal scroll rather
than widening the page.

## Verification

Automated tests assert the five views, command hierarchy, collapsed details,
unique render targets, API behavior, and existing cockpit workflows. Browser
checks cover desktop and mobile widths, view persistence, report lazy loading,
horizontal overflow, and console errors.
