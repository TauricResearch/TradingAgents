"""Heading-hierarchy normalization for ``complete_report.md``.

The report builder in ``cli/main.py`` wraps each agent's body in fixed
``## I. …`` / ``### Market Analyst`` headings. Anything an agent emits at
H1, H2, or H3 inside that body must be demoted to H4 so it doesn't visually
escape its wrapper section. H4+ stays put. Wrapper H2s and H3s are preserved.
The transform must be idempotent and must not touch fenced code blocks.
"""
from __future__ import annotations

import re

import pytest


@pytest.fixture(scope="module")
def transform():
    # Import the in-package normalizer the same way the installed CLI does,
    # rather than loading scripts/ by file path. scripts/ is not packaged
    # into the wheel, so a file-path load passes here but fails in Docker
    # (the bug this module guards against). See the two tests below.
    from cli.report_headings import transform as fn
    return fn


def test_heading_normalizer_ships_inside_cli_package():
    """The normalizer must live in the installed ``cli`` package, not scripts/.

    Regression guard: ``pyproject.toml`` only packages ``cli*``/``tradingagents*``,
    so anything under ``scripts/`` is absent from the Docker/site-packages
    install. Importing from ``cli`` is what keeps ``save_report_to_disk`` working
    there.
    """
    from cli.report_headings import transform as fn
    assert callable(fn)


def test_cli_main_uses_in_package_normalizer():
    """``cli.main`` must resolve the normalizer via package import.

    Importing ``cli.main`` would raise if it still loaded the transform from a
    ``scripts/`` file path that doesn't exist in the installed layout.
    """
    import cli.main as main
    from cli.report_headings import transform as fn
    assert main._prune_report_headings is fn


def test_preserves_wrapper_headings(transform):
    text = (
        "# Trading Analysis Report: ABC\n"
        "\n"
        "## I. Analyst Team Reports\n"
        "\n"
        "### Market Analyst\n"
        "body\n"
    )
    out = transform(text)
    assert "# Trading Analysis Report: ABC\n" in out
    assert "## I. Analyst Team Reports\n" in out
    assert "### Market Analyst\n" in out


def test_demotes_body_h3_to_h4(transform):
    text = (
        "## I. Analyst Team Reports\n"
        "\n"
        "### Market Analyst\n"
        "#### Existing H4 Title\n"
        "### Trend (50 SMA)\n"
        "body\n"
        "### Momentum\n"
        "more\n"
    )
    out = transform(text)
    # wrapper H3 stays
    assert "### Market Analyst\n" in out
    # body H3s demoted
    assert "#### Trend (50 SMA)\n" in out
    assert "#### Momentum\n" in out
    # No leftover H3 lines for body subsections (must NOT be the bare ### form).
    body_h3 = [ln for ln in out.splitlines() if re.match(r"^### (Trend|Momentum)\b", ln)]
    assert body_h3 == []


def test_demotes_body_h1_h2(transform):
    text = (
        "### Market Analyst\n"
        "# Stray H1\n"
        "## Stray H2\n"
        "body\n"
    )
    out = transform(text)
    assert "#### Stray H1\n" in out
    assert "#### Stray H2\n" in out


def test_leaves_h4_h5_h6_alone(transform):
    text = (
        "### Market Analyst\n"
        "#### Section\n"
        "##### Subsection\n"
        "###### Sub-subsection\n"
    )
    out = transform(text)
    assert "#### Section\n" in out
    assert "##### Subsection\n" in out
    assert "###### Sub-subsection\n" in out


def test_idempotent(transform):
    text = (
        "## I. Analyst Team Reports\n"
        "\n"
        "### Market Analyst\n"
        "### Trend\n"
        "body\n"
    )
    once = transform(text)
    twice = transform(once)
    assert once == twice


def test_does_not_touch_fenced_code_blocks(transform):
    text = (
        "### Market Analyst\n"
        "```\n"
        "### Looks like a heading but is code\n"
        "## Also code\n"
        "```\n"
        "### Real heading after fence\n"
    )
    out = transform(text)
    # Inside fence: untouched
    assert "### Looks like a heading but is code\n" in out
    assert "## Also code\n" in out
    # Outside fence: demoted
    assert "#### Real heading after fence\n" in out


def test_wrapper_h2_resets_body_state(transform):
    # Outside any agent body region, H1/H2/H3 should be untouched.
    text = (
        "# Trading Analysis Report: ABC\n"
        "## I. Analyst Team Reports\n"
        "### Market Analyst\n"
        "### Stray Body H3\n"
        "## II. Research Team Decision\n"
        "### Bull Researcher\n"
        "### Stray Body H3 #2\n"
    )
    out = transform(text)
    assert "# Trading Analysis Report: ABC\n" in out
    assert "## I. Analyst Team Reports\n" in out
    assert "## II. Research Team Decision\n" in out
    assert "### Market Analyst\n" in out
    assert "### Bull Researcher\n" in out
    assert "#### Stray Body H3\n" in out
    assert "#### Stray Body H3 #2\n" in out


def test_real_world_vsh_pattern(transform):
    # Reproduces the VSH bug exactly.
    text = (
        "## I. Analyst Team Reports\n"
        "\n"
        "### Market Analyst\n"
        "#### VSH (Vishay Intertechnology, Inc.) — Technical Analysis Report\n"
        "**As of close: Friday, May 29, 2026**\n"
        "\n"
        "#### 1. Price Action Overview\n"
        "Some prose\n"
        "\n"
        "### Trend (50 SMA, 200 SMA, 10 EMA)\n"
        "- bullets\n"
        "\n"
        "### Momentum (MACD, RSI)\n"
        "- bullets\n"
        "\n"
        "### Sentiment Analyst\n"
        "**Overall Sentiment:** Bullish\n"
        "\n"
        "### 1. Source-by-source breakdown\n"
        "- bullets\n"
        "\n"
        "### Bottom line\n"
        "summary\n"
    )
    out = transform(text)
    # Wrapper H3s preserved
    assert "### Market Analyst\n" in out
    assert "### Sentiment Analyst\n" in out
    # Body H3s demoted
    assert "#### Trend (50 SMA, 200 SMA, 10 EMA)\n" in out
    assert "#### Momentum (MACD, RSI)\n" in out
    assert "#### 1. Source-by-source breakdown\n" in out
    assert "#### Bottom line\n" in out
    # No body H3 leaks through
    body_h3 = [
        ln
        for ln in out.splitlines()
        if ln.startswith("### ")
        and ln.strip("# ").strip()
        not in {"Market Analyst", "Sentiment Analyst"}
    ]
    assert body_h3 == [], f"Unexpected body H3s: {body_h3}"
