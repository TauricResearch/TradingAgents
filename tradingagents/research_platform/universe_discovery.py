"""Tushare-first discovery of configurable A-share concept universes."""

from __future__ import annotations

import os
from collections import defaultdict
from collections.abc import Callable, Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .research_settings import ResearchSettings, SectorRule
from .tushare_provider import TushareDataUnavailableError, _default_pro_client_factory, _records


class DiscoveredStock(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    ts_code: str
    name: str = ""
    sectors: list[str] = Field(default_factory=list)
    sector_names: list[str] = Field(default_factory=list)
    matched_concepts: list[str] = Field(default_factory=list)


class UniverseDiscoveryResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str = "tushare_pro"
    source_endpoint: str
    stocks: list[DiscoveredStock]
    matched_concepts: dict[str, list[str]]
    warnings: list[str] = Field(default_factory=list)


class TushareUniverseDiscovery:
    """Resolve configured concept keywords to currently listed A-share members."""

    def __init__(
        self,
        *,
        pro_client: Any | None = None,
        token: str | None = None,
        pro_client_factory: Callable[[str], Any] | None = None,
    ):
        resolved_token = token or os.environ.get("TUSHARE_TOKEN", "").strip()
        if pro_client is None and not resolved_token:
            raise TushareDataUnavailableError("TUSHARE_TOKEN is required for universe discovery.")
        self._pro = pro_client or (pro_client_factory or _default_pro_client_factory)(
            resolved_token
        )

    def discover(self, settings: ResearchSettings) -> UniverseDiscoveryResult:
        rules = [rule for rule in settings.sector_rules if rule.enabled]
        profiles = self._stock_profiles()
        concepts, endpoint = self._concept_catalog()
        memberships: dict[str, set[str]] = defaultdict(set)
        matched_names: dict[str, set[str]] = defaultdict(set)
        warnings: list[str] = []
        matched_concepts: dict[str, list[str]] = {}

        for rule in rules:
            matches = [item for item in concepts if _matches_rule(str(item.get("name", "")), rule)]
            matched_concepts[rule.id] = sorted(
                {str(item.get("name", "")).strip() for item in matches if item.get("name")}
            )
            for concept in matches:
                concept_code = str(concept.get("ts_code") or concept.get("code") or "").strip()
                concept_name = str(concept.get("name", "")).strip()
                if not concept_code:
                    continue
                try:
                    members = self._concept_members(endpoint, concept_code)
                except Exception as error:
                    warnings.append(f"{concept_name or concept_code}: {error}")
                    continue
                for row in members:
                    ts_code = _member_ts_code(row)
                    if not ts_code or not _is_a_share(ts_code):
                        continue
                    symbol = ts_code.split(".", 1)[0]
                    memberships[symbol].add(rule.id)
                    matched_names[symbol].add(concept_name)

            for raw_symbol in rule.explicit_includes:
                symbol, ts_code = _normalize_config_symbol(raw_symbol, profiles)
                memberships[symbol].add(rule.id)
                profiles.setdefault(symbol, {"ts_code": ts_code, "name": ""})
            for raw_symbol in rule.explicit_excludes:
                symbol, _ = _normalize_config_symbol(raw_symbol, profiles)
                memberships[symbol].discard(rule.id)

        rule_names = {rule.id: rule.name for rule in rules}
        stocks = []
        for symbol, sectors in memberships.items():
            if not sectors:
                continue
            profile = profiles.get(symbol, {})
            stocks.append(
                DiscoveredStock(
                    symbol=symbol,
                    ts_code=str(profile.get("ts_code") or _guess_ts_code(symbol)),
                    name=str(profile.get("name") or ""),
                    sectors=sorted(sectors),
                    sector_names=[rule_names[item] for item in sorted(sectors)],
                    matched_concepts=sorted(name for name in matched_names[symbol] if name),
                )
            )
        return UniverseDiscoveryResult(
            source_endpoint=endpoint,
            stocks=sorted(stocks, key=lambda item: item.symbol),
            matched_concepts=matched_concepts,
            warnings=warnings[:50],
        )

    def _stock_profiles(self) -> dict[str, dict[str, str]]:
        try:
            rows = _records(
                self._pro.stock_basic(
                    exchange="",
                    list_status="L",
                    fields="ts_code,symbol,name,industry,market,exchange,list_status",
                )
            )
        except Exception as error:
            raise TushareDataUnavailableError(
                f"Tushare stock_basic unavailable: {error}"
            ) from error
        return {
            str(row.get("symbol") or str(row.get("ts_code", "")).split(".", 1)[0]): {
                "ts_code": str(row.get("ts_code", "")),
                "name": str(row.get("name", "")),
            }
            for row in rows
            if row.get("ts_code") and _is_a_share(str(row.get("ts_code")))
        }

    def _concept_catalog(self) -> tuple[list[Mapping[str, Any]], str]:
        errors = []
        try:
            rows = _records(
                self._pro.ths_index(
                    exchange="A", type="N", fields="ts_code,name,type,count,exchange,list_date"
                )
            )
            if rows:
                return rows, "ths_member"
        except Exception as error:
            errors.append(f"ths_index: {error}")
        try:
            rows = _records(self._pro.concept(src="ts"))
            if rows:
                return rows, "concept_detail"
        except Exception as error:
            errors.append(f"concept: {error}")
        raise TushareDataUnavailableError(
            "No usable Tushare concept catalog (" + "; ".join(errors) + ")"
        )

    def _concept_members(self, endpoint: str, concept_code: str) -> list[Mapping[str, Any]]:
        if endpoint == "ths_member":
            return _records(
                self._pro.ths_member(
                    ts_code=concept_code,
                    fields="ts_code,con_code,con_name,weight,in_date,out_date,is_new",
                )
            )
        return _records(self._pro.concept_detail(id=concept_code))


def _matches_rule(name: str, rule: SectorRule) -> bool:
    folded = name.casefold()
    return any(keyword.casefold() in folded for keyword in rule.keywords)


def _member_ts_code(row: Mapping[str, Any]) -> str:
    for key in ("code", "con_code", "ts_code"):
        value = str(row.get(key, "")).strip().upper()
        if _is_a_share(value):
            return value
    return ""


def _is_a_share(ts_code: str) -> bool:
    return ts_code.upper().endswith((".SH", ".SZ", ".BJ"))


def _normalize_config_symbol(
    raw_symbol: str, profiles: Mapping[str, Mapping[str, str]]
) -> tuple[str, str]:
    normalized = raw_symbol.strip().upper()
    if "." in normalized:
        symbol = normalized.split(".", 1)[0]
        return symbol, normalized
    profile = profiles.get(normalized)
    return normalized, str(profile.get("ts_code")) if profile else _guess_ts_code(normalized)


def _guess_ts_code(symbol: str) -> str:
    if symbol.startswith(("4", "8")):
        return f"{symbol}.BJ"
    if symbol.startswith(("5", "6", "9")):
        return f"{symbol}.SH"
    return f"{symbol}.SZ"
