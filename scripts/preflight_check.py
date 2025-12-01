from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tradingagents.default_config import DEFAULT_CONFIG


def _mask(value: str) -> str:
    if not value:
        return "<missing>"
    if len(value) <= 4:
        return "***"
    return f"{value[:2]}***{value[-2:]}"


def _check_env(var: str) -> Tuple[bool, str]:
    value = os.getenv(var, "")
    return (bool(value), _mask(value))


def _check_writable(path: Path) -> Tuple[bool, str]:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".preflight_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True, "writable"
    except Exception as exc:
        return False, f"not writable: {exc}"


def _print_block(title: str, rows: List[Tuple[str, Any]]) -> None:
    print(f"\n{title}")
    print("-" * len(title))
    for key, value in rows:
        print(f"{key}: {value}")


def run() -> int:
    config: Dict[str, Any] = DEFAULT_CONFIG.copy()
    results_dir = Path(config.get("results_dir", "./results"))
    memory_cfg = (config.get("auto_trade", {}) or {}).get("memory", {}) or {}
    memory_dir = Path(memory_cfg.get("dir", results_dir / "memory"))

    env_rows: List[Tuple[str, Any]] = []
    for var in ("OPENAI_API_KEY", "APCA_API_KEY_ID", "APCA_API_SECRET_KEY"):
        present, masked = _check_env(var)
        env_rows.append((var, masked if present else "<missing>"))

    alpaca_cfg = config.get("alpaca_mcp", {}) or {}
    alpaca_rows = [
        ("enabled", alpaca_cfg.get("enabled", False)),
        ("base_url", alpaca_cfg.get("base_url") or "<unset>"),
        ("host", alpaca_cfg.get("host") or "<unset>"),
        ("port", alpaca_cfg.get("port") or "<unset>"),
        ("transport", alpaca_cfg.get("transport") or "<unset>"),
        ("required_tools", ", ".join(alpaca_cfg.get("required_tools", []))),
    ]
    if alpaca_cfg.get("enabled"):
        missing_tool = not alpaca_cfg.get("required_tools")
        if missing_tool:
            alpaca_rows.append(("warning", "alpaca_mcp.enabled=true but required_tools is empty"))

    fs_rows = []
    writable_results, results_msg = _check_writable(results_dir)
    writable_memory, memory_msg = _check_writable(memory_dir)
    fs_rows.append(("results_dir", f"{results_dir} ({results_msg})"))
    fs_rows.append(("memory_dir", f"{memory_dir} ({memory_msg})"))

    trade_exec = config.get("trade_execution", {}) or {}
    exec_rows = [
        ("enabled", trade_exec.get("enabled", False)),
        ("dry_run", trade_exec.get("dry_run", True)),
        ("default_order_quantity", trade_exec.get("default_order_quantity")),
        ("time_in_force", trade_exec.get("time_in_force")),
    ]

    print("TradingAgents preflight")
    print("=======================")
    _print_block("Environment", env_rows)
    _print_block("Alpaca MCP config", alpaca_rows)
    _print_block("Filesystem", fs_rows)
    _print_block("Trade execution", exec_rows)

    warnings: List[str] = []
    if not _check_env("OPENAI_API_KEY")[0]:
        warnings.append("OPENAI_API_KEY is missing")
    if alpaca_cfg.get("enabled") and (not _check_env("APCA_API_KEY_ID")[0] or not _check_env("APCA_API_SECRET_KEY")[0]):
        warnings.append("Alpaca keys missing while alpaca_mcp.enabled=true")
    if not writable_results or not writable_memory:
        warnings.append("results_dir or memory_dir is not writable")

    if warnings:
        print("\nWarnings:")
        for item in warnings:
            print(f"- {item}")
        return 1

    print("\nPreflight checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
