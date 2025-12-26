# Trade Model Test Summary (Issue #6: DB-5)

## Overview

Comprehensive test suite for Trade model covering:
- Basic trade fields and enums
- CGT (Capital Gains Tax) calculations
- Multi-currency support
- Tax year handling (Australian FY)
- FIFO parcel matching
- Trade lifecycle management

## Test Files

### Unit Tests: `tests/unit/api/test_trade_model.py`
**65 tests** covering:

#### TestTradeBasicFields (4 tests)
- Create trade with required fields
- Default values (currency=AUD, fx_rate=1.0)
- All fields specified
- Timestamp auto-population

#### TestTradeSideEnum (3 tests)
- BUY side
- SELL side
- Invalid side rejection

#### TestTradeStatusEnum (5 tests)
- PENDING status
- FILLED status
- PARTIAL status
- CANCELLED status
- REJECTED status

#### TestTradeOrderTypeEnum (4 tests)
- MARKET order type
- LIMIT order type
- STOP order type
- STOP_LIMIT order type

#### TestTradeDecimalPrecision (7 tests)
- Quantity: Decimal(19,8) - supports crypto
- Price: Decimal(19,4)
- Total value: Decimal(19,4)
- CGT fields: Decimal(19,4)
- FX rate: Decimal(12,6)
- Signal confidence: Decimal(5,2) - range 0-100

#### TestTradeTaxYear (5 tests)
- FY2024 start (July 1, 2023)
- FY2024 end (June 30, 2024)
- FY2025 start (July 1, 2024)
- Before FY transition (June)
- After FY transition (July)

#### TestTradeCGTDiscount (4 tests)
- Not eligible: <367 days
- Eligible: exactly 367 days
- Eligible: >367 days
- Boundary: 366 days (not eligible)

#### TestTradeCGTCalculations (4 tests)
- Gross gain calculation
- Gross loss calculation
- Net gain with 50% discount
- Breakeven (no gain/loss)

#### TestTradeCurrencySupport (4 tests)
- Default AUD currency
- USD with FX rate conversion
- Common currency codes
- Currency uppercase enforcement

#### TestTradeConstraints (7 tests)
- Quantity must be > 0
- Quantity cannot be zero
- Price must be > 0
- Price cannot be zero
- Signal confidence: 0-100 range
- Signal confidence: >100 rejected
- Signal confidence: negative rejected

#### TestTradeSignalFields (3 tests)
- Signal source stored
- Signal confidence stored
- Signal fields optional

#### TestTradeProperties (4 tests)
- is_buy property (True for BUY)
- is_sell property (True for SELL)
- is_filled property (True for FILLED)
- is_filled False for PENDING

#### TestTradePortfolioRelationship (3 tests)
- Trade belongs to portfolio
- Portfolio has many trades
- Cascade delete with portfolio

#### TestTradeEdgeCases (6 tests)
- Very long symbol names
- Fractional shares (0.5)
- Very small quantities (crypto satoshis)
- Very large quantities (millions)
- Trade repr()

#### TestTradeQueryOperations (4 tests)
- Query by ID
- Filter by symbol
- Filter by side (BUY/SELL)
- Filter by status

### Integration Tests: `tests/integration/api/test_trade_integration.py`
**22 tests** covering:

#### TestTradePortfolioIntegration (4 tests)
- Create trade for portfolio
- Portfolio with multiple trades
- Cascade delete trades
- Multiple portfolios isolation

#### TestTradeCGTEndToEnd (3 tests)
- Simple buy-sell workflow
- Long-term hold with CGT discount
- Capital loss scenario

#### TestTradeFIFOMatching (3 tests)
- Single parcel full sale
- Multiple parcels - oldest first
- Partial parcel matching across buys

#### TestTradeMultiCurrency (3 tests)
- Foreign stock with FX conversion
- FX gain/loss in CGT calculation
- Mixed currency portfolio

#### TestTradeComplexQueries (5 tests)
- Aggregate position by symbol
- Query by tax year
- CGT discount eligibility filter
- Total CGT for year
- Order by date/value

#### TestTradeLifecycle (3 tests)
- Status progression (PENDING→PARTIAL→FILLED)
- Cancel pending order
- Reject invalid order

#### TestTradeReporting (2 tests)
- Portfolio performance metrics
- Symbol trading history

## Test Statistics

- **Total Tests**: 87 (65 unit + 22 integration)
- **All Tests**: SKIPPED (RED phase - implementation pending)
- **Expected Coverage**: 80%+ when implemented

## Key Test Patterns

### 1. TDD RED Phase
```python
try:
    from spektiv.api.models.trade import Trade, TradeSide
    # Test implementation
except ImportError:
    pytest.skip("Trade model not yet implemented (TDD RED phase)")
```

### 2. Async Database Operations
```python
@pytest.mark.asyncio
async def test_create_trade(db_session, test_portfolio):
    trade = Trade(portfolio_id=test_portfolio.id, ...)
    db_session.add(trade)
    await db_session.commit()
    await db_session.refresh(trade)
```

