"""SQLite database module for storing stock recommendations."""
import sqlite3
import json
import re
from pathlib import Path
from datetime import datetime
from typing import Optional

DB_PATH = Path(__file__).parent / "recommendations.db"


def sanitize_decision(raw: str) -> str:
    """Extract BUY/SELL/HOLD from potentially noisy LLM output.

    Handles: 'BUY', '**SELL**', 'HOLD\n\n---\nHOWEVER...', 'The decision is: **BUY**', etc.
    Returns 'HOLD' as fallback.
    """
    if not raw:
        return 'HOLD'
    text = raw.strip()

    # Quick exact match (most common case)
    upper = text.upper()
    if upper in ('BUY', 'SELL', 'HOLD'):
        return upper

    # Strip markdown bold/italic: **SELL** → SELL, *BUY* → BUY
    stripped = re.sub(r'[*_]+', '', text).strip().upper()
    if stripped in ('BUY', 'SELL', 'HOLD'):
        return stripped

    # First word after stripping markdown
    first_word = stripped.split()[0] if stripped else ''
    if first_word in ('BUY', 'SELL', 'HOLD'):
        return first_word

    # Search for decision keyword in the text (prioritize earlier occurrences)
    # Look for standalone BUY/SELL/HOLD words (not part of longer words)
    for keyword in ('BUY', 'SELL', 'HOLD'):
        if re.search(r'\b' + keyword + r'\b', upper):
            return keyword

    return 'HOLD'


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

    # Create agent_reports table (stores each analyst's detailed report)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            agent_type TEXT NOT NULL,
            report_content TEXT,
            data_sources_used TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, symbol, agent_type)
        )
    """)

    # Create debate_history table (stores investment and risk debates)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS debate_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            debate_type TEXT NOT NULL,
            bull_arguments TEXT,
            bear_arguments TEXT,
            risky_arguments TEXT,
            safe_arguments TEXT,
            neutral_arguments TEXT,
            judge_decision TEXT,
            full_history TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, symbol, debate_type)
        )
    """)

    # Create pipeline_steps table (stores step-by-step execution log)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            step_number INTEGER,
            step_name TEXT,
            status TEXT,
            started_at TEXT,
            completed_at TEXT,
            duration_ms INTEGER,
            output_summary TEXT,
            step_details TEXT,
            UNIQUE(date, symbol, step_number)
        )
    """)

    # Add step_details column if it doesn't exist (migration for existing DBs)
    try:
        cursor.execute("ALTER TABLE pipeline_steps ADD COLUMN step_details TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Create data_source_logs table (stores what raw data was fetched)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS data_source_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            source_type TEXT,
            source_name TEXT,
            method TEXT,
            args TEXT,
            data_fetched TEXT,
            fetch_timestamp TEXT,
            success INTEGER DEFAULT 1,
            error_message TEXT
        )
    """)

    # Migrate: add method/args columns if missing (existing databases)
    try:
        cursor.execute("ALTER TABLE data_source_logs ADD COLUMN method TEXT")
    except Exception:
        pass  # Column already exists
    try:
        cursor.execute("ALTER TABLE data_source_logs ADD COLUMN args TEXT")
    except Exception:
        pass  # Column already exists

    # Create backtest_results table (stores calculated backtest accuracy)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS backtest_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            decision TEXT,
            price_at_prediction REAL,
            price_1d_later REAL,
            price_1w_later REAL,
            price_1m_later REAL,
            return_1d REAL,
            return_1w REAL,
            return_1m REAL,
            prediction_correct INTEGER,
            calculated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, symbol)
        )
    """)

    # Add hold_days column if it doesn't exist (migration for existing DBs)
    try:
        cursor.execute("ALTER TABLE stock_analysis ADD COLUMN hold_days INTEGER")
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        cursor.execute("ALTER TABLE backtest_results ADD COLUMN hold_days INTEGER")
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        cursor.execute("ALTER TABLE backtest_results ADD COLUMN return_at_hold REAL")
        # New column added — delete stale backtest data so it gets recalculated with return_at_hold
        cursor.execute("DELETE FROM backtest_results")
        print("Migration: Added return_at_hold column, cleared stale backtest data for recalculation")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Add rank column if it doesn't exist (migration for existing DBs)
    try:
        cursor.execute("ALTER TABLE stock_analysis ADD COLUMN rank INTEGER")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Create indexes for new tables
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_agent_reports_date_symbol ON agent_reports(date, symbol)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_debate_history_date_symbol ON debate_history(date, symbol)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_pipeline_steps_date_symbol ON pipeline_steps(date, symbol)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_data_source_logs_date_symbol ON data_source_logs(date, symbol)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_backtest_results_date ON backtest_results(date)
    """)

    conn.commit()
    conn.close()

    # Fix data quality issues at startup
    _fix_default_hold_days()
    _fix_garbage_decisions()
    _cleanup_bad_backtest_data()


