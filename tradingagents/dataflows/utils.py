from datetime import date, datetime, timedelta
from typing import Annotated

import pandas as pd

SavePathType = Annotated[str, "File path to save data. If None, data is not saved."]

def save_output(data: pd.DataFrame, tag: str, save_path: SavePathType = None) -> None:
    if save_path:
        data.to_csv(save_path)
        print(f"{tag} saved to {save_path}")


def get_current_date() -> str:
    return date.today().strftime("%Y-%m-%d")


def decorate_all_methods(decorator: Callable[..., Any]) -> Callable[[type], type]:
    def class_decorator(cls: type) -> type:
        for attr_name, attr_value in cls.__dict__.items():
            if callable(attr_value):
                setattr(cls, attr_name, decorator(attr_value))
        return cls

    return class_decorator


def get_next_weekday(date_input: str | datetime) -> datetime:

    if not isinstance(date_input, datetime):
        date_input = datetime.strptime(date_input, "%Y-%m-%d")

    if date_input.weekday() >= 5:
        days_to_add = 7 - date_input.weekday()
        next_weekday = date_input + timedelta(days=days_to_add)
        return next_weekday
    else:
        return date_input
