# Koral Equities — Changelog

The original TradingAgents framework history has been preserved in [UPSTREAM_CHANGELOG.md](UPSTREAM_CHANGELOG.md). All changes below belong to the Koral Equities fork and are not upstream releases.

## Research desk branding — 22 October 2026

- Introduced a consistent Koral Equities identity across generated HTML/Markdown reports, CLI greetings, documentation and the dashboard.
- Removed vendor-specific logos and announcements from the application-facing experience, while retaining licence and contributor provenance in [UPSTREAM_ATTRIBUTION.md](UPSTREAM_ATTRIBUTION.md).
- Preserved the existing software module imports and paper-account storage; rebranding does not reset or re-create accounts.
- Audited the initial NVDA/META reports: conditional portfolio-manager entry plans are **not** implemented by the current label-to-order bridge. This limitation is flagged for a future structural risk fix, not silently masked by branding.

## Initial paper release — 21 October 2026

- Introduced an isolated £10,000 GBP paper portfolio, with 2% approximate initial risk/trade, a 6% combined risk budget, long-only next-session fills, and a sticky 10% guard on new buying.
- Built a local Koral Equities browser dashboard for account metrics, stock ratings, journal, CSV exports and scan status.
- Added market-feed validation and FX-rate safeguards, with auditable data-quality warnings.
- Added a separate, offline deterministic stock-screening candidate and a research charter. Not yet integrated into the live paper scan.
