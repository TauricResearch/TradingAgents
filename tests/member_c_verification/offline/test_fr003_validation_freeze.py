"""SEL-TA-FR-003 — Validate and freeze the selected snapshot.

Fit: valid populated, explicit empty and null-cash fixtures load; six invalid
classes (bad JSON, missing positions, missing quantity, nonfinite number, wrong
scalar type, unreadable file) and as-of mismatch each stop input with a
field/file diagnostic; editing the file after confirmation does not change the
frozen context or fingerprint.

Enforcing design: runapi/input_service.PortfolioInputService (INV-01/INV-02).
"""

from __future__ import annotations

import pytest

from tradingagents.runapi.input_service import PortfolioInputService
from tradingagents.runapi.result import InputError

pytestmark = pytest.mark.unit

TICKER = "AAPL"
DATE = "2026-11-12"


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# TC-FR003-a: valid populated book loads and freezes with matching as-of.
def test_tc_fr003_a_valid_populated_loads(tmp_path):
    path = _write(tmp_path, "p.json",
                  '{"cash": 1000.0, "currency": "USD", '
                  '"positions": [{"ticker": "AAPL", "quantity": 5, "average_price": 10.0}]}')
    ctx = PortfolioInputService(tmp_path).freeze_path(TICKER, DATE, path, portfolio_as_of=DATE)

    assert ctx.mode.value == "PORTFOLIO_PROVIDED"
    assert ctx.snapshot.basename == "p.json"
    assert ctx.snapshot.portfolio_as_of == DATE
    assert ctx.snapshot.as_of_basis == "USER_CONFIRMED"


# TC-FR003-b: an explicit empty positions list is a flat book, not missing input.
def test_tc_fr003_b_explicit_empty_positions_is_valid(tmp_path):
    path = _write(tmp_path, "flat.json", '{"positions": []}')
    ctx = PortfolioInputService(tmp_path).freeze_path(TICKER, DATE, path, portfolio_as_of=DATE)
    assert ctx.mode.value == "PORTFOLIO_PROVIDED"
    assert ctx.snapshot.positions == ()


# TC-FR003-c: null cash is accepted and preserved as None (not zero).
def test_tc_fr003_c_null_cash_is_preserved(tmp_path):
    path = _write(tmp_path, "p.json", '{"cash": null, "positions": [{"ticker": "AAPL", "quantity": 1}]}')
    ctx = PortfolioInputService(tmp_path).freeze_path(TICKER, DATE, path, portfolio_as_of=DATE)
    assert ctx.snapshot.cash is None


# TC-FR003-d: six invalid classes each raise a typed InputError with a field/file.
@pytest.mark.parametrize("case,body,kind,fragment", [
    ("bad_json", "{not json", "MALFORMED_JSON", "basename"),
    ("missing_positions", '{"cash": 1}', "MISSING_POSITIONS", "positions"),
    ("missing_quantity", '{"positions": [{"ticker": "AAPL"}]}', "MISSING_QUANTITY", "quantity"),
    ("nonfinite", '{"positions": [{"ticker": "AAPL", "quantity": NaN}]}', "NONFINITE_NUMBER", "quantity"),
    ("wrong_type", '{"positions": [{"ticker": "AAPL", "quantity": "5"}]}', "WRONG_SCALAR_TYPE", "quantity"),
])
def test_tc_fr003_d_invalid_classes(tmp_path, case, body, kind, fragment):
    path = _write(tmp_path, f"{case}.json", body)
    with pytest.raises(InputError) as info:
        PortfolioInputService(tmp_path).freeze_path(TICKER, DATE, path, portfolio_as_of=DATE)
    err = info.value
    assert err.kind == kind
    assert err.basename == f"{case}.json"
    assert fragment in (err.field or fragment)


# TC-FR003-e: an unreadable path is a typed UNREADABLE_PATH error.
def test_tc_fr003_e_unreadable_path(tmp_path):
    with pytest.raises(InputError) as info:
        PortfolioInputService(tmp_path).freeze_path(TICKER, DATE, tmp_path / "nope.json", portfolio_as_of=DATE)
    assert info.value.kind == "UNREADABLE_PATH"


# TC-FR003-f: as-of mismatch stops input with AS_OF_MISMATCH.
def test_tc_fr003_f_as_of_mismatch(tmp_path):
    path = _write(tmp_path, "p.json", '{"positions": []}')
    with pytest.raises(InputError) as info:
        PortfolioInputService(tmp_path).freeze_path(TICKER, DATE, path, portfolio_as_of="2026-11-11")
    assert info.value.kind == "AS_OF_MISMATCH"


# TC-FR003-g: editing the file after freeze does not change the frozen snapshot.
def test_tc_fr003_g_edit_after_freeze_does_not_change_snapshot(tmp_path):
    path = _write(tmp_path, "p.json", '{"positions": [{"ticker": "AAPL", "quantity": 5}]}')
    ctx = PortfolioInputService(tmp_path).freeze_path(TICKER, DATE, path, portfolio_as_of=DATE)
    frozen_digest = ctx.snapshot.fingerprint_sha256
    frozen_rows = ctx.snapshot.positions

    path.write_text('{"positions": [{"ticker": "AAPL", "quantity": 999}]}', encoding="utf-8")

    assert ctx.snapshot.fingerprint_sha256 == frozen_digest
    assert ctx.snapshot.positions == frozen_rows
