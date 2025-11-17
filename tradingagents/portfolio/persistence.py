"""
Portfolio state persistence for saving and loading portfolio data.

This module provides functionality to save and load portfolio state
to/from JSON files and SQLite databases, including trade history,
positions, and performance snapshots.
"""

import json
import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging

from tradingagents.security import sanitize_path_component
from .exceptions import PersistenceError, ValidationError

logger = logging.getLogger(__name__)


class PortfolioPersistence:
    """
    Handles persistence of portfolio state to disk.

    Supports both JSON file format for simple snapshots and SQLite
    for more complex historical data and querying.
    """

    def __init__(self, base_dir: Optional[str] = None):
        """
        Initialize the persistence manager.

        Args:
            base_dir: Base directory for portfolio data (defaults to ./portfolio_data)
        """
        self.base_dir = Path(base_dir) if base_dir else Path('./portfolio_data')
        self.base_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Initialized PortfolioPersistence with base_dir={self.base_dir}")

    def save_to_json(
        self,
        portfolio_data: Dict[str, Any],
        filename: str
    ) -> None:
        """
        Save portfolio state to a JSON file.

        Args:
            portfolio_data: Dictionary containing portfolio state
            filename: Name of the file to save to

        Raises:
            PersistenceError: If save operation fails
            ValidationError: If filename is invalid
        """
        try:
            # Sanitize filename
            safe_filename = sanitize_path_component(filename)
            if not safe_filename.endswith('.json'):
                safe_filename += '.json'

            filepath = self.base_dir / safe_filename

            # Convert Decimal values to strings for JSON serialization
            json_data = self._prepare_for_json(portfolio_data)

            # Write to file with atomic operation
            temp_filepath = filepath.with_suffix('.tmp')
            with open(temp_filepath, 'w') as f:
                json.dump(json_data, f, indent=2, default=str)

            # Atomic rename
            temp_filepath.replace(filepath)

            logger.info(f"Saved portfolio state to {filepath}")

        except (OSError, IOError, ValueError) as e:
            raise PersistenceError(f"Failed to save portfolio to JSON: {e}")

    def load_from_json(self, filename: str) -> Dict[str, Any]:
        """
        Load portfolio state from a JSON file.

        Args:
            filename: Name of the file to load from

        Returns:
            Dictionary containing portfolio state

        Raises:
            PersistenceError: If load operation fails
            ValidationError: If filename is invalid
        """
        try:
            # Sanitize filename
            safe_filename = sanitize_path_component(filename)
            if not safe_filename.endswith('.json'):
                safe_filename += '.json'

            filepath = self.base_dir / safe_filename

            if not filepath.exists():
                raise PersistenceError(f"Portfolio file not found: {filepath}")

            with open(filepath, 'r') as f:
                data = json.load(f)

            # Convert string values back to Decimal where appropriate
            data = self._restore_from_json(data)

            logger.info(f"Loaded portfolio state from {filepath}")

            return data

        except (OSError, IOError, json.JSONDecodeError) as e:
            raise PersistenceError(f"Failed to load portfolio from JSON: {e}")

    def save_to_sqlite(
        self,
        portfolio_data: Dict[str, Any],
        db_name: str = 'portfolio.db'
    ) -> None:
        """
        Save portfolio state to SQLite database.

        Creates tables if they don't exist and inserts/updates data.

        Args:
            portfolio_data: Dictionary containing portfolio state
            db_name: Name of the SQLite database file

        Raises:
            PersistenceError: If save operation fails
        """
        try:
            # Sanitize database name
            safe_db_name = sanitize_path_component(db_name)
            if not safe_db_name.endswith('.db'):
                safe_db_name += '.db'

            db_path = self.base_dir / safe_db_name

            with sqlite3.connect(db_path) as conn:
                self._create_tables(conn)
                self._insert_portfolio_snapshot(conn, portfolio_data)
                self._insert_positions(conn, portfolio_data.get('positions', {}))
                self._insert_trades(conn, portfolio_data.get('trade_history', []))

            logger.info(f"Saved portfolio state to SQLite: {db_path}")

        except (sqlite3.Error, OSError) as e:
            raise PersistenceError(f"Failed to save portfolio to SQLite: {e}")

    def load_from_sqlite(
        self,
        db_name: str = 'portfolio.db',
        snapshot_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Load portfolio state from SQLite database.

        Args:
            db_name: Name of the SQLite database file
            snapshot_id: Specific snapshot ID to load (loads latest if None)

        Returns:
            Dictionary containing portfolio state

        Raises:
            PersistenceError: If load operation fails
        """
        try:
            # Sanitize database name
            safe_db_name = sanitize_path_component(db_name)
            if not safe_db_name.endswith('.db'):
                safe_db_name += '.db'

            db_path = self.base_dir / safe_db_name

            if not db_path.exists():
                raise PersistenceError(f"Database not found: {db_path}")

            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row

                # Get snapshot
                if snapshot_id is None:
                    # Get latest snapshot
                    cursor = conn.execute(
                        'SELECT * FROM portfolio_snapshots ORDER BY timestamp DESC LIMIT 1'
                    )
                else:
                    cursor = conn.execute(
                        'SELECT * FROM portfolio_snapshots WHERE id = ?',
                        (snapshot_id,)
                    )

                snapshot = cursor.fetchone()
                if not snapshot:
                    raise PersistenceError("No portfolio snapshot found")

                # Build portfolio data
                portfolio_data = {
                    'cash': Decimal(snapshot['cash']),
                    'initial_capital': Decimal(snapshot['initial_capital']),
                    'commission_rate': Decimal(snapshot['commission_rate']),
                    'timestamp': snapshot['timestamp'],
                }

                # Load positions
                portfolio_data['positions'] = self._load_positions(
                    conn, snapshot['id']
                )

                # Load trade history
                portfolio_data['trade_history'] = self._load_trades(
                    conn, snapshot['id']
                )

            logger.info(f"Loaded portfolio state from SQLite: {db_path}")

            return portfolio_data

        except (sqlite3.Error, OSError) as e:
            raise PersistenceError(f"Failed to load portfolio from SQLite: {e}")

    def _create_tables(self, conn: sqlite3.Connection) -> None:
        """Create database tables if they don't exist."""
        cursor = conn.cursor()

        # Portfolio snapshots table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                cash TEXT NOT NULL,
                initial_capital TEXT NOT NULL,
                commission_rate TEXT NOT NULL,
                total_value TEXT,
                metadata TEXT
            )
        ''')

        # Positions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id INTEGER NOT NULL,
                ticker TEXT NOT NULL,
                quantity TEXT NOT NULL,
                cost_basis TEXT NOT NULL,
                sector TEXT,
                opened_at TEXT NOT NULL,
                last_updated TEXT NOT NULL,
                stop_loss TEXT,
                take_profit TEXT,
                metadata TEXT,
                FOREIGN KEY (snapshot_id) REFERENCES portfolio_snapshots (id)
            )
        ''')

        # Trade history table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id INTEGER NOT NULL,
                ticker TEXT NOT NULL,
                entry_date TEXT NOT NULL,
                exit_date TEXT,
                entry_price TEXT NOT NULL,
                exit_price TEXT,
                quantity TEXT NOT NULL,
                pnl TEXT,
                pnl_percent TEXT,
                commission TEXT NOT NULL,
                holding_period INTEGER,
                is_win INTEGER,
                FOREIGN KEY (snapshot_id) REFERENCES portfolio_snapshots (id)
            )
        ''')

        # Create indices for better query performance
        cursor.execute(
            'CREATE INDEX IF NOT EXISTS idx_positions_snapshot ON positions(snapshot_id)'
        )
        cursor.execute(
            'CREATE INDEX IF NOT EXISTS idx_trades_snapshot ON trades(snapshot_id)'
        )
        cursor.execute(
            'CREATE INDEX IF NOT EXISTS idx_trades_ticker ON trades(ticker)'
        )

        conn.commit()

    def _insert_portfolio_snapshot(
        self,
        conn: sqlite3.Connection,
        portfolio_data: Dict[str, Any]
    ) -> int:
        """Insert a portfolio snapshot and return its ID."""
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO portfolio_snapshots
            (timestamp, cash, initial_capital, commission_rate, total_value, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            portfolio_data.get('timestamp', datetime.now().isoformat()),
            str(portfolio_data.get('cash', '0')),
            str(portfolio_data.get('initial_capital', '0')),
            str(portfolio_data.get('commission_rate', '0')),
            str(portfolio_data.get('total_value', '0')),
            json.dumps(portfolio_data.get('metadata', {}))
        ))

        conn.commit()
        return cursor.lastrowid

    def _insert_positions(
        self,
        conn: sqlite3.Connection,
        positions: Dict[str, Dict[str, Any]]
    ) -> None:
        """Insert positions into the database."""
        cursor = conn.cursor()

        # Get the latest snapshot ID
        snapshot_id = cursor.execute(
            'SELECT MAX(id) FROM portfolio_snapshots'
        ).fetchone()[0]

        for ticker, position_data in positions.items():
            cursor.execute('''
                INSERT INTO positions
                (snapshot_id, ticker, quantity, cost_basis, sector, opened_at,
                 last_updated, stop_loss, take_profit, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                snapshot_id,
                ticker,
                str(position_data.get('quantity', '0')),
                str(position_data.get('cost_basis', '0')),
                position_data.get('sector'),
                position_data.get('opened_at', datetime.now().isoformat()),
                position_data.get('last_updated', datetime.now().isoformat()),
                str(position_data.get('stop_loss')) if position_data.get('stop_loss') else None,
                str(position_data.get('take_profit')) if position_data.get('take_profit') else None,
                json.dumps(position_data.get('metadata', {}))
            ))

        conn.commit()

    def _insert_trades(
        self,
        conn: sqlite3.Connection,
        trades: List[Dict[str, Any]]
    ) -> None:
        """Insert trades into the database."""
        cursor = conn.cursor()

        # Get the latest snapshot ID
        snapshot_id = cursor.execute(
            'SELECT MAX(id) FROM portfolio_snapshots'
        ).fetchone()[0]

        for trade_data in trades:
            cursor.execute('''
                INSERT INTO trades
                (snapshot_id, ticker, entry_date, exit_date, entry_price, exit_price,
                 quantity, pnl, pnl_percent, commission, holding_period, is_win)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                snapshot_id,
                trade_data.get('ticker', ''),
                trade_data.get('entry_date', ''),
                trade_data.get('exit_date'),
                str(trade_data.get('entry_price', '0')),
                str(trade_data.get('exit_price')) if trade_data.get('exit_price') else None,
                str(trade_data.get('quantity', '0')),
                str(trade_data.get('pnl')) if trade_data.get('pnl') else None,
                str(trade_data.get('pnl_percent')) if trade_data.get('pnl_percent') else None,
                str(trade_data.get('commission', '0')),
                trade_data.get('holding_period'),
                1 if trade_data.get('is_win') else 0
            ))

        conn.commit()

    def _load_positions(
        self,
        conn: sqlite3.Connection,
        snapshot_id: int
    ) -> Dict[str, Dict[str, Any]]:
        """Load positions from the database."""
        cursor = conn.execute(
            'SELECT * FROM positions WHERE snapshot_id = ?',
            (snapshot_id,)
        )

        positions = {}
        for row in cursor:
            ticker = row['ticker']
            positions[ticker] = {
                'quantity': row['quantity'],
                'cost_basis': row['cost_basis'],
                'sector': row['sector'],
                'opened_at': row['opened_at'],
                'last_updated': row['last_updated'],
                'stop_loss': row['stop_loss'],
                'take_profit': row['take_profit'],
                'metadata': json.loads(row['metadata']) if row['metadata'] else {}
            }

        return positions

    def _load_trades(
        self,
        conn: sqlite3.Connection,
        snapshot_id: int
    ) -> List[Dict[str, Any]]:
        """Load trades from the database."""
        cursor = conn.execute(
            'SELECT * FROM trades WHERE snapshot_id = ?',
            (snapshot_id,)
        )

        trades = []
        for row in cursor:
            trades.append({
                'ticker': row['ticker'],
                'entry_date': row['entry_date'],
                'exit_date': row['exit_date'],
                'entry_price': row['entry_price'],
                'exit_price': row['exit_price'],
                'quantity': row['quantity'],
                'pnl': row['pnl'],
                'pnl_percent': row['pnl_percent'],
                'commission': row['commission'],
                'holding_period': row['holding_period'],
                'is_win': bool(row['is_win'])
            })

        return trades

    def _prepare_for_json(self, data: Any) -> Any:
        """Recursively prepare data for JSON serialization."""
        if isinstance(data, Decimal):
            return str(data)
        elif isinstance(data, datetime):
            return data.isoformat()
        elif isinstance(data, dict):
            return {k: self._prepare_for_json(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._prepare_for_json(item) for item in data]
        else:
            return data

    def _restore_from_json(self, data: Any) -> Any:
        """Recursively restore data types from JSON."""
        if isinstance(data, dict):
            # Check for known keys that should be Decimal
            decimal_keys = {
                'cash', 'initial_capital', 'commission_rate', 'quantity',
                'cost_basis', 'stop_loss', 'take_profit', 'entry_price',
                'exit_price', 'pnl', 'pnl_percent', 'commission', 'limit_price',
                'stop_price', 'target_price', 'filled_price'
            }

            result = {}
            for k, v in data.items():
                if k in decimal_keys and v is not None:
                    try:
                        result[k] = Decimal(str(v))
                    except:
                        result[k] = v
                else:
                    result[k] = self._restore_from_json(v)

            return result
        elif isinstance(data, list):
            return [self._restore_from_json(item) for item in data]
        else:
            return data

    def export_to_csv(
        self,
        trades: List[Dict[str, Any]],
        filename: str
    ) -> None:
        """
        Export trade history to CSV file.

        Args:
            trades: List of trade records
            filename: Name of the CSV file

        Raises:
            PersistenceError: If export fails
        """
        try:
            import csv

            safe_filename = sanitize_path_component(filename)
            if not safe_filename.endswith('.csv'):
                safe_filename += '.csv'

            filepath = self.base_dir / safe_filename

            if not trades:
                logger.warning("No trades to export")
                return

            # Get all unique keys from trades
            fieldnames = set()
            for trade in trades:
                fieldnames.update(trade.keys())

            fieldnames = sorted(fieldnames)

            with open(filepath, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(trades)

            logger.info(f"Exported {len(trades)} trades to {filepath}")

        except (OSError, IOError) as e:
            raise PersistenceError(f"Failed to export to CSV: {e}")

    def cleanup_old_snapshots(
        self,
        db_name: str = 'portfolio.db',
        keep_last_n: int = 100
    ) -> int:
        """
        Clean up old snapshots from the database.

        Args:
            db_name: Name of the SQLite database file
            keep_last_n: Number of latest snapshots to keep

        Returns:
            Number of snapshots deleted

        Raises:
            PersistenceError: If cleanup fails
        """
        try:
            safe_db_name = sanitize_path_component(db_name)
            if not safe_db_name.endswith('.db'):
                safe_db_name += '.db'

            db_path = self.base_dir / safe_db_name

            if not db_path.exists():
                return 0

            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()

                # Get IDs of snapshots to delete
                cursor.execute('''
                    SELECT id FROM portfolio_snapshots
                    ORDER BY timestamp DESC
                    LIMIT -1 OFFSET ?
                ''', (keep_last_n,))

                ids_to_delete = [row[0] for row in cursor.fetchall()]

                if not ids_to_delete:
                    return 0

                # SECURITY NOTE: The f-strings below are SAFE because:
                # 1. They only generate placeholder "?" characters, never actual data
                # 2. All actual values are passed via parameterized query (ids_to_delete)
                # 3. ids_to_delete contains integers from database, not user input
                # This pattern creates: "DELETE FROM table WHERE id IN (?,?,?)"
                # and then passes the actual IDs separately to prevent SQL injection

                # Delete related positions and trades
                placeholders = ','.join('?' * len(ids_to_delete))
                cursor.execute(
                    f'DELETE FROM positions WHERE snapshot_id IN ({placeholders})',
                    ids_to_delete
                )
                cursor.execute(
                    f'DELETE FROM trades WHERE snapshot_id IN ({placeholders})',
                    ids_to_delete
                )

                # Delete snapshots
                cursor.execute(
                    f'DELETE FROM portfolio_snapshots WHERE id IN ({placeholders})',
                    ids_to_delete
                )

                conn.commit()

                logger.info(f"Deleted {len(ids_to_delete)} old snapshots")

                return len(ids_to_delete)

        except (sqlite3.Error, OSError) as e:
            raise PersistenceError(f"Failed to cleanup old snapshots: {e}")
