"""``tradingagents-pro`` — operator CLI for the live-trading subsystem.

Deliberately separate from the base ``tradingagents`` analysis CLI. Every
command here operates on the /data volume the running service shares
(arming state, OMS journal, audit chain) and, where it must touch the
venue, builds a fresh adapter from the secrets layer.

Commands:
  arm-live         multi-step ceremony to arm a pair at a tier
  disarm           return a pair (or all) to paper
  flatten          EMERGENCY: cancel all, close all at market, disarm all
  status           show arming + kill-switch state
  readiness-report run the go-live self-check
  reconcile        resolve book-vs-venue drift (--accept-venue)

Nothing here bypasses a gate. Arming grants no capability on its own; the
router still runs every deterministic check.
"""

from __future__ import annotations

import secrets as _secrets
import sys
from pathlib import Path

import typer

app = typer.Typer(add_completion=False, no_args_is_help=True,
                  help="TradingAgents Pro live-trading operator CLI.")


def _data_dir() -> Path:
    from tradingagents.pro.dashboard.prefs import default_data_dir

    return default_data_dir()


def _audit():
    from tradingagents.pro.execution import AuditLog

    return AuditLog(_data_dir() / "audit.jsonl")


def _arming(audit=None):
    from tradingagents.pro.arming import ArmingStore

    return ArmingStore(_data_dir() / "arming.json", audit=audit or _audit())


def _build_adapter(testnet: bool):
    """Live venue adapter from the secrets layer. Testnet unless the
    operator explicitly asks for production."""
    from tradingagents.pro.execution.adapters.delta import DeltaAdapter

    return DeltaAdapter.from_env(testnet=testnet)


def _confirm_phrase(action: str) -> str:
    return f"{action}-{_secrets.token_hex(3)}"


@app.command("status")
def status() -> None:
    """Show per-pair arming and the kill-switch state (read-only)."""
    arming = _arming()
    typer.echo("arming state (per pair):")
    for pair, info in arming.status().items():
        typer.echo(f"  {pair:10s} {info['label']}")
    kill = _data_dir() / "KILL"
    typer.echo(f"\nkill switch: {'ENGAGED' if kill.exists() else 'clear'}"
               + (f' — {kill.read_text().strip()}' if kill.exists() else ""))


@app.command("readiness-report")
def readiness_report(
    testnet: bool = typer.Option(True, help="Check against testnet (default) "
                                 "or production venue."),
) -> None:
    """Run the go-live self-check. Any FAIL blocks arming."""
    from tradingagents.pro.preflight import go_live_readiness

    try:
        adapter = _build_adapter(testnet)
    except Exception as exc:
        typer.echo(f"(no venue adapter: {exc})")
        adapter = None
    report = go_live_readiness(adapter=adapter, audit=_audit())
    typer.echo(report.render())
    raise typer.Exit(code=0 if report.ok else 1)


@app.command("arm-live")
def arm_live(
    config: Path = typer.Option(..., exists=True, help="Path to live.yaml."),
    pair: str = typer.Option(..., help="Pair to arm, e.g. BTC-USD."),
    operator: str = typer.Option(..., help="Your identity, for the audit log."),
    testnet: bool = typer.Option(True, help="Arm against testnet (default)."),
    ttl_days: int = typer.Option(30, help="Arming lifetime before it expires."),
) -> None:
    """Ceremony: readiness -> show balance/limits/worst-case -> typed
    confirmation -> arm. Refuses on any readiness FAIL."""
    from tradingagents.pro.live_config import LiveConfigError, load_live_config
    from tradingagents.pro.preflight import go_live_readiness

    try:
        cfg = load_live_config(config)
    except LiveConfigError as exc:
        typer.secho(f"live config rejected: {exc}", fg="red")
        raise typer.Exit(code=2) from exc

    tier = cfg.mode_for(pair)
    if tier is None:
        typer.secho(f"{pair} is not configured in {config}", fg="red")
        raise typer.Exit(code=2)

    try:
        adapter = _build_adapter(testnet)
    except Exception as exc:
        typer.secho(f"cannot build venue adapter: {exc}", fg="red")
        raise typer.Exit(code=2) from exc

    report = go_live_readiness(adapter=adapter, audit=_audit())
    typer.echo(report.render())
    if not report.ok:
        typer.secho("\narming blocked — resolve every FAIL above.", fg="red")
        raise typer.Exit(code=1)

    account = adapter.account()
    worst_case = account.equity * cfg.risk.daily_loss_limit_pct / 100.0
    typer.echo("\n" + "=" * 52)
    typer.secho(f"  ARM {pair} at tier '{tier}'  ({'TESTNET' if testnet else 'PRODUCTION'})",
                fg="yellow", bold=True)
    typer.echo("=" * 52)
    typer.echo(f"  venue equity        : {account.equity:,.2f}")
    typer.echo(f"  max allocation      : {cfg.risk.live_max_account_allocation_pct}% "
               f"(~{account.equity * cfg.risk.live_max_account_allocation_pct / 100:,.2f})")
    typer.echo(f"  max notional/trade  : {cfg.risk.max_notional_per_trade:,.2f}")
    typer.echo(f"  daily loss limit    : {cfg.risk.daily_loss_limit_pct}% "
               f"(worst-case ~{worst_case:,.2f} before auto-flatten)")
    typer.echo(f"  max leverage        : {cfg.risk.max_leverage}x")
    typer.echo(f"  breach action       : {cfg.breach_action}")
    typer.echo(f"  arming expires in   : {ttl_days} days")
    typer.echo("=" * 52)

    phrase = _confirm_phrase(f"arm-{pair.lower()}")
    typer.echo(f"\nType this phrase to confirm:  {phrase}")
    typed = typer.prompt("confirmation")
    if typed.strip() != phrase:
        typer.secho("phrase mismatch — not armed.", fg="red")
        raise typer.Exit(code=1)

    record = _arming().arm(pair, tier, operator=operator, ttl_days=ttl_days)
    typer.secho(f"\n✓ {pair} armed at '{tier}', expires {record.expires_at[:10]}.",
                fg="green")


