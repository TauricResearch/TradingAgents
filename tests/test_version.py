"""The package version has one source, tradingagents.__version__, which the build reads."""

import re
from pathlib import Path

import pytest

import tradingagents

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
CHANGELOG = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


@pytest.mark.unit
def test_the_build_reads_the_version_from_the_package():
    assert re.search(r'^dynamic = \["version"\]', PYPROJECT, re.M)
    assert 'version = {attr = "tradingagents.__version__"}' in PYPROJECT
    assert not re.search(r'^version = "', PYPROJECT, re.M)
    assert re.fullmatch(r"\d+\.\d+\.\d+(\.dev\d+|rc\d+)?", tradingagents.__version__)


def _unreleased_body() -> str:
    """The entries under ``[Unreleased]``, up to the next release heading."""
    match = re.search(r"^## \[Unreleased\]\s*$(.*?)(?=^## \[)", CHANGELOG, re.M | re.S)
    assert match, "CHANGELOG.md has no [Unreleased] section"
    return match.group(1).strip()


@pytest.mark.unit
def test_the_changelog_has_a_dated_section_for_the_running_version():
    """A development closes its own release, so the two never disagree."""
    version = tradingagents.__version__
    assert re.search(
        rf"^## \[{re.escape(version)}\] — \d{{4}}-\d{{2}}-\d{{2}}$", CHANGELOG, re.M
    ), f"CHANGELOG.md has no dated section for {version}"


@pytest.mark.unit
def test_no_entries_pile_up_in_unreleased():
    """Entries belong to a release section; [Unreleased] is a placeholder."""
    assert _unreleased_body() == "", (
        "CHANGELOG.md [Unreleased] still lists entries: close them into a dated "
        "section together with the version bump"
    )