def _fix_default_hold_days():
    """Re-extract hold_days from raw_analysis for rows where hold_days is NULL or 5 (defaults).

    The signal processor sometimes defaults to 5 or leaves hold_days NULL when the
    LLM fails to extract the actual hold period. This function uses regex on the
    raw_analysis text to find the correct value.
    """
    import re

    patterns = [
        r'(\d+)[\s-]*(?:day|trading[\s-]*day)[\s-]*(?:hold|horizon|period|timeframe)',
        r'(?:hold|holding)[\s\w]*?(?:for|of|period\s+of)[\s]*(\d+)[\s]*(?:trading\s+)?days?',
        r'setting\s+(\d+)\s+(?:trading\s+)?days',
        r'(?:over|within|next)\s+(\d+)\s+(?:trading\s+)?days',
        r'(\d+)\s+trading\s+days?\s*\(',
    ]

    def extract_days(text):
        if not text:
            return None
        # Search the conclusion/rationale section first (last 500 chars)
        conclusion = text[-500:]
        for pattern in patterns:
            for match in re.finditer(pattern, conclusion, re.IGNORECASE):
                days = int(match.group(1))
                if 1 <= days <= 90:
                    return days
        # Fall back to full text
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                days = int(match.group(1))
                if 1 <= days <= 90:
                    return days
        return None

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Fix rows where hold_days is NULL or the default 5
        cursor.execute(
            "SELECT id, symbol, date, raw_analysis, hold_days, decision FROM stock_analysis "
            "WHERE (hold_days IS NULL OR hold_days = 5) "
            "AND decision != 'SELL' "
            "AND raw_analysis IS NOT NULL AND raw_analysis != ''"
        )
        rows = cursor.fetchall()
        fixed = 0
        for row in rows:
            extracted = extract_days(row['raw_analysis'])
            old_val = row['hold_days']
            if extracted is not None and extracted != old_val:
                cursor.execute(
                    "UPDATE stock_analysis SET hold_days = ? WHERE id = ?",
                    (extracted, row['id'])
                )
                fixed += 1
                print(f"  Fixed hold_days for {row['symbol']} ({row['date']}): {old_val} -> {extracted}")

        if fixed > 0:
            conn.commit()
            # Also clear backtest results so they recalculate with correct hold_days
            cursor.execute("DELETE FROM backtest_results")
            conn.commit()
            print(f"Fixed {fixed} stock(s) with missing/default hold_days. Cleared backtest cache.")
    finally:
        conn.close()


def _fix_garbage_decisions():
    """Fix stock_analysis rows where the decision field contains garbage LLM output.

    Uses sanitize_decision() to extract the real BUY/SELL/HOLD from the text,
    then updates the DB rows and rebuilds daily_recommendations summaries.
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Find rows where decision is not a clean BUY/SELL/HOLD
        cursor.execute(
            "SELECT id, date, symbol, decision FROM stock_analysis "
            "WHERE decision NOT IN ('BUY', 'SELL', 'HOLD') AND decision IS NOT NULL"
        )
        rows = cursor.fetchall()
        if not rows:
            return

        fixed = 0
        affected_dates = set()
        for row in rows:
            clean = sanitize_decision(row['decision'])
            if clean != row['decision']:
                cursor.execute(
                    "UPDATE stock_analysis SET decision = ? WHERE id = ?",
                    (clean, row['id'])
                )
                fixed += 1
                affected_dates.add(row['date'])
                old_preview = row['decision'][:40].replace('\n', ' ')
                print(f"  Fixed decision for {row['symbol']} ({row['date']}): '{old_preview}...' -> {clean}")

        if fixed > 0:
            conn.commit()
            print(f"Fixed {fixed} stock(s) with garbage decision values.")

            # Rebuild daily_recommendations summaries for affected dates
            for date in affected_dates:
                cursor.execute(
                    "SELECT decision FROM stock_analysis WHERE date = ?", (date,)
                )
                decisions = [sanitize_decision(r['decision']) for r in cursor.fetchall()]
                buy_count = decisions.count('BUY')
                sell_count = decisions.count('SELL')
                hold_count = decisions.count('HOLD')
                cursor.execute(
                    "UPDATE daily_recommendations SET summary_buy=?, summary_sell=?, summary_hold=?, summary_total=? WHERE date=?",
                    (buy_count, sell_count, hold_count, len(decisions), date)
                )
            conn.commit()
            print(f"Rebuilt summaries for {len(affected_dates)} date(s).")

            # Clear backtest results that may have wrong decisions stored
            cursor.execute("DELETE FROM backtest_results WHERE decision NOT IN ('BUY', 'SELL', 'HOLD')")
            conn.commit()
    finally:
        conn.close()


def _cleanup_bad_backtest_data():
    """Remove backtest results that have invalid data.

    Deletes rows where:
    - return_1d is exactly 0.0 AND return_1w is also 0.0 or NULL (indicates same-day resolution)
    - return_1d is NULL and return_1w is NULL and return_at_hold is NULL (no usable data)
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Delete rows where return_1d=0 and no other useful return data
        # This typically means pred_date and next-day resolved to the same trading day
        cursor.execute(
            "DELETE FROM backtest_results "
            "WHERE return_1d = 0.0 AND (return_1w IS NULL OR return_1w = 0.0) "
            "AND (return_at_hold IS NULL OR return_at_hold = 0.0)"
        )
        deleted_zero = cursor.rowcount

        # Delete rows where all returns are NULL (no price data available)
        cursor.execute(
            "DELETE FROM backtest_results "
            "WHERE return_1d IS NULL AND return_1w IS NULL AND return_at_hold IS NULL"
        )
        deleted_null = cursor.rowcount

        if deleted_zero + deleted_null > 0:
            conn.commit()
            print(f"Cleaned up backtest data: removed {deleted_zero} zero-return rows, {deleted_null} null-return rows.")

        # Fix rows where prediction_correct is NULL but we have return data
        # Cross-reference with stock_analysis for the correct decision
        cursor.execute("""
            SELECT br.id, br.date, br.symbol, br.return_1d, br.return_at_hold,
                   sa.decision as sa_decision
            FROM backtest_results br
            JOIN stock_analysis sa ON br.date = sa.date AND br.symbol = sa.symbol
            WHERE br.prediction_correct IS NULL
              AND (br.return_1d IS NOT NULL OR br.return_at_hold IS NOT NULL)
        """)
        null_correct_rows = cursor.fetchall()
        fixed_count = 0
        for row in null_correct_rows:
            decision = sanitize_decision(row['sa_decision'])
            primary_return = row['return_at_hold'] if row['return_at_hold'] is not None else row['return_1d']
            if primary_return is None:
                continue
            if decision in ('BUY', 'HOLD'):
                is_correct = 1 if primary_return > 0 else 0
            elif decision == 'SELL':
                is_correct = 1 if primary_return < 0 else 0
            else:
                continue
            cursor.execute(
                "UPDATE backtest_results SET prediction_correct = ?, decision = ? WHERE id = ?",
                (is_correct, decision, row['id'])
            )
            fixed_count += 1

        if fixed_count > 0:
            conn.commit()
            print(f"Fixed prediction_correct for {fixed_count} backtest rows.")
    finally:
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
                (date, symbol, company_name, decision, confidence, risk, raw_analysis, hold_days)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                date,
                symbol,
                analysis.get('company_name', ''),
                analysis.get('decision'),
                analysis.get('confidence'),
                analysis.get('risk'),
                analysis.get('raw_analysis', ''),
                analysis.get('hold_days')
            ))

        conn.commit()
    finally:
        conn.close()


