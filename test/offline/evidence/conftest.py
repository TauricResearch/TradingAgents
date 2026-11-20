"""Shared fixtures for the offline evidence time-filtering suite."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_DIR = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

FROZEN_NOW = datetime(2026, 11, 11, 0, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def frozen_now():
    return FROZEN_NOW


@pytest.fixture
def load_case():
    def _load_case(case_id: str) -> dict:
        path = FIXTURES_DIR / f"{case_id}.json"
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)

    return _load_case


@pytest.fixture
def iter_items():
    def _iter_items(case: dict) -> list:
        return case["items"]

    return _iter_items
