from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf
from langchain_core.messages import HumanMessage

from .charts import render_technical_chart

logger = logging.getLogger(__name__)


def build_visual_message(ticker: str, image_path: str | Path) -> HumanMessage:
    encoded = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
    return HumanMessage(
        content=[
            {
                "type": "text",
                "text": (
                    f"Analyze the {ticker} chart. Identify trend, support and resistance, "
                    "and visible patterns. Keep the report concise and evidence-based."
                ),
            },
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}},
        ]
    )


class VisualChartAnalyst:
    def __init__(self, llm: Any, cache_dir: str | Path, lookback_days: int = 120):
        self.llm = llm
        self.cache_dir = Path(cache_dir)
        self.lookback_days = lookback_days

    def analyze(self, ticker: str, trade_date: str) -> str:
        try:
            start = (pd.Timestamp(trade_date) - pd.Timedelta(days=self.lookback_days)).strftime("%Y-%m-%d")
            data = yf.download(ticker, start=start, end=trade_date, auto_adjust=True, progress=False)
            if data.empty:
                return ""
            image_path = render_technical_chart(data, ticker, self.cache_dir / f"{ticker}-{trade_date}.png")
            return self.llm.invoke([build_visual_message(ticker, image_path)]).content
        except Exception as exc:
            logger.warning("Visual analysis skipped for %s: %s", ticker, exc)
            return ""
