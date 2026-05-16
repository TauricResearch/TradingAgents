"""Shared services for the TradingAgents Desktop feedback loop.

Services are stateless singletons (created once, used by all pages).
Each service owns one concern:

- ``recommendation_extractor`` — extract structured data from markdown
- ``price_service`` — per-ticker yfinance with TTL cache
- ``alert_engine`` — background polling + desktop notifications
- ``outcome_tracker`` — automated recommendation accuracy tracking
- ``scheduler`` — cron-style timer scheduler for pre-market automation
- ``pdf_export`` — markdown → HTML → PDF pipeline
- ``email_service`` — SMTP send with attachment
"""
