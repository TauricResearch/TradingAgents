"""One credential-key registry shared by persistence, hashing, logs, and HTTP."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from typing import Any

from tradingagents.llm_clients.api_key_env import PROVIDER_API_KEY_ENV

REDACTED_VALUE = "[REDACTED]"
DATAFRAME_TAG = "$tradingagents:dataframe"
DATAFRAME_SERIALIZER_VERSION = 1
EXACT_CREDENTIAL_LEAVES = frozenset(
    {
        "authorization",
        "proxy_authorization",
        "cookie",
        "set_cookie",
        "password",
        "passwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "id_token",
        "bearer_token",
        "client_secret",
        "private_key",
        "aws_secret_access_key",
    }
)
SECRET_SUFFIXES = ("_api_key", "_token", "_secret", "_password", "_private_key")


def normalize_key_segment(segment: str) -> str:
    return re.sub(r"[-\s]+", "_", segment.strip().lower())


def split_normalized_key(raw_key: str) -> tuple[str, ...]:
    return tuple(normalize_key_segment(segment) for segment in raw_key.split("."))


def provider_credential_leaves() -> frozenset[str]:
    return frozenset(normalize_key_segment(name) for name in PROVIDER_API_KEY_ENV.values() if name)


def is_secret_leaf(
    leaf: str,
    additional_credential_names: tuple[str, ...] | frozenset[str] = (),
) -> bool:
    normalized = normalize_key_segment(leaf)
    exact = (
        EXACT_CREDENTIAL_LEAVES
        | provider_credential_leaves()
        | frozenset(normalize_key_segment(name) for name in additional_credential_names)
    )
    return normalized in exact or normalized.endswith(SECRET_SUFFIXES)


@dataclass(frozen=True)
class RedactionRecord:
    path: str
    normalized_leaf: str


@dataclass(frozen=True)
class RedactionResult:
    value: Any
    manifest: tuple[RedactionRecord, ...] = ()

    @property
    def redacted(self) -> bool:
        return bool(self.manifest)


def _is_pandas_dataframe(value: Any) -> bool:
    """Recognize pandas DataFrame instances without importing pandas eagerly."""
    return any(
        (base.__module__ == "pandas" or base.__module__.startswith("pandas."))
        and base.__name__ == "DataFrame"
        for base in type(value).__mro__
    )


def _dataframe_payload(value: Any) -> dict[str, Any]:
    """Project a DataFrame into the versioned observation-table contract."""
    return {
        "version": DATAFRAME_SERIALIZER_VERSION,
        "columns": list(value.columns),
        "column_names": list(value.columns.names),
        "index": list(value.index),
        "index_names": list(value.index.names),
        "data": [list(row) for row in value.itertuples(index=False, name=None)],
        "attrs": dict(value.attrs),
    }


def _is_dataframe_envelope(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == {DATAFRAME_TAG}
        and isinstance(value[DATAFRAME_TAG], Mapping)
        and value[DATAFRAME_TAG].get("version") == DATAFRAME_SERIALIZER_VERSION
    )


def _dataframe_column_path(
    path: tuple[str, ...],
    column: Any,
    position: int,
    additional_credential_names: tuple[str, ...] | frozenset[str] = (),
) -> tuple[tuple[str, ...], str | None]:
    if isinstance(column, str):
        segments = split_normalized_key(column)
        column_path = (*path, "dataframe", *segments)
    elif isinstance(column, tuple):
        string_segments = tuple(
            segment
            for level in column
            if isinstance(level, str)
            for segment in split_normalized_key(level)
        )
        column_path = (
            (*path, "dataframe", *string_segments)
            if len(string_segments) == len(column)
            else (*path, "dataframe", f"column_{position}", *string_segments)
        )
        segments = string_segments
    else:
        return (*path, "dataframe", f"column_{position}"), None

    secret_leaf = next(
        (
            segment
            for segment in reversed(segments)
            if is_secret_leaf(segment, additional_credential_names)
        ),
        None,
    )
    return column_path, secret_leaf


def _declared_mapping(value: Any) -> Any:
    try:
        from langchain_core.messages import BaseMessage, message_to_dict

        if isinstance(value, BaseMessage):
            return message_to_dict(value)
    except ImportError:
        pass
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: getattr(value, item.name) for item in fields(value)}
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="python")
    return value


def redact_recursive(
    value: Any,
    *,
    additional_credential_names: tuple[str, ...] | frozenset[str] = (),
) -> RedactionResult:
    """Redact credential-valued mapping leaves and return a normalized manifest."""
    records: list[RedactionRecord] = []

    def visit_dataframe(payload: Mapping[str, Any], path: tuple[str, ...]) -> Any:
        columns = list(payload.get("columns", ()))
        data = list(payload.get("data", ()))
        transformed_rows = []
        for row_index, row in enumerate(data):
            row_values = list(row)
            transformed_row = []
            for column_index, child in enumerate(row_values):
                column = columns[column_index] if column_index < len(columns) else column_index
                child_path, leaf = _dataframe_column_path(
                    path, column, column_index, additional_credential_names
                )
                if leaf is not None:
                    records.append(RedactionRecord(".".join(child_path), leaf))
                    transformed_row.append(REDACTED_VALUE)
                else:
                    transformed_row.append(visit(child, (*child_path, str(row_index))))
            transformed_rows.append(transformed_row)

        return {
            "version": payload.get("version"),
            "columns": visit(columns, (*path, "dataframe", "columns")),
            "column_names": visit(
                list(payload.get("column_names", ())),
                (*path, "dataframe", "column_names"),
            ),
            "index": visit(list(payload.get("index", ())), (*path, "dataframe", "index")),
            "index_names": visit(
                list(payload.get("index_names", ())),
                (*path, "dataframe", "index_names"),
            ),
            "data": transformed_rows,
            "attrs": visit(dict(payload.get("attrs", {})), (*path, "dataframe", "attrs")),
        }

    def visit(current: Any, path: tuple[str, ...]) -> Any:
        if _is_pandas_dataframe(current):
            current = {DATAFRAME_TAG: _dataframe_payload(current)}
        current = _declared_mapping(current)
        if _is_dataframe_envelope(current):
            return {DATAFRAME_TAG: visit_dataframe(current[DATAFRAME_TAG], path)}
        if isinstance(current, Mapping):
            output = {}
            for raw_key, child in current.items():
                if isinstance(raw_key, str):
                    normalized_segments = split_normalized_key(raw_key)
                    child_path = (*path, *normalized_segments)
                    leaf = normalized_segments[-1]
                    if is_secret_leaf(leaf, additional_credential_names):
                        records.append(RedactionRecord(".".join(child_path), leaf))
                        output[raw_key] = REDACTED_VALUE
                        continue
                else:
                    child_path = (*path, str(raw_key))
                output[raw_key] = visit(child, child_path)
            return output
        if isinstance(current, list):
            return [visit(child, (*path, str(index))) for index, child in enumerate(current)]
        if isinstance(current, tuple):
            return tuple(visit(child, (*path, str(index))) for index, child in enumerate(current))
        if isinstance(current, set):
            return {visit(child, path) for child in current}
        if isinstance(current, frozenset):
            return frozenset(visit(child, path) for child in current)
        return current

    redacted = visit(value, ())
    manifest = tuple(
        sorted(
            set(records),
            key=lambda record: (record.path, record.normalized_leaf),
        )
    )
    return RedactionResult(redacted, manifest)


def remove_credentials_recursive(
    value: Any,
    *,
    additional_credential_names: tuple[str, ...] | frozenset[str] = (),
) -> RedactionResult:
    """Remove credential-named mapping leaves for resume fingerprinting."""
    records: list[RedactionRecord] = []

    def visit_dataframe(payload: Mapping[str, Any], path: tuple[str, ...]) -> Any:
        columns = list(payload.get("columns", ()))
        kept_positions = []
        for position, column in enumerate(columns):
            column_path, leaf = _dataframe_column_path(
                path, column, position, additional_credential_names
            )
            if leaf is not None:
                records.append(RedactionRecord(".".join(column_path), leaf))
            else:
                kept_positions.append(position)

        transformed_rows = []
        for row_index, row in enumerate(payload.get("data", ())):
            row_values = list(row)
            transformed_row = []
            for position in kept_positions:
                if position >= len(row_values):
                    continue
                column_path, _leaf = _dataframe_column_path(path, columns[position], position)
                transformed_row.append(visit(row_values[position], (*column_path, str(row_index))))
            transformed_rows.append(transformed_row)

        return {
            "version": payload.get("version"),
            "columns": visit(
                [columns[position] for position in kept_positions],
                (*path, "dataframe", "columns"),
            ),
            "column_names": visit(
                list(payload.get("column_names", ())),
                (*path, "dataframe", "column_names"),
            ),
            "index": visit(list(payload.get("index", ())), (*path, "dataframe", "index")),
            "index_names": visit(
                list(payload.get("index_names", ())),
                (*path, "dataframe", "index_names"),
            ),
            "data": transformed_rows,
            "attrs": visit(dict(payload.get("attrs", {})), (*path, "dataframe", "attrs")),
        }

    def visit(current: Any, path: tuple[str, ...]) -> Any:
        if _is_pandas_dataframe(current):
            current = {DATAFRAME_TAG: _dataframe_payload(current)}
        current = _declared_mapping(current)
        if _is_dataframe_envelope(current):
            return {DATAFRAME_TAG: visit_dataframe(current[DATAFRAME_TAG], path)}
        if isinstance(current, Mapping):
            output = {}
            for raw_key, child in current.items():
                if isinstance(raw_key, str):
                    normalized_segments = split_normalized_key(raw_key)
                    child_path = (*path, *normalized_segments)
                    leaf = normalized_segments[-1]
                    if is_secret_leaf(leaf, additional_credential_names):
                        records.append(RedactionRecord(".".join(child_path), leaf))
                        continue
                else:
                    child_path = (*path, str(raw_key))
                output[raw_key] = visit(child, child_path)
            return output
        if isinstance(current, list):
            return [visit(child, (*path, str(index))) for index, child in enumerate(current)]
        if isinstance(current, tuple):
            return tuple(visit(child, (*path, str(index))) for index, child in enumerate(current))
        return current

    stripped = visit(value, ())
    manifest = tuple(
        sorted(
            set(records),
            key=lambda record: (record.path, record.normalized_leaf),
        )
    )
    return RedactionResult(stripped, manifest)
