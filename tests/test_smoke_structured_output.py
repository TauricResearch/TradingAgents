import pytest

from scripts.smoke_structured_output import _missing_markers, _run_structure_checks


@pytest.mark.unit
def test_missing_markers_handles_non_string_output_without_typeerror():
    class StructuredLikeOutput:
        def __str__(self) -> str:
            return "recommendation='Hold' rationale='balanced'"

    missing = _missing_markers(StructuredLikeOutput(), ["**Recommendation**:"])

    assert missing == ["**Recommendation**:"]


@pytest.mark.unit
def test_run_structure_checks_counts_missing_markers(capsys):
    failures = _run_structure_checks(
        [
            ("Research Manager", "**Recommendation**: Hold", ["**Recommendation**:"]),
            ("Trader", "**Action**: Hold", ["**Action**:", "FINAL TRANSACTION PROPOSAL:"]),
        ]
    )

    output = capsys.readouterr().out
    assert failures == 1
    assert "PASS  Research Manager" in output
    assert "FAIL  Trader" in output
