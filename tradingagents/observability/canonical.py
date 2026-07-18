"""Canonical redacted business values and declared AgentState projections."""

from __future__ import annotations

import base64
import hashlib
import math
import types
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime, time
from enum import Enum
from typing import Annotated, Any, get_args, get_origin, get_type_hints

import rfc8785
from typing_extensions import is_typeddict

from tradingagents.agents.utils.agent_states import AgentState

from .redaction import RedactionResult, redact_recursive


SERIALIZER_VERSION = 1
BUSINESS_PROJECTION_VERSION = 1
RESERVED_OBSERVATION_FIELD = "_observation_commits"


class UnsupportedCanonicalValue(TypeError):
    pass


def _tag(kind: str, value: str) -> str:
    return f"$tradingagents:{kind}:{value}"


def _convert(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return _tag("float", "nan")
        if math.isinf(value):
            return _tag("float", "infinity" if value > 0 else "-infinity")
        return value
    if isinstance(value, bytes):
        encoded = base64.b64encode(value).decode("ascii")
        return _tag("bytes-base64", encoded)
    if isinstance(value, datetime):
        return _tag("datetime", value.isoformat())
    if isinstance(value, date):
        return _tag("date", value.isoformat())
    if isinstance(value, time):
        return _tag("time", value.isoformat())
    if isinstance(value, Enum):
        return _convert(value.value)
    if is_dataclass(value) and not isinstance(value, type):
        return _convert({item.name: getattr(value, item.name) for item in fields(value)})
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _convert(model_dump(mode="python"))
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            invalid = next(key for key in value if not isinstance(key, str))
            raise UnsupportedCanonicalValue(
                f"canonical mapping keys must be strings, got {type(invalid).__name__}"
            )
        output = {}
        for key in sorted(value):
            output[key] = _convert(value[key])
        return output
    if isinstance(value, (list, tuple)):
        return [_convert(item) for item in value]
    if isinstance(value, (set, frozenset)):
        converted = [_convert(item) for item in value]
        return sorted(converted, key=rfc8785.dumps)
    raise UnsupportedCanonicalValue(
        f"unsupported canonical value: {type(value).__module__}.{type(value).__qualname__}"
    )


@dataclass(frozen=True)
class CanonicalBusinessValueV1:
    value: Any
    redaction: RedactionResult

    @property
    def bytes(self) -> bytes:
        try:
            return rfc8785.dumps(self.value)
        except rfc8785.CanonicalizationError as exc:
            raise UnsupportedCanonicalValue(f"RFC 8785 serialization failed: {exc}") from exc

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.bytes).hexdigest()


def canonical_business_value(
    value: Any,
    *,
    additional_credential_names: tuple[str, ...] | frozenset[str] = (),
) -> CanonicalBusinessValueV1:
    redaction = redact_recursive(
        value,
        additional_credential_names=additional_credential_names,
    )
    return CanonicalBusinessValueV1(_convert(redaction.value), redaction)


def canonical_json_bytes(value: Any) -> bytes:
    return canonical_business_value(value).bytes


def canonical_sha256(value: Any) -> str:
    return canonical_business_value(value).sha256


def _normalized_type_description(annotation: Any) -> str:
    origin = get_origin(annotation)
    if origin is Annotated:
        return _normalized_type_description(get_args(annotation)[0])
    if origin in (types.UnionType,):
        return "union[" + ",".join(
            _normalized_type_description(arg) for arg in get_args(annotation)
        ) + "]"
    if origin is not None:
        name = getattr(origin, "__qualname__", str(origin).replace("typing.", ""))
        args = get_args(annotation)
        if not args:
            return name
        return f"{name}[{','.join(_normalized_type_description(arg) for arg in args)}]"
    if is_typeddict(annotation):
        hints = get_type_hints(annotation, include_extras=True)
        required = getattr(annotation, "__required_keys__", frozenset(hints))
        described = ",".join(
            f"{name}{'!' if name in required else '?'}:{_normalized_type_description(hints[name])}"
            for name in sorted(hints)
        )
        return f"typed-dict:{annotation.__module__}.{annotation.__qualname__}{{{described}}}"
    if isinstance(annotation, type):
        return f"{annotation.__module__}.{annotation.__qualname__}"
    return str(annotation).replace("typing.", "")


@dataclass(frozen=True)
class ApplicationStateSchema:
    application_fields: tuple[str, ...]
    document: dict[str, Any]
    sha256: str


def derive_application_state_schema(state_type: type) -> ApplicationStateSchema:
    hints = get_type_hints(state_type, include_extras=True)
    application_fields = tuple(
        sorted(name for name in hints if name != RESERVED_OBSERVATION_FIELD)
    )
    document = {
        "projection_version": BUSINESS_PROJECTION_VERSION,
        "fields": [
            {"name": name, "type": _normalized_type_description(hints[name])}
            for name in application_fields
        ],
    }
    return ApplicationStateSchema(
        application_fields=application_fields,
        document=document,
        sha256=canonical_sha256(document),
    )


_AGENT_STATE_SCHEMA = derive_application_state_schema(AgentState)
APPLICATION_STATE_FIELDS = _AGENT_STATE_SCHEMA.application_fields
AGENT_STATE_SCHEMA_DOCUMENT = _AGENT_STATE_SCHEMA.document
AGENT_STATE_SCHEMA_SHA256 = _AGENT_STATE_SCHEMA.sha256


@dataclass(frozen=True)
class BusinessStateProjectionV1:
    values: dict[str, Any]
    application_fields: tuple[str, ...] = APPLICATION_STATE_FIELDS
    agent_state_schema_sha256: str = AGENT_STATE_SCHEMA_SHA256
    projection_version: int = BUSINESS_PROJECTION_VERSION

    @classmethod
    def from_channel_values(
        cls,
        channel_values: Mapping[str, Any],
    ) -> BusinessStateProjectionV1:
        return cls(
            {name: channel_values[name] for name in APPLICATION_STATE_FIELDS if name in channel_values}
        )

    @property
    def canonical(self) -> CanonicalBusinessValueV1:
        return canonical_business_value(self.values)

    @property
    def sha256(self) -> str:
        return self.canonical.sha256


def project_business_delta(delta: Mapping[str, Any]) -> dict[str, Any]:
    unknown = set(delta) - set(APPLICATION_STATE_FIELDS) - {RESERVED_OBSERVATION_FIELD}
    if unknown:
        raise UnsupportedCanonicalValue(
            "node output contains undeclared application keys: " + ", ".join(sorted(unknown))
        )
    return {name: delta[name] for name in APPLICATION_STATE_FIELDS if name in delta}


def business_delta_sha256(delta: Mapping[str, Any]) -> str:
    return canonical_sha256(project_business_delta(delta))


def pending_writes_touch_business_state(
    pending_writes: list[tuple[str, str, Any]] | tuple[tuple[str, str, Any], ...],
) -> bool:
    return any(
        len(write) >= 2 and write[1] in APPLICATION_STATE_FIELDS
        for write in pending_writes
    )