### 3. Foreign Key Storage Pattern
```python
# Store foreign keys BEFORE async operations
portfolio_id = test_portfolio.id
# ... async operations ...
# Use stored ID to avoid lazy load after rollback
```

### 4. Constraint Testing
```python
with pytest.raises((IntegrityError, ValueError)):
    trade = Trade(quantity=Decimal("-100"))  # Invalid
    await db_session.commit()
```

## Model Requirements (From Tests)

### Enums
```python
class TradeSide(Enum):
    BUY = "BUY"
    SELL = "SELL"

class TradeStatus(Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"

class TradeOrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"
```

### Required Fields
- portfolio_id (ForeignKey)
- symbol (String)
- side (TradeSide enum)
- quantity (Decimal(19,8))
- price (Decimal(19,4))
- order_type (TradeOrderType enum)
- status (TradeStatus enum)
- executed_at (DateTime, nullable for pending)

### Optional Fields
- total_value (Decimal(19,4))
- signal_source (String, nullable)
- signal_confidence (Decimal(5,2), 0-100 range, nullable)
- acquisition_date (Date, nullable)
- cost_basis_per_unit (Decimal(19,4), nullable)
- cost_basis_total (Decimal(19,4), nullable)
- holding_period_days (Integer, nullable)
- cgt_discount_eligible (Boolean, nullable)
- cgt_gross_gain (Decimal(19,4), nullable)
- cgt_gross_loss (Decimal(19,4), nullable)
- cgt_net_gain (Decimal(19,4), nullable)
- currency (String(3), default="AUD")
- fx_rate_to_aud (Decimal(12,6), default=1.0)
- total_value_aud (Decimal(19,4), nullable)

### Properties
- tax_year: String - Calculated from executed_at (Australian FY)
- is_buy: Boolean - True if side == BUY
- is_sell: Boolean - True if side == SELL
- is_filled: Boolean - True if status == FILLED

### Constraints
- quantity > 0
- price > 0
- signal_confidence: 0 <= value <= 100 (when not null)
- currency: uppercase, 3 letters

### Relationships
- portfolio: Many-to-One with Portfolio
  - Cascade delete: trades deleted when portfolio deleted
  - Back-populates: portfolio.trades

## Australian Tax Year Calculation

```python
# FY2024 = July 1, 2023 to June 30, 2024
if executed_at.month >= 7:
    fy_year = executed_at.year + 1
else:
    fy_year = executed_at.year

tax_year = f"FY{fy_year}"
```

## CGT Discount Eligibility

- **Eligible**: holding_period_days >= 367
- **Discount**: 50% of gross gain
- **Formula**: net_gain = gross_gain * 0.5 if eligible else gross_gain

## FIFO Matching Rules

1. Sell trades matched to oldest buy (by acquisition_date)
2. Partial parcel matching supported
3. Weighted average cost basis for multi-parcel sales
4. Holding period calculated from earliest acquisition

## Multi-Currency Support

- All trades stored in original currency
- FX rate at execution time stored
- AUD equivalent calculated for reporting
- CGT calculated in AUD (tax reporting currency)

## Next Steps (Implementation Phase)

1. Create `spektiv/api/models/trade.py`
2. Define enums (TradeSide, TradeStatus, TradeOrderType)
3. Create Trade model with all fields
4. Add check constraints
5. Add properties (tax_year, is_buy, is_sell, is_filled)
6. Add relationship to Portfolio
7. Create migration: `alembic revision --autogenerate -m "Add Trade model"`
8. Run tests: `pytest tests/unit/api/test_trade_model.py -v`
9. Run integration tests: `pytest tests/integration/api/test_trade_integration.py -v`
10. Verify 80%+ coverage

## Test Execution

```bash
# Run all trade tests
pytest tests/unit/api/test_trade_model.py tests/integration/api/test_trade_integration.py -v

# Run with coverage
pytest tests/unit/api/test_trade_model.py tests/integration/api/test_trade_integration.py --cov=spektiv/api/models/trade --cov-report=term-missing

# Run specific test class
pytest tests/unit/api/test_trade_model.py::TestTradeCGTCalculations -v

# Run with minimal verbosity (avoid pipe deadlock)
pytest tests/unit/api/test_trade_model.py --tb=line -q
```

## Coverage Goals

- **Unit Tests**: Basic CRUD, enums, constraints, properties
- **Integration Tests**: Relationships, CGT workflows, FIFO, multi-currency
- **Edge Cases**: Fractional shares, crypto quantities, long symbols
- **Boundary Tests**: CGT discount threshold (367 days), signal confidence (0-100)

## Related Issues

- **Issue #4 (DB-3)**: Portfolio model - parent relationship
- **Issue #6 (DB-5)**: Trade model - this test suite
- **Issue #7 (DB-6)**: Position model - will use trade data
- **Issue #8 (DB-7)**: Tax report - will aggregate CGT data

---

**Status**: ✅ Tests Complete (RED phase)
**Created**: 2025-12-26
**Tests**: 87 total (65 unit + 22 integration)
**Coverage**: Comprehensive (all requirements from spec)
