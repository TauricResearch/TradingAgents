from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from tradingagents.integrations.alpaca_mcp import AlpacaMCPClient, AlpacaMCPConfig, AlpacaMCPError


@dataclass
class AccountSnapshot:
    """Structured representation of the Alpaca account state."""

    fetched_at: datetime
    account_text: str
    positions_text: str
    orders_text: str
    account: Dict[str, Any]
    positions: List[Dict[str, Any]]
    orders: List[Dict[str, Any]]

    def buying_power(self) -> float:
        value = self.account.get("buying_power") or self.account.get("buying_power_usd")
        return _as_float(value)

    def cash(self) -> float:
        value = self.account.get("cash") or self.account.get("cash_usd")
        return _as_float(value)

    def portfolio_value(self) -> float:
        value = (
            self.account.get("portfolio_value")
            or self.account.get("equity")
            or self.account.get("equity_value")
        )
        return _as_float(value)

    def position_symbols(self) -> List[str]:
        symbols = []
        for position in self.positions:
            symbol = str(position.get("symbol") or position.get("symbol:") or "").upper()
            qty = _as_float(position.get("quantity") or position.get("qty") or 0)
            if symbol and qty != 0:
                symbols.append(symbol)
        return symbols


class AccountService:
    """Fetch and cache Alpaca MCP account information."""

    def __init__(self, alpaca_config: Dict[str, Any], logger: Optional[logging.Logger] = None) -> None:
        config = AlpacaMCPConfig.from_dict(alpaca_config or {})
        self.client = AlpacaMCPClient(config, logger=logger)
        self.logger = logger or logging.getLogger(__name__)
        self._snapshot: Optional[AccountSnapshot] = None
        self.enabled = bool(getattr(self.client.config, "enabled", False))
        if not self.enabled:
            self.logger.info("Alpaca MCP integration disabled; account snapshot will be unavailable.")

    def refresh(self) -> AccountSnapshot:
        """Fetch the latest account snapshot from the Alpaca MCP server."""

        if not self.enabled:
            raise RuntimeError(
                "Alpaca MCP integration is disabled. Set ALPACA_MCP_ENABLED=true (and related connection settings) to use the auto-trade workflow."
            )

        import asyncio

        async def _fetch_all() -> Dict[str, str]:
            async with self.client._acquire_session() as session:  # type: ignore[attr-defined]
                account_text = await self.client._call_tool_async("get_account_info", {}, session=session)
                positions_text = await self.client._call_tool_async("get_positions", {}, session=session, validate=False)
                orders_text = await self.client._call_tool_async("get_orders", {"status": "all", "limit": 50}, session=session, validate=False)
                return {
                    "account": account_text,
                    "positions": positions_text,
                    "orders": orders_text,
                }

        try:
            texts = asyncio.run(_fetch_all())
        except AlpacaMCPError as exc:
            raise RuntimeError(f"Failed to retrieve Alpaca account snapshot: {exc}") from exc
        except Exception as exc:
            raise RuntimeError(f"Failed to retrieve Alpaca account snapshot: {exc}") from exc

        snapshot = AccountSnapshot(
            fetched_at=datetime.utcnow(),
            account_text=texts["account"],
            positions_text=texts["positions"],
            orders_text=texts["orders"],
            account=_parse_key_values(texts["account"]),
            positions=_parse_position_blocks(texts["positions"]),
            orders=_parse_order_blocks(texts["orders"]),
        )
        self._snapshot = snapshot
        return snapshot

    @property
    def snapshot(self) -> Optional[AccountSnapshot]:
        return self._snapshot


def _parse_key_values(text: str) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    pattern = re.compile(r"^([A-Za-z0-9 _/-]+):\s*(.+)$")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.endswith(":"):
            continue
        match = pattern.match(line)
        if not match:
            continue
        key = match.group(1).strip().lower().replace(" ", "_")
        value = match.group(2).strip()
        data[key] = value
    return data


def _parse_position_blocks(text: str) -> List[Dict[str, Any]]:
    if not text or "No open positions" in text:
        return []
    blocks = []
    current: Dict[str, Any] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("Symbol:") and current:
            blocks.append(current)
            current = {}
        if ":" in line:
            key, value = line.split(":", 1)
            current[key.strip().lower().replace(" ", "_")] = value.strip()
    if current:
        blocks.append(current)
    return blocks


def _parse_order_blocks(text: str) -> List[Dict[str, Any]]:
    if not text or "No all orders" in text or "No orders" in text:
        return []
    blocks = []
    current: Dict[str, Any] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("Order ID:") and current:
            blocks.append(current)
            current = {}
        if ":" in line:
            key, value = line.split(":", 1)
            current[key.strip().lower().replace(" ", "_")] = value.strip()
    if current:
        blocks.append(current)
    return blocks


def _as_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return 0.0
    cleaned = text.replace("$", "").replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0
