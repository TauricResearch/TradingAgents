"""Explicit account commands for ChatGPT subscription authentication."""

from __future__ import annotations

import typer

from cli.display import console
from tradingagents.llm_clients import chatgpt_auth

app = typer.Typer(
    name="auth",
    help="Manage provider authentication.",
    no_args_is_help=True,
)


def _require_chatgpt(provider: str) -> None:
    """Reject providers that do not have explicit subscription auth commands."""
    if provider.lower() != "chatgpt":
        console.print("[red]Only --provider chatgpt is supported by auth commands.[/red]")
        raise typer.Exit(code=2)


@app.command()
def login(
    provider: str = typer.Option("chatgpt", "--provider", help="Authentication provider."),
    add_account: bool = typer.Option(
        False,
        "--add-account",
        help="Sign in to an additional ChatGPT account.",
    ),
) -> None:
    """Sign in to a ChatGPT subscription account in the browser."""
    _require_chatgpt(provider)
    try:
        result = chatgpt_auth.sign_in(enable_plan_use=True, add_account=add_account)
    except chatgpt_auth.OAuthError as exc:
        console.print(f"[red]ChatGPT sign-in failed: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if result.inference_enabled:
        console.print("[green]ChatGPT sign-in complete. Plan use is enabled.[/green]")
    else:
        console.print(
            "[yellow]ChatGPT account is signed in, but plan use is disabled. "
            "Run `tradingagents auth login --provider chatgpt` to enable it.[/yellow]"
        )


@app.command()
def status(
    provider: str = typer.Option("chatgpt", "--provider", help="Authentication provider."),
) -> None:
    """Show saved ChatGPT account and plan-use state without credentials."""
    _require_chatgpt(provider)
    try:
        accounts = chatgpt_auth.saved_accounts()
    except chatgpt_auth.OAuthError as exc:
        console.print(f"[red]Unable to read ChatGPT accounts: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if not accounts:
        console.print("ChatGPT is not signed in.")
        return

    try:
        selected = chatgpt_auth.pinned_session().registration.client_id
    except chatgpt_auth.OAuthError:
        selected = None
    for index, account in enumerate(accounts, start=1):
        state = "selected" if account.client_id == selected else "saved"
        if account.requires_reauthorization:
            permission = "sign-in required"
        elif account.inference_enabled:
            permission = "plan use enabled"
        else:
            permission = "plan use disabled"
        console.print(
            f"Account {index} ({account.client_id[-8:]}): {state}; {permission}"
        )
        if account.requires_reauthorization or not account.inference_enabled:
            console.print(
                "  Inference is disabled. Run `tradingagents auth login "
                "--provider chatgpt` to enable plan use."
            )


@app.command()
def logout(
    provider: str = typer.Option("chatgpt", "--provider", help="Authentication provider."),
) -> None:
    """Clear the selected ChatGPT account credentials."""
    _require_chatgpt(provider)
    try:
        result = chatgpt_auth.logout()
    except chatgpt_auth.OAuthError as exc:
        console.print(f"[red]ChatGPT logout failed: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if result.client_id is None:
        console.print("No selected ChatGPT account is signed in.")
    elif result.revocation_confirmed:
        console.print("ChatGPT credentials cleared and revocation confirmed.")
    else:
        console.print(
            "[yellow]ChatGPT credentials were cleared locally, but remote "
            "revocation was not confirmed.[/yellow]"
        )
