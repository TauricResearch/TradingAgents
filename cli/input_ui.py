"""Terminal-only portfolio selection and explicit consent coordinator."""

from __future__ import annotations

import sys

import typer
from rich.markup import escape

from cli.display import console
from tradingagents.runapi.input_service import (
    DirectoryReadError,
    LoadedPortfolio,
    PortfolioInputService,
    freeze_explicit,
    freeze_no_portfolio,
)
from tradingagents.runapi.result import InputError


class RunCancelled(Exception):
    """The user declined or cancelled before any graph/provider run began."""


def _confirm(message: str) -> bool:
    try:
        return typer.confirm(message, default=False)
    except (EOFError, typer.Abort):
        return False


def _cancel_if_declined(context, message: str):
    if not _confirm(message):
        raise RunCancelled("Run cancelled before analysis started.")
    return context.confirm()


def _choose_file(service: PortfolioInputService, interactive: bool) -> LoadedPortfolio | None:
    while True:
        try:
            choices = service.discover()
        except DirectoryReadError:
            console.print("[yellow]Could not read the portfolio folder.[/yellow]")
            if not interactive:
                raise InputError("UNREADABLE_PATH", "Could not read the portfolio directory.") from None
            action = typer.prompt("Choose retry, no-portfolio, or cancel", default="cancel").strip().casefold()
            if action in {"retry", "r"}:
                continue
            if action in {"no", "n", "no-portfolio"}:
                return None
            raise RunCancelled("Portfolio selection cancelled.") from None
        if not choices:
            return None
        console.print("Eligible portfolio files:")
        for index, path in enumerate(choices, 1):
            console.print(f"  {index}. {escape(path.name)}")
        answer = typer.prompt("Enter a number, N for no portfolio, or C to cancel").strip().casefold()
        if answer in {"n", "no"}:
            return None
        if answer in {"c", "cancel", "q"}:
            raise RunCancelled("Portfolio selection cancelled.")
        try:
            index = int(answer) - 1
            if index < 0 or index >= len(choices):
                raise ValueError
        except ValueError:
            console.print("[red]Choose one of the listed numbers, N, or C.[/red]")
            continue
        try:
            return service.read_file(choices[index])
        except InputError as exc:
            console.print(f"[red]{escape(exc.detail)}[/red]")
            if not _confirm("Try selecting a portfolio file again?"):
                raise RunCancelled("Portfolio selection cancelled.") from None


def resolve_run_context(ticker: str, analysis_date: str, *, portfolio_path: str | None = None,
                        without_portfolio: bool = False, portfolio_as_of: str | None = None,
                        loaded_portfolio: LoadedPortfolio | None = None,
                        portfolio=None, interactive: bool | None = None):
    """Resolve explicit mode, freeze one snapshot, then require explicit consent."""
    if interactive is None:
        interactive = bool(sys.stdin and sys.stdin.isatty())
    if portfolio_path and without_portfolio:
        raise InputError("FLAG_CONFLICT", "Use either --portfolio or --without-portfolio, not both.")
    if portfolio_as_of and not portfolio_path:
        raise InputError("FLAG_CONFLICT", "--portfolio-as-of requires --portfolio.")
    has_explicit_mode = bool(portfolio_path or without_portfolio or portfolio is not None)
    if not has_explicit_mode and not interactive:
        raise InputError("FLAG_CONFLICT", "Unattended runs require --portfolio PATH or --without-portfolio.")

    if without_portfolio:
        return freeze_no_portfolio(ticker, analysis_date).confirm()

    service = PortfolioInputService()
    if portfolio_path:
        if not interactive and not portfolio_as_of:
            raise InputError("AS_OF_MISMATCH", "Unattended --portfolio requires --portfolio-as-of matching --date.")
        loaded = loaded_portfolio or service.read_file(portfolio_path)
        context = service.freeze_loaded(
            ticker, analysis_date, loaded, portfolio_as_of or analysis_date,
        )
        if not interactive:
            return context.confirm()
        snap = context.snapshot
        disclosure = (
            f"Selected file: {snap.basename}\nAnalysis date: {analysis_date}\n"
            f"Holdings are user-supplied and unverified; as-of date is user-confirmed.\n"
            "The holdings will be sent to the configured model provider after you confirm."
        )
        console.print(disclosure)
        return _cancel_if_declined(context, "Send the selected holdings to the model provider and continue?")

    if portfolio is not None:
        context = freeze_explicit(ticker, analysis_date, portfolio)
        if not interactive:
            raise InputError("FLAG_CONFLICT", "Programmatic portfolio input must be explicitly confirmed with RunContext.confirm().")
        console.print(
            f"In-memory holdings are unverified and will be sent to the configured model provider "
            f"for analysis dated {analysis_date}."
        )
        return _cancel_if_declined(context, "Continue with this portfolio context?")

    selected = _choose_file(service, interactive)
    if selected is None:
        context = freeze_no_portfolio(ticker, analysis_date)
        console.print("Holdings and cash were not provided; no account ownership is assumed.")
        return _cancel_if_declined(context, "Continue without portfolio information?")
    context = service.freeze_loaded(ticker, analysis_date, selected, analysis_date)
    snap = context.snapshot
    console.print(
        f"Selected file: {snap.basename}\nAnalysis date: {analysis_date}\n"
        "Holdings are user-supplied and unverified; as-of date is user-confirmed.\n"
        "The holdings will be sent to the configured model provider after you confirm."
    )
    return _cancel_if_declined(context, "Send the selected holdings to the model provider and continue?")
