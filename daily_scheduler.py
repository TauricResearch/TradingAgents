"""Daily stock analysis scheduler.

Loads stocks from stocks_watchlist.json, runs TradingAgentsGraph for each ticker,
generates a PDF report, and uploads it via email or S3.

Schedule: every day at 06:00 local time.

Required env vars (add to .env):
  # LLM
  OPENAI_API_KEY=...          (or provider-specific key)

  # Upload — choose one mode
  UPLOAD_MODE=email           # email | s3 | none  (default: email)

  # Email (UPLOAD_MODE=email)
  SMTP_HOST=smtp.gmail.com
  SMTP_PORT=587
  EMAIL_SENDER=you@gmail.com
  EMAIL_PASSWORD=app-password
  EMAIL_RECIPIENTS=a@example.com,b@example.com

  # S3 (UPLOAD_MODE=s3)
  S3_BUCKET=my-bucket
  S3_PREFIX=trading-reports   (default: trading-reports)
  AWS_ACCESS_KEY_ID=...
  AWS_SECRET_ACCESS_KEY=...
  AWS_DEFAULT_REGION=us-east-1

  # Optional overrides
  DEEP_THINK_LLM=gpt-5.4-mini
  QUICK_THINK_LLM=gpt-5.4-mini
  MAX_DEBATE_ROUNDS=1
  RUN_AT=06:00               (default: 06:00)
"""

import json
import logging
import os
import smtplib
import ssl
import time
from datetime import date, datetime
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import schedule
from dotenv import load_dotenv
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("scheduler.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WATCHLIST_FILE = Path(__file__).parent / "stocks_watchlist.json"

_SIGNAL_COLOR = {
    "Buy": "#1e8449",
    "Overweight": "#2ecc71",
    "Hold": "#d4ac0d",
    "Underweight": "#e67e22",
    "Sell": "#c0392b",
}


def _load_watchlist() -> list[str]:
    with open(WATCHLIST_FILE, encoding="utf-8") as f:
        data = json.load(f)
    stocks = data.get("stocks", [])
    if not stocks:
        raise ValueError(f"No stocks found in {WATCHLIST_FILE}")
    return stocks


def _build_config() -> dict:
    config = DEFAULT_CONFIG.copy()
    config["deep_think_llm"] = os.getenv("DEEP_THINK_LLM", "gpt-5.4-mini")
    config["quick_think_llm"] = os.getenv("QUICK_THINK_LLM", "gpt-5.4-mini")
    config["max_debate_rounds"] = int(os.getenv("MAX_DEBATE_ROUNDS", "1"))
    config["checkpoint_enabled"] = True
    return config


# ---------------------------------------------------------------------------
# PDF generation
# ---------------------------------------------------------------------------

_REPORT_SECTIONS = [
    ("Market Analysis", "market_report"),
    ("Sentiment Analysis", "sentiment_report"),
    ("News Analysis", "news_report"),
    ("Fundamentals Analysis", "fundamentals_report"),
    ("Investment Plan", "investment_plan"),
    ("Trader Decision", "trader_investment_plan"),
    ("Final Trade Decision", "final_trade_decision"),
]


def generate_pdf(
    ticker: str,
    trade_date: str,
    final_state: dict,
    signal: str,
    results_dir: str | Path,
) -> Path:
    """Build a PDF from final_state and save it under results_dir."""
    out_dir = Path(results_dir) / ticker / trade_date / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / f"{ticker}_{trade_date}_report.pdf"

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    base = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle", parent=base["Heading1"], fontSize=18, spaceAfter=6
    )
    meta_style = ParagraphStyle(
        "ReportMeta", parent=base["Normal"], fontSize=11, spaceAfter=8
    )
    heading_style = ParagraphStyle(
        "SectionHeading", parent=base["Heading2"], fontSize=13, spaceAfter=4
    )
    body_style = ParagraphStyle(
        "SectionBody", parent=base["Normal"], fontSize=9, leading=14, spaceAfter=6
    )

    sig_hex = _SIGNAL_COLOR.get(signal, "#1a5276")
    signal_style = ParagraphStyle(
        "SignalBadge",
        parent=base["Normal"],
        fontSize=13,
        textColor=colors.HexColor(sig_hex),
        spaceAfter=8,
    )

    story = []
    story.append(Paragraph(f"TradingAgents Analysis — {ticker}", title_style))
    story.append(
        Paragraph(
            f"Date: {trade_date} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"Signal: <b>{signal}</b>",
            signal_style,
        )
    )
    story.append(HRFlowable(width="100%", thickness=1, color=colors.grey))
    story.append(Spacer(1, 4 * mm))

    for section_title, state_key in _REPORT_SECTIONS:
        content: str = final_state.get(state_key) or ""
        if not content.strip():
            continue
        story.append(Paragraph(section_title, heading_style))
        safe = (
            content.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br/>")
        )
        story.append(Paragraph(safe, body_style))
        story.append(
            HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey)
        )
        story.append(Spacer(1, 3 * mm))

    doc.build(story)
    logger.info("PDF saved: %s", pdf_path)
    return pdf_path


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


