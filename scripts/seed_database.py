#!/usr/bin/env python3
"""
Seed the TradingAgents database with realistic simulation data.

Usage:
    python scripts/seed_database.py              # Full reset + seed
    python scripts/seed_database.py --positions  # Positions only
    python scripts/seed_database.py --signals    # Signals only
    python scripts/seed_database.py --all        # Everything (default)

Clears existing seeded data (keeps schema), then populates:
- SQLite: positions, signals, watchlist, analyses
- YAML: exit plans per platform
- Markdown: post-mortems
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "portfolio.db"
POSITIONS_BASE = Path.home() / ".tradingagents" / "positions"
POST_MORTEMS_DIR = Path.home() / ".tradingagents" / "post-mortems"

# ── Secret sanitization ───────────────────────────────────────────────────────
# Strips API keys, tokens, and credentials from text before writing to DB.
# Applied to all user-facing and AI-generated text fields.
import re

_SANITIZE_PATTERNS = [
    (re.compile(r'sk-[-A-Za-z0-9]{20,}'),        '[API_KEY_REMOVED]'),
    (re.compile(r'sk-ant(?:thropic)?[-][A-Za-z0-9]{20,}', re.I), '[API_KEY_REMOVED]'),
    (re.compile(r'Bearer\s+[A-Za-z0-9_\-]{10,}'),          '[TOKEN_REMOVED]'),
    (re.compile(r'https?://[^:\s]+:[^@\s]+@[^\s]+'),      '[URL_CREDS_REMOVED]'),
    (re.compile(r'(?:password|secret|apikey|api_key|token|auth)[=:]\s*[^\s;,]{8,}', re.I), '[SECRET_REMOVED]'),
    (re.compile(r'-----BEGIN\s+(?:RSA|EC|OPENSSH|DSA|PRIVATE)\s+KEY-----[\s\S]+?-----END\s+\w+\s+KEY-----'), '[PRIVATE_KEY_REMOVED]'),
    (re.compile(r'[A-Fa-f0-9]{40,}'),                        '[HEX_TOKEN_REMOVED]'),
]

def sanitize_for_db(value: str | None) -> str | None:
    if value is None:
        return None
    result = str(value)
    for pattern, replacement in _SANITIZE_PATTERNS:
        result = pattern.sub(replacement, result)
    return result

# ── Date helpers ────────────────────────────────────────────────────

TODAY = date.today()
WEEKS_AGO = lambda n: (TODAY - timedelta(weeks=n)).isoformat()
DAYS_AGO = lambda n: (TODAY - timedelta(days=n)).isoformat()
MONTHS_AGO = lambda n: (TODAY - timedelta(days=n * 30)).isoformat()


def d(weeks=0, days=0):
    return (TODAY - timedelta(weeks=weeks, days=days)).isoformat()


# ── SQLite helpers ─────────────────────────────────────────────────

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def clear_table(table: str, keep_types: list = None):
    """Delete seeded rows (identified by platform != 'unknown' or known dates)."""
    db = get_db()
    if table == "positions":
        db.execute("DELETE FROM positions WHERE platform != 'unknown'")
    elif table == "signals":
        # Only clear synthetic test signals (we mark them with specific dates)
        db.execute("DELETE FROM signals WHERE date BETWEEN '2026-01-01' AND '2026-04-01'")
    elif table == "watchlist":
        db.execute("DELETE FROM watchlist WHERE platform != 'unknown'")
    elif table == "analyses":
        db.execute("DELETE FROM analyses WHERE date BETWEEN '2026-01-01' AND '2026-04-01'")
    db.commit()
    print(f"  Cleared {table}")


def seed_positions():
    clear_table("positions")

    positions = [
        # ── DeGiro: sensible, diversified ─────────────────────────────────────
        {
            "ticker": "VWCE.DE",
            "exchange": "XETRA",
            "platform": "degiero",
            "quantity": 35,
            "avg_cost": 126.40,
            "entry_date": d(weeks=16),
            "thesis": "All-world ETF — low-cost core holding, accumulating",
            "status": "open",
            "notes": "Accumulating quarterly. MSCI World exposure.",
        },
        {
            "ticker": "AAPL",
            "exchange": "US",
            "platform": "degiero",
            "quantity": 25,
            "avg_cost": 188.50,
            "entry_date": d(weeks=10),
            "thesis": "Services segment compounding; Vision Pro ecosystem building",
            "status": "open",
            "notes": "Hold signal from analysis. Services revenue acceleration.",
        },
        {
            "ticker": "MSFT",
            "exchange": "US",
            "platform": "degiero",
            "quantity": 20,
            "avg_cost": 430.00,
            "entry_date": d(weeks=8),
            "thesis": "Azure AI monetization accelerating; Copilot enterprise adoption strong",
            "status": "open",
        },
        {
            "ticker": "NVDA",
            "exchange": "US",
            "platform": "degiero",
            "quantity": 15,
            "avg_cost": 880.00,
            "entry_date": d(weeks=6),
            "thesis": "AI infrastructure demand insatiable; H100/H200 supply constrained",
            "status": "open",
        },
        # ── IBKR: slightly overweight — triggers governance ───────────────────
        {
            "ticker": "AAPL",
            "exchange": "US",
            "platform": "ibkr",
            "quantity": 150,
            "avg_cost": 182.30,
            "entry_date": d(weeks=14),
            "thesis": "Long-term AI services compounding — larger position here",
            "status": "open",
            "notes": "Note: this position alone is ~28% of ibkr portfolio — triggers max-position rule",
        },
        {
            "ticker": "MSFT",
            "exchange": "US",
            "platform": "ibkr",
            "quantity": 40,
            "avg_cost": 408.00,
            "entry_date": d(weeks=7),
            "thesis": "Cloud + AI platform play; GitHub Copilot enterprise roll-out",
            "status": "open",
        },
        {
            "ticker": "TKA.DE",
            "exchange": "XETRA",
            "platform": "ibkr",
            "quantity": 1000,
            "avg_cost": 8.62,
            "entry_date": d(weeks=5),
            "thesis": "German industrial automation; order pipeline strong for H2",
            "status": "open",
        },
        {
            "ticker": "VWCE.DE",
            "exchange": "XETRA",
            "platform": "ibkr",
            "quantity": 20,
            "avg_cost": 133.20,
            "entry_date": d(weeks=4),
            "thesis": "Core satnav ETF position alongside individual stock picks",
            "status": "open",
        },
        # ── Test platform: edge cases ────────────────────────────────────────
        {
            "ticker": "AAPL",
            "exchange": "US",
            "platform": "test",
            "quantity": 10,
            "avg_cost": 192.00,
            "entry_date": d(weeks=3),
            "thesis": "Testing signal accuracy — smaller position",
            "status": "open",
        },
        {
            "ticker": "ETH",
            "exchange": "CRYPTO",
            "platform": "test",
            "quantity": 0.5,
            "avg_cost": 2850.00,
            "entry_date": d(weeks=2),
            "thesis": "Crypto exposure test — ETH blockchain infrastructure",
            "status": "open",
            "notes": "Crypto position — risk-off behaviour expected",
        },
        {
            "ticker": "TSLA",
            "exchange": "US",
            "platform": "test",
            "quantity": 5,
            "avg_cost": 245.00,
            "entry_date": d(weeks=1),
            "thesis": "EV market share pressure; FSD licensing optionality",
            "status": "open",
            "notes": "Recent addition — watch for thesis invalidation",
        },
    ]

    db = get_db()
    for p in positions:
        # Ensure all columns present (sqlite3 requires all named params)
        p.setdefault("notes", None)
        p["thesis"] = sanitize_for_db(p.get("thesis"))
        p["notes"] = sanitize_for_db(p.get("notes"))
        db.execute("""
            INSERT INTO positions (ticker, exchange, platform, quantity, avg_cost, entry_date, thesis, status, notes)
            VALUES (:ticker, :exchange, :platform, :quantity, :avg_cost, :entry_date, :thesis, :status, :notes)
        """, p)
    db.commit()
    print(f"  Inserted {len(positions)} positions")


def seed_signals():
    clear_table("signals")

    signals = [
        # ── VWCE.DE signals ──────────────────────────────────────────────────
        {"ticker": "VWCE.DE", "platform": "degiero", "date": d(weeks=16), "signal": "hold", "confidence": "0.72", "reasoning": "All-world ETF, low-cost, accumulating position. No thesis change."},
        {"ticker": "VWCE.DE", "platform": "degiero", "date": d(weeks=12), "signal": "hold", "confidence": "0.70", "reasoning": "MSCI World constituents strong. No need to rebalance."},
        {"ticker": "VWCE.DE", "platform": "degiero", "date": d(weeks=8), "signal": "overweight", "confidence": "0.75", "reasoning": "Q4 earnings beat. Global equity markets favouring developed market exposure."},
        {"ticker": "VWCE.DE", "platform": "degiero", "date": d(weeks=4), "signal": "buy", "confidence": "0.78", "reasoning": "Market dip provides entry opportunity. Accumulation phase continues."},
        {"ticker": "VWCE.DE", "platform": "ibkr", "date": d(weeks=4), "signal": "buy", "confidence": "0.75", "reasoning": "Core satnav position. Low-cost exposure to global equity."},

        # ── AAPL signals ────────────────────────────────────────────────────
        {"ticker": "AAPL", "platform": "test", "date": d(weeks=14), "signal": "buy", "confidence": "0.78", "reasoning": "AI services integration driving margin expansion. Vision Pro ecosystem."},
        {"ticker": "AAPL", "platform": "degiero", "date": d(weeks=10), "signal": "hold", "confidence": "0.70", "reasoning": "Services revenue acceleration offset by iPhone softness. Hold."},
        {"ticker": "AAPL", "platform": "degiero", "date": d(weeks=6), "signal": "overweight", "confidence": "0.80", "reasoning": "WWDC catalyst identified. AI integration across device lineup strong."},
        {"ticker": "AAPL", "platform": "degiero", "date": d(weeks=2), "signal": "buy", "confidence": "0.85", "reasoning": "Services margins hit 74%. AI features driving upgrade cycle. Target raised."},
        {"ticker": "AAPL", "platform": "ibkr", "date": d(weeks=14), "signal": "buy", "confidence": "0.82", "reasoning": "Long-term AI compounding thesis. Larger position justified by conviction."},
        {"ticker": "AAPL", "platform": "ibkr", "date": d(weeks=8), "signal": "overweight", "confidence": "0.78", "reasoning": "Position overweight but thesis unchanged. Monitor for rebalancing."},
        {"ticker": "AAPL", "platform": "ibkr", "date": d(weeks=3), "signal": "buy", "confidence": "0.88", "reasoning": "Services segment 3-year CAGR 15%. Target price raised to $220."},
        {"ticker": "AAPL", "platform": "test", "date": d(weeks=3), "signal": "buy", "confidence": "0.82", "reasoning": "Signal accuracy test. AI services still primary driver."},

        # ── MSFT signals ────────────────────────────────────────────────────
        {"ticker": "MSFT", "platform": "degiero", "date": d(weeks=8), "signal": "buy", "confidence": "0.76", "reasoning": "Azure AI monetization ahead of schedule. Copilot enterprise adoption."},
        {"ticker": "MSFT", "platform": "degiero", "date": d(weeks=4), "signal": "buy", "confidence": "0.80", "reasoning": "GitHub Copilot at 1.3M paid subscribers. Azure AI services revenue growing 30%."},
        {"ticker": "MSFT", "platform": "ibkr", "date": d(weeks=7), "signal": "buy", "confidence": "0.75", "reasoning": "Cloud + AI platform. GitHub Copilot enterprise rollout strong."},
        {"ticker": "MSFT", "platform": "ibkr", "date": d(weeks=2), "signal": "overweight", "confidence": "0.79", "reasoning": "Azure AI competitive moat widening. Target raised to $460."},

        # ── NVDA signals ────────────────────────────────────────────────────
        {"ticker": "NVDA", "platform": "degiero", "date": d(weeks=6), "signal": "buy", "confidence": "0.72", "reasoning": "AI infrastructure spend insatiable. H100 supply constrained through Q2."},
        {"ticker": "NVDA", "platform": "degiero", "date": d(weeks=2), "signal": "overweight", "confidence": "0.80", "reasoning": "Blackwell架构 ( Blackwell architecture) driving next wave. Data centre revenue +85%."},

        # ── TKA.DE signals ──────────────────────────────────────────────────
        {"ticker": "TKA.DE", "platform": "ibkr", "date": d(weeks=5), "signal": "buy", "confidence": "0.68", "reasoning": "German industrial automation cycle bottoming. Order pipeline strong for H2."},
        {"ticker": "TKA.DE", "platform": "ibkr", "date": d(weeks=1), "signal": "buy", "confidence": "0.73", "reasoning": "KONE partnership accelerating revenue. Price target €10.50."},
        {"ticker": "TKA.DE", "platform": "test", "date": d(weeks=16), "signal": "sell", "confidence": "0.55", "reasoning": "Position too small for delisted tracking. Closed out."},

        # ── ETH signals ────────────────────────────────────────────────────
        {"ticker": "ETH", "platform": "test", "date": d(weeks=2), "signal": "buy", "confidence": "0.60", "reasoning": "Crypto exposure test. ETH staking yield 3.8%. Small position."},

        # ── TSLA signals ────────────────────────────────────────────────────
        {"ticker": "TSLA", "platform": "test", "date": d(weeks=1), "signal": "underweight", "confidence": "0.65", "reasoning": "EV price war compressing margins. FSD licensing uncertain. Reduce."},

        # ── Historical / closed signals (for post-mortems) ─────────────────
        {"ticker": "AAPL", "platform": "ibkr", "date": d(weeks=26), "signal": "buy", "confidence": "0.75", "reasoning": "Initial AAPL position entry"},
        {"ticker": "AAPL", "platform": "ibkr", "date": d(weeks=20), "signal": "overweight", "confidence": "0.80", "reasoning": "AI integration thesis strengthening"},
        {"ticker": "AAPL", "platform": "ibkr", "date": d(weeks=16), "signal": "hold", "confidence": "0.72", "reasoning": "Hold signal. Services growth stable."},
        {"ticker": "MSFT", "platform": "degiero", "date": d(weeks=12), "signal": "buy", "confidence": "0.70", "reasoning": "Initial MSFT position. Cloud + AI platform."},
    ]

    db = get_db()
    for s in signals:
        s["reasoning"] = sanitize_for_db(s.get("reasoning"))
        db.execute("""
            INSERT INTO signals (ticker, platform, date, signal, reasoning, confidence)
            VALUES (:ticker, :platform, :date, :signal, :reasoning, :confidence)
        """, s)
    db.commit()
    print(f"  Inserted {len(signals)} signals")


def seed_watchlist():
    clear_table("watchlist")

    watchlist = [
        {"ticker": "GOOGL", "platform": "degiero", "exchange": "US", "thesis": "Gemini Ultra competitive with GPT-4. Cloud growth accelerating.", "priority": "high", "stage": "analyzed"},
        {"ticker": "AMZN", "platform": "degiero", "exchange": "US", "thesis": "AWS AI services and Rufus e-commerce AI. Margin expansion.", "priority": "high", "stage": "candidate"},
        {"ticker": "META", "platform": "ibkr", "exchange": "US", "thesis": "Llama ecosystem and AI ad tools driving efficiency. Threads growth.", "priority": "high", "stage": "analyzed"},
        {"ticker": "ASML", "platform": "degiero", "exchange": "EUR", "thesis": "Lithography monopoly for advanced chips. AI capex beneficiaries.", "priority": "medium", "stage": "researching"},
        {"ticker": "SAP", "platform": "degiero", "exchange": "EUR", "thesis": "RISE with SAP transitioning to cloud. Joule AI assistant.", "priority": "medium", "stage": "researching"},
        {"ticker": "BTC", "platform": "test", "exchange": "CRYPTO", "thesis": "Bitcoin ETF inflows strong. Store of value narrative.", "priority": "low", "stage": "researching"},
        {"ticker": "SOL", "platform": "test", "exchange": "CRYPTO", "thesis": "Solana DeFi ecosystem growing. Low-cost transactions.", "priority": "low", "stage": "researching"},
        {"ticker": "ARM", "platform": "degiero", "exchange": "US", "thesis": "AI inference chip design. Royalty revenue growing.", "priority": "medium", "stage": "researching"},
    ]

    db = get_db()
    for w in watchlist:
        w["added_date"] = d(weeks=8)
        w["thesis"] = sanitize_for_db(w.get("thesis"))
        db.execute("""
            INSERT INTO watchlist (ticker, exchange, platform, thesis, priority, stage, added_date)
            VALUES (:ticker, :exchange, :platform, :thesis, :priority, :stage, :added_date)
        """, w)
    db.commit()
    print(f"  Inserted {len(watchlist)} watchlist items")


def seed_analyses():
    clear_table("analyses")

    analyses = [
        {"ticker": "AAPL", "platform": "degiero", "date": d(weeks=10), "decision": "Hold — Services revenue acceleration confirmed at 74% margins. iPhone softness offset by AI-driven upgrade cycle. Confidence 0.70."},
        {"ticker": "AAPL", "platform": "ibkr", "date": d(weeks=14), "decision": "Buy (overweight) — AI services compounding thesis strong. Position size justified by high conviction. Confidence 0.82."},
        {"ticker": "MSFT", "platform": "degiero", "date": d(weeks=8), "decision": "Buy — Azure AI monetization ahead of schedule. Copilot enterprise adoption exceeding targets. Confidence 0.76."},
        {"ticker": "NVDA", "platform": "degiero", "date": d(weeks=6), "decision": "Buy — AI infrastructure demand insatiable. H100 supply constrained. Confidence 0.72."},
        {"ticker": "TKA.DE", "platform": "ibkr", "date": d(weeks=5), "decision": "Buy — German industrial cycle bottoming. KONE deal pipeline strong. Confidence 0.68."},
        {"ticker": "VWCE.DE", "platform": "degiero", "date": d(weeks=4), "decision": "Buy — Market dip entry opportunity. Accumulation continues. Confidence 0.78."},
        {"ticker": "AAPL", "platform": "degiero", "date": d(weeks=2), "decision": "Buy — WWDC catalyst. AI features across device lineup strong. Target raised. Confidence 0.85."},
    ]

    db = get_db()
    for a in analyses:
        db.execute("""
            INSERT INTO analyses (ticker, platform, date, decision)
            VALUES (:ticker, :platform, :date, :decision)
        """, a)
    db.commit()
    print(f"  Inserted {len(analyses)} analyses")


def seed_exit_plans():
    """Create YAML exit plans per platform directory."""

    plans = [
        # ── DeGiro plans ────────────────────────────────────────────────────
        {
            "platform": "degiero", "ticker": "VWCE.DE",
            "entry_price": 126.40, "quantity": 35, "entry_date": d(weeks=16),
            "thesis": "All-world ETF accumulation — low-cost core holding",
            "invalidation_price": 113.76, "invalidation_thesis": "Global equity bear market; MSCI World -15% from peak",
            "targets": [
                {"price": 142.00, "label": "Target 1: +12%", "fraction": 0.33},
                {"price": 158.00, "label": "Target 2: +25%", "fraction": 0.33},
                {"price": 175.00, "label": "Target 3: +38%", "fraction": 0.34},
            ],
            "time_stop": (TODAY + timedelta(days=180)).isoformat(),
            "notes": "Accumulating quarterly. No rush to exit core ETF position.",
        },
        {
            "platform": "degiero", "ticker": "AAPL",
            "entry_price": 188.50, "quantity": 25, "entry_date": d(weeks=10),
            "thesis": "Services segment compounding; Vision Pro ecosystem building",
            "invalidation_price": 160.00, "invalidation_thesis": "Services growth below 10% YoY — core thesis broken",
            "targets": [
                {"price": 220.00, "label": "Target 1: +17%", "fraction": 0.33},
                {"price": 250.00, "label": "Target 2: +33%", "fraction": 0.33},
                {"price": 280.00, "label": "Target 3: +49%", "fraction": 0.34},
            ],
            "time_stop": (TODAY + timedelta(days=120)).isoformat(),
            "notes": "Watch WWDC (June) for AI catalyst.",
        },
        {
            "platform": "degiero", "ticker": "MSFT",
            "entry_price": 430.00, "quantity": 20, "entry_date": d(weeks=8),
            "thesis": "Azure AI monetization accelerating; Copilot enterprise adoption strong",
            "invalidation_price": 387.00, "invalidation_thesis": "Azure growth decelerates below 25% YoY",
            "targets": [
                {"price": 502.00, "label": "Target 1: +17%", "fraction": 0.50},
                {"price": 580.00, "label": "Target 2: +35%", "fraction": 0.50},
            ],
            "time_stop": (TODAY + timedelta(days=150)).isoformat(),
        },
        {
            "platform": "degiero", "ticker": "NVDA",
            "entry_price": 880.00, "quantity": 15, "entry_date": d(weeks=6),
            "thesis": "AI infrastructure demand insatiable; H100/H200 supply constrained",
            "invalidation_price": 748.00, "invalidation_thesis": "Data centre spend cuts; AMD MI300X competitive threat",
            "targets": [
                {"price": 1056.00, "label": "Target 1: +20%", "fraction": 0.50},
                {"price": 1320.00, "label": "Target 2: +50%", "fraction": 0.50},
            ],
            "time_stop": (TODAY + timedelta(days=180)).isoformat(),
        },
        # ── IBKR plans ─────────────────────────────────────────────────────
        {
            "platform": "ibkr", "ticker": "AAPL",
            "entry_price": 182.30, "quantity": 150, "entry_date": d(weeks=14),
            "thesis": "Long-term AI services compounding — high conviction position",
            "invalidation_price": 155.00, "invalidation_thesis": "Services growth below 12%; antitrust risk materialises",
            "targets": [
                {"price": 215.00, "label": "Target 1: +18%", "fraction": 0.33},
                {"price": 250.00, "label": "Target 2: +37%", "fraction": 0.33},
                {"price": 290.00, "label": "Target 3: +59%", "fraction": 0.34},
            ],
            "time_stop": (TODAY + timedelta(days=240)).isoformat(),
            "notes": "NOTE: Position is ~28% of ibkr portfolio — violates max-position rule (15%). Should trim to 65 shares.",
        },
        {
            "platform": "ibkr", "ticker": "MSFT",
            "entry_price": 408.00, "quantity": 40, "entry_date": d(weeks=7),
            "thesis": "Cloud + AI platform play; GitHub Copilot enterprise roll-out",
            "invalidation_price": 347.00, "invalidation_thesis": "Azure decelerates; Copilot adoption below targets",
            "targets": [
                {"price": 480.00, "label": "Target 1: +18%", "fraction": 0.50},
                {"price": 550.00, "label": "Target 2: +35%", "fraction": 0.50},
            ],
            "time_stop": (TODAY + timedelta(days=180)).isoformat(),
        },
        {
            "platform": "ibkr", "ticker": "TKA.DE",
            "entry_price": 8.62, "quantity": 1000, "entry_date": d(weeks=5),
            "thesis": "German industrial automation; order pipeline strong for H2",
            "invalidation_price": 7.33, "invalidation_thesis": "Order intake negative; Chinese competition侵蚀 margins",
            "targets": [
                {"price": 10.35, "label": "Target 1: +20%", "fraction": 0.50},
                {"price": 12.08, "label": "Target 2: +40%", "fraction": 0.50},
            ],
            "time_stop": (TODAY + timedelta(days=120)).isoformat(),
            "notes": "KONE partnership expected to close Q3.",
        },
        {
            "platform": "ibkr", "ticker": "VWCE.DE",
            "entry_price": 133.20, "quantity": 20, "entry_date": d(weeks=4),
            "thesis": "Core satnav ETF position alongside individual stock picks",
            "invalidation_price": 113.22, "invalidation_thesis": "Global equity drawdown > 15%",
            "targets": [
                {"price": 146.52, "label": "Target 1: +10%", "fraction": 0.50},
                {"price": 159.84, "label": "Target 2: +20%", "fraction": 0.50},
            ],
            "time_stop": (TODAY + timedelta(days=180)).isoformat(),
        },
        # ── Test plans ─────────────────────────────────────────────────────
        {
            "platform": "test", "ticker": "AAPL",
            "entry_price": 192.00, "quantity": 10, "entry_date": d(weeks=3),
            "thesis": "Testing signal accuracy — smaller position",
            "invalidation_price": 163.20, "invalidation_thesis": "Services growth below 10%",
            "targets": [
                {"price": 225.00, "label": "Target 1: +17%", "fraction": 0.50},
                {"price": 268.00, "label": "Target 2: +40%", "fraction": 0.50},
            ],
            "time_stop": (TODAY + timedelta(days=120)).isoformat(),
        },
        {
            "platform": "test", "ticker": "ETH",
            "entry_price": 2850.00, "quantity": 0.5, "entry_date": d(weeks=2),
            "thesis": "Crypto exposure test — ETH staking yield 3.8%",
            "invalidation_price": 2280.00, "invalidation_thesis": "Ethereum mainnet failure; regulatory crackdown",
            "targets": [
                {"price": 3420.00, "label": "Target 1: +20%", "fraction": 0.50},
                {"price": 4275.00, "label": "Target 2: +50%", "fraction": 0.50},
            ],
            "time_stop": (TODAY + timedelta(days=90)).isoformat(),
            "notes": "Risk-off behaviour expected. Small position.",
        },
        {
            "platform": "test", "ticker": "TSLA",
            "entry_price": 245.00, "quantity": 5, "entry_date": d(weeks=1),
            "thesis": "EV market share pressure; FSD licensing optionality",
            "invalidation_price": 208.25, "invalidation_thesis": "Margin compression below -5%; FSD delays",
            "targets": [
                {"price": 294.00, "label": "Target 1: +20%", "fraction": 0.50},
                {"price": 343.00, "label": "Target 2: +40%", "fraction": 0.50},
            ],
            "time_stop": (TODAY + timedelta(days=90)).isoformat(),
        },
    ]

    # Clear existing YAML plans (only in platform subdirs)
    for subdir in ["degiero", "ibkr", "test"]:
        subdir_path = POSITIONS_BASE / subdir
        if subdir_path.exists():
            for f in subdir_path.glob("*.yaml"):
                f.unlink()

    for plan in plans:
        platform = plan.pop("platform")
        dir_path = POSITIONS_BASE / platform
        dir_path.mkdir(parents=True, exist_ok=True)

        import yaml
        ticker = plan["ticker"]
        path = dir_path / f"{ticker}.yaml"

        with open(path, "w") as f:
            yaml.dump(plan, f, default_flow_style=False, sort_keys=False)

    print(f"  Wrote {len(plans)} exit plan YAML files")


def seed_post_mortems():
    """Create post-mortem markdown files for completed trades."""

    post_mortems = [
        {
            "ticker": "AAPL",
            "platform": "ibkr",
            "exit_date": d(weeks=22),
            "entry_price": 175.00,
            "exit_price": 198.50,
            "thesis": "Long-term AI services compounding — initial position entry",
            "thesis_played_out": True,
            "ai_signal_correct": True,
            "exit_trigger": "target",
            "lesson": "First target hit at +13.4%. Thesis unchanged — allowed to run to second target. Correct patience. AI signal (buy, 0.75) proved accurate. Exited 1/3 at first target, rode remainder.",
        },
        {
            "ticker": "MSFT",
            "platform": "ibkr",
            "exit_date": d(weeks=12),
            "entry_price": 392.00,
            "exit_price": 451.00,
            "thesis": "Cloud + AI platform. GitHub Copilot enterprise rollout",
            "thesis_played_out": True,
            "ai_signal_correct": True,
            "exit_trigger": "target",
            "lesson": "Azure AI services revenue +30% QoQ confirmed. Copilot adoption strong. Exited full position at +15%. AI signal (buy, 0.70) fully justified. No regrets on exit timing.",
        },
        {
            "ticker": "AAPL",
            "platform": "ibkr",
            "exit_date": d(weeks=18),
            "entry_price": 178.50,
            "exit_price": 172.00,
            "thesis": "Overweight — position size increased",
            "thesis_played_out": False,
            "ai_signal_correct": False,
            "exit_trigger": "manual",
            "lesson": "Thesis partially played out but position thesis (overweight) correct. Sold 30 shares at breakeven to reduce exposure. AI signal (overweight, 0.80) was too aggressive for position size. Rule: never increase conviction AND size simultaneously.",
        },
        {
            "ticker": "TKA.DE",
            "platform": "test",
            "exit_date": d(weeks=16),
            "entry_price": 9.80,
            "exit_price": 7.20,
            "thesis": "Position too small for delisted tracking. Closed out.",
            "thesis_played_out": False,
            "ai_signal_correct": False,
            "exit_trigger": "stop",
            "lesson": "Stop loss correctly triggered at -26.5%. Thesis (delisted tracking) was wrong. Exit at stop was correct — saved remaining capital. AI signal (sell, 0.55) was low-confidence and correct.",
        },
    ]

    POST_MORTEMS_DIR.mkdir(parents=True, exist_ok=True)

    for pm in post_mortems:
        import yaml
        exit_date = pm.pop("exit_date")
        entry_price = pm.pop("entry_price")
        exit_price = pm.pop("exit_price")
        thesis = pm.pop("thesis")
        thesis = sanitize_for_db(thesis) or ""
        thesis_played_out = pm.pop("thesis_played_out")
        ai_signal_correct = pm.pop("ai_signal_correct")
        exit_trigger = pm.pop("exit_trigger")
        lesson = pm.pop("lesson")
        lesson = sanitize_for_db(lesson) or ""
        platform = pm.pop("platform", "unknown")

        ret = ((exit_price - entry_price) / entry_price) * 100

        content = f"""# Post-Mortem: {pm['ticker']}