def save_single_stock_analysis(date: str, symbol: str, analysis: dict):
    """Save analysis for a single stock.

    Args:
        date: Date string (YYYY-MM-DD)
        symbol: Stock symbol
        analysis: Dict with keys: company_name, decision, confidence, risk, raw_analysis, hold_days
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT OR REPLACE INTO stock_analysis
            (date, symbol, company_name, decision, confidence, risk, raw_analysis, hold_days)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            date,
            symbol,
            analysis.get('company_name', symbol),
            analysis.get('decision', 'HOLD'),
            analysis.get('confidence', 'MEDIUM'),
            analysis.get('risk', 'MEDIUM'),
            analysis.get('raw_analysis', ''),
            analysis.get('hold_days')
        ))
        conn.commit()
    finally:
        conn.close()


def get_analyzed_symbols_for_date(date: str) -> list:
    """Get list of symbols that already have analysis for a given date.

    Used by bulk analysis to skip already-completed stocks when resuming.
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT symbol FROM stock_analysis WHERE date = ?", (date,))
        return [row['symbol'] for row in cursor.fetchall()]
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

        # Get stock analysis for this date
        cursor.execute("""
            SELECT * FROM stock_analysis WHERE date = ?
        """, (date,))
        analysis_rows = cursor.fetchall()

        # If no daily_recommendations AND no stock_analysis, return None
        if not row and not analysis_rows:
            return None

        analysis = {}
        for a in analysis_rows:
            decision = sanitize_decision(a['decision'])
            analysis[a['symbol']] = {
                'symbol': a['symbol'],
                'company_name': a['company_name'],
                'decision': decision,
                'confidence': a['confidence'] or 'MEDIUM',
                'risk': a['risk'] or 'MEDIUM',
                'raw_analysis': a['raw_analysis'],
                'hold_days': a['hold_days'] if 'hold_days' in a.keys() else None,
                'rank': a['rank'] if 'rank' in a.keys() else None
            }

        if row:
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

        # Fallback: build summary from stock_analysis when daily_recommendations is missing
        buy_count = sum(1 for a in analysis.values() if a['decision'] == 'BUY')
        sell_count = sum(1 for a in analysis.values() if a['decision'] == 'SELL')
        hold_count = sum(1 for a in analysis.values() if a['decision'] == 'HOLD')
        return {
            'date': date,
            'analysis': analysis,
            'summary': {
                'total': len(analysis),
                'buy': buy_count,
                'sell': sell_count,
                'hold': hold_count
            },
            'top_picks': [],
            'stocks_to_avoid': []
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
    """Get all available dates (union of daily_recommendations and stock_analysis)."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT DISTINCT date FROM (
                SELECT date FROM daily_recommendations
                UNION
                SELECT date FROM stock_analysis
            ) ORDER BY date DESC
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
            SELECT date, decision, confidence, risk, hold_days, rank
            FROM stock_analysis
            WHERE symbol = ?
            ORDER BY date DESC
        """, (symbol,))

        results = []
        for row in cursor.fetchall():
            decision = sanitize_decision(row['decision'])
            results.append({
                'date': row['date'],
                'decision': decision,
                'confidence': row['confidence'] or 'MEDIUM',
                'risk': row['risk'] or 'MEDIUM',
                'hold_days': row['hold_days'] if 'hold_days' in row.keys() else None,
                'rank': row['rank'] if 'rank' in row.keys() else None
            })
        return results
    finally:
        conn.close()