def upload_report(pdf_path: Path, ticker: str, signal: str) -> None:
    mode = os.getenv("UPLOAD_MODE", "email").lower()
    if mode == "email":
        _send_email(pdf_path, ticker, signal)
    elif mode == "s3":
        _upload_s3(pdf_path, ticker)
    else:
        logger.info("Upload skipped (UPLOAD_MODE=none). Report at: %s", pdf_path)


def _send_email(pdf_path: Path, ticker: str, signal: str) -> None:
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    sender = os.getenv("EMAIL_SENDER", "")
    password = os.getenv("EMAIL_PASSWORD", "")
    raw_recipients = os.getenv("EMAIL_RECIPIENTS", "")
    recipients = [r.strip() for r in raw_recipients.split(",") if r.strip()]

    if not (sender and password and recipients):
        logger.warning(
            "Email not configured. Set EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENTS."
        )
        return

    today = date.today().isoformat()
    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = f"[TradingAgents] {ticker} — {signal} ({today})"
    msg.attach(
        MIMEText(
            f"Trading analysis for {ticker} on {today}.\n"
            f"Signal: {signal}\n\n"
            "See the attached PDF for the full report.",
            "plain",
        )
    )

    with open(pdf_path, "rb") as fh:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(fh.read())
    encoders.encode_base64(part)
    part.add_header(
        "Content-Disposition", f'attachment; filename="{pdf_path.name}"'
    )
    msg.attach(part)

    ctx = ssl.create_default_context()
    with smtplib.SMTP(smtp_host, smtp_port) as srv:
        srv.starttls(context=ctx)
        srv.login(sender, password)
        srv.sendmail(sender, recipients, msg.as_string())

    logger.info("Email sent for %s → %s", ticker, recipients)


def _upload_s3(pdf_path: Path, ticker: str) -> None:
    try:
        import boto3  # type: ignore
    except ImportError:
        logger.error("boto3 not installed. Run: pip install boto3")
        return

    bucket = os.getenv("S3_BUCKET", "")
    if not bucket:
        logger.warning("S3_BUCKET not set.")
        return

    prefix = os.getenv("S3_PREFIX", "trading-reports")
    key = f"{prefix}/{ticker}/{pdf_path.name}"
    boto3.client("s3").upload_file(str(pdf_path), bucket, key)
    logger.info("Uploaded to s3://%s/%s", bucket, key)


# ---------------------------------------------------------------------------
# Core daily job
# ---------------------------------------------------------------------------


def run_daily_analysis() -> None:
    trade_date = datetime.now().strftime("%Y-%m-%d")
    logger.info("=== Daily analysis started: %s ===", trade_date)

    try:
        stocks = _load_watchlist()
    except Exception as exc:
        logger.error("Failed to load watchlist: %s", exc)
        return

    config = _build_config()
    results_dir = config.get("results_dir", Path.home() / ".tradingagents" / "logs")

    # One graph instance re-used for all tickers (avoids re-compiling LangGraph).
    ta = TradingAgentsGraph(debug=False, config=config)

    summary: list[tuple[str, str]] = []

    for ticker in stocks:
        logger.info("Analysing %s …", ticker)
        try:
            final_state, signal = ta.propagate(ticker, trade_date)
            pdf_path = generate_pdf(ticker, trade_date, final_state, signal, results_dir)
            upload_report(pdf_path, ticker, signal)
            summary.append((ticker, signal))
            logger.info("%s → %s", ticker, signal)
        except Exception as exc:
            logger.error("%s failed: %s", ticker, exc, exc_info=True)
            summary.append((ticker, f"ERROR: {exc}"))

    logger.info("=== Daily summary ===")
    for ticker, result in summary:
        logger.info("  %-8s %s", ticker, result)
    logger.info("=====================")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    run_at = os.getenv("RUN_AT", "06:00")
    logger.info("Scheduler started. Daily run at %s.", run_at)
    schedule.every().day.at(run_at).do(run_daily_analysis)

    # Run immediately on first launch if explicitly requested.
    if os.getenv("RUN_NOW", "").lower() in ("1", "true", "yes"):
        logger.info("RUN_NOW=true — running analysis immediately.")
        run_daily_analysis()

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
