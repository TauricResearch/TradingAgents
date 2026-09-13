"""Configuration for the Devin bridge sidecar."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field

# Display string used in health/logs when the bridge lets the Devin CLI pick
# the model (no explicit --model passed to `devin -p`).
DEVIN_CLI_DEFAULT = "devin-cli-default"

# Semantic aliases TradingAgents sends. Both map to the same Devin model
# by default; the mapping is centralized here so deep/quick can diverge
# without touching TradingAgents.
DEFAULT_ALIASES: dict[str, str] = {
    "devin-quick": DEVIN_CLI_DEFAULT,
    "devin-deep": DEVIN_CLI_DEFAULT,
}

# Restrictive project config written into the runtime workspace.
# Tool-level deny matchers restrict the Devin CLI to inference-only mode.
RUNTIME_CONFIG: dict = {
    "permissions": {
        "deny": [
            "read",
            "grep",
            "glob",
            "edit",
            "exec",
            "mcp__*",
            "Fetch(*)",
        ],
        "allow": [],
    },
    "read_config_from": {
        "agents_standard": False,
        "cursor": False,
        "windsurf": False,
        "claude": False,
        "copilot": False,
        "opencode": False,
        "zed": False,
    },
}

# Prefix for automatically-created temporary runtime directories.
# Lives under the OS temp location (e.g. /tmp), NEVER inside the checkout.
_RUNTIME_PREFIX = "tradingagents-devin-bridge-"


@dataclass
class BridgeConfig:
    """Runtime configuration for the bridge sidecar.

    Model resolution precedence (highest to lowest):
      1. CLI --quick-model / --deep-model (explicit per-alias)
      2. CLI --model (shorthand for both)
      3. ENV DEVIN_BRIDGE_QUICK_MODEL / DEVIN_BRIDGE_DEEP_MODEL
      4. ENV DEVIN_BRIDGE_MODEL
      5. None — let the Devin CLI use its own configured/default model
    """

    host: str = "127.0.0.1"
    port: int = 8765
    # The resolved quick and deep models (after precedence resolution).
    # None means "let the Devin CLI choose its configured/default model"
    # (no --model flag passed to `devin -p`).
    quick_model: str | None = None
    deep_model: str | None = None
    aliases: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_ALIASES))
    timeout: int = 180
    max_concurrency: int = 1
    devin_bin: str = ""
    runtime_dir: str = ""
    export_dir: str | None = None
    debug: bool = False
    # Set to the auto-created temp dir so the server can clean it up on shutdown.
    # None means the user supplied --runtime-dir explicitly (do NOT auto-delete).
    _auto_runtime_dir: str | None = None

    def resolve_devin_bin(self) -> str:
        """Return the Devin executable path, defaulting to PATH lookup."""
        if self.devin_bin:
            return self.devin_bin
        candidate = os.path.expanduser("~/.local/bin/devin")
        return candidate if os.path.exists(candidate) else "devin"

    def resolve_runtime_dir(self) -> str:
        """Return the runtime workspace directory.

        If the user supplied --runtime-dir, use that (after safety checks).
        Otherwise create a unique temp directory under the OS temp location.
        """
        if self.runtime_dir:
            return self.runtime_dir
        if self._auto_runtime_dir:
            return self._auto_runtime_dir
        self._auto_runtime_dir = tempfile.mkdtemp(prefix=_RUNTIME_PREFIX)
        return self._auto_runtime_dir

    def is_auto_runtime(self) -> bool:
        """True if the runtime dir was auto-created (safe to delete on shutdown)."""
        return self._auto_runtime_dir is not None and not self.runtime_dir

    def resolve_model(self, requested: str) -> str | None:
        """Map a TradingAgents model alias to a real Devin model name.

        Returns None when the alias maps to the Devin CLI default (no explicit
        model configured). Raises ValueError for unknown aliases.
        """
        if requested == "devin-quick":
            return self.quick_model
        if requested == "devin-deep":
            return self.deep_model
        # Allow direct Devin model names if they match a configured model.
        if requested == self.quick_model or requested == self.deep_model:
            return requested
        raise ValueError(
            f"Unknown model alias {requested!r}. "
            f"Known aliases: devin-quick, devin-deep"
        )

    def known_models(self) -> list[str]:
        """Return all model names the bridge accepts from TradingAgents."""
        return list(self.aliases.keys())

    def model_mapping(self) -> dict[str, str]:
        """Return the alias → model mapping for health reporting.

        None (Devin CLI default) is rendered as DEVIN_CLI_DEFAULT for display.
        """
        return {
            "devin-quick": self.quick_model or DEVIN_CLI_DEFAULT,
            "devin-deep": self.deep_model or DEVIN_CLI_DEFAULT,
        }


def resolve_config_from_cli(
    model: str | None = None,
    quick_model: str | None = None,
    deep_model: str | None = None,
) -> tuple[str | None, str | None]:
    """Resolve (quick_model, deep_model) from CLI args and environment.

    Precedence (highest to lowest):
      1. --quick-model / --deep-model
      2. --model (sets both)
      3. DEVIN_BRIDGE_QUICK_MODEL / DEVIN_BRIDGE_DEEP_MODEL
      4. DEVIN_BRIDGE_MODEL
      5. None — let the Devin CLI use its own configured/default model
    """
    env_quick = os.environ.get("DEVIN_BRIDGE_QUICK_MODEL", "")
    env_deep = os.environ.get("DEVIN_BRIDGE_DEEP_MODEL", "")
    env_common = os.environ.get("DEVIN_BRIDGE_MODEL", "")

    # Resolve quick: CLI --quick-model > CLI --model > ENV quick > ENV common > None
    q = quick_model or model or env_quick or env_common or None
    # Resolve deep: CLI --deep-model > CLI --model > ENV deep > ENV common > None
    d = deep_model or model or env_deep or env_common or None

    return q, d