def get_all_recommendations() -> list:
    """Get all daily recommendations."""
    dates = get_all_dates()
    return [get_recommendation_by_date(date) for date in dates]


# ============== Pipeline Data Functions ==============

def save_agent_report(date: str, symbol: str, agent_type: str,
                      report_content: str, data_sources_used: list = None):
    """Save an individual agent's report."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT OR REPLACE INTO agent_reports
            (date, symbol, agent_type, report_content, data_sources_used)
            VALUES (?, ?, ?, ?, ?)
        """, (
            date, symbol, agent_type, report_content,
            json.dumps(data_sources_used) if data_sources_used else '[]'
        ))
        conn.commit()
    finally:
        conn.close()


def save_agent_reports_bulk(date: str, symbol: str, reports: dict):
    """Save all agent reports for a stock at once.

    Args:
        date: Date string (YYYY-MM-DD)
        symbol: Stock symbol
        reports: Dict with keys 'market', 'news', 'social_media', 'fundamentals'
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        for agent_type, report_data in reports.items():
            if isinstance(report_data, str):
                report_content = report_data
                data_sources = []
            else:
                report_content = report_data.get('content', '')
                data_sources = report_data.get('data_sources', [])

            cursor.execute("""
                INSERT OR REPLACE INTO agent_reports
                (date, symbol, agent_type, report_content, data_sources_used)
                VALUES (?, ?, ?, ?, ?)
            """, (date, symbol, agent_type, report_content, json.dumps(data_sources)))

        conn.commit()
    finally:
        conn.close()


def get_agent_reports(date: str, symbol: str) -> dict:
    """Get all agent reports for a stock on a date."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT agent_type, report_content, data_sources_used, created_at
            FROM agent_reports
            WHERE date = ? AND symbol = ?
        """, (date, symbol))

        reports = {}
        for row in cursor.fetchall():
            reports[row['agent_type']] = {
                'agent_type': row['agent_type'],
                'report_content': row['report_content'],
                'data_sources_used': json.loads(row['data_sources_used']) if row['data_sources_used'] else [],
                'created_at': row['created_at']
            }
        return reports
    finally:
        conn.close()


def save_debate_history(date: str, symbol: str, debate_type: str,
                        bull_arguments: str = None, bear_arguments: str = None,
                        risky_arguments: str = None, safe_arguments: str = None,
                        neutral_arguments: str = None, judge_decision: str = None,
                        full_history: str = None):
    """Save debate history for investment or risk debate."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT OR REPLACE INTO debate_history
            (date, symbol, debate_type, bull_arguments, bear_arguments,
             risky_arguments, safe_arguments, neutral_arguments,
             judge_decision, full_history)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            date, symbol, debate_type,
            bull_arguments, bear_arguments,
            risky_arguments, safe_arguments, neutral_arguments,
            judge_decision, full_history
        ))
        conn.commit()
    finally:
        conn.close()


def get_debate_history(date: str, symbol: str) -> dict:
    """Get all debate history for a stock on a date."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT * FROM debate_history
            WHERE date = ? AND symbol = ?
        """, (date, symbol))

        debates = {}
        for row in cursor.fetchall():
            debates[row['debate_type']] = {
                'debate_type': row['debate_type'],
                'bull_arguments': row['bull_arguments'],
                'bear_arguments': row['bear_arguments'],
                'risky_arguments': row['risky_arguments'],
                'safe_arguments': row['safe_arguments'],
                'neutral_arguments': row['neutral_arguments'],
                'judge_decision': row['judge_decision'],
                'full_history': row['full_history'],
                'created_at': row['created_at']
            }
        return debates
    finally:
        conn.close()


