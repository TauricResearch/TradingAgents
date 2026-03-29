import os
import json
import pandas as pd
import calendar
from datetime import date, timedelta, datetime
from typing import Annotated

SavePathType = Annotated[str, "File path to save data. If None, data is not saved."]

def save_output(data: pd.DataFrame, tag: str, save_path: SavePathType = None) -> None:
    if save_path:
        data.to_csv(save_path)
        print(f"{tag} saved to {save_path}")


def get_current_date():
    return date.today().strftime("%Y-%m-%d")


def normalize_iso_date(date_str: str) -> str:
    """Normalize YYYY-MM-DD dates, clamping invalid month-end days.

    LLM tool calls occasionally produce dates like 2026-02-29 when they mean
    "the end of February". For valid ISO dates this returns the input as-is.
    For invalid day-of-month values within a valid year/month, it clamps to the
    last valid day of that month. Other malformed values still raise ValueError.
    """
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError as exc:
        try:
            year_str, month_str, day_str = date_str.split("-")
            year = int(year_str)
            month = int(month_str)
            day = int(day_str)
        except (AttributeError, ValueError) as parse_exc:
            raise ValueError(f"Unsupported date format: {date_str}") from parse_exc

        if not 1 <= month <= 12:
            raise exc
        if day < 1:
            raise exc

        last_day = calendar.monthrange(year, month)[1]
        if day > last_day:
            return f"{year:04d}-{month:02d}-{last_day:02d}"

        raise exc


def normalize_date_range(start_date: str, end_date: str) -> tuple[str, str]:
    """Normalize and order an ISO date range."""
    normalized_start = normalize_iso_date(start_date)
    normalized_end = normalize_iso_date(end_date)

    start_dt = datetime.strptime(normalized_start, "%Y-%m-%d")
    end_dt = datetime.strptime(normalized_end, "%Y-%m-%d")

    if start_dt <= end_dt:
        return normalized_start, normalized_end
    return normalized_end, normalized_start


def decorate_all_methods(decorator):
    def class_decorator(cls):
        for attr_name, attr_value in cls.__dict__.items():
            if callable(attr_value):
                setattr(cls, attr_name, decorator(attr_value))
        return cls

    return class_decorator


def get_next_weekday(date):

    if not isinstance(date, datetime):
        date = datetime.strptime(date, "%Y-%m-%d")

    if date.weekday() >= 5:
        days_to_add = 7 - date.weekday()
        next_weekday = date + timedelta(days=days_to_add)
        return next_weekday
    else:
        return date
