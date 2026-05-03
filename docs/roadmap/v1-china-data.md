# v1 China Data: A-Share Data Source Expansion

## Status

Implemented in this workspace as a lightweight provider pass.

## Changes

- Added China A-share data providers with default policy:
  1. Yahoo Finance remains the primary source.
  2. Tushare supplements A-share data when Yahoo Finance is empty or incomplete.
  3. AkShare supplements A-share data when both Yahoo Finance and Tushare cannot provide enough data.
  4. Existing global providers remain as final fallback when applicable.
- Added ticker normalization for A-share inputs such as `000001`, `000001.SZ`, `000001SZ`, `600519`, and `688981.SH`.
- Route A-share price and fundamentals through the unified vendor adapter.
- Route Tushare statements through the unified vendor adapter when Tushare is installed and configured.
- Added configurable Yahoo Finance completeness checks for A-shares:
  - `a_share_yfinance_min_coverage_ratio`
  - `a_share_yfinance_min_rows`
  - `a_share_yfinance_min_fundamental_fields`
- Kept the implementation lightweight and avoided importing the larger TradingAgents-CN web/database stack.
- Tushare and AkShare are optional dependencies; missing SDKs produce recoverable vendor errors and fall back to existing sources.

## Configuration

- `TUSHARE_TOKEN` for Tushare.
- `TUSHARE_API_KEY` is accepted as an alias.
- AkShare should not require an API key.

## Verification

- Mocked provider tests cover Tushare success, Yahoo-primary behavior, Yahoo-incomplete supplementation, Tushare-to-AKShare fallback, non-A-share skip behavior, and hard failure when required data is unavailable.
- Live smoke tests require optional dependencies: `pip install tushare akshare`.