def save_pipeline_step(date: str, symbol: str, step_number: int, step_name: str,
                       status: str, started_at: str = None, completed_at: str = None,
                       duration_ms: int = None, output_summary: str = None):
    """Save a pipeline step status."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT OR REPLACE INTO pipeline_steps
            (date, symbol, step_number, step_name, status,
             started_at, completed_at, duration_ms, output_summary)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            date, symbol, step_number, step_name, status,
            started_at, completed_at, duration_ms, output_summary
        ))
        conn.commit()
    finally:
        conn.close()


def save_pipeline_steps_bulk(date: str, symbol: str, steps: list):
    """Save all pipeline steps at once.

    Args:
        date: Date string
        symbol: Stock symbol
        steps: List of step dicts with step_number, step_name, status, etc.
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        for step in steps:
            step_details = step.get('step_details')
            if step_details and not isinstance(step_details, str):
                step_details = json.dumps(step_details)
            cursor.execute("""
                INSERT OR REPLACE INTO pipeline_steps
                (date, symbol, step_number, step_name, status,
                 started_at, completed_at, duration_ms, output_summary, step_details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                date, symbol,
                step.get('step_number'),
                step.get('step_name'),
                step.get('status'),
                step.get('started_at'),
                step.get('completed_at'),
                step.get('duration_ms'),
                step.get('output_summary'),
                step_details
            ))
        conn.commit()
    finally:
        conn.close()


def get_pipeline_steps(date: str, symbol: str) -> list:
    """Get all pipeline steps for a stock on a date."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT * FROM pipeline_steps
            WHERE date = ? AND symbol = ?
            ORDER BY step_number
        """, (date, symbol))

        results = []
        for row in cursor.fetchall():
            step_details = None
            raw_details = row['step_details'] if 'step_details' in row.keys() else None
            if raw_details:
                try:
                    step_details = json.loads(raw_details)
                except (json.JSONDecodeError, TypeError):
                    step_details = None
            results.append({
                'step_number': row['step_number'],
                'step_name': row['step_name'],
                'status': row['status'],
                'started_at': row['started_at'],
                'completed_at': row['completed_at'],
                'duration_ms': row['duration_ms'],
                'output_summary': row['output_summary'],
                'step_details': step_details,
            })
        return results
    finally:
        conn.close()


def save_data_source_log(date: str, symbol: str, source_type: str,
                         source_name: str, data_fetched: dict = None,
                         fetch_timestamp: str = None, success: bool = True,
                         error_message: str = None):
    """Log a data source fetch."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO data_source_logs
            (date, symbol, source_type, source_name, data_fetched,
             fetch_timestamp, success, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            date, symbol, source_type, source_name,
            json.dumps(data_fetched) if data_fetched else None,
            fetch_timestamp or datetime.now().isoformat(),
            1 if success else 0,
            error_message
        ))
        conn.commit()
    finally:
        conn.close()


def save_data_source_logs_bulk(date: str, symbol: str, logs: list):
    """Save multiple data source logs at once."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        for log in logs:
            cursor.execute("""
                INSERT INTO data_source_logs
                (date, symbol, source_type, source_name, method, args, data_fetched,
                 fetch_timestamp, success, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                date, symbol,
                log.get('source_type'),
                log.get('source_name'),
                log.get('method'),
                log.get('args'),
                json.dumps(log.get('data_fetched')) if log.get('data_fetched') else None,
                log.get('fetch_timestamp') or datetime.now().isoformat(),
                1 if log.get('success', True) else 0,
                log.get('error_message')
            ))
        conn.commit()
    finally:
        conn.close()


def get_data_source_logs(date: str, symbol: str) -> list:
    """Get all data source logs for a stock on a date.
    Falls back to generating entries from agent_reports if no explicit logs exist."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT * FROM data_source_logs
            WHERE date = ? AND symbol = ?
            ORDER BY fetch_timestamp
        """, (date, symbol))

        logs = [
            {
                'source_type': row['source_type'],
                'source_name': row['source_name'],
                'method': row['method'] if 'method' in row.keys() else None,
                'args': row['args'] if 'args' in row.keys() else None,
                'data_fetched': json.loads(row['data_fetched']) if row['data_fetched'] else None,
                'fetch_timestamp': row['fetch_timestamp'],
                'success': bool(row['success']),
                'error_message': row['error_message']
            }
            for row in cursor.fetchall()
        ]

        if logs:
            return logs

        # No explicit logs — generate from agent_reports with full raw content
        AGENT_TO_SOURCE = {
            'market': ('market_data', 'Yahoo Finance'),
            'news': ('news', 'Google News'),
            'social_media': ('social_media', 'Social Sentiment'),
            'fundamentals': ('fundamentals', 'Financial Data'),
        }

        cursor.execute("""
            SELECT agent_type, report_content, created_at
            FROM agent_reports
            WHERE date = ? AND symbol = ?
        """, (date, symbol))

        generated = []
        for row in cursor.fetchall():
            source_type, source_name = AGENT_TO_SOURCE.get(
                row['agent_type'], ('other', row['agent_type'])
            )
            generated.append({
                'source_type': source_type,
                'source_name': source_name,
                'data_fetched': row['report_content'],
                'fetch_timestamp': row['created_at'],
                'success': True,
                'error_message': None
            })

        return generated
    finally:
        conn.close()


def get_full_pipeline_data(date: str, symbol: str) -> dict:
    """Get complete pipeline data for a stock on a date."""
    return {
        'date': date,
        'symbol': symbol,
        'agent_reports': get_agent_reports(date, symbol),
        'debates': get_debate_history(date, symbol),
        'pipeline_steps': get_pipeline_steps(date, symbol),
        'data_sources': get_data_source_logs(date, symbol)
    }


