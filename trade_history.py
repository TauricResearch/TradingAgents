"""
매매 이력 관리 (SQLite)
- 매수/매도 기록 저장
- 누적 수익률 조회
- 통화별 수익 요약
- 일일 상태 관리 (재시작 중복 방지)
"""

import datetime
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "trade_history.db"


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == column for r in rows)


def _migrate_schema(conn: sqlite3.Connection):
    """기존 DB에 누락 컬럼을 idempotent하게 추가."""
    if not _has_column(conn, "trades", "market"):
        conn.execute("ALTER TABLE trades ADD COLUMN market TEXT NOT NULL DEFAULT 'KR'")
    if not _has_column(conn, "trades", "currency"):
        conn.execute("ALTER TABLE trades ADD COLUMN currency TEXT NOT NULL DEFAULT 'KRW'")
    if not _has_column(conn, "pnl_log", "market"):
        conn.execute("ALTER TABLE pnl_log ADD COLUMN market TEXT NOT NULL DEFAULT 'KR'")
    if not _has_column(conn, "pnl_log", "currency"):
        conn.execute("ALTER TABLE pnl_log ADD COLUMN currency TEXT NOT NULL DEFAULT 'KRW'")


def init_db():
    """테이블 생성 (최초 1회) + 스키마 마이그레이션."""
    conn = _get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS trades (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker      TEXT NOT NULL,
            name        TEXT NOT NULL DEFAULT '',
            side        TEXT NOT NULL CHECK(side IN ('BUY', 'SELL')),
            qty         INTEGER NOT NULL,
            price       REAL NOT NULL,
            amount      REAL NOT NULL,
            market      TEXT NOT NULL DEFAULT 'KR',
            currency    TEXT NOT NULL DEFAULT 'KRW',
            order_no    TEXT DEFAULT '',
            reason      TEXT DEFAULT '',
            created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS pnl_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker      TEXT NOT NULL,
            name        TEXT NOT NULL DEFAULT '',
            buy_price   REAL NOT NULL,
            sell_price  REAL NOT NULL,
            qty         INTEGER NOT NULL,
            pnl         REAL NOT NULL,
            pnl_rate    REAL NOT NULL,
            market      TEXT NOT NULL DEFAULT 'KR',
            currency    TEXT NOT NULL DEFAULT 'KRW',
            created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS daily_state (
            date         TEXT NOT NULL,
            action       TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            details      TEXT DEFAULT '',
            PRIMARY KEY (date, action)
        );

        CREATE TABLE IF NOT EXISTS pnl_resets (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            currency    TEXT DEFAULT NULL,
            reset_by    TEXT DEFAULT '',
            reason      TEXT DEFAULT '',
            created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS budget_anchor (
            market       TEXT PRIMARY KEY,
            anchor_amount REAL NOT NULL DEFAULT 0,
            updated_at   TEXT NOT NULL
        );
    """
    )

    _migrate_schema(conn)
    conn.commit()
    conn.close()


def record_trade(
    ticker: str,
    name: str,
    side: str,
    qty: int,
    price: float,
    order_no: str = "",
    reason: str = "",
    market: str = "KR",
    currency: str = "KRW",
):
    """매수/매도 기록 저장."""
    side = side.upper()
    market = (market or "KR").upper()
    currency = (currency or "KRW").upper()
    px = float(price)
    amount = float(qty) * px

    conn = _get_conn()
    conn.execute(
        """INSERT INTO trades
           (ticker, name, side, qty, price, amount, market, currency, order_no, reason)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (ticker, name, side, qty, px, amount, market, currency, order_no, reason),
    )
    conn.commit()
    conn.close()


def record_pnl(
    ticker: str,
    name: str,
    buy_price: float,
    sell_price: float,
    qty: int,
    market: str = "KR",
    currency: str = "KRW",
):
    """실현 손익 기록."""
    buy_px = float(buy_price)
    sell_px = float(sell_price)
    pnl = (sell_px - buy_px) * qty
    pnl_rate = ((sell_px - buy_px) / buy_px * 100) if buy_px > 0 else 0.0
    market = (market or "KR").upper()
    currency = (currency or "KRW").upper()

    conn = _get_conn()
    conn.execute(
        """INSERT INTO pnl_log
           (ticker, name, buy_price, sell_price, qty, pnl, pnl_rate, market, currency)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (ticker, name, buy_px, sell_px, qty, pnl, round(pnl_rate, 2), market, currency),
    )
    conn.commit()
    conn.close()


def _aggregate_pnl(
    market: str | None = None,
    currency: str | None = None,
) -> dict:
    conn = _get_conn()
    where_clause, params = _build_pnl_where_clause(conn, market=market, currency=currency)
    row = conn.execute(
        f"""SELECT
             COALESCE(SUM(pnl), 0) as total_pnl,
             COUNT(*) as trade_count,
             COALESCE(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END), 0) as win_count,
             COALESCE(SUM(CASE WHEN pnl <= 0 THEN 1 ELSE 0 END), 0) as loss_count
           FROM pnl_log
           {where_clause}""",
        params,
    ).fetchone()
    conn.close()

    total = float(row["total_pnl"])
    count = int(row["trade_count"])
    win = int(row["win_count"])
    loss = int(row["loss_count"])
    win_rate = (win / count * 100) if count > 0 else 0.0

    return {
        "total_pnl": total,
        "trade_count": count,
        "win_count": win,
        "loss_count": loss,
        "win_rate": round(win_rate, 1),
    }


def _get_pnl_reset_cutoff(
    conn: sqlite3.Connection,
    currency: str | None = None,
) -> str | None:
    target_currency = (currency or "").upper() or None
    if target_currency:
        row = conn.execute(
            """
            SELECT MAX(created_at) AS cutoff
            FROM pnl_resets
            WHERE currency IS NULL OR currency = ?
            """,
            (target_currency,),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT MAX(created_at) AS cutoff
            FROM pnl_resets
            WHERE currency IS NULL
            """
        ).fetchone()

    cutoff = row["cutoff"] if row else None
    return str(cutoff) if cutoff else None


