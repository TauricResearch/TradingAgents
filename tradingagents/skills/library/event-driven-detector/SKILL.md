---
name: event-driven-detector
description: Classify corporate events and distinguish confirmed facts from rumors, schedules, and unresolved risks.
roles:
  - news_analyst
triggers:
  - corporate action, regulatory filing, or capital-markets event appears
  - event timing may affect the investment case
output_schema:
  - event_type
  - status
  - materiality
  - next_verification
---

Classify events such as earnings, buybacks, shareholder changes, asset injections,
lock-up expiries, index changes, restructurings, regulatory actions, and major
contracts. Record source, date, status (confirmed, scheduled, reported, or
rumor), expected timing, and the specific economic channel.

Do not assume completion from an announcement. Highlight approval conditions,
counterparty risk, dilution, lock-up supply, and regulatory dependencies. If an
event cannot be sourced, describe it as unverified and do not use it as a core
thesis premise.