def save_full_pipeline_data(date: str, symbol: str, pipeline_data: dict):
    """Save complete pipeline data for a stock.

    Args:
        date: Date string
        symbol: Stock symbol
        pipeline_data: Dict containing agent_reports, debates, pipeline_steps, data_sources
    """
    if 'agent_reports' in pipeline_data:
        save_agent_reports_bulk(date, symbol, pipeline_data['agent_reports'])

    if 'investment_debate' in pipeline_data:
        debate = pipeline_data['investment_debate']
        save_debate_history(
            date, symbol, 'investment',
            bull_arguments=debate.get('bull_history'),
            bear_arguments=debate.get('bear_history'),
            judge_decision=debate.get('judge_decision'),
            full_history=debate.get('history')
        )

    if 'risk_debate' in pipeline_data:
        debate = pipeline_data['risk_debate']
        save_debate_history(
            date, symbol, 'risk',
            risky_arguments=debate.get('risky_history'),
            safe_arguments=debate.get('safe_history'),
            neutral_arguments=debate.get('neutral_history'),
            judge_decision=debate.get('judge_decision'),
            full_history=debate.get('history')
        )

    if 'pipeline_steps' in pipeline_data:
        save_pipeline_steps_bulk(date, symbol, pipeline_data['pipeline_steps'])

    if 'data_sources' in pipeline_data:
        save_data_source_logs_bulk(date, symbol, pipeline_data['data_sources'])


def get_pipeline_summary_for_date(date: str) -> list:
    """Get pipeline summary for all stocks on a date."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Get all symbols for this date
        cursor.execute("""
            SELECT DISTINCT symbol FROM stock_analysis WHERE date = ?
        """, (date,))
        symbols = [row['symbol'] for row in cursor.fetchall()]

        # Batch fetch all pipeline steps for the date (avoids N+1)
        cursor.execute("""
            SELECT symbol, step_name, status FROM pipeline_steps
            WHERE date = ?
            ORDER BY symbol, step_number
        """, (date,))
        all_steps = cursor.fetchall()
        steps_by_symbol = {}
        for row in all_steps:
            if row['symbol'] not in steps_by_symbol:
                steps_by_symbol[row['symbol']] = []
            steps_by_symbol[row['symbol']].append({'step_name': row['step_name'], 'status': row['status']})

        # Batch fetch agent report counts (avoids N+1)
        cursor.execute("""
            SELECT symbol, COUNT(*) as count FROM agent_reports
            WHERE date = ?
            GROUP BY symbol
        """, (date,))
        agent_counts = {row['symbol']: row['count'] for row in cursor.fetchall()}

        # Batch fetch debates existence (avoids N+1)
        cursor.execute("""
            SELECT DISTINCT symbol FROM debate_history WHERE date = ?
        """, (date,))
        symbols_with_debates = {row['symbol'] for row in cursor.fetchall()}

        summaries = []
        for symbol in symbols:
            summaries.append({
                'symbol': symbol,
                'pipeline_steps': steps_by_symbol.get(symbol, []),
                'agent_reports_count': agent_counts.get(symbol, 0),
                'has_debates': symbol in symbols_with_debates
            })

        return summaries
    finally:
        conn.close()


def save_backtest_result(date: str, symbol: str, decision: str,
                         price_at_prediction: float, price_1d_later: float = None,
                         price_1w_later: float = None, price_1m_later: float = None,
                         return_1d: float = None, return_1w: float = None,
                         return_1m: float = None, prediction_correct: bool = None,
                         hold_days: int = None, return_at_hold: float = None):
    """Save a backtest result for a stock recommendation."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT OR REPLACE INTO backtest_results
            (date, symbol, decision, price_at_prediction,
             price_1d_later, price_1w_later, price_1m_later,
             return_1d, return_1w, return_1m, prediction_correct, hold_days, return_at_hold)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            date, symbol, decision, price_at_prediction,
            price_1d_later, price_1w_later, price_1m_later,
            return_1d, return_1w, return_1m,
            1 if prediction_correct else 0 if prediction_correct is not None else None,
            hold_days, return_at_hold
        ))
        conn.commit()
    finally:
        conn.close()


def get_backtest_result(date: str, symbol: str) -> Optional[dict]:
    """Get backtest result for a specific stock and date."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT * FROM backtest_results WHERE date = ? AND symbol = ?
        """, (date, symbol))
        row = cursor.fetchone()

        if row:
            return {
                'date': row['date'],
                'symbol': row['symbol'],
                'decision': row['decision'],
                'price_at_prediction': row['price_at_prediction'],
                'price_1d_later': row['price_1d_later'],
                'price_1w_later': row['price_1w_later'],
                'price_1m_later': row['price_1m_later'],
                'return_1d': row['return_1d'],
                'return_1w': row['return_1w'],
                'return_1m': row['return_1m'],
                'prediction_correct': bool(row['prediction_correct']) if row['prediction_correct'] is not None else None,
                'hold_days': row['hold_days'] if 'hold_days' in row.keys() else None,
                'return_at_hold': row['return_at_hold'] if 'return_at_hold' in row.keys() else None,
                'calculated_at': row['calculated_at']
            }
        return None
    finally:
        conn.close()


def get_backtest_results_by_date(date: str) -> list:
    """Get all backtest results for a specific date."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT * FROM backtest_results WHERE date = ?
        """, (date,))

        return [
            {
                'symbol': row['symbol'],
                'decision': row['decision'],
                'price_at_prediction': row['price_at_prediction'],
                'price_1d_later': row['price_1d_later'],
                'price_1w_later': row['price_1w_later'],
                'price_1m_later': row['price_1m_later'],
                'return_1d': row['return_1d'],
                'return_1w': row['return_1w'],
                'return_1m': row['return_1m'],
                'prediction_correct': bool(row['prediction_correct']) if row['prediction_correct'] is not None else None,
                'hold_days': row['hold_days'] if 'hold_days' in row.keys() else None,
                'return_at_hold': row['return_at_hold'] if 'return_at_hold' in row.keys() else None,
            }
            for row in cursor.fetchall()
        ]
    finally:
        conn.close()