def _build_pnl_where_clause(
    conn: sqlite3.Connection,
    market: str | None = None,
    currency: str | None = None,
) -> tuple[str, list[object]]:
    conditions: list[str] = []
    params: list[object] = []
    if market:
        conditions.append("market = ?")
        params.append(market.upper())
    if currency:
        conditions.append("currency = ?")
        params.append(currency.upper())

    cutoff = _get_pnl_reset_cutoff(conn, currency=currency)
    if cutoff:
        conditions.append("created_at > ?")
        params.append(cutoff)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return where_clause, params


def get_total_pnl(
    market: str | None = None,
    currency: str | None = None,
) -> dict:
    """누적 수익 요약 (기존 호환: 인자 없이 전체 반환)."""
    return _aggregate_pnl(market=market, currency=currency)


def get_total_pnl_by_currency() -> dict[str, dict]:
    """통화별 누적 수익 요약."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT DISTINCT currency FROM pnl_log ORDER BY currency"
    ).fetchall()
    conn.close()

    currencies = [r["currency"] for r in rows] or ["KRW", "USD"]
    result: dict[str, dict] = {}
    for cur in currencies:
        result[cur] = _aggregate_pnl(currency=cur)
    return result


def get_recent_trades(
    limit: int = 20,
    market: str | None = None,
    currency: str | None = None,
) -> list[dict]:
    """최근 매매 이력."""
    conn = _get_conn()
    conditions: list[str] = []
    params: list[object] = []
    if market:
        conditions.append("market = ?")
        params.append(market.upper())
    if currency:
        conditions.append("currency = ?")
        params.append(currency.upper())
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)
    rows = conn.execute(
        f"SELECT * FROM trades {where_clause} ORDER BY id DESC LIMIT ?", params
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_pnl(
    limit: int = 20,
    market: str | None = None,
    currency: str | None = None,
) -> list[dict]:
    """최근 실현손익."""
    conn = _get_conn()
    where_clause, params = _build_pnl_where_clause(conn, market=market, currency=currency)
    params.append(limit)
    rows = conn.execute(
        f"SELECT * FROM pnl_log {where_clause} ORDER BY id DESC LIMIT ?", params
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_ticker_summary(
    market: str | None = None,
    currency: str | None = None,
) -> list[dict]:
    """종목별 누적 수익 요약."""
    conn = _get_conn()
    where_clause, params = _build_pnl_where_clause(conn, market=market, currency=currency)
    rows = conn.execute(
        f"""SELECT
             ticker, name, market, currency,
             COUNT(*) as count,
             SUM(pnl) as total_pnl,
             AVG(pnl_rate) as avg_pnl_rate
           FROM pnl_log
           {where_clause}
           GROUP BY ticker, name, market, currency
           ORDER BY total_pnl DESC""",
        params,
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def reset_pnl_history(
    currency: str | None = None,
    reset_by: str = "",
    reason: str = "",
) -> str:
    """실현손익 집계 기준 시점을 기록한다.

    기존 손익 로그는 보존하고, 이후 조회 시 마지막 초기화 시점 이후 데이터만 집계한다.
    """
    target_currency = (currency or "").upper() or None
    reset_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = _get_conn()
    conn.execute(
        """
        INSERT INTO pnl_resets (currency, reset_by, reason, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (target_currency, reset_by, reason, reset_at),
    )
    conn.commit()
    conn.close()
    return reset_at


