"""SQLite database module for storing stock recommendations."""
import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

DB_PATH = Path(__file__).parent / "recommendations.db"


def get_connection():
    """Get SQLite database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the database with required tables."""
    conn = get_connection()
    cursor = conn.cursor()

    # Create recommendations table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE NOT NULL,
            summary_total INTEGER,
            summary_buy INTEGER,
            summary_sell INTEGER,
            summary_hold INTEGER,
            top_picks TEXT,
            stocks_to_avoid TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create stock analysis table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            company_name TEXT,
            decision TEXT,
            confidence TEXT,
            risk TEXT,
            raw_analysis TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, symbol)
        )
    """)

    # Create index for faster queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_stock_analysis_date ON stock_analysis(date)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_stock_analysis_symbol ON stock_analysis(symbol)
    """)

    conn.commit()
    conn.close()


def save_recommendation(date: str, analysis_data: dict, summary: dict,
                        top_picks: list, stocks_to_avoid: list):
    """Save a daily recommendation to the database."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Insert or replace daily recommendation
        cursor.execute("""
            INSERT OR REPLACE INTO daily_recommendations
            (date, summary_total, summary_buy, summary_sell, summary_hold, top_picks, stocks_to_avoid)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            date,
            summary.get('total', 0),
            summary.get('buy', 0),
            summary.get('sell', 0),
            summary.get('hold', 0),
            json.dumps(top_picks),
            json.dumps(stocks_to_avoid)
        ))

        # Insert stock analysis for each stock
        for symbol, analysis in analysis_data.items():
            cursor.execute("""
                INSERT OR REPLACE INTO stock_analysis
                (date, symbol, company_name, decision, confidence, risk, raw_analysis)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                date,
                symbol,
                analysis.get('company_name', ''),
                analysis.get('decision'),
                analysis.get('confidence'),
                analysis.get('risk'),
                analysis.get('raw_analysis', '')
            ))

        conn.commit()
    finally:
        conn.close()


def get_recommendation_by_date(date: str) -> Optional[dict]:
    """Get recommendation for a specific date."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Get daily summary
        cursor.execute("""
            SELECT * FROM daily_recommendations WHERE date = ?
        """, (date,))
        row = cursor.fetchone()

        if not row:
            return None

        # Get stock analysis for this date
        cursor.execute("""
            SELECT * FROM stock_analysis WHERE date = ?
        """, (date,))
        analysis_rows = cursor.fetchall()

        analysis = {}
        for a in analysis_rows:
            analysis[a['symbol']] = {
                'symbol': a['symbol'],
                'company_name': a['company_name'],
                'decision': a['decision'],
                'confidence': a['confidence'],
                'risk': a['risk'],
                'raw_analysis': a['raw_analysis']
            }

        return {
            'date': row['date'],
            'analysis': analysis,
            'summary': {
                'total': row['summary_total'],
                'buy': row['summary_buy'],
                'sell': row['summary_sell'],
                'hold': row['summary_hold']
            },
            'top_picks': json.loads(row['top_picks']) if row['top_picks'] else [],
            'stocks_to_avoid': json.loads(row['stocks_to_avoid']) if row['stocks_to_avoid'] else []
        }
    finally:
        conn.close()


def get_latest_recommendation() -> Optional[dict]:
    """Get the most recent recommendation."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT date FROM daily_recommendations ORDER BY date DESC LIMIT 1
        """)
        row = cursor.fetchone()

        if not row:
            return None

        return get_recommendation_by_date(row['date'])
    finally:
        conn.close()


def get_all_dates() -> list:
    """Get all available dates."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT date FROM daily_recommendations ORDER BY date DESC
        """)
        return [row['date'] for row in cursor.fetchall()]
    finally:
        conn.close()


def get_stock_history(symbol: str) -> list:
    """Get historical recommendations for a specific stock."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT date, decision, confidence, risk
            FROM stock_analysis
            WHERE symbol = ?
            ORDER BY date DESC
        """, (symbol,))

        return [
            {
                'date': row['date'],
                'decision': row['decision'],
                'confidence': row['confidence'],
                'risk': row['risk']
            }
            for row in cursor.fetchall()
        ]
    finally:
        conn.close()


def get_all_recommendations() -> list:
    """Get all daily recommendations."""
    dates = get_all_dates()
    return [get_recommendation_by_date(date) for date in dates]


# Initialize database on module import
init_db()
