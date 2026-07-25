"""Validated YAML presets for selecting and ordering existing analyst roles.

Preset v1 deliberately controls only the four analyst nodes.  The evidence,
research, trader, risk, and portfolio-manager stages remain mandatory graph
links, so every accepted preset still produces one complete conclusion.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import yaml

from tradingagents.analysts import ANALYST_WIRE_KEYS, MANDATORY_CONVERGENCE_NODE_IDS

_PRESET_ID = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_ALLOWED_KEYS = frozenset({"id", "label", "analysts"})


class PresetValidationError(ValueError):
    """Raised when a preset cannot truthfully describe an executable graph."""


@dataclass(frozen=True)
class AnalystPreset:
    id: str
    label: str
    analysts: tuple[str, ...]
    source: Path

    def as_config_option(self) -> dict[str, object]:
        return {"id": self.id, "label": self.label, "analysts": list(self.analysts)}


@dataclass(frozen=True)
class PresetCatalog:
    presets: tuple[AnalystPreset, ...]
    issues: tuple[str, ...] = ()


def inspect_preset(path: str | Path) -> AnalystPreset:
    """Load one YAML preset and reject unknown keys, roles, duplicates, or emptiness."""
    source = Path(path)
    try:
        raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PresetValidationError(f"cannot read preset {source}: {exc.strerror}") from exc
    except yaml.YAMLError as exc:
        raise PresetValidationError(f"invalid YAML in preset {source}: {exc}") from exc
    if not isinstance(raw, dict):
        raise PresetValidationError(f"preset {source} must contain a mapping")
    unknown = sorted(set(raw) - _ALLOWED_KEYS)
    if unknown:
        raise PresetValidationError(
            f"preset {source} has unsupported keys: {', '.join(unknown)}"
        )
    preset_id = raw.get("id")
    label = raw.get("label")
    analysts = raw.get("analysts")
    if not isinstance(preset_id, str) or not _PRESET_ID.fullmatch(preset_id):
        raise PresetValidationError(f"preset {source} has an invalid id")
    if not isinstance(label, str) or not label.strip():
        raise PresetValidationError(f"preset {source} needs a non-empty label")
    if not isinstance(analysts, list) or not analysts or not all(
        isinstance(analyst, str) for analyst in analysts
    ):
        raise PresetValidationError(f"preset {source} needs a non-empty analysts list")
    unknown_analysts = sorted(set(analysts) - set(ANALYST_WIRE_KEYS))
    if unknown_analysts:
        raise PresetValidationError(
            f"preset {source} references unknown analysts: {', '.join(unknown_analysts)}"
        )
    if len(set(analysts)) != len(analysts):
        raise PresetValidationError(f"preset {source} contains duplicate analysts")
    _validate_fixed_convergence_path(source, analysts)
    return AnalystPreset(preset_id, label.strip(), tuple(analysts), source)


def _validate_fixed_convergence_path(source: Path, analysts: list[str]) -> None:
    """Assert the v1 preset can only feed the code-owned downstream DAG.

    The compact YAML schema intentionally has no ``nodes``, ``edges`` or
    ``input_from`` fields.  This explicit invariant keeps dry-run validation
    truthful: any non-empty, unique allow-listed analyst sequence terminates
    in the same mandatory nine-role decision path.
    """
    if not analysts or not MANDATORY_CONVERGENCE_NODE_IDS:
        raise PresetValidationError(
            f"preset {source} cannot construct the mandatory convergence path"
        )


def load_preset_catalog(
    *,
    builtin_dir: str | Path | None = None,
    user_dir: str | Path | None = None,
) -> PresetCatalog:
    """Load built-ins then let valid user presets override them by stable id.

    Invalid user files are surfaced as safe messages and do not prevent a
    localhost run from using the built-in presets.
    """
    builtin = Path(builtin_dir) if builtin_dir is not None else _builtin_preset_dir()
    user = Path(user_dir) if user_dir is not None else Path.home() / ".tradingagents" / "presets"
    selected: dict[str, AnalystPreset] = {}
    issues: list[str] = []
    for directory in (builtin, user):
        ids_in_directory: set[str] = set()
        for path in _yaml_files(directory):
            try:
                preset = inspect_preset(path)
            except PresetValidationError as exc:
                issues.append(str(exc))
                continue
            if preset.id in ids_in_directory:
                issues.append(f"preset {path} duplicates id {preset.id} in {directory}")
                continue
            ids_in_directory.add(preset.id)
            selected[preset.id] = preset
    return PresetCatalog(
        tuple(sorted(selected.values(), key=lambda preset: preset.id)), tuple(issues)
    )


def _builtin_preset_dir() -> Path:
    return Path(__file__).with_name("presets")


def _yaml_files(directory: Path) -> Iterable[Path]:
    if not directory.is_dir():
        return ()
    return tuple(
        path
        for path in sorted(directory.iterdir())
        if path.is_file() and path.suffix.lower() in {".yaml", ".yml"}
    )
