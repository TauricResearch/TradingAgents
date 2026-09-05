# PR23: A-share Capital and Audit Event Evidence

## Purpose

PR23 extends company-specific A-share disclosures with three additional evidence types:

- dividend plans from `dividend`;
- share repurchase disclosures from `repurchase`; and
- audit opinions from `fina_audit`.

They are normalized into the existing `NewsItem` contract with disclosure-date filtering and stable endpoint-aware source identifiers.

## Availability Rules

Earnings forecast and express-report evidence keep their existing strict failure behavior. The new capital and audit endpoints are optional enhancements because Tushare permissions vary by account: an unavailable optional endpoint is omitted rather than failing the whole research run.

Returned records are still filtered to the requested announcement window and the run's `as_of_date`. Missing fields remain absent; the platform does not infer dividend yield, repurchase intent, audit severity, or trading implications.
