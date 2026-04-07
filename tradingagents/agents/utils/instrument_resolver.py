from __future__ import annotations

import re
from dataclasses import dataclass


class InstrumentResolutionError(ValueError):
    """Raised when a user-provided instrument cannot be normalized."""


@dataclass(frozen=True)
class InstrumentProfile:
    display_name: str
    primary_symbol: str
    exchange: str
    country: str
    timezone: str
    currency: str
    yahoo_symbol: str | None = None
    krx_code: str | None = None
    dart_corp_code: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "display_name": self.display_name,
            "primary_symbol": self.primary_symbol,
            "exchange": self.exchange,
            "country": self.country,
            "timezone": self.timezone,
            "currency": self.currency,
            "yahoo_symbol": self.yahoo_symbol or self.primary_symbol,
            "krx_code": self.krx_code,
            "dart_corp_code": self.dart_corp_code,
        }


_KRX_ALIAS_MAP = {
    "삼성전자": ("삼성전자", "005930.KS", "005930"),
    "SAMSUNG ELECTRONICS": ("삼성전자", "005930.KS", "005930"),
    "005930": ("삼성전자", "005930.KS", "005930"),
    "005930.KS": ("삼성전자", "005930.KS", "005930"),
    "NAVER": ("NAVER", "035420.KS", "035420"),
    "035420": ("NAVER", "035420.KS", "035420"),
    "035420.KS": ("NAVER", "035420.KS", "035420"),
}


def is_krx_symbol(symbol: str) -> bool:
    return bool(re.fullmatch(r"\d{6}\.(KS|KQ)", symbol.upper()))


def resolve_instrument(user_input: str) -> InstrumentProfile:
    raw_value = (user_input or "").strip()
    if not raw_value:
        raise InstrumentResolutionError("Instrument input is empty.")

    alias_key = raw_value.upper()
    if raw_value in _KRX_ALIAS_MAP:
        display_name, symbol, code = _KRX_ALIAS_MAP[raw_value]
        return _build_krx_profile(display_name, symbol, code)
    if alias_key in _KRX_ALIAS_MAP:
        display_name, symbol, code = _KRX_ALIAS_MAP[alias_key]
        return _build_krx_profile(display_name, symbol, code)

    upper = raw_value.upper()
    if is_krx_symbol(upper):
        code = upper.split(".", 1)[0]
        display_name = _KRX_ALIAS_MAP.get(upper, (code, upper, code))[0]
        return _build_krx_profile(display_name, upper, code)

    if re.fullmatch(r"\d{6}", raw_value):
        symbol = f"{raw_value}.KS"
        display_name = _KRX_ALIAS_MAP.get(raw_value, (raw_value, symbol, raw_value))[0]
        return _build_krx_profile(display_name, symbol, raw_value)

    if re.fullmatch(r"[A-Za-z][A-Za-z0-9.\-]{0,14}", raw_value):
        return InstrumentProfile(
            display_name=upper,
            primary_symbol=upper,
            exchange="US",
            country="US",
            timezone="US/Eastern",
            currency="USD",
            yahoo_symbol=upper,
        )

    raise InstrumentResolutionError(
        f"Could not resolve instrument '{user_input}'. Pass an exchange-qualified ticker or a known company name/code."
    )


def _build_krx_profile(display_name: str, primary_symbol: str, krx_code: str) -> InstrumentProfile:
    exchange = "KOSDAQ" if primary_symbol.endswith(".KQ") else "KRX"
    return InstrumentProfile(
        display_name=display_name,
        primary_symbol=primary_symbol,
        exchange=exchange,
        country="KR",
        timezone="Asia/Seoul",
        currency="KRW",
        yahoo_symbol=primary_symbol,
        krx_code=krx_code,
    )