**Exit Date:** {exit_date}
**Entry Price:** €{entry_price:.2f}
**Exit Price:** €{exit_price:.2f}
**Return:** {ret:+.1f}%

## Thesis
{thesis}

## Outcome
- Thesis played out: {"✅ Yes" if thesis_played_out else "❌ No"}
- AI signal correct: {"✅ Yes" if ai_signal_correct else "❌ No"}
- Exit trigger: {exit_trigger}

## Lesson
{lesson}

---
*Post-mortem for {pm['ticker']} position ({platform})*
"""

        filename = f"{exit_date.replace('-','')}-{pm['ticker']}.md"
        path = POST_MORTEMS_DIR / filename
        with open(path, "w") as f:
            f.write(content)

    print(f"  Wrote {len(post_mortems)} post-mortems")


def main():
    parser = argparse.ArgumentParser(description="Seed TradingAgents database with simulation data")
    parser.add_argument("--positions", action="store_true", help="Seed positions only")
    parser.add_argument("--signals", action="store_true", help="Seed signals only")
    parser.add_argument("--watchlist", action="store_true", help="Seed watchlist only")
    parser.add_argument("--analyses", action="store_true", help="Seed analyses only")
    parser.add_argument("--exit-plans", action="store_true", help="Seed exit plans only")
    parser.add_argument("--post-mortems", action="store_true", help="Seed post-mortems only")
    args = parser.parse_args()

    # Default: seed everything
    seed_all = not any([args.positions, args.signals, args.watchlist,
                        args.analyses, args.exit_plans, args.post_mortems])

    print("Seeding TradingAgents database...")

    if seed_all or args.positions:
        seed_positions()
    if seed_all or args.signals:
        seed_signals()
    if seed_all or args.watchlist:
        seed_watchlist()
    if seed_all or args.analyses:
        seed_analyses()
    if seed_all or args.exit_plans:
        seed_exit_plans()
    if seed_all or args.post_mortems:
        seed_post_mortems()

    print("Done.")


if __name__ == "__main__":
    main()