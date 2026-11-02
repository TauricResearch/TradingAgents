"""CSV-backed Indian market universe and deterministic security resolution."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from tradingagents.dataflows.india.symbols import normalize_indian_symbol

_ISIN_RE = re.compile(r"^IN[A-Z0-9]{9}[0-9]$")


def _is_valid_indian_isin(value: str) -> bool:
    if not _ISIN_RE.fullmatch(value):
        return False
    digits = "".join(str(ord(char) - 55) if char.isalpha() else char for char in value)
    total = 0
    double_digit = len(digits) % 2 == 0
    for char in digits:
        digit = int(char)
        if double_digit:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
        double_digit = not double_digit
    return total % 10 == 0


class UnknownInstrumentError(LookupError):
    """No universe constituent matches the supplied identifier."""


class AmbiguousInstrumentError(LookupError):
    """An identifier matches multiple listings and needs exchange context."""


@dataclass(frozen=True)
class IndianConstituent:
    symbol: str
    exchange: str
    company_name: str | None = None
    isin: str | None = None
    sector: str | None = None


@dataclass(frozen=True)
class IndianMarketUniverse:
    constituents: tuple[IndianConstituent, ...]
    data_source: str
    last_updated: date
    name: str = "Nifty 500"

    def __post_init__(self):
        if not isinstance(self.data_source, str) or not self.data_source.strip():
            raise ValueError("data_source must not be empty")
        if not isinstance(self.last_updated, date) or isinstance(self.last_updated, datetime):
            raise ValueError("last_updated must be a date, not a datetime")
        for item in self.constituents:
            if not isinstance(item, IndianConstituent):
                raise TypeError("constituents must contain IndianConstituent values")
            if item.exchange not in {"NSE", "BSE"}:
                raise ValueError("constituent exchange must be NSE or BSE")
            if normalize_indian_symbol(item.symbol, item.exchange) != item.symbol:
                raise ValueError("constituent symbols must be canonical NSE/BSE symbols")
            if item.isin is not None and not _is_valid_indian_isin(item.isin):
                raise ValueError(f"invalid Indian ISIN {item.isin!r}")
        if len({(item.symbol, item.exchange) for item in self.constituents}) != len(
            self.constituents
        ):
            raise ValueError("universe contains duplicate symbol/exchange listings")

    def resolve(self, identifier: str, exchange: str | None = None) -> IndianConstituent:
        """Resolve a ticker or ISIN; require context when it maps to many listings."""
        if not isinstance(identifier, str) or not identifier.strip():
            raise ValueError("identifier must be a non-empty ticker or ISIN")

        value = identifier.strip().upper()
        explicit_exchange = exchange.strip().upper() if isinstance(exchange, str) else exchange
        if explicit_exchange is not None and explicit_exchange not in {"NSE", "BSE"}:
            raise ValueError(f"Unsupported Indian exchange {exchange!r}; use NSE or BSE")

        suffix_exchange = None
        if value.endswith(".NS"):
            suffix_exchange = "NSE"
        elif value.endswith(".BO"):
            suffix_exchange = "BSE"
        if suffix_exchange and explicit_exchange and suffix_exchange != explicit_exchange:
            raise ValueError(
                f"Ticker {identifier!r} identifies {suffix_exchange}, not {explicit_exchange}"
            )
        selected_exchange = explicit_exchange or suffix_exchange

        if _ISIN_RE.fullmatch(value):
            candidates = [item for item in self.constituents if item.isin == value]
        elif selected_exchange or value.endswith((".NS", ".BO")):
            ticker = normalize_indian_symbol(value, selected_exchange)
            candidates = [item for item in self.constituents if item.symbol == ticker]
        else:
            candidates = [
                item for item in self.constituents
                if item.symbol.removesuffix(".NS").removesuffix(".BO") == value
            ]

        if selected_exchange:
            candidates = [item for item in candidates if item.exchange == selected_exchange]
        if not candidates:
            raise UnknownInstrumentError(
                f"No {self.name} listing found for {identifier!r}"
                + (f" on {selected_exchange}" if selected_exchange else "")
            )
        if len(candidates) > 1:
            raise AmbiguousInstrumentError(
                f"{identifier!r} matches multiple listings; specify NSE or BSE"
            )
        return candidates[0]


def load_nifty500_universe(
    csv_path: str | Path,
    *,
    data_source: str,
    last_updated: date | str,
) -> IndianMarketUniverse:
    """Load supplied constituents; no membership is bundled or inferred.

    CSV columns: ``symbol`` is required; ``exchange``, ``company_name``,
    ``isin`` and ``sector`` are optional when each row can otherwise be
    identified unambiguously. ``data_source`` and ``last_updated`` are explicit
    metadata supplied by the caller rather than inferred from the local clock.
    """
    if isinstance(last_updated, datetime):
        raise ValueError("last_updated must be a date, not a datetime")
    if isinstance(last_updated, str):
        try:
            parsed = date.fromisoformat(last_updated)
        except ValueError as exc:
            raise ValueError("last_updated must be an ISO date (YYYY-MM-DD)") from exc
        if parsed.isoformat() != last_updated:
            raise ValueError("last_updated must be an ISO date (YYYY-MM-DD)")
        last_updated = parsed
    if type(last_updated) is not date:
        raise ValueError("last_updated must be a date or ISO date string")
    if not isinstance(data_source, str) or not data_source.strip():
        raise ValueError("data_source must identify the supplied constituent source")

    constituents = []
    with Path(csv_path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "symbol" not in reader.fieldnames:
            raise ValueError("CSV must include a 'symbol' column")
        for line, row in enumerate(reader, start=2):
            raw_symbol = (row.get("symbol") or "").strip()
            raw_exchange = (row.get("exchange") or "").strip() or None
            try:
                symbol = normalize_indian_symbol(raw_symbol, raw_exchange)
            except ValueError as exc:
                raise ValueError(f"Invalid listing on CSV line {line}: {exc}") from exc
            exchange = "NSE" if symbol.endswith(".NS") else "BSE"
            isin = (row.get("isin") or "").strip().upper() or None
            if isin and not _is_valid_indian_isin(isin):
                raise ValueError(f"Invalid Indian ISIN on CSV line {line}: {isin!r}")
            constituents.append(
                IndianConstituent(
                    symbol=symbol,
                    exchange=exchange,
                    company_name=(row.get("company_name") or "").strip() or None,
                    isin=isin,
                    sector=(row.get("sector") or "").strip() or None,
                )
            )

    if not constituents:
        raise ValueError("CSV contains no constituent rows")
    return IndianMarketUniverse(tuple(constituents), data_source.strip(), last_updated)