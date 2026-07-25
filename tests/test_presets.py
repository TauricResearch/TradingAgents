from __future__ import annotations

import pytest
from typer.testing import CliRunner

from cli.main import app
from tradingagents.analysts import MANDATORY_CONVERGENCE_NODE_IDS
from tradingagents.presets import (
    PresetValidationError,
    inspect_preset,
    load_preset_catalog,
)

pytestmark = pytest.mark.unit


def _write(path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_inspect_preset_preserves_existing_analyst_order(tmp_path):
    path = tmp_path / "ordered.yaml"
    _write(
        path,
        "id: news-first\nlabel: 新闻优先\nanalysts:\n  - news\n  - market\n",
    )

    preset = inspect_preset(path)

    assert preset.id == "news-first"
    assert preset.analysts == ("news", "market")


def test_preset_v1_has_a_named_fixed_downstream_convergence_invariant(tmp_path):
    path = tmp_path / "safe.yaml"
    _write(path, "id: safe\nlabel: Safe\nanalysts: [market]\n")

    inspect_preset(path)

    assert MANDATORY_CONVERGENCE_NODE_IDS == (
        "Evidence Steward",
        "Bull Researcher",
        "Bear Researcher",
        "Research Manager",
        "Trader",
        "Aggressive Analyst",
        "Neutral Analyst",
        "Conservative Analyst",
        "Portfolio Manager",
    )


@pytest.mark.parametrize(
    "content, message",
    [
        ("id: invalid\nlabel: x\nanalysts: []\n", "non-empty analysts"),
        ("id: invalid\nlabel: x\nanalysts: [market, market]\n", "duplicate"),
        ("id: invalid\nlabel: x\nanalysts: [unknown]\n", "unknown analysts"),
        ("id: invalid\nlabel: x\nanalysts: [market]\nretries: 2\n", "unsupported keys"),
    ],
)
def test_inspect_preset_rejects_unsafe_or_unsupported_shape(tmp_path, content, message):
    path = tmp_path / "invalid.yaml"
    _write(path, content)

    with pytest.raises(PresetValidationError, match=message):
        inspect_preset(path)


def test_valid_user_preset_overrides_builtin_and_invalid_file_is_degraded(tmp_path):
    builtin = tmp_path / "builtin"
    user = tmp_path / "user"
    builtin.mkdir()
    user.mkdir()
    _write(
        builtin / "full.yaml",
        "id: full-research\nlabel: Builtin\nanalysts: [market, news]\n",
    )
    _write(
        user / "full.yaml",
        "id: full-research\nlabel: User\nanalysts: [news, market]\n",
    )
    _write(user / "broken.yaml", "id: broken\nlabel: Broken\nanalysts: [made-up]\n")

    catalog = load_preset_catalog(builtin_dir=builtin, user_dir=user)

    assert [preset.as_config_option() for preset in catalog.presets] == [
        {"id": "full-research", "label": "User", "analysts": ["news", "market"]}
    ]
    assert len(catalog.issues) == 1


def test_catalog_rejects_duplicate_ids_in_one_directory_but_allows_user_override(tmp_path):
    builtin = tmp_path / "builtin"
    user = tmp_path / "user"
    builtin.mkdir()
    user.mkdir()
    _write(builtin / "one.yaml", "id: same\nlabel: One\nanalysts: [market]\n")
    _write(builtin / "two.yaml", "id: same\nlabel: Two\nanalysts: [news]\n")
    _write(user / "override.yaml", "id: same\nlabel: User\nanalysts: [news]\n")

    catalog = load_preset_catalog(builtin_dir=builtin, user_dir=user)

    assert catalog.presets[0].label == "User"
    assert any("duplicates id same" in issue for issue in catalog.issues)


def test_inspect_preset_cli_renders_requested_order_and_fixed_convergence_path(tmp_path):
    path = tmp_path / "news-first.yaml"
    _write(path, "id: news-first\nlabel: News first\nanalysts: [news, market]\n")

    result = CliRunner().invoke(app, ["inspect-preset", str(path)])

    assert result.exit_code == 0, result.output
    assert result.output == "\n".join(
        (
            "Preset inspection accepted",
            "id: news-first",
            "label: News first",
            "analyst_order:",
            "  1. news",
            "  2. market",
            "mandatory_convergence_roles:",
            "  1. Evidence Steward",
            "  2. Bull Researcher",
            "  3. Bear Researcher",
            "  4. Research Manager",
            "  5. Trader",
            "  6. Aggressive Analyst",
            "  7. Neutral Analyst",
            "  8. Conservative Analyst",
            "  9. Portfolio Manager",
            "",
        )
    )


@pytest.mark.parametrize(
    "content, expected_error",
    [
        (
            "id: invalid\nlabel: Invalid\nanalysts: [made-up]\n",
            "references unknown analysts: made-up",
        ),
        (
            "id: invalid\nlabel: Invalid\nanalysts: [market]\nretries: 2\n",
            "has unsupported keys: retries",
        ),
    ],
)
def test_inspect_preset_cli_rejects_invalid_yaml_with_stable_nonzero_result(
    tmp_path, content, expected_error
):
    path = tmp_path / "invalid.yaml"
    _write(path, content)

    result = CliRunner().invoke(app, ["inspect-preset", str(path)])

    assert result.exit_code == 2
    assert result.output == f"Preset inspection failed: preset {path} {expected_error}\n"
