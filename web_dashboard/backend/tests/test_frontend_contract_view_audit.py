from pathlib import Path
import re


FRONTEND_SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"
CONTRACT_VIEW = FRONTEND_SRC / "utils" / "contractView.js"
LEGACY_TOP_LEVEL_FIELDS = ("decision", "confidence", "quant_signal", "llm_signal")
DIRECT_FIELD_ACCESS = re.compile(r"(?:\?|)\.\s*(decision|confidence|quant_signal|llm_signal)\b")


def test_contract_view_reads_contract_result_before_compat_fields():
    source = CONTRACT_VIEW.read_text()

    assert "getResult(payload).decision ?? getCompat(payload).decision" in source
    assert "getResult(payload).confidence ?? getCompat(payload).confidence" in source
    assert "getResult(payload).signals?.quant?.rating ?? getCompat(payload).quant_signal" in source
    assert "getResult(payload).signals?.llm?.rating ?? getCompat(payload).llm_signal" in source


def test_frontend_consumers_use_contract_view_helpers_for_signal_fields():
    offenders: list[str] = []

    for path in sorted(FRONTEND_SRC.rglob("*.js")) + sorted(FRONTEND_SRC.rglob("*.jsx")):
        if path == CONTRACT_VIEW:
            continue
        matches = {
            match.group(1)
            for match in DIRECT_FIELD_ACCESS.finditer(path.read_text())
            if match.group(1) in LEGACY_TOP_LEVEL_FIELDS
        }
        if matches:
            offenders.append(f"{path.relative_to(FRONTEND_SRC)} -> {sorted(matches)}")

    assert offenders == []