@app.command("disarm")
def disarm(
    pair: str = typer.Option("", help="Pair to disarm (omit with --all)."),
    all_pairs: bool = typer.Option(False, "--all", help="Disarm every pair."),
    operator: str = typer.Option("cli", help="Your identity, for the audit log."),
) -> None:
    """Return a pair (or all pairs) to paper. Always allowed, never gated."""
    arming = _arming()
    if all_pairs:
        arming.disarm_all("manual disarm", operator=operator)
        typer.secho("✓ all pairs disarmed (paper).", fg="green")
    elif pair:
        arming.disarm(pair, "manual disarm", operator=operator)
        typer.secho(f"✓ {pair} disarmed (paper).", fg="green")
    else:
        typer.secho("specify --pair or --all", fg="red")
        raise typer.Exit(code=2)


@app.command("flatten")
def flatten(
    confirm: bool = typer.Option(False, "--confirm",
                                 help="Required. Skips the typed prompt when "
                                 "set in scripts."),
    operator: str = typer.Option("cli", help="Your identity, for the audit log."),
    testnet: bool = typer.Option(True, help="Act on testnet (default) or prod."),
) -> None:
    """EMERGENCY: cancel all orders, close all positions at market, disarm."""
    if not confirm:
        phrase = _confirm_phrase("flatten")
        typer.secho("This cancels ALL orders and closes ALL positions at "
                    "market, then disarms.", fg="yellow", bold=True)
        typer.echo(f"Type this phrase to proceed:  {phrase}")
        if typer.prompt("confirmation").strip() != phrase:
            typer.secho("phrase mismatch — aborted.", fg="red")
            raise typer.Exit(code=1)

    from tradingagents.pro.flatten import emergency_flatten

    router = _build_flatten_router(testnet)
    summary = emergency_flatten(router, arming=_arming(router.audit),
                                operator=operator)
    typer.secho(f"✓ flattened {len(summary['flattened'])} position(s), "
                f"cancelled {len(summary['cancelled'])} order(s); kill switch "
                "engaged; all pairs disarmed.", fg="green")
    if summary["errors"]:
        typer.secho(f"  with errors: {summary['errors']}", fg="red")
        raise typer.Exit(code=1)


@app.command("reconcile")
def reconcile(
    accept_venue: bool = typer.Option(False, "--accept-venue",
                                      help="Adopt the venue's book as truth."),
    testnet: bool = typer.Option(True),
) -> None:
    """Report book-vs-venue drift; --accept-venue resolves it (audited)."""
    router = _build_flatten_router(testnet)
    report = router.reconcile()
    typer.echo(f"in_sync: {report.in_sync}")
    if report.missing_on_venue:
        typer.echo(f"  missing on venue : {list(report.missing_on_venue)}")
    if report.unknown_on_venue:
        typer.echo(f"  unknown on venue : {list(report.unknown_on_venue)}")
    if report.quantity_mismatches:
        typer.echo(f"  mismatches       : {list(report.quantity_mismatches)}")
    if not report.in_sync and accept_venue:
        router.local_book.clear()
        for p in router.adapter.positions():
            router.local_book[p.symbol] = (
                p.quantity if p.side == "BUY" else -p.quantity)
        router.audit.append("reconcile_accept_venue",
                            {"book": dict(router.local_book)})
        typer.secho("✓ adopted venue book as truth (audited).", fg="green")


def _build_flatten_router(testnet: bool):
    """Minimal router + recovered OMS over the shared /data journal, for
    flatten/reconcile from the CLI process."""
    from tradingagents.contracts import RiskLimits
    from tradingagents.pro.execution import (
        AuditLog,
        CircuitBreaker,
        ExecutionRouter,
        KillSwitch,
        OrderManager,
    )

    data = _data_dir()
    adapter = _build_adapter(testnet)
    limits = RiskLimits()
    router = ExecutionRouter(
        adapter=adapter, limits=limits,
        kill_switch=KillSwitch(data / "KILL"),
        breaker=CircuitBreaker(limits, equity_base=adapter.account().equity),
        audit=AuditLog(data / "audit.jsonl"),
    )
    oms = OrderManager(adapter, journal_path=data / "oms" / "journal.jsonl",
                       audit=router.audit)
    oms.recover()
    router.oms = oms
    return router


def main() -> None:
    import contextlib

    # honor the base package's .env auto-load for keys
    with contextlib.suppress(Exception):
        import tradingagents  # noqa: F401
    app()


if __name__ == "__main__":
    sys.exit(main() or 0)
