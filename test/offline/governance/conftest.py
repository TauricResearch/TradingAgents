"""Fixtures for the Phase 7 governance-tool specification."""

from __future__ import annotations

import pytest
from harness import GitRepo


@pytest.fixture
def git_repo(tmp_path):
    return GitRepo(tmp_path / "repo")
