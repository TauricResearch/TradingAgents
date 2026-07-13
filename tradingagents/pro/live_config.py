"""live.yaml loader (go-live Phase 4).

Live capital may only be armed from an explicit config file where a human
wrote out EVERY risk limit — no silent defaults. A missing key is refused
with the key named. The loader validates against ``LiveRiskLimits`` (which
re-checks bounds and the leverage acknowledgement), so a malformed number
fails here, not at the venue.

deploy/live.yaml.example documents every field. The file is gitignored.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tradingagents.contracts import LiveRiskLimits

_REQUIRED_RISK_KEYS = tuple(LiveRiskLimits.model_fields.keys())
_VALID_MODES = ("shadow", "canary", "live")
_VALID_BREACH = ("cancel_and_flatten", "cancel_only")


class LiveConfigError(Exception):
    """The config is absent, unparseable, or missing a required key."""


@dataclass(frozen=True)
class LiveConfig:
    venue: str
    pair_modes: dict[str, str]         # pair -> shadow|canary|live
    risk: LiveRiskLimits
    breach_action: str
    promotion: dict
    path: Path

    def mode_for(self, pair: str) -> str | None:
        return self.pair_modes.get(pair)


def _require(mapping: dict, key: str, ctx: str):
    if key not in mapping:
        raise LiveConfigError(f"live config missing required key: {ctx}{key}")
    return mapping[key]


def load_live_config(path: str | Path) -> LiveConfig:
    import yaml

    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LiveConfigError(f"live config not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise LiveConfigError(f"live config is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise LiveConfigError("live config must be a mapping")

    venue = _require(raw, "venue", "")
    pairs = _require(raw, "pairs", "")
    if not isinstance(pairs, dict) or not pairs:
        raise LiveConfigError("live config 'pairs' must be a non-empty mapping")
    pair_modes: dict[str, str] = {}
    for pair, cfg in pairs.items():
        mode = _require(cfg or {}, "mode", f"pairs.{pair}.")
        if mode not in _VALID_MODES:
            raise LiveConfigError(
                f"pairs.{pair}.mode must be one of {_VALID_MODES}, got {mode!r}")
        pair_modes[pair] = mode

    risk_raw = _require(raw, "risk", "")
    if not isinstance(risk_raw, dict):
        raise LiveConfigError("live config 'risk' must be a mapping")
    # no silent defaults: every LiveRiskLimits field must be present
    missing = [k for k in _REQUIRED_RISK_KEYS if k not in risk_raw]
    if missing:
        raise LiveConfigError(
            "live config 'risk' missing required keys (no defaults for real "
            f"capital): {missing}")
    try:
        risk = LiveRiskLimits(**risk_raw)
    except Exception as exc:  # pydantic ValidationError incl. leverage ack
        raise LiveConfigError(f"live config 'risk' invalid: {exc}") from exc

    breach = _require(raw, "breach_action", "")
    if breach not in _VALID_BREACH:
        raise LiveConfigError(
            f"breach_action must be one of {_VALID_BREACH}, got {breach!r}")

    return LiveConfig(
        venue=venue, pair_modes=pair_modes, risk=risk,
        breach_action=breach, promotion=raw.get("promotion", {}), path=path,
    )
