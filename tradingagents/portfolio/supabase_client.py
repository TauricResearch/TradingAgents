"""PostgreSQL database client for the Portfolio Manager.

Uses ``psycopg2`` with the ``SUPABASE_CONNECTION_STRING`` env var to talk
directly to the Supabase-hosted PostgreSQL database. No ORM — see
``docs/agent/decisions/012-portfolio-no-orm.md`` for rationale.

Usage::

    from tradingagents.portfolio.supabase_client import SupabaseClient

    client = SupabaseClient.get_instance()
    portfolio = client.get_portfolio("some-uuid")
"""

from __future__ import annotations

import json
import uuid

import psycopg2
import psycopg2.extras

from tradingagents.portfolio.config import get_portfolio_config
from tradingagents.portfolio.exceptions import (
    DuplicatePortfolioError,
    HoldingNotFoundError,
    PortfolioError,
    PortfolioNotFoundError,
)
from tradingagents.portfolio.models import (
    Holding,
    Portfolio,
    PortfolioSnapshot,
    Trade,
)


class SupabaseClient:
    """Singleton PostgreSQL CRUD client for portfolio data.

    All public methods translate database errors into domain exceptions
    and return typed model instances.
    """

    _instance: SupabaseClient | None = None

    def __init__(self, connection_string: str) -> None:
        self._dsn = self._fix_dsn(connection_string)
        self._conn = psycopg2.connect(self._dsn)
        self._conn.autocommit = True

    @staticmethod
    def _fix_dsn(dsn: str) -> str:
        """URL-encode the password if it contains special characters."""
        from urllib.parse import quote
        if "://" not in dsn:
            return dsn  # already key=value format
        scheme, rest = dsn.split("://", 1)
        at_idx = rest.rfind("@")
        if at_idx == -1:
            return dsn
        userinfo = rest[:at_idx]
        hostinfo = rest[at_idx + 1:]
        colon_idx = userinfo.find(":")
        if colon_idx == -1:
            return dsn
        user = userinfo[:colon_idx]
        password = userinfo[colon_idx + 1:]
        encoded = quote(password, safe="")
        return f"{scheme}://{user}:{encoded}@{hostinfo}"

    @classmethod
    def get_instance(cls) -> SupabaseClient:
        """Return the singleton instance, creating it if necessary."""
        if cls._instance is None:
            cfg = get_portfolio_config()
            dsn = cfg["supabase_connection_string"]
            if not dsn:
                raise PortfolioError(
                    "SUPABASE_CONNECTION_STRING not configured. "
                    "Set it in .env or as an environment variable."
                )
            cls._instance = cls(dsn)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Close and reset the singleton (for testing)."""
        if cls._instance is not None:
            try:
                cls._instance._conn.close()
            except Exception:
                pass
            cls._instance = None

    def _cursor(self):
        """Return a RealDictCursor, reconnecting if the connection was dropped."""
        if self._conn.closed:
            self._conn = psycopg2.connect(self._dsn)
            self._conn.autocommit = True
        return self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # ------------------------------------------------------------------
    # Portfolio CRUD
    # ------------------------------------------------------------------

    def create_portfolio(self, portfolio: Portfolio) -> Portfolio:
        """Insert a new portfolio row."""
        pid = portfolio.portfolio_id or str(uuid.uuid4())
        try:
            with self._cursor() as cur:
                cur.execute(
                    """INSERT INTO portfolios
                       (portfolio_id, name, cash, initial_cash, currency, report_path, metadata)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)
                       RETURNING *""",
                    (pid, portfolio.name, portfolio.cash, portfolio.initial_cash,
                     portfolio.currency, portfolio.report_path,
                     json.dumps(portfolio.metadata)),
                )
                row = cur.fetchone()
        except psycopg2.errors.UniqueViolation as exc:
            raise DuplicatePortfolioError(f"Portfolio already exists: {pid}") from exc
        return self._row_to_portfolio(row)

    def get_portfolio(self, portfolio_id: str) -> Portfolio:
        """Fetch a portfolio by ID."""
        with self._cursor() as cur:
            cur.execute("SELECT * FROM portfolios WHERE portfolio_id = %s", (portfolio_id,))
            row = cur.fetchone()
        if not row:
            raise PortfolioNotFoundError(f"Portfolio not found: {portfolio_id}")
        return self._row_to_portfolio(row)

    def list_portfolios(self) -> list[Portfolio]:
        """Return all portfolios ordered by created_at DESC."""
        with self._cursor() as cur:
            cur.execute("SELECT * FROM portfolios ORDER BY created_at DESC")
            rows = cur.fetchall()
        return [self._row_to_portfolio(r) for r in rows]

    def update_portfolio(self, portfolio: Portfolio) -> Portfolio:
        """Update mutable portfolio fields (cash, report_path, metadata)."""
        with self._cursor() as cur:
            cur.execute(
                """UPDATE portfolios
                   SET cash = %s, report_path = %s, metadata = %s
                   WHERE portfolio_id = %s
                   RETURNING *""",
                (portfolio.cash, portfolio.report_path,
                 json.dumps(portfolio.metadata), portfolio.portfolio_id),
            )
            row = cur.fetchone()
        if not row:
            raise PortfolioNotFoundError(f"Portfolio not found: {portfolio.portfolio_id}")
        return self._row_to_portfolio(row)

    def delete_portfolio(self, portfolio_id: str) -> None:
        """Delete a portfolio and all associated data (CASCADE)."""
        with self._cursor() as cur:
            cur.execute(
                "DELETE FROM portfolios WHERE portfolio_id = %s RETURNING portfolio_id",
                (portfolio_id,),
            )
            row = cur.fetchone()
        if not row:
            raise PortfolioNotFoundError(f"Portfolio not found: {portfolio_id}")

    # ------------------------------------------------------------------
    # Holdings CRUD
    # ------------------------------------------------------------------

    def upsert_holding(self, holding: Holding) -> Holding:
        """Insert or update a holding row (upsert on portfolio_id + ticker)."""
        hid = holding.holding_id or str(uuid.uuid4())
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO holdings
                   (holding_id, portfolio_id, ticker, shares, avg_cost, sector, industry)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT ON CONSTRAINT holdings_portfolio_ticker_unique
                   DO UPDATE SET shares = EXCLUDED.shares,
                                 avg_cost = EXCLUDED.avg_cost,
                                 sector = EXCLUDED.sector,
                                 industry = EXCLUDED.industry
                   RETURNING *""",
                (hid, holding.portfolio_id, holding.ticker.upper(),
                 holding.shares, holding.avg_cost, holding.sector, holding.industry),
            )
            row = cur.fetchone()
        return self._row_to_holding(row)

    def get_holding(self, portfolio_id: str, ticker: str) -> Holding | None:
        """Return the holding for (portfolio_id, ticker), or None."""
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM holdings WHERE portfolio_id = %s AND ticker = %s",
                (portfolio_id, ticker.upper()),
            )
            row = cur.fetchone()
        return self._row_to_holding(row) if row else None

    def list_holdings(self, portfolio_id: str) -> list[Holding]:
        """Return all holdings for a portfolio ordered by cost_basis DESC."""
        with self._cursor() as cur:
            cur.execute(
                """SELECT * FROM holdings
                   WHERE portfolio_id = %s
                   ORDER BY shares * avg_cost DESC""",
                (portfolio_id,),
            )
            rows = cur.fetchall()
        return [self._row_to_holding(r) for r in rows]

    def delete_holding(self, portfolio_id: str, ticker: str) -> None:
        """Delete the holding for (portfolio_id, ticker)."""
        with self._cursor() as cur:
            cur.execute(
                "DELETE FROM holdings WHERE portfolio_id = %s AND ticker = %s RETURNING holding_id",
                (portfolio_id, ticker.upper()),
            )
            row = cur.fetchone()
        if not row:
            raise HoldingNotFoundError(
                f"Holding not found: {ticker} in portfolio {portfolio_id}"
            )


    def batch_upsert_holdings(self, holdings: list[Holding]) -> None:
        if not holdings:
            return
        query = '''
            INSERT INTO holdings
            (holding_id, portfolio_id, ticker, shares, avg_cost, sector, industry)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT ON CONSTRAINT holdings_portfolio_ticker_unique
            DO UPDATE SET shares = EXCLUDED.shares,
                          avg_cost = EXCLUDED.avg_cost,
                          sector = EXCLUDED.sector,
                          industry = EXCLUDED.industry
        '''
        params = [
            (h.holding_id or str(uuid.uuid4()), h.portfolio_id, h.ticker.upper(), h.shares, h.avg_cost, h.sector, h.industry)
            for h in holdings
        ]
        with self._cursor() as cur:
            psycopg2.extras.execute_batch(cur, query, params)

    def batch_delete_holdings(self, portfolio_id: str, tickers: list[str]) -> None:
        if not tickers:
            return
        query = "DELETE FROM holdings WHERE portfolio_id = %s AND ticker = %s"
        params = [(portfolio_id, ticker.upper()) for ticker in tickers]
        with self._cursor() as cur:
            psycopg2.extras.execute_batch(cur, query, params)

    # ------------------------------------------------------------------
    # Trades
    # ------------------------------------------------------------------

    def record_trade(self, trade: Trade) -> Trade:
        """Insert a new trade record."""
        tid = trade.trade_id or str(uuid.uuid4())
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO trades
                   (trade_id, portfolio_id, ticker, action, shares, price,
                    total_value, rationale, signal_source, metadata)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING *""",
                (tid, trade.portfolio_id, trade.ticker, trade.action,
                 trade.shares, trade.price, trade.total_value,
                 trade.rationale, trade.signal_source,
                 json.dumps(trade.metadata)),
            )
            row = cur.fetchone()
        return self._row_to_trade(row)

    def list_trades(
        self,
        portfolio_id: str,
        ticker: str | None = None,
        limit: int = 100,
    ) -> list[Trade]:
        """Return recent trades for a portfolio, newest first."""
        if ticker:
            query = """SELECT * FROM trades
                       WHERE portfolio_id = %s AND ticker = %s
                       ORDER BY trade_date DESC LIMIT %s"""
            params = (portfolio_id, ticker.upper(), limit)
        else:
            query = """SELECT * FROM trades
                       WHERE portfolio_id = %s
                       ORDER BY trade_date DESC LIMIT %s"""
            params = (portfolio_id, limit)
        with self._cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
        return [self._row_to_trade(r) for r in rows]


    def batch_record_trades(self, trades: list[Trade]) -> None:
        if not trades:
            return
        query = '''
            INSERT INTO trades
            (trade_id, portfolio_id, ticker, action, shares, price,
             total_value, rationale, signal_source, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        '''
        params = [
            (t.trade_id or str(uuid.uuid4()), t.portfolio_id, t.ticker, t.action,
             t.shares, t.price, t.total_value, t.rationale, t.signal_source,
             json.dumps(t.metadata))
            for t in trades
        ]
        with self._cursor() as cur:
            psycopg2.extras.execute_batch(cur, query, params)

    # ------------------------------------------------------------------
    # Snapshots
    # ------------------------------------------------------------------

    def save_snapshot(self, snapshot: PortfolioSnapshot) -> PortfolioSnapshot:
        """Insert a new immutable portfolio snapshot."""
        sid = snapshot.snapshot_id or str(uuid.uuid4())
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO snapshots
                   (snapshot_id, portfolio_id, total_value, cash, equity_value,
                    num_positions, holdings_snapshot, metadata)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING *""",
                (sid, snapshot.portfolio_id, snapshot.total_value,
                 snapshot.cash, snapshot.equity_value, snapshot.num_positions,
                 json.dumps(snapshot.holdings_snapshot),
                 json.dumps(snapshot.metadata)),
            )
            row = cur.fetchone()
        return self._row_to_snapshot(row)

    def get_latest_snapshot(self, portfolio_id: str) -> PortfolioSnapshot | None:
        """Return the most recent snapshot for a portfolio, or None."""
        with self._cursor() as cur:
            cur.execute(
                """SELECT * FROM snapshots
                   WHERE portfolio_id = %s
                   ORDER BY snapshot_date DESC LIMIT 1""",
                (portfolio_id,),
            )
            row = cur.fetchone()
        return self._row_to_snapshot(row) if row else None

    def list_snapshots(
        self,
        portfolio_id: str,
        limit: int = 30,
    ) -> list[PortfolioSnapshot]:
        """Return snapshots newest-first up to limit."""
        with self._cursor() as cur:
            cur.execute(
                """SELECT * FROM snapshots
                   WHERE portfolio_id = %s
                   ORDER BY snapshot_date DESC LIMIT %s""",
                (portfolio_id, limit),
            )
            rows = cur.fetchall()
        return [self._row_to_snapshot(r) for r in rows]

    # ------------------------------------------------------------------
    # Row -> Model helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_portfolio(row: dict) -> Portfolio:
        metadata = row.get("metadata") or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        return Portfolio(
            portfolio_id=str(row["portfolio_id"]),
            name=row["name"],
            cash=float(row["cash"]),
            initial_cash=float(row["initial_cash"]),
            currency=row["currency"].strip(),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            report_path=row.get("report_path"),
            metadata=metadata,
        )

    @staticmethod
    def _row_to_holding(row: dict) -> Holding:
        return Holding(
            holding_id=str(row["holding_id"]),
            portfolio_id=str(row["portfolio_id"]),
            ticker=row["ticker"],
            shares=float(row["shares"]),
            avg_cost=float(row["avg_cost"]),
            sector=row.get("sector"),
            industry=row.get("industry"),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _row_to_trade(row: dict) -> Trade:
        metadata = row.get("metadata") or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        return Trade(
            trade_id=str(row["trade_id"]),
            portfolio_id=str(row["portfolio_id"]),
            ticker=row["ticker"],
            action=row["action"],
            shares=float(row["shares"]),
            price=float(row["price"]),
            total_value=float(row["total_value"]),
            trade_date=str(row["trade_date"]),
            rationale=row.get("rationale"),
            signal_source=row.get("signal_source"),
            metadata=metadata,
        )

    @staticmethod
    def _row_to_snapshot(row: dict) -> PortfolioSnapshot:
        holdings = row.get("holdings_snapshot") or []
        if isinstance(holdings, str):
            holdings = json.loads(holdings)
        metadata = row.get("metadata") or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        return PortfolioSnapshot(
            snapshot_id=str(row["snapshot_id"]),
            portfolio_id=str(row["portfolio_id"]),
            snapshot_date=str(row["snapshot_date"]),
            total_value=float(row["total_value"]),
            cash=float(row["cash"]),
            equity_value=float(row["equity_value"]),
            num_positions=int(row["num_positions"]),
            holdings_snapshot=holdings,
            metadata=metadata,
        )