# ─── 일일 상태 관리 (재시작 중복 방지) ─────────────────────
def is_action_done(action: str, date: str | None = None) -> bool:
    """오늘 해당 액션이 이미 완료되었는지 확인.

    Args:
        action: 'morning_buy', 'afternoon_sell', 'us_morning_buy' 등
        date: 날짜 (기본: 오늘)
    """
    if date is None:
        date = datetime.date.today().isoformat()
    conn = _get_conn()
    row = conn.execute(
        "SELECT 1 FROM daily_state WHERE date = ? AND action = ?",
        (date, action),
    ).fetchone()
    conn.close()
    return row is not None


def mark_action_done(action: str, details: str = "", date: str | None = None):
    """해당 액션을 완료로 표시."""
    if date is None:
        date = datetime.date.today().isoformat()
    now = datetime.datetime.now().isoformat()
    conn = _get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO daily_state (date, action, completed_at, details) VALUES (?, ?, ?, ?)",
        (date, action, now, details),
    )
    conn.commit()
    conn.close()


def get_daily_state(date: str | None = None) -> list[dict]:
    """오늘 완료된 모든 액션 조회."""
    if date is None:
        date = datetime.date.today().isoformat()
    conn = _get_conn()
    rows = conn.execute(
        "SELECT action, completed_at, details FROM daily_state WHERE date = ? ORDER BY completed_at",
        (date,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_budget_anchor(market: str = "KR") -> float:
    """시장별 자동매수 기준 자금(anchor) 조회."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT anchor_amount FROM budget_anchor WHERE market = ?",
        ((market or "KR").upper(),),
    ).fetchone()
    conn.close()
    return float(row["anchor_amount"]) if row else 0.0


def set_budget_anchor(market: str, anchor_amount: float) -> float:
    """시장별 자동매수 기준 자금을 저장한다."""
    market = (market or "KR").upper()
    amount = max(float(anchor_amount), 0.0)
    now = datetime.datetime.now().isoformat()

    conn = _get_conn()
    conn.execute(
        """
        INSERT INTO budget_anchor (market, anchor_amount, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(market) DO UPDATE SET
            anchor_amount = excluded.anchor_amount,
            updated_at = excluded.updated_at
        """,
        (market, amount, now),
    )
    conn.commit()
    conn.close()
    return amount


def ensure_budget_anchor(market: str, available_cash: float) -> float:
    """기준 자금이 없으면 현재 예수금으로 초기화하고, 더 큰 값이 들어오면 상향 반영한다."""
    market = (market or "KR").upper()
    cash = max(float(available_cash), 0.0)
    current = get_budget_anchor(market)

    if cash > 0 and (current <= 0 or cash > current):
        return set_budget_anchor(market, cash)
    return current


# 모듈 로드 시 DB 초기화
init_db()
