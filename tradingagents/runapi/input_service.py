"""Single noninteractive boundary for portfolio discovery, validation, and freezing."""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from tradingagents.portfolio import PortfolioContext

from .context import FrozenSnapshot, InputMode, RunContext, new_run_id, snapshot_fingerprint
from .result import InputError


@dataclass(frozen=True)
class LoadedPortfolio:
    """Validated content read once; callers freeze it after choosing an analysis date."""
    context: PortfolioContext
    basename: str


class DirectoryReadError(OSError):
    pass


class PortfolioInputService:
    def __init__(self, portfolio_dir: str | Path | None = None):
        self.portfolio_dir = Path(portfolio_dir or os.getenv(
            "PORTFOLIO_DIR", Path(__file__).resolve().parents[2] / "portfolios"))

    def discover(self) -> list[Path]:
        """List regular, direct-child JSON files in deterministic filename order."""
        try:
            with os.scandir(self.portfolio_dir) as entries:
                files = [Path(entry.path) for entry in entries
                         if entry.name.lower().endswith(".json")
                         and not entry.is_symlink() and entry.is_file(follow_symlinks=False)]
        except FileNotFoundError:
            return []
        except OSError as exc:
            raise DirectoryReadError("Could not read the portfolio directory.") from exc
        return sorted(files, key=lambda path: (path.name.casefold(), path.name))

    @staticmethod
    def read_file(path: str | Path) -> LoadedPortfolio:
        path = Path(path)
        basename = path.name or None
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise InputError("UNREADABLE_PATH", "Could not read the selected portfolio file.", basename) from exc
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InputError("MALFORMED_JSON", "The selected file is not valid UTF-8 JSON.", basename) from exc
        if not isinstance(value, dict):
            raise InputError("WRONG_SCALAR_TYPE", "The top-level JSON value must be an object.", basename)
        if "positions" not in value or not isinstance(value["positions"], list):
            raise InputError("MISSING_POSITIONS", "A positions list is required.", basename, "positions")
        for index, row in enumerate(value["positions"]):
            prefix = f"positions[{index}]"
            if not isinstance(row, dict):
                raise InputError("WRONG_SCALAR_TYPE", "Each position must be an object.", basename, prefix)
            if "quantity" not in row:
                raise InputError("MISSING_QUANTITY", "A quantity is required.", basename, f"{prefix}.quantity")
            if not isinstance(row.get("ticker"), str) or not row["ticker"].strip():
                raise InputError("WRONG_SCALAR_TYPE", "Ticker must be a non-empty string.", basename, f"{prefix}.ticker")
            for key in ("quantity", "average_price"):
                if key == "average_price" and (key not in row or row[key] is None):
                    continue
                number = row[key]
                if isinstance(number, bool) or not isinstance(number, (int, float)):
                    raise InputError("WRONG_SCALAR_TYPE", "Value must be a JSON number or null.", basename, f"{prefix}.{key}")
                if not math.isfinite(float(number)):
                    raise InputError("NONFINITE_NUMBER", "Value must be finite.", basename, f"{prefix}.{key}")
        for key in ("cash",):
            if key in value and value[key] is not None:
                number = value[key]
                if isinstance(number, bool) or not isinstance(number, (int, float)):
                    raise InputError("WRONG_SCALAR_TYPE", "Value must be a JSON number or null.", basename, key)
                if not math.isfinite(float(number)):
                    raise InputError("NONFINITE_NUMBER", "Value must be finite.", basename, key)
        if "currency" in value and value["currency"] is not None and not isinstance(value["currency"], str):
            raise InputError("WRONG_SCALAR_TYPE", "Currency must be a string or null.", basename, "currency")
        normalized = {
            "cash": value.get("cash"), "currency": value.get("currency"),
            "positions": [{"ticker": row["ticker"], "quantity": row["quantity"],
                           "average_price": row.get("average_price")}
                          for row in value["positions"]],
        }
        try:
            context = PortfolioContext.model_validate(normalized)
        except ValidationError as exc:
            issue = exc.errors()[0]
            location = ".".join(str(part) for part in issue.get("loc", ())) or None
            if issue.get("type") == "finite_number":
                kind = "NONFINITE_NUMBER"
            elif "quantity" in str(issue.get("loc", ())):
                kind = "MISSING_QUANTITY" if issue.get("type") == "missing" else "WRONG_SCALAR_TYPE"
            else:
                kind = "WRONG_SCALAR_TYPE"
            raise InputError(kind, "Portfolio fields do not match the required schema.", basename, location) from exc
        return LoadedPortfolio(context, basename or "portfolio.json")

    def freeze_loaded(self, ticker: str, analysis_date: str, loaded: LoadedPortfolio,
                      portfolio_as_of: str) -> RunContext:
        if portfolio_as_of != analysis_date:
            raise InputError("AS_OF_MISMATCH", "Portfolio as-of date must match the analysis date.", loaded.basename,
                             "portfolio_as_of")
        digest, rows = snapshot_fingerprint(loaded.context)
        snapshot = FrozenSnapshot(
            basename=loaded.basename, cash=loaded.context.cash, currency=loaded.context.currency,
            positions=rows, fingerprint_sha256=digest, portfolio_as_of=portfolio_as_of,
        )
        return RunContext(new_run_id(), ticker.strip(), analysis_date, InputMode.PORTFOLIO_PROVIDED,
                          snapshot, True, True)

    def freeze_path(self, ticker: str, analysis_date: str, path: str | Path,
                    portfolio_as_of: str) -> RunContext:
        return self.freeze_loaded(ticker, analysis_date, self.read_file(path), portfolio_as_of)


def freeze_no_portfolio(ticker: str, analysis_date: str) -> RunContext:
    return RunContext(new_run_id(), ticker.strip(), analysis_date, InputMode.NO_PORTFOLIO,
                      None, False, False)


def freeze_explicit(ticker: str, analysis_date: str,
                    portfolio: PortfolioContext | None = None) -> RunContext:
    """Prompt-free API helper. Always returns FROZEN; callers must call confirm()."""
    if portfolio is None:
        return freeze_no_portfolio(ticker, analysis_date)
    digest, rows = snapshot_fingerprint(portfolio)
    snapshot = FrozenSnapshot("<in-memory>", portfolio.cash, portfolio.currency, rows,
                              digest, analysis_date)
    return RunContext(new_run_id(), ticker.strip(), analysis_date, InputMode.PORTFOLIO_PROVIDED,
                      snapshot, True, True)
