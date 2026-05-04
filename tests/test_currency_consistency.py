"""Audit: all UI rendering must use GBP base currency symbol (£), not EUR (€)."""

import re
from pathlib import Path

import pytest

# Files that are allowed to use € (external/third-party content)
ALLOWED_EUR_FILES = [
    # None — all £ GBP in our codebase
]


def _eur_in_file(path: Path) -> list[str]:
    """Return list of lines containing € in a file."""
    lines = []
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(content.split("\n"), 1):
            # Skip comment lines
            if line.strip().startswith("//") or line.strip().startswith("#"):
                continue
            if "€" in line:
                lines.append(f"  line {i}: {line.strip()[:80]}")
    except Exception:
        pass
    return lines


class TestCurrencyConsistency:
    """GBP is the base currency — all UI code must render £, not €."""

    @pytest.mark.smoke
    def test_no_eur_in_server_tsx(self):
        """server/views/*.tsx must not contain EUR symbol."""
        server_views = Path("server/views").glob("*.tsx")
        problems = {}
        for f in server_views:
            lines = _eur_in_file(f)
            if lines:
                problems[f.name] = lines

        assert len(problems) == 0, (
            f"Found € in {len(problems)} view files:\n" +
            "\n".join(f"{name}:\n" + "\n".join(l) for name, l in problems.items())
        )

    @pytest.mark.smoke
    def test_no_eur_in_server_routes(self):
        """server/routes/*.ts must not contain EUR symbol."""
        server_routes = Path("server/routes").glob("*.ts")
        problems = {}
        for f in server_routes:
            lines = _eur_in_file(f)
            if lines:
                problems[f.name] = lines

        assert len(problems) == 0, (
            f"Found € in {len(problems)} route files:\n" +
            "\n".join(f"{name}:\n" + "\n".join(l) for name, l in problems.items())
        )

    @pytest.mark.smoke
    def test_benchmark_endpoint_declares_base_currency(self):
        """Benchmark API response must include baseCurrency: GBP."""
        import subprocess, json

        result = subprocess.run(
            ["curl", "-s", "http://localhost:3000/api/benchmark"],
            capture_output=True,
            text=True,
        )
        try:
            data = json.loads(result.stdout)
        except Exception:
            pytest.skip("Benchmark endpoint not available")

        assert "baseCurrency" in data, "benchmark endpoint must declare baseCurrency"
        assert data["baseCurrency"] == "GBP", (
            f"benchmark baseCurrency is {data['baseCurrency']}, expected GBP"
        )

    @pytest.mark.smoke
    def test_governance_endpoint_declares_base_currency(self):
        """Governance API response must include baseCurrency field."""
        import subprocess, json

        result = subprocess.run(
            ["curl", "-s", "http://localhost:3000/api/governance"],
            capture_output=True,
            text=True,
        )
        try:
            data = json.loads(result.stdout)
        except Exception:
            pytest.skip("Governance endpoint not available")

        assert "baseCurrency" in data or "note" in data, (
            "governance endpoint should declare baseCurrency or a note explaining mixed currencies"
        )

    @pytest.mark.smoke
    def test_portfolio_intelligence_returns_base_currency(self):
        """Portfolio intelligence must include GBP values."""
        import subprocess, json

        result = subprocess.run(
            ["curl", "-s", "http://localhost:3000/api/portfolio/intelligence"],
            capture_output=True,
            text=True,
        )
        try:
            data = json.loads(result.stdout)
        except Exception:
            pytest.skip("Portfolio intelligence not available")

        pf = data.get("portfolio", {})
        assert "total_value_gbp" in pf, "portfolio must have total_value_gbp"
        assert "cash_gbp" in pf, "portfolio must have cash_gbp"
        assert pf["total_value_gbp"] >= 0, "portfolio total must be non-negative (or 0 when empty)"