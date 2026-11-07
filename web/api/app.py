"""The read-only HTTP API over the paper account: the app factory and its routes.

``create_app`` wires the settings and an OKX client into the routes; ``python -m
web.api`` serves it on this machine. Every route reads: nothing here writes the
ledger or runs the research. The built UI, when ``web/ui/dist`` exists, is served
at ``/`` with the client-side routes falling back to its index.html.
"""

# No ``from __future__ import annotations``: FastAPI reads the route signatures at
# definition time, and the dependency aliases are locals of ``create_app``.

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Path as PathParam, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles

from trader.ledger import Ledger
from trader.okx import OKX
from trader.settings import Settings
from web.api import data

UI_DIST = Path(__file__).resolve().parents[1] / "ui" / "dist"
ORIGINS = ["http://127.0.0.1:5173", "http://localhost:5173"]  # the Vite dev server
# Both name a file under the results directory, so neither may hold a separator
# or be "." or "..": a coin starts with a letter or digit.
COIN = r"^[A-Z0-9][A-Z0-9.-]{0,19}$"
TRADE_DATE = r"^\d{4}-\d{2}-\d{2}$"

Since = Annotated[datetime | None, Query(description="ISO 8601; UTC when it has no offset")]
Limit = Annotated[int, Query(ge=1)]


def create_app(settings: Settings, okx: OKX | None = None) -> FastAPI:
    accounts = data.accounts(settings)
    market = data.Market(okx or OKX())
    app = FastAPI(title="TradingAgents trader")
    app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=["GET"])

    def _account(account_id: str) -> data.Account:
        if account_id not in accounts:
            raise HTTPException(404, f"no account {account_id!r}")
        return accounts[account_id]

    def _open(account: data.Account):
        if not account.ledger_path.is_file():
            raise HTTPException(
                404, f"account {account.id!r} has no ledger at {account.ledger_path}"
            )
        return data.open_ledger(account)

    AccountDep = Annotated[data.Account, Depends(_account)]

    def _ledger(account: AccountDep) -> Iterator[Ledger]:
        with _open(account) as ledger:
            yield ledger

    LedgerDep = Annotated[Ledger, Depends(_ledger)]

    @app.get("/api/accounts")
    def list_accounts():
        return [data.summary(account) for account in accounts.values()]

    @app.get("/api/accounts/{account_id}/overview")
    def overview(account: AccountDep, ledger: LedgerDep):
        return data.overview(account, ledger, market)

    @app.get("/api/accounts/{account_id}/equity")
    def equity(account: AccountDep, ledger: LedgerDep):
        return data.equity(account, ledger, market)

    @app.get("/api/accounts/{account_id}/fills")
    def fills(account: AccountDep, ledger: LedgerDep, since: Since = None, limit: Limit = 500):
        return data.fills(account, ledger, _since_ms(since), limit)

    @app.get("/api/accounts/{account_id}/funding")
    def funding(account: AccountDep, ledger: LedgerDep, since: Since = None, limit: Limit = 500):
        return data.funding(account, ledger, _since_ms(since), limit)

    @app.get("/api/accounts/{account_id}/events")
    def events(ledger: LedgerDep):
        return data.events(ledger)

    @app.get("/api/accounts/{account_id}/attempts")
    def attempts(ledger: LedgerDep):
        return data.attempts(ledger)

    @app.get("/api/accounts/{account_id}/accuracy")
    def accuracy(account: AccountDep):
        return data.accuracy(account)

    # The research records are the paper account's; an account would enter the
    # path once there is more than one.
    @app.get("/api/research")
    def research_index():
        account = accounts["paper"]
        with _open(account) as ledger:
            return data.research_index(account, ledger)

    @app.get("/api/research/{coin}/{trade_date}")
    def research_record(
        coin: Annotated[str, PathParam(pattern=COIN)],
        trade_date: Annotated[str, PathParam(pattern=TRADE_DATE)],
    ):
        body = data.research_record(accounts["paper"], coin, trade_date)
        if body is None:
            raise HTTPException(404, f"no research record of {coin} for {trade_date}")
        return Response(body, media_type="application/json")

    if UI_DIST.is_dir():
        app.mount("/", _UIFiles(directory=UI_DIST, html=True), name="ui")
    else:
        @app.get("/", include_in_schema=False)
        def no_ui():
            return PlainTextResponse("The API is at /api. The UI is not built: see web/ui.")

    return app


class _UIFiles(StaticFiles):
    """The built UI; a path that is no file of it gets index.html, so the client-side
    routes load on refresh. Unknown API paths stay 404."""

    async def get_response(self, path: str, scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or path.startswith("api/"):
                raise
            return await super().get_response("index.html", scope)


def _since_ms(since: datetime | None) -> int:
    if since is None:
        return 0
    if since.tzinfo is None:
        since = since.replace(tzinfo=UTC)
    return int(since.timestamp() * 1000)
