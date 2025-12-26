# Trade Model Test Reference Card

## Quick Stats
- **Total Tests**: 87
- **Unit Tests**: 65 (in `tests/unit/api/test_trade_model.py`)
- **Integration Tests**: 22 (in `tests/integration/api/test_trade_integration.py`)
- **Status**: All SKIPPED (TDD RED phase - awaiting implementation)

## Test Organization

### Unit Tests (65)
| Class | Tests | Coverage |
|-------|-------|----------|
| TestTradeBasicFields | 4 | CRUD, defaults, timestamps |
| TestTradeSideEnum | 3 | BUY/SELL validation |
| TestTradeStatusEnum | 5 | All status values |
| TestTradeOrderTypeEnum | 4 | MARKET/LIMIT/STOP/STOP_LIMIT |
| TestTradeDecimalPrecision | 7 | Quantity(19,8), Price(19,4), CGT fields |
| TestTradeTaxYear | 5 | Australian FY (July-June) |
| TestTradeCGTDiscount | 4 | 367+ days eligibility |
| TestTradeCGTCalculations | 4 | Gross gain/loss, net gain |
| TestTradeCurrencySupport | 4 | Multi-currency, FX rates |
| TestTradeConstraints | 7 | quantity>0, price>0, confidence 0-100 |
| TestTradeSignalFields | 3 | signal_source, signal_confidence |
| TestTradeProperties | 4 | is_buy, is_sell, is_filled |
| TestTradePortfolioRelationship | 3 | belongs_to, cascade delete |
| TestTradeEdgeCases | 6 | Fractional shares, crypto, edge cases |
| TestTradeQueryOperations | 4 | Query by ID, symbol, side, status |

### Integration Tests (22)
| Class | Tests | Coverage |
|-------|-------|----------|
| TestTradePortfolioIntegration | 4 | Portfolio relationships |
| TestTradeCGTEndToEnd | 3 | Full buy-sell lifecycle |
| TestTradeFIFOMatching | 3 | FIFO parcel matching |
| TestTradeMultiCurrency | 3 | Foreign assets, FX |
| TestTradeComplexQueries | 5 | Aggregations, tax year queries |
| TestTradeLifecycle | 3 | Status transitions |
| TestTradeReporting | 2 | Performance, history |

## Key Test Commands

```bash
# Run all trade tests
pytest tests/unit/api/test_trade_model.py tests/integration/api/test_trade_integration.py -v

# Run with minimal verbosity (recommended)
pytest tests/unit/api/test_trade_model.py tests/integration/api/test_trade_integration.py --tb=line -q

# Run unit tests only
pytest tests/unit/api/test_trade_model.py -v

# Run integration tests only
pytest tests/integration/api/test_trade_integration.py -v

# Run specific test class
pytest tests/unit/api/test_trade_model.py::TestTradeCGTCalculations -v

# Run with coverage
pytest tests/unit/api/test_trade_model.py --cov=spektiv.api.models.trade --cov-report=term-missing

# Count tests
pytest tests/unit/api/test_trade_model.py tests/integration/api/test_trade_integration.py --collect-only -q
```

## Model Fields (from tests)

### Core Fields
- `portfolio_id`: ForeignKey → Portfolio
- `symbol`: String(50)
- `side`: Enum (BUY, SELL)
- `quantity`: Decimal(19,8) - supports crypto
- `price`: Decimal(19,4)
- `total_value`: Decimal(19,4)
- `order_type`: Enum (MARKET, LIMIT, STOP, STOP_LIMIT)
- `status`: Enum (PENDING, FILLED, PARTIAL, CANCELLED, REJECTED)
- `executed_at`: DateTime (nullable for pending)

### Signal Fields
- `signal_source`: String (nullable)
- `signal_confidence`: Decimal(5,2), 0-100 range (nullable)

### CGT Fields
- `acquisition_date`: Date (nullable)
- `cost_basis_per_unit`: Decimal(19,4) (nullable)
- `cost_basis_total`: Decimal(19,4) (nullable)
- `holding_period_days`: Integer (nullable)
- `cgt_discount_eligible`: Boolean (nullable)
- `cgt_gross_gain`: Decimal(19,4) (nullable)
- `cgt_gross_loss`: Decimal(19,4) (nullable)
- `cgt_net_gain`: Decimal(19,4) (nullable)

### Currency Fields
- `currency`: String(3), default="AUD"
- `fx_rate_to_aud`: Decimal(12,6), default=1.0
- `total_value_aud`: Decimal(19,4) (nullable)

### Properties
- `tax_year`: String - Australian FY (July-June)
- `is_buy`: Boolean - side == BUY
- `is_sell`: Boolean - side == SELL
- `is_filled`: Boolean - status == FILLED

## Business Rules (tested)

### CGT Discount
- **Eligible**: holding_period_days >= 367
- **Discount**: 50% of gross_gain
- **Application**: net_gain = gross_gain * 0.5

### Tax Year (Australian)
```python
# FY starts July 1, ends June 30
if month >= 7:
    fy_year = year + 1  # July 2023 → FY2024
else:
    fy_year = year      # June 2024 → FY2024
```

### FIFO Matching
1. Sells matched to oldest buys first
2. By `acquisition_date` ascending
3. Weighted average for multi-parcel sales

### Constraints
- ✓ quantity > 0
- ✓ price > 0
- ✓ 0 <= signal_confidence <= 100
- ✓ currency uppercase, 3 chars
- ✓ cascade delete with portfolio

## Test Fixtures Used

From `tests/api/conftest.py`:
- `db_session`: Async SQLAlchemy session
- `test_portfolio`: Test portfolio instance
- `test_user`: Portfolio owner
- `another_user`: For isolation tests

## Expected Test Results (after implementation)

```
tests/unit/api/test_trade_model.py::TestTradeBasicFields::test_create_trade_with_required_fields PASSED
tests/unit/api/test_trade_model.py::TestTradeBasicFields::test_trade_defaults PASSED
...
tests/integration/api/test_trade_integration.py::TestTradePortfolioIntegration::test_create_trade_for_portfolio PASSED
...

========================= 87 passed in 5.23s =========================
Coverage: 85%+ target
```

## Implementation Checklist

- [ ] Create `spektiv/api/models/trade.py`
- [ ] Define enums (TradeSide, TradeStatus, TradeOrderType)
- [ ] Create Trade model class
- [ ] Add decimal fields with correct precision
- [ ] Add check constraints
- [ ] Add properties (tax_year, is_buy, is_sell, is_filled)
- [ ] Add Portfolio relationship
- [ ] Create Alembic migration
- [ ] Run unit tests
- [ ] Run integration tests
- [ ] Verify 80%+ coverage

## Related Files

- Tests: `tests/unit/api/test_trade_model.py`
- Tests: `tests/integration/api/test_trade_integration.py`
- Summary: `tests/unit/api/TEST_TRADE_SUMMARY.md`
- Model: `spektiv/api/models/trade.py` (to be created)
- Migration: `alembic/versions/*_add_trade_model.py` (to be created)

---

**Created**: 2025-12-26
**Issue**: #6 (DB-5)
**TDD Phase**: RED (all 87 tests skipped, awaiting implementation)
