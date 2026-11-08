"""Usage endpoints, sharing the console's local-only middleware."""
import csv
import io
from datetime import UTC, date, datetime, time, timedelta

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from tradingagents.usage import UsageStore

router = APIRouter()


class PricePayload(BaseModel):
    provider: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=250)
    input_rate: float = Field(ge=0, allow_inf_nan=False)
    output_rate: float = Field(ge=0, allow_inf_nan=False)
    cache_rate: float | None = Field(default=None, ge=0, allow_inf_nan=False)


def filtered(start: date | None = None, end: date | None = None,
             ticker: str | None = None, model: str | None = None, run_id: str | None = None):
    if start and end and start > end:
        raise HTTPException(422, "La data iniziale deve precedere quella finale")
    def stamp(day):
        return datetime.combine(day, time.min, tzinfo=UTC).timestamp()
    try:
        end_stamp = stamp(end + timedelta(days=1)) if end else None
    except OverflowError:
        raise HTTPException(422, "Data finale fuori intervallo") from None
    return UsageStore().report(stamp(start) if start else None, end_stamp,
                               ticker.strip().upper() if ticker else None,
                               model.strip() if model else None, run_id)


@router.get("/api/usage")
def usage(start: date | None = None, end: date | None = None,
          ticker: str | None = None, model: str | None = None, run_id: str | None = None):
    report = filtered(start, end, ticker, model, run_id)
    report["calls"] = report["calls"][:500]
    return report


@router.get("/api/usage.csv")
def usage_csv(start: date | None = None, end: date | None = None,
              ticker: str | None = None, model: str | None = None, run_id: str | None = None):
    report = filtered(start, end, ticker, model, run_id)
    output = io.StringIO(newline="")
    columns = ["id", "run_id", "ticker", "analysis_date", "source", "provider", "model", "agent",
               "started_at", "duration", "status", "tokens_in", "tokens_out", "cached_tokens", "cost_usd"]
    writer = csv.writer(output)
    writer.writerow(columns)
    for call in report["calls"]:
        # Prevent formula execution when a model ID is opened in a spreadsheet.
        writer.writerow(["'" + v if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@")) else v
                         for v in (call[key] for key in columns)])
    return Response(output.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="tradingagents-consumi.csv"'})


@router.get("/api/usage/prices")
def prices():
    return {"prices": UsageStore().prices(), "currency": "USD", "unit": "per million tokens"}


@router.put("/api/usage/prices")
def set_price(payload: PricePayload):
    provider, model = payload.provider.strip().lower(), payload.model.strip()
    if not provider or not model:
        raise HTTPException(422, "Provider e modello sono obbligatori")
    UsageStore().set_price(provider, model, payload.input_rate, payload.output_rate, payload.cache_rate)
    return {"saved": True}