def get_all_backtest_results_grouped() -> dict:
    """Get all backtest results grouped by date for the History page bundle.

    Returns: { date: { symbol: { return_1d, return_1w, return_1m, return_at_hold, hold_days, prediction_correct, decision } } }
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT date, symbol, decision, return_1d, return_1w, return_1m,
                   return_at_hold, hold_days, prediction_correct,
                   price_at_prediction
            FROM backtest_results
            ORDER BY date
        """)

        grouped: dict = {}
        for row in cursor.fetchall():
            date = row['date']
            if date not in grouped:
                grouped[date] = {}
            grouped[date][row['symbol']] = {
                'return_1d': row['return_1d'],
                'return_1w': row['return_1w'],
                'return_1m': row['return_1m'],
                'return_at_hold': row['return_at_hold'],
                'hold_days': row['hold_days'] if 'hold_days' in row.keys() else None,
                'prediction_correct': bool(row['prediction_correct']) if row['prediction_correct'] is not None else None,
                'decision': row['decision'],
            }
        return grouped
    finally:
        conn.close()


def get_all_backtest_results() -> list:
    """Get all backtest results for accuracy calculation."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT br.*, sa.confidence, sa.risk
            FROM backtest_results br
            LEFT JOIN stock_analysis sa ON br.date = sa.date AND br.symbol = sa.symbol
            WHERE br.prediction_correct IS NOT NULL
            ORDER BY br.date DESC
        """)

        return [
            {
                'date': row['date'],
                'symbol': row['symbol'],
                'decision': row['decision'],
                'confidence': row['confidence'],
                'risk': row['risk'],
                'price_at_prediction': row['price_at_prediction'],
                'return_1d': row['return_1d'],
                'return_1w': row['return_1w'],
                'return_1m': row['return_1m'],
                'prediction_correct': bool(row['prediction_correct']),
                'hold_days': row['hold_days'] if 'hold_days' in row.keys() else None,
                'return_at_hold': row['return_at_hold'] if 'return_at_hold' in row.keys() else None,
            }
            for row in cursor.fetchall()
        ]
    finally:
        conn.close()


def calculate_accuracy_metrics() -> dict:
    """Calculate overall backtest accuracy metrics.

    Cross-references backtest_results with stock_analysis to use the correct
    (sanitized) decision values and compute prediction correctness accurately.
    """
    conn = get_connection()
    cursor = conn.cursor()
    empty = {
        'overall_accuracy': 0,
        'total_predictions': 0,
        'correct_predictions': 0,
        'by_decision': {'BUY': {'accuracy': 0, 'total': 0, 'correct': 0},
                        'SELL': {'accuracy': 0, 'total': 0, 'correct': 0},
                        'HOLD': {'accuracy': 0, 'total': 0, 'correct': 0}},
        'by_confidence': {}
    }

    try:
        # Join backtest_results with stock_analysis to get the correct decision
        cursor.execute("""
            SELECT br.date, br.symbol, br.return_1d, br.return_1w, br.return_at_hold,
                   sa.decision as sa_decision, sa.confidence
            FROM backtest_results br
            JOIN stock_analysis sa ON br.date = sa.date AND br.symbol = sa.symbol
            WHERE br.return_1d IS NOT NULL OR br.return_at_hold IS NOT NULL
        """)
        rows = cursor.fetchall()

        if not rows:
            return empty

        # Compute accuracy using sanitized decisions and primaryReturn logic
        total = 0
        correct = 0
        by_decision = {'BUY': {'total': 0, 'correct': 0}, 'SELL': {'total': 0, 'correct': 0}, 'HOLD': {'total': 0, 'correct': 0}}

        for row in rows:
            decision = sanitize_decision(row['sa_decision'])
            primary_return = row['return_at_hold'] if row['return_at_hold'] is not None else row['return_1d']
            if primary_return is None:
                continue

            total += 1
            if decision in by_decision:
                by_decision[decision]['total'] += 1

            if decision in ('BUY', 'HOLD'):
                is_correct = primary_return > 0
            elif decision == 'SELL':
                is_correct = primary_return < 0
            else:
                continue

            if is_correct:
                correct += 1
                if decision in by_decision:
                    by_decision[decision]['correct'] += 1

        # Build response
        for d in by_decision:
            t = by_decision[d]['total']
            c = by_decision[d]['correct']
            by_decision[d]['accuracy'] = round(c / t * 100, 1) if t > 0 else 0

        return {
            'overall_accuracy': round(correct / total * 100, 1) if total > 0 else 0,
            'total_predictions': total,
            'correct_predictions': correct,
            'by_decision': by_decision,
            'by_confidence': {}
        }
    finally:
        conn.close()


