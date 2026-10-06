"""India data layer: NSE's public archives and filings in a local SQLite database.

    fetch    throttled, cached downloads from archives.nseindia.com
    nse      where each archive file lives and how to read it
    actions  corporate actions: NSE's purpose text, adjustment factors
    xbrl     results and shareholding-pattern XBRL (NSE and BSE share the taxonomies)
    store    the schema, idempotent writes and the point-in-time reads
    sync     the jobs `tradingagents india ...` runs
    profile  the Company page for Indian stocks (live view; not an agent tool)

Sources, as checked on 2026-10-05:

- archives.nseindia.com serves the equity list, index lists, bhavcopies (with
  ISINs from 2016), delivery files and the daily PR zip (from 2010) to a plain,
  honestly named client. These are synced automatically, one request a second.
- NSE's JSON APIs and nsearchives.nseindia.com (where results and shareholding
  XBRL live) answer only browsers; BSE's API and downloads refuse non-browser
  clients outright. Neither is fetched. Filings are saved by hand from NSE's (or
  BSE's) filing pages and imported from a folder.
- NSE's terms of use prohibit "systematic or automated data collection"; the
  archive sync runs on the user's decision to accept that for personal use.

Only ``store`` is meant for a future agent-facing vendor: its reads are point in
time and import nothing from the Company page.
"""
