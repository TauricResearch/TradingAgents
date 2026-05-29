"""SQLite database schema and operations for mock trading system."""

import sqlite3
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)


class TradingDatabase:
    """Manage SQLite database for mock trading system."""
    
    def __init__(self, db_path: str = None):
        """Initialize database connection.
        
        Args:
            db_path: Path to SQLite database file. Defaults to ~/.tradingagents/mock_trading.db
        """
        if db_path is None:
            db_path = Path.home() / ".tradingagents" / "mock_trading.db"
        elif db_path == ":memory:":
            db_path = ":memory:"
        else:
            db_path = Path(db_path)
        
        if db_path != ":memory:":
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self.db_path = str(db_path)
        else:
            self.db_path = ":memory:"
            
        self._local = threading.local()
        self.init_schema()
        logger.info(f"Database schema initialized (path: {self.db_path})")

    @property
    def conn(self):
        """Thread-safe connection getter. Uses shared connection for :memory: database to support tests."""
        if self.db_path == ":memory:":
            if not hasattr(self, "_shared_conn") or self._shared_conn is None:
                self._shared_conn = sqlite3.connect(self.db_path, check_same_thread=False)
                self._shared_conn.row_factory = sqlite3.Row
            return self._shared_conn
            
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return self._local.conn

    @property
    def cursor(self):
        """Thread-safe cursor getter."""
        if self.db_path == ":memory:":
            if not hasattr(self, "_shared_cursor") or self._shared_cursor is None:
                self._shared_cursor = self.conn.cursor()
            return self._shared_cursor
            
        if not hasattr(self._local, "cursor") or self._local.cursor is None:
            self._local.cursor = self.conn.cursor()
        return self._local.cursor
    
    def connect(self):
        """No-op for backward compatibility. Connections are created lazily per thread."""
        pass
    
    def close(self):
        """Close database connection for the current thread."""
        if self.db_path == ":memory:":
            if hasattr(self, "_shared_conn") and self._shared_conn is not None:
                self._shared_conn.close()
                self._shared_conn = None
                self._shared_cursor = None
                logger.info("Shared database connection closed")
            return
            
        if hasattr(self._local, "conn") and self._local.conn is not None:
            try:
                self._local.conn.close()
            except Exception:
                pass
            self._local.conn = None
            self._local.cursor = None
            logger.info("Thread database connection closed")
            
    @contextmanager
    def transaction(self):
        """SQL transaction context manager that commits on success or rolls back on error."""
        conn = self.conn
        try:
            yield self.cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database transaction rolled back due to error: {e}")
            raise e
    
    def init_schema(self):
        """Initialize database schema with all tables."""
        self.cursor.executescript("""
            -- Portfolios: Track active trading portfolio
            CREATE TABLE IF NOT EXISTS portfolios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                initial_capital REAL NOT NULL,
                current_balance REAL NOT NULL,
                cash_available REAL NOT NULL,
                date_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                date_last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'active' CHECK (status IN ('active', 'paused', 'closed')),
                UNIQUE(id)
            );
            
            -- Transactions: Log all buy/sell operations
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portfolio_id INTEGER NOT NULL,
                transaction_type TEXT NOT NULL CHECK (transaction_type IN ('BUY', 'SELL')),
                ticker TEXT NOT NULL,
                quantity_requested REAL NOT NULL,
                quantity_filled REAL NOT NULL,
                order_status TEXT DEFAULT 'PENDING' CHECK (order_status IN ('PENDING', 'FILLED', 'PARTIALLY_FILLED', 'REJECTED')),
                price_type TEXT NOT NULL CHECK (price_type IN ('OPEN', 'CLOSE', 'VWAP', 'LAST')),
                price_per_share REAL NOT NULL,
                total_value REAL NOT NULL,
                slippage_pct REAL DEFAULT 0.0,
                fees REAL DEFAULT 0.0,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                execution_timestamp TIMESTAMP,
                expiry_timestamp TIMESTAMP,
                ai_decision_id INTEGER,
                notes TEXT,
                FOREIGN KEY (portfolio_id) REFERENCES portfolios(id),
                FOREIGN KEY (ai_decision_id) REFERENCES ai_decisions(id)
            );
            
            -- Holdings: Current stock positions
            CREATE TABLE IF NOT EXISTS holdings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portfolio_id INTEGER NOT NULL,
                ticker TEXT NOT NULL,
                quantity_held REAL NOT NULL,
                avg_buy_price REAL NOT NULL,
                current_price REAL NOT NULL,
                unrealized_pl REAL NOT NULL,
                quantity_adjusted REAL DEFAULT 0.0,
                split_ratio REAL DEFAULT 1.0,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_split_date TIMESTAMP,
                FOREIGN KEY (portfolio_id) REFERENCES portfolios(id),
                UNIQUE(portfolio_id, ticker)
            );
            
            -- Daily Snapshots: End-of-day portfolio state
            CREATE TABLE IF NOT EXISTS daily_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portfolio_id INTEGER NOT NULL,
                date DATE NOT NULL,
                total_portfolio_value REAL NOT NULL,
                cash_balance REAL NOT NULL,
                total_invested REAL NOT NULL,
                daily_return REAL DEFAULT 0.0,
                cumulative_return REAL DEFAULT 0.0,
                dividend_income REAL DEFAULT 0.0,
                benchmark_return REAL DEFAULT 0.0,
                alpha REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (portfolio_id) REFERENCES portfolios(id),
                UNIQUE(portfolio_id, date)
            );
            
            -- AI Decisions: Trading signals from TradingAgentsGraph
            CREATE TABLE IF NOT EXISTS ai_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portfolio_id INTEGER NOT NULL,
                ticker TEXT NOT NULL,
                decision TEXT NOT NULL CHECK (decision IN ('BUY', 'SELL', 'HOLD')),
                confidence_score REAL DEFAULT 0.5,
                reasoning TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                analysis_start_time TIMESTAMP,
                analysis_end_time TIMESTAMP,
                executed BOOLEAN DEFAULT 0,
                execution_status TEXT CHECK (execution_status IS NULL OR execution_status IN ('FILLED', 'PARTIAL', 'REJECTED')),
                execution_price REAL,
                realized_pl REAL,
                reward_score REAL,
                reward_calculation_date TIMESTAMP,
                reward_type TEXT CHECK (reward_type IS NULL OR reward_type IN ('BENCHMARK_ALPHA', 'ABSOLUTE_RETURN', 'SHARPE_RATIO')),
                FOREIGN KEY (portfolio_id) REFERENCES portfolios(id)
            );
            
            -- Reflections: Hindsight RL learnings
            CREATE TABLE IF NOT EXISTS reflections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                decision_id INTEGER NOT NULL,
                reflection_text TEXT,
                lesson_learned TEXT,
                reward_achieved REAL,
                outperformed_benchmark BOOLEAN,
                improvement_suggested TEXT,
                date_reflected TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (decision_id) REFERENCES ai_decisions(id)
            );
            
            -- Corporate Actions: Stock splits, dividends
            CREATE TABLE IF NOT EXISTS corporate_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portfolio_id INTEGER NOT NULL,
                ticker TEXT NOT NULL,
                action_type TEXT NOT NULL CHECK (action_type IN ('STOCK_SPLIT', 'REVERSE_SPLIT', 'DIVIDEND')),
                action_date DATE NOT NULL,
                ratio REAL,
                dividend_per_share REAL,
                dividend_total REAL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (portfolio_id) REFERENCES portfolios(id)
            );
            
            -- Benchmark Data: SPY or other benchmark prices
            CREATE TABLE IF NOT EXISTS benchmark_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                benchmark_ticker TEXT DEFAULT 'SPY',
                date DATE NOT NULL,
                open REAL,
                close REAL,
                daily_return REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(benchmark_ticker, date)
            );
            
            -- Create indexes for common queries
            CREATE INDEX IF NOT EXISTS idx_transactions_portfolio ON transactions(portfolio_id);
            CREATE INDEX IF NOT EXISTS idx_transactions_ticker ON transactions(ticker);
            CREATE INDEX IF NOT EXISTS idx_transactions_timestamp ON transactions(timestamp);
            CREATE INDEX IF NOT EXISTS idx_holdings_portfolio ON holdings(portfolio_id);
            CREATE INDEX IF NOT EXISTS idx_holdings_ticker ON holdings(ticker);
            CREATE INDEX IF NOT EXISTS idx_daily_snapshots_portfolio ON daily_snapshots(portfolio_id);
            CREATE INDEX IF NOT EXISTS idx_daily_snapshots_date ON daily_snapshots(date);
            CREATE INDEX IF NOT EXISTS idx_ai_decisions_portfolio ON ai_decisions(portfolio_id);
            CREATE INDEX IF NOT EXISTS idx_ai_decisions_ticker ON ai_decisions(ticker);
            CREATE INDEX IF NOT EXISTS idx_reflections_decision ON reflections(decision_id);
        """)
        self.conn.commit()
        logger.info("Database schema initialized")
    
    def create_portfolio(self, initial_capital: float) -> int:
        """Create a new trading portfolio.
        
        Args:
            initial_capital: Starting capital in USD
            
        Returns:
            Portfolio ID
        """
        self.cursor.execute("""
            INSERT INTO portfolios (initial_capital, current_balance, cash_available)
            VALUES (?, ?, ?)
        """, (initial_capital, initial_capital, initial_capital))
        self.conn.commit()
        portfolio_id = self.cursor.lastrowid
        logger.info(f"Created portfolio {portfolio_id} with ${initial_capital}")
        return portfolio_id
    
    def add_transaction(self, portfolio_id: int, transaction_type: str, ticker: str,
                       quantity_requested: float, quantity_filled: float,
                       order_status: str, price_type: str, price_per_share: float,
                       total_value: float, slippage_pct: float = 0.0, fees: float = 0.0,
                       ai_decision_id: Optional[int] = None, notes: str = None) -> int:
        """Record a transaction.
        
        Args:
            portfolio_id: Portfolio ID
            transaction_type: 'BUY' or 'SELL'
            ticker: Stock ticker
            quantity_requested: Original quantity requested
            quantity_filled: Actual quantity filled
            order_status: 'PENDING', 'FILLED', 'PARTIALLY_FILLED', 'REJECTED'
            price_type: 'OPEN', 'CLOSE', 'VWAP', 'LAST'
            price_per_share: Execution price
            total_value: quantity_filled * price_per_share
            slippage_pct: Percentage difference from expected price
            fees: Trading fees
            ai_decision_id: Link to decision that triggered trade
            notes: Additional notes
            
        Returns:
            Transaction ID
        """
        execution_timestamp = datetime.now() if order_status in ('FILLED', 'PARTIALLY_FILLED') else None
        
        self.cursor.execute("""
            INSERT INTO transactions 
            (portfolio_id, transaction_type, ticker, quantity_requested, quantity_filled,
             order_status, price_type, price_per_share, total_value, slippage_pct, fees,
             execution_timestamp, ai_decision_id, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (portfolio_id, transaction_type, ticker, quantity_requested, quantity_filled,
              order_status, price_type, price_per_share, total_value, slippage_pct, fees,
              execution_timestamp, ai_decision_id, notes))
        self.conn.commit()
        return self.cursor.lastrowid
    
    def update_portfolio_balance(self, portfolio_id: int, new_balance: float, new_cash: float):
        """Update portfolio balance and cash.
        
        Args:
            portfolio_id: Portfolio ID
            new_balance: New total portfolio value
            new_cash: New cash available
        """
        self.cursor.execute("""
            UPDATE portfolios 
            SET current_balance = ?, cash_available = ?, date_last_updated = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (new_balance, new_cash, portfolio_id))
        self.conn.commit()
    
    def add_holding(self, portfolio_id: int, ticker: str, quantity: float,
                   avg_buy_price: float, current_price: float) -> int:
        """Add or update a holding.
        
        Args:
            portfolio_id: Portfolio ID
            ticker: Stock ticker
            quantity: Quantity held
            avg_buy_price: Average buy price
            current_price: Current market price
            
        Returns:
            Holding ID
        """
        unrealized_pl = (current_price - avg_buy_price) * quantity
        
        try:
            self.cursor.execute("""
                INSERT INTO holdings (portfolio_id, ticker, quantity_held, avg_buy_price, 
                                      current_price, unrealized_pl)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (portfolio_id, ticker, quantity, avg_buy_price, current_price, unrealized_pl))
            self.conn.commit()
            return self.cursor.lastrowid
        except sqlite3.IntegrityError:
            # Update existing
            self.cursor.execute("""
                UPDATE holdings 
                SET quantity_held = ?, avg_buy_price = ?, current_price = ?, unrealized_pl = ?,
                    last_updated = CURRENT_TIMESTAMP
                WHERE portfolio_id = ? AND ticker = ?
            """, (quantity, avg_buy_price, current_price, unrealized_pl, portfolio_id, ticker))
            self.conn.commit()
            return self.cursor.lastrowid
    
    def get_portfolio(self, portfolio_id: int) -> Dict:
        """Get portfolio details.
        
        Args:
            portfolio_id: Portfolio ID
            
        Returns:
            Portfolio dictionary
        """
        self.cursor.execute("SELECT * FROM portfolios WHERE id = ?", (portfolio_id,))
        row = self.cursor.fetchone()
        return dict(row) if row else None
    
    def get_holdings(self, portfolio_id: int) -> List[Dict]:
        """Get all holdings for portfolio.
        
        Args:
            portfolio_id: Portfolio ID
            
        Returns:
            List of holding dictionaries
        """
        self.cursor.execute("SELECT * FROM holdings WHERE portfolio_id = ?", (portfolio_id,))
        return [dict(row) for row in self.cursor.fetchall()]
    
    def add_ai_decision(self, portfolio_id: int, ticker: str, decision: str,
                       confidence_score: float = 0.5, reasoning: str = None,
                       analysis_start_time: datetime = None,
                       analysis_end_time: datetime = None) -> int:
        """Record an AI trading decision.
        
        Args:
            portfolio_id: Portfolio ID
            ticker: Stock ticker
            decision: 'BUY', 'SELL', 'HOLD'
            confidence_score: 0.0-1.0
            reasoning: JSON or text explanation
            analysis_start_time: When analysis started
            analysis_end_time: When analysis completed
            
        Returns:
            Decision ID
        """
        self.cursor.execute("""
            INSERT INTO ai_decisions 
            (portfolio_id, ticker, decision, confidence_score, reasoning,
             analysis_start_time, analysis_end_time)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (portfolio_id, ticker, decision, confidence_score, reasoning,
              analysis_start_time, analysis_end_time))
        self.conn.commit()
        return self.cursor.lastrowid
    
    def add_daily_snapshot(self, portfolio_id: int, date: str, total_portfolio_value: float,
                          cash_balance: float, total_invested: float, daily_return: float = 0.0,
                          cumulative_return: float = 0.0, dividend_income: float = 0.0,
                          benchmark_return: float = 0.0, alpha: float = 0.0) -> int:
        """Add end-of-day portfolio snapshot.
        
        Args:
            portfolio_id: Portfolio ID
            date: Date (YYYY-MM-DD)
            total_portfolio_value: Total NAV
            cash_balance: Cash available
            total_invested: Total in positions
            daily_return: Daily return %
            cumulative_return: Cumulative return %
            dividend_income: Dividends received
            benchmark_return: Benchmark return %
            alpha: Alpha vs benchmark
            
        Returns:
            Snapshot ID
        """
        self.cursor.execute("""
            INSERT INTO daily_snapshots 
            (portfolio_id, date, total_portfolio_value, cash_balance, total_invested,
             daily_return, cumulative_return, dividend_income, benchmark_return, alpha)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (portfolio_id, date, total_portfolio_value, cash_balance, total_invested,
              daily_return, cumulative_return, dividend_income, benchmark_return, alpha))
        self.conn.commit()
        return self.cursor.lastrowid
    
    def execute_query(self, query: str, params: tuple = None) -> List[Dict]:
        """Execute a custom SELECT query.
        
        Args:
            query: SQL query
            params: Query parameters
            
        Returns:
            List of row dictionaries
        """
        if params:
            self.cursor.execute(query, params)
        else:
            self.cursor.execute(query)
        return [dict(row) for row in self.cursor.fetchall()]
