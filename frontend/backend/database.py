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
            decision = (a['decision'] or '').strip().upper()
            if decision not in ('BUY', 'SELL', 'HOLD'):
                decision = 'HOLD'
            analysis[a['symbol']] = {
                'symbol': a['symbol'],
                'company_name': a['company_name'],
                'decision': decision,
                'confidence': a['confidence'] or 'MEDIUM',
                'risk': a['risk'] or 'MEDIUM',
                'raw_analysis': a['raw_analysis'],
                'hold_days': a['hold_days'] if 'hold_days' in a.keys() else None
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
            SELECT date, decision, confidence, risk, hold_days
            FROM stock_analysis
            WHERE symbol = ?
            ORDER BY date DESC
        """, (symbol,))

        results = []
        for row in cursor.fetchall():
            decision = (row['decision'] or '').strip().upper()
            # Sanitize: only allow BUY/SELL/HOLD
            if decision not in ('BUY', 'SELL', 'HOLD'):
                decision = 'HOLD'
            results.append({
                'date': row['date'],
                'decision': decision,
                'confidence': row['confidence'] or 'MEDIUM',
                'risk': row['risk'] or 'MEDIUM',
                'hold_days': row['hold_days'] if 'hold_days' in row.keys() else None
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
                         hold_days: int = None):
    """Save a backtest result for a stock recommendation."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT OR REPLACE INTO backtest_results
            (date, symbol, decision, price_at_prediction,
             price_1d_later, price_1w_later, price_1m_later,
             return_1d, return_1w, return_1m, prediction_correct, hold_days)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            date, symbol, decision, price_at_prediction,
            price_1d_later, price_1w_later, price_1m_later,
            return_1d, return_1w, return_1m,
            1 if prediction_correct else 0 if prediction_correct is not None else None,
            hold_days
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
                'hold_days': row['hold_days'] if 'hold_days' in row.keys() else None
            }
            for row in cursor.fetchall()
        ]
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
                'prediction_correct': bool(row['prediction_correct'])
            }
            for row in cursor.fetchall()
        ]
    finally:
        conn.close()


def calculate_accuracy_metrics() -> dict:
    """Calculate overall backtest accuracy metrics."""
    results = get_all_backtest_results()

    if not results:
        return {
            'overall_accuracy': 0,
            'total_predictions': 0,
            'correct_predictions': 0,
            'by_decision': {'BUY': {'accuracy': 0, 'total': 0}, 'SELL': {'accuracy': 0, 'total': 0}, 'HOLD': {'accuracy': 0, 'total': 0}},
            'by_confidence': {'High': {'accuracy': 0, 'total': 0}, 'Medium': {'accuracy': 0, 'total': 0}, 'Low': {'accuracy': 0, 'total': 0}}
        }

    total = len(results)
    correct = sum(1 for r in results if r['prediction_correct'])

    # By decision type
    by_decision = {}
    for decision in ['BUY', 'SELL', 'HOLD']:
        decision_results = [r for r in results if r['decision'] == decision]
        if decision_results:
            decision_correct = sum(1 for r in decision_results if r['prediction_correct'])
            by_decision[decision] = {
                'accuracy': round(decision_correct / len(decision_results) * 100, 1),
                'total': len(decision_results),
                'correct': decision_correct
            }
        else:
            by_decision[decision] = {'accuracy': 0, 'total': 0, 'correct': 0}

    # By confidence level
    by_confidence = {}
    for conf in ['High', 'Medium', 'Low']:
        conf_results = [r for r in results if r.get('confidence') == conf]
        if conf_results:
            conf_correct = sum(1 for r in conf_results if r['prediction_correct'])
            by_confidence[conf] = {
                'accuracy': round(conf_correct / len(conf_results) * 100, 1),
                'total': len(conf_results),
                'correct': conf_correct
            }
        else:
            by_confidence[conf] = {'accuracy': 0, 'total': 0, 'correct': 0}

    return {
        'overall_accuracy': round(correct / total * 100, 1) if total > 0 else 0,
        'total_predictions': total,
        'correct_predictions': correct,
        'by_decision': by_decision,
        'by_confidence': by_confidence
    }


def update_daily_recommendation_summary(date: str):
    """Auto-create/update daily_recommendations from stock_analysis for a date.

    Counts BUY/SELL/HOLD decisions, generates top_picks and stocks_to_avoid,
    and upserts the daily_recommendations row.
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Get all stock analyses for this date
        cursor.execute("""
            SELECT symbol, company_name, decision, confidence, risk, raw_analysis
            FROM stock_analysis WHERE date = ?
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
            decision = (row['decision'] or '').upper()
            if decision == 'BUY':
                buy_count += 1
                buy_stocks.append({
                    'symbol': row['symbol'],
                    'company_name': row['company_name'] or row['symbol'],
                    'decision': 'BUY',
                    'confidence': row['confidence'] or 'MEDIUM',
                    'reason': (row['raw_analysis'] or '')[:200]
                })
            elif decision == 'SELL':
                sell_count += 1
                sell_stocks.append({
                    'symbol': row['symbol'],
                    'company_name': row['company_name'] or row['symbol'],
                    'decision': 'SELL',
                    'confidence': row['confidence'] or 'MEDIUM',
                    'reason': (row['raw_analysis'] or '')[:200]
                })
            else:
                hold_count += 1

        total = buy_count + sell_count + hold_count

        # Top picks: up to 5 BUY stocks
        top_picks = [
            {'symbol': s['symbol'], 'company_name': s['company_name'],
             'confidence': s['confidence'], 'reason': s['reason']}
            for s in buy_stocks[:5]
        ]

        # Stocks to avoid: up to 5 SELL stocks
        stocks_to_avoid = [
            {'symbol': s['symbol'], 'company_name': s['company_name'],
             'confidence': s['confidence'], 'reason': s['reason']}
            for s in sell_stocks[:5]
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
