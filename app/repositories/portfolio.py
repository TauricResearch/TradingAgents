"""Repository for the paper account, positions (paper + real), and trades."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import PaperAccount, Position, Trade


class PortfolioRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    # --- accounts (books) ---

    async def get_account(self, label: str = "strategic") -> PaperAccount | None:
        result = await self._session.execute(
            select(PaperAccount).where(PaperAccount.label == label).limit(1)
        )
        account = result.scalar_one_or_none()
        if account is None and label == "strategic":
            # Pre-label rows have label defaulted by the migration; belt and braces.
            result = await self._session.execute(select(PaperAccount).limit(1))
            account = result.scalar_one_or_none()
        return account

    async def create_account(self, starting_cash: float, label: str = "strategic") -> PaperAccount:
        account = PaperAccount(label=label, starting_cash=starting_cash, cash=starting_cash)
        self._session.add(account)
        await self._session.flush()
        return account

    async def list_accounts(self) -> list[PaperAccount]:
        result = await self._session.execute(select(PaperAccount).order_by(PaperAccount.id))
        return list(result.scalars())

    # --- positions ---

    async def list_positions(self, account_type: str | None = None) -> list[Position]:
        stmt = select(Position).order_by(Position.symbol)
        if account_type:
            stmt = stmt.where(Position.account_type == account_type)
        result = await self._session.execute(stmt)
        return list(result.scalars())

    async def get_position(self, account_type: str, symbol: str) -> Position | None:
        result = await self._session.execute(
            select(Position).where(
                Position.account_type == account_type,
                Position.symbol == symbol.upper(),
            )
        )
        return result.scalar_one_or_none()

    async def get_position_by_id(self, position_id: int) -> Position | None:
        return await self._session.get(Position, position_id)

    async def add_position(self, position: Position) -> Position:
        self._session.add(position)
        await self._session.flush()
        return position

    async def remove_position(self, position: Position) -> None:
        await self._session.delete(position)

    # --- trades ---

    async def add_trade(self, trade: Trade) -> Trade:
        self._session.add(trade)
        await self._session.flush()
        return trade

    async def list_trades(
        self, limit: int | None = 100, account_type: str | None = None
    ) -> list[Trade]:
        """Newest first. ``limit=None`` returns every trade.

        Callers that total something (realised P&L, win counts) must pass None:
        a cap there silently understates the answer instead of failing.
        """
        query = select(Trade)
        if account_type is not None:
            query = query.where(Trade.account_type == account_type)
        query = query.order_by(Trade.executed_at.desc())
        if limit is not None:
            query = query.limit(limit)
        result = await self._session.execute(query)
        return list(result.scalars())

    # --- equity snapshots ---

    async def record_snapshot(self, book: str, snapshot_date: str, equity_usd: float) -> None:
        from app.models.entities import EquitySnapshot

        existing = await self._session.execute(
            select(EquitySnapshot).where(
                EquitySnapshot.book == book,
                EquitySnapshot.snapshot_date == snapshot_date,
            )
        )
        row = existing.scalar_one_or_none()
        if row is not None:
            row.equity_usd = equity_usd
        else:
            self._session.add(EquitySnapshot(
                book=book, snapshot_date=snapshot_date, equity_usd=equity_usd
            ))

    async def list_snapshots(self, book: str, limit: int = 90) -> list:
        from app.models.entities import EquitySnapshot

        result = await self._session.execute(
            select(EquitySnapshot)
            .where(EquitySnapshot.book == book)
            .order_by(EquitySnapshot.snapshot_date.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))
