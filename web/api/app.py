"""The HTTP API over the paper accounts: the app factory and its routes.

``create_app`` wires the settings and an OKX client into the routes; ``python -m
web.api`` serves it on this machine. Every route reads, but one: nothing here
writes a ledger or runs the research; ``POST /api/settings/llm`` writes the models
and prices to ``TRADER_HOME/settings.json`` (ADR 0007), which the accounts read at
their next run. The built UI, when ``web/ui/dist`` exists, is served at ``/`` with
the client-side routes falling back to its index.html.
"""

# No ``from __future__ import annotations``: FastAPI reads the route signatures at
# definition time, and the dependency aliases are locals of ``create_app``.

import secrets
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Path as PathParam, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles

from trader import overrides, prices
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


class TierChoice(BaseModel):
    """One tier of POST /api/settings/llm: the model, its provider and its price in USD
    per million tokens (input, output); a null price asks for the official one."""

    model: str
    provider: str
    price: tuple[float, float] | None = None


class LLMChoice(BaseModel):
    deep: TierChoice
    quick: TierChoice
    confirm: bool = False


def create_app(settings: Settings, okx: OKX | None = None) -> FastAPI:
    accounts = data.accounts(settings)
    market = data.Market(okx or OKX())
    app = FastAPI(title="TradingAgents trader")
    app.add_middleware(
        CORSMiddleware, allow_origins=ORIGINS, allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # A quote OKX cannot give is null in the routes that degrade (overview, equity);
    # anywhere else it is a 503 naming the cause, not a 500 with a traceback.
    for exc_type in (data.MarketUnavailable, *data.MARKET_ERRORS):
        app.add_exception_handler(exc_type, _market_unavailable)

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

    # The settings are read again per request: a switch shows without a restart, and
    # the accounts' next run reads the same file.
    @app.get("/api/strategy")
    def strategy():
        return data.strategy(Settings.with_overrides(settings.home))

    @app.get("/api/models")
    def models():
        return data.models(Settings.with_overrides(settings.home), accounts)

    def _write_auth(authorization: Annotated[str | None, Header()] = None) -> None:
        """The write endpoint's gate: with TRADER_WEB_TOKEN set, the request must carry
        it as ``Authorization: Bearer <token>``; without it, anyone who reaches the
        API may write (the loopback-only deployment of ADR 0005)."""
        if settings.web_token is None:
            return
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not secrets.compare_digest(
            token.strip().encode(), settings.web_token.encode()
        ):
            raise HTTPException(
                401, "令牌无效或缺失：需要 TRADER_WEB_TOKEN 的值作为 Bearer 令牌",
                headers={"WWW-Authenticate": "Bearer"},
            )

    @app.post("/api/settings/llm", dependencies=[Depends(_write_auth)])
    def set_llm(choice: LLMChoice):
        llm, chosen = _validated(choice)
        overrides.save(settings.home, llm, chosen, note="web", now=datetime.now(UTC))
        return data.models(Settings.with_overrides(settings.home), accounts)

    @app.get("/api/accounts/{account_id}/overview")
    def overview(account: AccountDep, ledger: LedgerDep):
        return data.overview(account, ledger, market)

    @app.get("/api/accounts/{account_id}/equity")
    def equity(account: AccountDep, ledger: LedgerDep):
        return data.equity(account, ledger, market)

    @app.get("/api/accounts/{account_id}/daily")
    def daily(account: AccountDep, ledger: LedgerDep, limit: Limit = 400):
        return data.daily(account, ledger, market, limit)

    @app.get("/api/accounts/{account_id}/fills")
    def fills(account: AccountDep, ledger: LedgerDep, since: Since = None, limit: Limit = 500):
        return data.fills(account, ledger, _since_ms(since), limit)

    @app.get("/api/accounts/{account_id}/funding")
    def funding(account: AccountDep, ledger: LedgerDep, since: Since = None, limit: Limit = 500):
        return data.funding(account, ledger, _since_ms(since), limit)

    @app.get("/api/accounts/{account_id}/signals")
    def signals(account: AccountDep, ledger: LedgerDep, since: Since = None, limit: Limit = 500):
        if account.demo:  # the intraday signals it follows, with what it did about each
            with _open(accounts["intraday"]) as source:
                return data.followed_signals(account, ledger, source, _since_ms(since), limit)
        return data.signals(account, ledger, _since_ms(since), limit)

    @app.get("/api/accounts/{account_id}/events")
    def events(ledger: LedgerDep, since: Since = None, limit: Limit = 500):
        return data.events(ledger, _since_ms(since), limit)

    @app.get("/api/accounts/{account_id}/attempts")
    def attempts(ledger: LedgerDep, since: Since = None, limit: Limit = 500):
        return data.attempts(ledger, _since_ms(since), limit)

    @app.get("/api/accounts/{account_id}/accuracy")
    def accuracy(account: AccountDep):
        return data.accuracy(account)

    # The demo account executes on the exchange (ADR 0008): its last reconciliation,
    # and how it compares with the intraday account whose signals it follows.
    def _demo(account: AccountDep) -> data.Account:
        if not account.demo:
            raise HTTPException(404, f"account {account.id!r} does not execute on an exchange")
        return account

    DemoDep = Annotated[data.Account, Depends(_demo)]

    @app.get("/api/accounts/{account_id}/execution")
    def execution(account: DemoDep, ledger: LedgerDep):
        return data.execution(account, ledger)

    @app.get("/api/accounts/{account_id}/mirror")
    def mirror(account: DemoDep, ledger: LedgerDep, limit: Limit = 500):
        with _open(accounts["intraday"]) as source:
            return data.mirror(account, ledger, source, limit)

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


async def _market_unavailable(request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        {"detail": f"行情暂不可用（OKX）：{type(exc).__name__}: {str(exc)[:200]}"}, status_code=503
    )


def _since_ms(since: datetime | None) -> int:
    if since is None:
        return 0
    if since.tzinfo is None:
        since = since.replace(tzinfo=UTC)
    return int(since.timestamp() * 1000)


def _validated(choice: LLMChoice) -> tuple[dict, dict[str, tuple[float, float]]]:
    """The ``llm`` and ``prices`` of a confirmed choice, as overrides.save takes them.

    400 when the choice is not confirmed, a model id is empty, a provider has no API key
    in the environment, or a price is negative or missing: a null price takes the
    official one and a model the table lacks must be priced by hand.
    """
    if not choice.confirm:
        raise HTTPException(400, "切换需要确认（confirm: true）")
    llm: dict = {}
    chosen: dict[str, tuple[float, float]] = {}
    for tier in ("deep", "quick"):
        pick: TierChoice = getattr(choice, tier)
        model, provider = pick.model.strip(), pick.provider.strip().lower()
        if not model:
            raise HTTPException(400, f"{tier} 档的模型 ID 为空")
        if not data.has_key(provider):
            raise HTTPException(400, f"provider {provider or '(空)'} 没有配置 API 密钥")
        price = pick.price
        if price is None:
            official = prices.lookup(model)
            price = (official.input, official.output) if official else None
        if price is None:
            raise HTTPException(400, f"{model} 缺少单价：定价表里没有，需要手填")
        if min(price) < 0:
            raise HTTPException(400, f"{model} 的单价不能为负")
        llm[f"{tier}_think_llm"], llm[f"{tier}_think_provider"] = model, provider
        chosen[model] = price
    return llm, chosen
