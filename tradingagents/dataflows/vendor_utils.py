import csv
import json
from io import StringIO
from typing import Iterable


def rows_to_csv(rows: Iterable[dict], columns: list[str]) -> str:
    """Serialize provider rows to the CSV shape expected by stock-data tools."""
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in columns})
    return output.getvalue()


def format_json_section(title: str, payload) -> str:
    return f"## {title}\n\n```json\n{json.dumps(payload, indent=2, sort_keys=True)}\n```"
