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
            UNIQUE(date, symbol, step_number)
        )
    """)

    # Create data_source_logs table (stores what raw data was fetched)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS data_source_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            source_type TEXT,
            source_name TEXT,
            data_fetched TEXT,
            fetch_timestamp TEXT,
            success INTEGER DEFAULT 1,
            error_message TEXT
        )
    """)

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
            cursor.execute("""
                INSERT OR REPLACE INTO pipeline_steps
                (date, symbol, step_number, step_name, status,
                 started_at, completed_at, duration_ms, output_summary)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                date, symbol,
                step.get('step_number'),
                step.get('step_name'),
                step.get('status'),
                step.get('started_at'),
                step.get('completed_at'),
                step.get('duration_ms'),
                step.get('output_summary')
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

        return [
            {
                'step_number': row['step_number'],
                'step_name': row['step_name'],
                'status': row['status'],
                'started_at': row['started_at'],
                'completed_at': row['completed_at'],
                'duration_ms': row['duration_ms'],
                'output_summary': row['output_summary']
            }
            for row in cursor.fetchall()
        ]
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
                (date, symbol, source_type, source_name, data_fetched,
                 fetch_timestamp, success, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                date, symbol,
                log.get('source_type'),
                log.get('source_name'),
                json.dumps(log.get('data_fetched')) if log.get('data_fetched') else None,
                log.get('fetch_timestamp') or datetime.now().isoformat(),
                1 if log.get('success', True) else 0,
                log.get('error_message')
            ))
        conn.commit()
    finally:
        conn.close()


def get_data_source_logs(date: str, symbol: str) -> list:
    """Get all data source logs for a stock on a date."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT * FROM data_source_logs
            WHERE date = ? AND symbol = ?
            ORDER BY fetch_timestamp
        """, (date, symbol))

        return [
            {
                'source_type': row['source_type'],
                'source_name': row['source_name'],
                'data_fetched': json.loads(row['data_fetched']) if row['data_fetched'] else None,
                'fetch_timestamp': row['fetch_timestamp'],
                'success': bool(row['success']),
                'error_message': row['error_message']
            }
            for row in cursor.fetchall()
        ]
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

        summaries = []
        for symbol in symbols:
            # Get pipeline status
            cursor.execute("""
                SELECT step_name, status FROM pipeline_steps
                WHERE date = ? AND symbol = ?
                ORDER BY step_number
            """, (date, symbol))
            steps = cursor.fetchall()

            # Get agent report count
            cursor.execute("""
                SELECT COUNT(*) as count FROM agent_reports
                WHERE date = ? AND symbol = ?
            """, (date, symbol))
            agent_count = cursor.fetchone()['count']

            summaries.append({
                'symbol': symbol,
                'pipeline_steps': [{'step_name': s['step_name'], 'status': s['status']} for s in steps],
                'agent_reports_count': agent_count,
                'has_debates': bool(get_debate_history(date, symbol))
            })

        return summaries
    finally:
        conn.close()


# Initialize database on module import
init_db()