def compute_stock_rankings(date: str):
    """Compute and store rank (1..N) for all stocks analyzed on a given date.

    Uses a deterministic composite score:
      decision:   BUY=30, HOLD=15, SELL=0
      confidence: HIGH=20, MEDIUM=10, LOW=0
      risk (inv): LOW=15, MEDIUM=8, HIGH=0
      hold bonus: BUY with short hold gets up to +5

    Score range: 0-70. Sorted descending; ties broken alphabetically.
    """
    DECISION_W = {'BUY': 30, 'HOLD': 15, 'SELL': 0}
    CONFIDENCE_W = {'HIGH': 20, 'MEDIUM': 10, 'LOW': 0}
    RISK_W = {'LOW': 15, 'MEDIUM': 8, 'HIGH': 0}

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT id, symbol, decision, confidence, risk, hold_days
            FROM stock_analysis WHERE date = ?
        """, (date,))
        rows = cursor.fetchall()

        if not rows:
            return

        scored = []
        for row in rows:
            decision = sanitize_decision(row['decision'])
            confidence = (row['confidence'] or 'MEDIUM').upper()
            risk = (row['risk'] or 'MEDIUM').upper()
            hold_days = row['hold_days']

            score = DECISION_W.get(decision, 0)
            score += CONFIDENCE_W.get(confidence, 0)
            score += RISK_W.get(risk, 0)

            # Hold days bonus: BUY with shorter hold = more immediate opportunity
            if decision == 'BUY' and hold_days and hold_days > 0:
                if hold_days <= 5:
                    score += 5
                elif hold_days <= 10:
                    score += 4
                elif hold_days <= 15:
                    score += 3
                elif hold_days <= 20:
                    score += 2
                else:
                    score += 1

            scored.append((row['id'], row['symbol'], score))

        # Sort by score descending, then symbol ascending for ties
        scored.sort(key=lambda x: (-x[2], x[1]))

        for rank, (row_id, _symbol, _score) in enumerate(scored, start=1):
            cursor.execute(
                "UPDATE stock_analysis SET rank = ? WHERE id = ?",
                (rank, row_id)
            )

        conn.commit()
    finally:
        conn.close()


def update_daily_recommendation_summary(date: str):
    """Auto-create/update daily_recommendations from stock_analysis for a date.

    Computes rankings first, then counts BUY/SELL/HOLD decisions, generates
    rank-ordered top_picks and stocks_to_avoid, and upserts the row.
    """
    # Compute rankings first so top_picks/stocks_to_avoid use rank order
    compute_stock_rankings(date)

    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Get all stock analyses ordered by rank
        cursor.execute("""
            SELECT symbol, company_name, decision, confidence, risk, raw_analysis, rank
            FROM stock_analysis WHERE date = ?
            ORDER BY rank ASC NULLS LAST
        """, (date,))
        rows = cursor.fetchall()

        if not rows:
            return

        buy_count = 0
        sell_count = 0
        hold_count = 0
        buy_stocks = []
        sell_stocks = []

        for row in rows:
            decision = sanitize_decision(row['decision'])
            if decision == 'BUY':
                buy_count += 1
                buy_stocks.append({
                    'symbol': row['symbol'],
                    'company_name': row['company_name'] or row['symbol'],
                    'confidence': row['confidence'] or 'MEDIUM',
                    'reason': (row['raw_analysis'] or '')[:200],
                    'rank': row['rank']
                })
            elif decision == 'SELL':
                sell_count += 1
                sell_stocks.append({
                    'symbol': row['symbol'],
                    'company_name': row['company_name'] or row['symbol'],
                    'confidence': row['confidence'] or 'MEDIUM',
                    'reason': (row['raw_analysis'] or '')[:200],
                    'rank': row['rank']
                })
            else:
                hold_count += 1

        total = buy_count + sell_count + hold_count

        # Top picks: top 5 BUY stocks by rank (already rank-sorted)
        top_picks = [
            {'symbol': s['symbol'], 'company_name': s['company_name'],
             'confidence': s['confidence'], 'reason': s['reason'],
             'rank': s['rank']}
            for s in buy_stocks[:5]
        ]

        # Stocks to avoid: all SELL stocks
        stocks_to_avoid = [
            {'symbol': s['symbol'], 'company_name': s['company_name'],
             'confidence': s['confidence'], 'reason': s['reason'],
             'rank': s['rank']}
            for s in sell_stocks
        ]

        cursor.execute("""
            INSERT OR REPLACE INTO daily_recommendations
            (date, summary_total, summary_buy, summary_sell, summary_hold, top_picks, stocks_to_avoid)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            date, total, buy_count, sell_count, hold_count,
            json.dumps(top_picks),
            json.dumps(stocks_to_avoid)
        ))
        conn.commit()
    finally:
        conn.close()


def rebuild_all_daily_recommendations():
    """Rebuild daily_recommendations for all dates that have stock_analysis data.

    This ensures dates with stock_analysis but missing daily_recommendations
    entries become visible to the API.
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT DISTINCT date FROM stock_analysis")
        dates = [row['date'] for row in cursor.fetchall()]
    finally:
        conn.close()

    for date in dates:
        update_daily_recommendation_summary(date)

    if dates:
        print(f"[DB] Rebuilt daily_recommendations for {len(dates)} dates: {sorted(dates)}")


# Initialize database on module import
init_db()
