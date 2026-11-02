"""India market identity primitives avoid implicit exchange guesses."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from tradingagents.dataflows.india import (
    AmbiguousInstrumentError,
    UnknownInstrumentError,
    load_nifty500_universe,
    normalize_indian_symbol,
)
from tradingagents.dataflows.india.calendar import CalendarCoverageError, IndianExchangeCalendar
from tradingagents.dataflows.india.provenance import (
    ConflictingProviderDataError,
    DataProvenance,
    LookAheadDataError,
    MarketQuote,
    StaleMarketDataError,
    select_single_provider_quote,
)
from tradingagents.dataflows.india.providers import IndiaProviderRegistry, IndianMarketDataProvider
from tradingagents.dataflows.symbols import normalize_symbol, safe_ticker_component


@pytest.mark.unit
@pytest.mark.parametrize(
    "ticker,exchange,expected",
    [
        ("reliance", "NSE", "RELIANCE.NS"),
        ("500325", "BSE", "500325.BO"),
        ("RELIANCE.NS", "NSE", "RELIANCE.NS"),
        ("reliance.bo", None, "RELIANCE.BO"),
    ],
)
def test_indian_symbol_normalization(ticker, exchange, expected):
    assert normalize_indian_symbol(ticker, exchange) == expected


@pytest.mark.unit
def test_generic_normalization_never_guesses_an_indian_exchange():
    assert normalize_symbol("reliance") == "RELIANCE"
    assert normalize_symbol("ABC+") == "ABC"
    assert normalize_symbol("reliance", "NSE") == "RELIANCE.NS"
    assert normalize_symbol("reliance", "BSE") == "RELIANCE.BO"
    assert normalize_symbol("ABC+", "NSE") == "ABC.NS"


@pytest.mark.unit
@pytest.mark.parametrize(
    "ticker,exchange",
    [("RELIANCE", None), ("RELIANCE.NS", "BSE"), ("RELIANCE", "NFO")],
)
def test_indian_symbol_requires_unambiguous_exchange(ticker, exchange):
    with pytest.raises(ValueError):
        normalize_indian_symbol(ticker, exchange)


@pytest.mark.unit
@pytest.mark.parametrize("ticker", ["../ABC", "ABC/DEF", "-ABC", "ABC_"])
def test_indian_symbol_rejects_unsafe_or_invalid_ticker_syntax(ticker):
    with pytest.raises(ValueError, match="ticker syntax"):
        normalize_indian_symbol(ticker, "NSE")


@pytest.mark.unit
def test_indian_symbol_accepts_exchange_tickers_with_documented_characters():
    assert normalize_indian_symbol("M&M", "NSE") == "M&M.NS"
    assert safe_ticker_component("M&M.NS") == "M&M.NS"
    max_base = "A" * 29
    assert safe_ticker_component(normalize_indian_symbol(max_base, "NSE")) == f"{max_base}.NS"
    with pytest.raises(ValueError, match="ticker syntax"):
        normalize_indian_symbol("A" * 30, "NSE")


@pytest.mark.unit
def test_csv_universe_resolves_ticker_exchange_and_isin(tmp_path):
    csv_path = tmp_path / "constituents.csv"
    csv_path.write_text(
        "symbol,exchange,company_name,isin,sector\n"
        "ACME,NSE,Acme Limited,INE002A01018,Industrials\n"
        "ACME,BSE,Acme Limited,INE002A01018,Industrials\n",
        encoding="utf-8",
    )
    universe = load_nifty500_universe(
        csv_path, data_source="verified constituent file", last_updated="2026-10-30"
    )

    assert universe.data_source == "verified constituent file"
    assert str(universe.last_updated) == "2026-10-30"
    assert universe.resolve("ACME", "NSE").symbol == "ACME.NS"
    assert universe.resolve("ACME.BO").exchange == "BSE"
    assert universe.resolve("INE002A01018", "BSE").symbol == "ACME.BO"
    with pytest.raises(AmbiguousInstrumentError):
        universe.resolve("ACME")
    with pytest.raises(AmbiguousInstrumentError):
        universe.resolve("INE002A01018")
    with pytest.raises(UnknownInstrumentError):
        universe.resolve("NOT-LISTED", "NSE")


@pytest.mark.unit
def test_csv_universe_requires_source_and_date_metadata(tmp_path):
    csv_path = tmp_path / "constituents.csv"
    csv_path.write_text("symbol,exchange\nACME,NSE\n", encoding="utf-8")
    with pytest.raises(ValueError, match="data_source"):
        load_nifty500_universe(csv_path, data_source="", last_updated="2026-10-30")
    with pytest.raises(ValueError, match="last_updated"):
        load_nifty500_universe(csv_path, data_source="source", last_updated="unknown")
    with pytest.raises(ValueError, match="date, not a datetime"):
        load_nifty500_universe(
            csv_path, data_source="source", last_updated=datetime.now(timezone.utc)
        )


@pytest.mark.unit
@pytest.mark.parametrize("isin", ["US002A01018", "INE002A01019", "IN123"])
def test_csv_universe_rejects_non_indian_or_invalid_isin(tmp_path, isin):
    csv_path = tmp_path / "constituents.csv"
    csv_path.write_text(f"symbol,exchange,isin\nACME,NSE,{isin}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid Indian ISIN"):
        load_nifty500_universe(csv_path, data_source="source", last_updated="2026-10-30")


@pytest.mark.unit
def test_universe_does_not_invent_membership(tmp_path):
    csv_path = tmp_path / "empty.csv"
    csv_path.write_text("symbol,exchange\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no constituent rows"):
        load_nifty500_universe(csv_path, data_source="source", last_updated="2026-10-30")


@pytest.mark.unit
def test_universe_direct_construction_validates_exchange_and_date_types():
    from tradingagents.dataflows.india.universe import IndianConstituent, IndianMarketUniverse

    with pytest.raises(ValueError, match="date, not a datetime"):
        IndianMarketUniverse((), "source", datetime.now(timezone.utc))
    with pytest.raises(ValueError, match="exchange must be NSE or BSE"):
        IndianMarketUniverse(
            (IndianConstituent("ACME.NS", "nse"),), "source", datetime.now().date()
        )


@pytest.mark.unit
def test_indian_calendar_uses_weekends_and_exchange_local_session_times():
    calendar = IndianExchangeCalendar("NSE")
    bounds = calendar.session_bounds("2026-11-02")

    assert calendar.holiday_data_status == "weekends_only_unverified"
    assert bounds[0].isoformat() == "2026-11-02T09:15:00+05:30"
    assert bounds[1].isoformat() == "2026-11-02T15:30:00+05:30"
    assert calendar.is_session("2026-11-02")
    assert not calendar.is_session("2026-11-01")
    assert calendar.is_open(bounds[0])
    assert not calendar.is_open(bounds[1])


@pytest.mark.unit
def test_indian_calendar_holidays_are_supplied_and_explicitly_verified():
    unverified = IndianExchangeCalendar("BSE", holidays=("2026-11-03",))
    verified = IndianExchangeCalendar(
        "BSE",
        holidays=("2026-11-03",),
        holiday_source="exchange holiday schedule",
        last_updated="2026-10-30",
        holidays_verified=True,
        holiday_verified_by="reviewer",
        coverage_start="2026-01-01",
        coverage_end="2026-12-31",
    )

    assert not unverified.is_session("2026-11-03")
    assert unverified.holiday_data_status == "unverified"
    assert verified.holiday_data_status == "verified"
    with pytest.raises(ValueError, match="source, last_updated, verifier, and coverage"):
        IndianExchangeCalendar("NSE", holidays=("2026-11-03",), holidays_verified=True)
    with pytest.raises(CalendarCoverageError, match="outside BSE calendar coverage"):
        verified.is_session("2027-01-01")


@pytest.mark.unit
def test_calendar_loads_exchange_specific_verified_holidays_from_csv(tmp_path):
    csv_path = tmp_path / "exchange_holidays.csv"
    csv_path.write_text(
        "exchange,date,source,verified_on,verified_by,verification_status,"
        "coverage_start,coverage_end\n"
        "NSE,2026-11-03,NSE schedule,2026-10-30,analyst,verified,"
        "2026-01-01,2026-12-31\n"
        "BSE,2026-11-04,BSE schedule,2026-10-31,reviewer,verified,"
        "2026-01-01,2026-12-31\n",
        encoding="utf-8",
    )

    nse = IndianExchangeCalendar.from_csv("NSE", csv_path)
    bse = IndianExchangeCalendar.from_csv("BSE", csv_path)
    assert nse.holiday_source == "NSE schedule"
    assert nse.last_updated.isoformat() == "2026-10-30"
    assert nse.holiday_verified_by == "analyst"
    assert nse.coverage_start.isoformat() == "2026-01-01"
    assert nse.coverage_end.isoformat() == "2026-12-31"
    assert not nse.is_session("2026-11-03")
    assert bse.is_session("2026-11-03")
    assert not bse.is_session("2026-11-04")
    with pytest.raises(CalendarCoverageError):
        nse.session_bounds("2027-01-01")


@pytest.mark.unit
def test_calendar_rejects_unverified_or_missing_exchange_file_data(tmp_path):
    csv_path = tmp_path / "exchange_holidays.csv"
    csv_path.write_text(
        "exchange,date,source,verified_on,verified_by,verification_status,"
        "coverage_start,coverage_end\n"
        "NSE,2026-11-03,schedule,2026-10-30,reviewer,unverified,"
        "2026-01-01,2026-12-31\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="not marked verified"):
        IndianExchangeCalendar.from_csv("NSE", csv_path)
    with pytest.raises(ValueError, match="no rows for BSE"):
        IndianExchangeCalendar.from_csv("BSE", csv_path)


@pytest.mark.unit
def test_calendar_converts_aware_timestamps_to_india_before_extracting_date():
    calendar = IndianExchangeCalendar("NSE", holidays=("2026-11-03",))
    utc_evening = datetime(2026, 11, 2, 20, tzinfo=timezone.utc)
    assert not calendar.is_session(utc_evening)


@pytest.mark.unit
def test_calendar_rejects_future_verified_dates_and_invalid_direct_metadata():
    india_today = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Kolkata")).date()
    future_date = (india_today + timedelta(days=1)).isoformat()
    with pytest.raises(ValueError, match="verified_on cannot be in the future"):
        IndianExchangeCalendar(
            "NSE",
            holidays=("2026-11-03",),
            holiday_source="source",
            last_updated=future_date,
            holidays_verified=True,
            holiday_verified_by="reviewer",
            coverage_start="2026-01-01",
            coverage_end="2026-12-31",
        )
    with pytest.raises(ValueError, match="coverage_start must not be after coverage_end"):
        IndianExchangeCalendar("BSE", coverage_start="2026-12-31", coverage_end="2026-01-01")
    with pytest.raises(ValueError, match="exchange must be NSE or BSE"):
        IndianExchangeCalendar(None)


@pytest.mark.unit
def test_verified_calendar_can_represent_holiday_free_coverage(tmp_path):
    csv_path = tmp_path / "holiday_free.csv"
    csv_path.write_text(
        "exchange,date,source,verified_on,verified_by,verification_status,"
        "coverage_start,coverage_end\n"
        "NSE,,exchange schedule,2026-10-30,reviewer,verified,"
        "2026-01-01,2026-12-31\n",
        encoding="utf-8",
    )
    calendar = IndianExchangeCalendar.from_csv("NSE", csv_path)
    assert calendar.holiday_data_status == "verified"
    assert calendar.is_session("2026-04-15")


def _quote(provider, value):
    retrieval = datetime.now(timezone.utc)
    return MarketQuote(
        value,
        DataProvenance(
            provider=provider,
            symbol="ACME.NS",
            exchange="NSE",
            retrieval_timestamp=retrieval,
            market_timestamp=retrieval - timedelta(seconds=2),
            currency="INR",
            data_quality="provider-reported",
            publication_timestamp=retrieval - timedelta(seconds=1),
        ),
    )


@pytest.mark.unit
def test_quote_provenance_is_timezone_normalized_and_sources_are_not_merged():
    yahoo_quote = _quote("yahoo", "123.45")
    av_quote = _quote("alpha_vantage", "123.46")

    assert yahoo_quote.provenance.retrieval_timestamp.tzinfo is timezone.utc
    as_of = datetime.now(timezone.utc)
    assert select_single_provider_quote(
        [yahoo_quote], as_of=as_of, max_age=timedelta(minutes=1)
    ) is yahoo_quote
    assert select_single_provider_quote(
        [yahoo_quote, av_quote],
        provider="yahoo",
        as_of=as_of,
        max_age=timedelta(minutes=1),
    ) is yahoo_quote
    with pytest.raises(ConflictingProviderDataError):
        select_single_provider_quote(
            [yahoo_quote, av_quote], as_of=as_of, max_age=timedelta(minutes=1)
        )
    with pytest.raises(TypeError, match="as_of"):
        select_single_provider_quote([yahoo_quote], max_age=timedelta(minutes=1))


@pytest.mark.unit
def test_quote_provenance_rejects_naive_timestamps_and_non_finite_values():
    with pytest.raises(ValueError, match="timezone-aware"):
        DataProvenance(
            "provider", "ACME.NS", "NSE", datetime.now(), None, "INR", "unknown"
        )
    with pytest.raises(ValueError, match="finite"):
        MarketQuote("NaN", _quote("yahoo", "1").provenance)
    with pytest.raises(ValueError, match="exchange must be NSE, BSE, or None"):
        DataProvenance(
            "provider", "ACME.NS", "NYSE", datetime.now(timezone.utc), None, "INR", "unknown"
        )
    with pytest.raises(TypeError, match="provenance must be a DataProvenance"):
        MarketQuote("1", None)


@pytest.mark.unit
def test_provenance_rejects_future_or_out_of_order_timestamps():
    now = datetime.now(timezone.utc)
    common = dict(provider="test", symbol="ACME.NS", exchange="NSE", currency="INR", data_quality="ok")
    with pytest.raises(ValueError, match="retrieval_timestamp cannot be in the future"):
        DataProvenance(**common, retrieval_timestamp=now + timedelta(minutes=1), market_timestamp=None)
    with pytest.raises(ValueError, match="market_timestamp cannot be after retrieval_timestamp"):
        DataProvenance(
            **common,
            retrieval_timestamp=now - timedelta(minutes=1),
            market_timestamp=now,
        )
    with pytest.raises(ValueError, match="publication_timestamp cannot be after retrieval_timestamp"):
        DataProvenance(
            **common,
            retrieval_timestamp=now - timedelta(minutes=1),
            market_timestamp=None,
            publication_timestamp=now,
        )
    with pytest.raises(ValueError, match="publication_timestamp cannot precede market_timestamp"):
        DataProvenance(
            **common,
            retrieval_timestamp=now,
            market_timestamp=now - timedelta(minutes=1),
            publication_timestamp=now - timedelta(minutes=2),
        )


@pytest.mark.unit
def test_quote_detects_staleness_and_fails_closed_without_market_timestamp():
    now = datetime.now(timezone.utc)
    provenance = DataProvenance(
        "test", "ACME.NS", "NSE", now, now - timedelta(minutes=10), "INR", "ok",
        publication_timestamp=now - timedelta(minutes=9),
    )
    quote = MarketQuote("10", provenance)
    assert quote.is_stale(timedelta(minutes=5), as_of=now)
    assert not quote.is_stale(timedelta(minutes=15), as_of=now)
    assert not _quote("test", "10").is_stale(timedelta(minutes=5), as_of=now)
    missing_market = DataProvenance(
        "test", "ACME.NS", "NSE", now, None, "INR", "unknown",
        publication_timestamp=now,
    )
    with pytest.raises(LookAheadDataError, match="market timestamp is required"):
        MarketQuote("10", missing_market).is_stale(timedelta(minutes=5), as_of=now)

    missing_publication = DataProvenance(
        "test", "ACME.NS", "NSE", now, now, "INR", "unknown"
    )
    with pytest.raises(LookAheadDataError, match="publication timestamp is required"):
        MarketQuote("10", missing_publication).is_stale(timedelta(minutes=5), as_of=now)
    with pytest.raises(ValueError, match="non-negative timedelta"):
        quote.is_stale(timedelta(seconds=-1), as_of=now)


@pytest.mark.unit
def test_staleness_uses_historical_as_of_instead_of_current_clock():
    provenance = DataProvenance(
        "test",
        "ACME.NS",
        "NSE",
        datetime(2026, 1, 5, 17, tzinfo=timezone.utc),
        datetime(2026, 1, 5, 15, tzinfo=timezone.utc),
        "INR",
        "ok",
        publication_timestamp=datetime(2026, 1, 5, 16, tzinfo=timezone.utc),
    )
    quote = MarketQuote("10", provenance)
    assert not quote.is_stale(timedelta(hours=4), as_of="2026-01-05")
    assert quote.is_stale(timedelta(hours=1), as_of="2026-01-05")


@pytest.mark.unit
def test_historical_availability_requires_publication_time_before_as_of():
    retrieval = datetime(2026, 1, 7, 12, tzinfo=timezone.utc)
    common = dict(
        provider="test", symbol="ACME.NS", exchange="NSE", currency="INR",
        data_quality="ok", retrieval_timestamp=retrieval,
        market_timestamp=datetime(2026, 1, 5, 10, tzinfo=timezone.utc),
    )
    available = DataProvenance(
        **common, publication_timestamp=datetime(2026, 1, 5, 11, tzinfo=timezone.utc)
    )
    available.ensure_available_as_of("2026-01-05")
    late = DataProvenance(
        **common, publication_timestamp=datetime(2026, 1, 6, 1, tzinfo=timezone.utc)
    )
    with pytest.raises(LookAheadDataError, match="published after"):
        late.ensure_available_as_of("2026-01-05")
    missing_publication = DataProvenance(**common)
    with pytest.raises(LookAheadDataError, match="publication timestamp is required"):
        missing_publication.ensure_available_as_of("2026-01-05")
    missing_market = DataProvenance(
        provider="test",
        symbol="ACME.NS",
        exchange="NSE",
        retrieval_timestamp=retrieval,
        market_timestamp=None,
        publication_timestamp=datetime(2026, 1, 5, 11, tzinfo=timezone.utc),
        currency="INR",
        data_quality="ok",
    )
    with pytest.raises(LookAheadDataError, match="market timestamp is required"):
        missing_market.ensure_available_as_of("2026-01-05")
    with pytest.raises(ValueError, match="as_of date cannot be in the future"):
        available.ensure_available_as_of("2026-12-31")


@pytest.mark.unit
def test_provider_registry_requires_explicit_selection_and_validates_provenance():
    now = datetime.now(timezone.utc)

    class FakeIndiaProvider:
        provider_name = "fake"

        def __init__(self, name="fake", symbol="ACME.NS", price="123.45"):
            self.name = name
            self.symbol = symbol
            self.price = price

        def get_quote(self, symbol, exchange):
            return MarketQuote(
                self.price,
                DataProvenance(
                    self.name, self.symbol, exchange, now, now, "INR", "reported",
                    publication_timestamp=now,
                ),
            )

    registry = IndiaProviderRegistry()
    registry.register(FakeIndiaProvider())
    assert registry.provider_names == ("fake",)
    quote = registry.get_quote(
        "FAKE", "ACME", "NSE", as_of=now, max_age=timedelta(minutes=1)
    )
    assert quote.provenance.provider == "fake"
    with pytest.raises(ValueError, match="already registered"):
        registry.register(FakeIndiaProvider())
    replacement = FakeIndiaProvider(price="222.00")
    registry.register(replacement, replace=True)
    assert registry.get_quote(
        "fake", "ACME", "NSE", as_of=now, max_age=timedelta(minutes=1)
    ).value == 222
    with pytest.raises(LookupError, match="not registered"):
        registry.get_quote(
            "other", "ACME", "NSE", as_of=now, max_age=timedelta(minutes=1)
        )
    bad_registry = IndiaProviderRegistry()
    bad_registry.register(FakeIndiaProvider(name="wrong"))
    with pytest.raises(ValueError, match="provenance provider"):
        bad_registry.get_quote(
            "fake", "ACME", "NSE", as_of=now, max_age=timedelta(minutes=1)
        )


@pytest.mark.unit
def test_provider_registry_rejects_malformed_and_inconsistent_adapters():
    now = datetime.now(timezone.utc)
    registry = IndiaProviderRegistry()

    class MissingMethod:
        provider_name = "missing"

    class NonCallableMethod:
        provider_name = "noncallable"
        get_quote = None

    with pytest.raises(TypeError, match="implement IndianMarketDataProvider"):
        registry.register(MissingMethod())
    with pytest.raises(TypeError, match="implement IndianMarketDataProvider"):
        registry.register(NonCallableMethod())

    class StaticProvider:
        provider_name = "static"

        def __init__(self, quote):
            self.quote = quote

        def get_quote(self, symbol, exchange):
            return self.quote

    good_provenance = DataProvenance(
        "static", "ACME.NS", "NSE", now, now, "INR", "reported",
        publication_timestamp=now,
    )
    with pytest.raises(TypeError, match="must return MarketQuote"):
        registry.register(StaticProvider("not a quote"))
        registry.get_quote("static", "ACME", "NSE", as_of=now, max_age=timedelta(minutes=1))

    registry = IndiaProviderRegistry()
    registry.register(StaticProvider(MarketQuote("1", good_provenance)))
    with pytest.raises(ValueError, match="exchange does not match"):
        bad_exchange = DataProvenance(
            "static", "ACME.BO", "BSE", now, now, "INR", "reported",
            publication_timestamp=now,
        )
        bad_registry = IndiaProviderRegistry()
        bad_registry.register(StaticProvider(MarketQuote("1", bad_exchange)))
        bad_registry.get_quote("static", "ACME", "NSE", as_of=now, max_age=timedelta(minutes=1))
    with pytest.raises(ValueError, match="symbol does not match"):
        bad_symbol = DataProvenance(
            "static", "OTHER.NS", "NSE", now, now, "INR", "reported",
            publication_timestamp=now,
        )
        bad_registry = IndiaProviderRegistry()
        bad_registry.register(StaticProvider(MarketQuote("1", bad_symbol)))
        bad_registry.get_quote("static", "ACME", "NSE", as_of=now, max_age=timedelta(minutes=1))
    with pytest.raises(TypeError, match="as_of"):
        registry.get_quote("static", "ACME", "NSE", max_age=timedelta(minutes=1))
    with pytest.raises(TypeError, match="max_age"):
        registry.get_quote("static", "ACME", "NSE", as_of=now)


@pytest.mark.unit
def test_provider_registry_rejects_stale_quotes_for_historical_queries():
    now = datetime.now(timezone.utc)
    old_observation = now - timedelta(days=2)
    quote = MarketQuote(
        "1",
        DataProvenance(
            "static", "ACME.NS", "NSE", now, old_observation, "INR", "reported",
            publication_timestamp=old_observation + timedelta(minutes=1),
        ),
    )

    class StaticProvider:
        provider_name = "static"

        def get_quote(self, symbol, exchange):
            return quote

    registry = IndiaProviderRegistry()
    registry.register(StaticProvider())
    with pytest.raises(StaleMarketDataError, match="maximum age"):
        registry.get_quote(
            "static", "ACME", "NSE", as_of=now, max_age=timedelta(hours=1)
        )


@pytest.mark.unit
def test_provider_protocol_accepts_adapters_implementing_the_contract():
    class FakeIndiaProvider:
        provider_name = "fake"

        def get_quote(self, symbol, exchange):
            return _quote(self.provider_name, "123.45")

    assert isinstance(FakeIndiaProvider(), IndianMarketDataProvider)