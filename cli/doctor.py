"""Diagnostic command to verify environment, API keys, and vendor connectivity."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from rich.panel import Panel
from rich.table import Table

from cli.display import console
from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.net import vendor_reachable
from tradingagents.dataflows.vendors.yahoo.ohlcv import YAHOO_HOST

LLM_KEYS = [
    ("Google Gemini", "GOOGLE_API_KEY"),
    ("OpenAI", "OPENAI_API_KEY"),
    ("Anthropic Claude", "ANTHROPIC_API_KEY"),
    ("xAI Grok", "XAI_API_KEY"),
    ("OpenRouter", "OPENROUTER_API_KEY"),
]

VENDOR_ENDPOINTS = [
    ("Yahoo Finance", YAHOO_HOST),
    ("SEC EDGAR", "https://data.sec.gov"),
    ("Polymarket", "https://gamma-api.polymarket.com"),
    ("FRED", "https://api.stlouisfed.org"),
    ("Alpha Vantage", "https://www.alphavantage.co"),
]


def _mask_key(val: str) -> str:
    """Mask an API key for safe terminal display, showing only endpoints."""
    if not val:
        return "[red]Not configured[/red]"
    if len(val) <= 8:
        return "[green]Configured[/green] (***)"
    return f"[green]Configured[/green] ({val[:4]}...{val[-4:]})"


def run_doctor() -> None:
    """Run diagnostics and output a comprehensive health check."""
    console.print(
        Panel(
            "[bold cyan]TradingAgents Health Check & Diagnostics[/bold cyan]",
            border_style="cyan",
        )
    )

    env_table = Table(
        title="System & Runtime",
        title_justify="left",
        show_header=True,
        header_style="bold magenta",
    )
    env_table.add_column("Component", style="dim", width=25)
    env_table.add_column("Status", width=15)
    env_table.add_column("Details")

    py_ver = sys.version.split()[0]
    py_ok = sys.version_info >= (3, 10)
    env_table.add_row(
        "Python Version",
        "[green]✓ OK[/green]" if py_ok else "[red]✗ Upgrade needed[/red]",
        f"Python {py_ver} ({sys.platform})",
    )

    config = get_config()
    cache_dir = Path(config.get("data_cache_dir", "./data_cache"))
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        test_file = cache_dir / ".write_test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink()
        cache_status = "[green]✓ Writable[/green]"
    except Exception as exc:
        cache_status = f"[red]✗ Error ({exc})[/red]"

    env_table.add_row("Cache Directory", cache_status, str(cache_dir.resolve()))
    console.print(env_table)
    console.print()

    llm_table = Table(
        title="LLM Providers",
        title_justify="left",
        show_header=True,
        header_style="bold magenta",
    )
    llm_table.add_column("Provider", style="dim", width=25)
    llm_table.add_column("Env Variable", width=25)
    llm_table.add_column("Status")

    configured_count = 0
    for name, env_var in LLM_KEYS:
        val = os.getenv(env_var, "").strip()
        if val:
            configured_count += 1
        llm_table.add_row(name, env_var, _mask_key(val))

    console.print(llm_table)
    if configured_count == 0:
        console.print(
            "[yellow]⚠ Warning: No LLM API keys are configured in your environment "
            "or .env file.[/yellow]"
        )
    else:
        console.print(f"[dim]Found {configured_count} configured LLM provider key(s).[/dim]")
    console.print()

    vendor_table = Table(
        title="Data Vendors Connectivity",
        title_justify="left",
        show_header=True,
        header_style="bold magenta",
    )
    vendor_table.add_column("Vendor", style="dim", width=25)
    vendor_table.add_column("Endpoint", width=35)
    vendor_table.add_column("Reachability")

    for name, host in VENDOR_ENDPOINTS:
        reachable = vendor_reachable(host)
        status = "[green]✓ Reachable[/green]" if reachable else "[yellow]✗ Unreachable[/yellow]"
        vendor_table.add_row(name, host, status)

    console.print(vendor_table)
    console.print()

    console.print(
        "[bold green]Diagnostics complete.[/bold green] System ready for running analyses.\n"
    )
