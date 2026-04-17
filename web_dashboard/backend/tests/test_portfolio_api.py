"""
Tests for portfolio API — covers critical security and correctness fixes.
"""
import asyncio
import json
from pathlib import Path


class TestRemovePositionMassDeletion:
    """CRITICAL: ensure empty position_id does NOT delete all positions."""

    def test_empty_position_id_returns_false(self, tmp_path, monkeypatch):
        """position_id='' must be rejected, not treated as wildcard."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        watchlist_file = data_dir / "watchlist.json"
        positions_file = data_dir / "positions.json"
        positions_file.write_text(json.dumps({
            "accounts": {
                "默认账户": {
                    "positions": {
                        "AAPL": [
                            {"position_id": "pos_001", "shares": 10, "cost_price": 150.0, "account": "默认账户"},
                            {"position_id": "pos_002", "shares": 20, "cost_price": 160.0, "account": "默认账户"},
                        ]
                    }
                }
            }
        }))

        import fcntl
        monkeypatch.setattr(fcntl, "flock", lambda *args: None)

        # Patch DATA_DIR before importing
        monkeypatch.syspath_prepend(str(tmp_path.parent))
        monkeypatch.setattr("api.portfolio.DATA_DIR", data_dir)
        monkeypatch.setattr("api.portfolio.POSITIONS_FILE", positions_file)
        monkeypatch.setattr("api.portfolio.POSITIONS_LOCK", data_dir / "positions.lock")

        from api.portfolio import remove_position

        result = remove_position("AAPL", "", "默认账户")
        assert result is False, "Empty position_id must be rejected"

        # Verify BOTH positions still exist
        data = json.loads(positions_file.read_text())
        aapl_positions = data["accounts"]["默认账户"]["positions"]["AAPL"]
        assert len(aapl_positions) == 2, "Empty position_id must NOT delete any position"

    def test_none_position_id_returns_false(self, tmp_path, monkeypatch):
        """position_id=None must be rejected (API layer converts to '')."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        positions_file = data_dir / "positions.json"
        positions_file.write_text(json.dumps({
            "accounts": {
                "默认账户": {
                    "positions": {
                        "AAPL": [
                            {"position_id": "pos_001", "shares": 10, "cost_price": 150.0, "account": "默认账户"},
                        ]
                    }
                }
            }
        }))

        import fcntl
        monkeypatch.setattr(fcntl, "flock", lambda *args: None)

        monkeypatch.setattr("api.portfolio.DATA_DIR", data_dir)
        monkeypatch.setattr("api.portfolio.POSITIONS_FILE", positions_file)
        monkeypatch.setattr("api.portfolio.POSITIONS_LOCK", data_dir / "positions.lock")

        from api.portfolio import remove_position

        result = remove_position("AAPL", None, "默认账户")
        assert result is False

    def test_valid_position_id_removes_one(self, tmp_path, monkeypatch):
        """Valid position_id removes exactly that position."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        positions_file = data_dir / "positions.json"
        positions_file.write_text(json.dumps({
            "accounts": {
                "默认账户": {
                    "positions": {
                        "AAPL": [
                            {"position_id": "pos_001", "shares": 10, "cost_price": 150.0, "account": "默认账户"},
                            {"position_id": "pos_002", "shares": 20, "cost_price": 160.0, "account": "默认账户"},
                        ]
                    }
                }
            }
        }))

        import fcntl
        monkeypatch.setattr(fcntl, "flock", lambda *args: None)

        monkeypatch.setattr("api.portfolio.DATA_DIR", data_dir)
        monkeypatch.setattr("api.portfolio.POSITIONS_FILE", positions_file)
        monkeypatch.setattr("api.portfolio.POSITIONS_LOCK", data_dir / "positions.lock")

        from api.portfolio import remove_position

        result = remove_position("AAPL", "pos_001", "默认账户")
        assert result is True

        data = json.loads(positions_file.read_text())
        aapl_positions = data["accounts"]["默认账户"]["positions"]["AAPL"]
        assert len(aapl_positions) == 1
        assert aapl_positions[0]["position_id"] == "pos_002"


class TestGetRecommendationPathTraversal:
    """CRITICAL: ensure path traversal is blocked in get_recommendation."""

    def test_traversal_in_ticker_returns_none(self, tmp_path, monkeypatch):
        """Ticker with path separators must be rejected."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        rec_dir = data_dir / "recommendations" / "2026-01-01"
        rec_dir.mkdir(parents=True)

        import fcntl
        monkeypatch.setattr(fcntl, "flock", lambda *args: None)

        monkeypatch.setattr("api.portfolio.DATA_DIR", data_dir)
        monkeypatch.setattr("api.portfolio.RECOMMENDATIONS_DIR", data_dir / "recommendations")
        monkeypatch.setattr("api.portfolio.WATCHLIST_FILE", data_dir / "watchlist.json")
        monkeypatch.setattr("api.portfolio.POSITIONS_FILE", data_dir / "positions.json")
        monkeypatch.setattr("api.portfolio.WATCHLIST_LOCK", data_dir / "watchlist.lock")
        monkeypatch.setattr("api.portfolio.POSITIONS_LOCK", data_dir / "positions.lock")

        from api.portfolio import get_recommendation

        assert get_recommendation("2026-01-01", "../etc/passwd") is None
        assert get_recommendation("2026-01-01", "..\\..\\etc") is None
        assert get_recommendation("2026-01-01", "foo/../../etc") is None

    def test_traversal_in_date_returns_none(self, tmp_path, monkeypatch):
        """Date with path traversal must be rejected."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        import fcntl
        monkeypatch.setattr(fcntl, "flock", lambda *args: None)

        monkeypatch.setattr("api.portfolio.DATA_DIR", data_dir)
        monkeypatch.setattr("api.portfolio.RECOMMENDATIONS_DIR", data_dir / "recommendations")
        monkeypatch.setattr("api.portfolio.WATCHLIST_FILE", data_dir / "watchlist.json")
        monkeypatch.setattr("api.portfolio.POSITIONS_FILE", data_dir / "positions.json")
        monkeypatch.setattr("api.portfolio.WATCHLIST_LOCK", data_dir / "watchlist.lock")
        monkeypatch.setattr("api.portfolio.POSITIONS_LOCK", data_dir / "positions.lock")

        from api.portfolio import get_recommendation

        assert get_recommendation("../../../etc/passwd", "AAPL") is None
        assert get_recommendation("2026-01/../../etc", "AAPL") is None


class TestGetRecommendationsPagination:
    """Pagination on get_recommendations."""

    def test_pagination_returns_correct_slice(self, tmp_path, monkeypatch):
        """limit/offset must correctly slice results."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        rec_dir = data_dir / "recommendations"
        rec_dir.mkdir()

        import fcntl
        monkeypatch.setattr(fcntl, "flock", lambda *args: None)

        monkeypatch.setattr("api.portfolio.DATA_DIR", data_dir)
        monkeypatch.setattr("api.portfolio.RECOMMENDATIONS_DIR", rec_dir)
        monkeypatch.setattr("api.portfolio.WATCHLIST_FILE", data_dir / "watchlist.json")
        monkeypatch.setattr("api.portfolio.POSITIONS_FILE", data_dir / "positions.json")
        monkeypatch.setattr("api.portfolio.WATCHLIST_LOCK", data_dir / "watchlist.lock")
        monkeypatch.setattr("api.portfolio.POSITIONS_LOCK", data_dir / "positions.lock")

        # Create 5 recs
        for i in range(5):
            date_dir = rec_dir / f"2026-01-0{i+1}"
            date_dir.mkdir()
            (date_dir / "AAPL.json").write_text(json.dumps({"ticker": "AAPL", "decision": "BUY"}))

        from api.portfolio import get_recommendations

        result = get_recommendations(limit=10, offset=0)
        assert result["total"] == 5
        assert len(result["recommendations"]) == 5
        assert result["recommendations"][0]["contract_version"] == "v1alpha1"
        assert result["recommendations"][0]["result"]["decision"] == "BUY"

        result = get_recommendations(limit=2, offset=0)
        assert result["total"] == 5
        assert len(result["recommendations"]) == 2
        assert result["offset"] == 0

        result = get_recommendations(limit=2, offset=2)
        assert len(result["recommendations"]) == 2
        assert result["offset"] == 2
        assert result["limit"] == 2

    def test_single_recommendation_is_normalized_contract(self, tmp_path, monkeypatch):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        rec_dir = data_dir / "recommendations" / "2026-01-01"
        rec_dir.mkdir(parents=True)

        import fcntl
        monkeypatch.setattr(fcntl, "flock", lambda *args: None)

        monkeypatch.setattr("api.portfolio.DATA_DIR", data_dir)
        monkeypatch.setattr("api.portfolio.RECOMMENDATIONS_DIR", data_dir / "recommendations")
        monkeypatch.setattr("api.portfolio.WATCHLIST_FILE", data_dir / "watchlist.json")
        monkeypatch.setattr("api.portfolio.POSITIONS_FILE", data_dir / "positions.json")
        monkeypatch.setattr("api.portfolio.WATCHLIST_LOCK", data_dir / "watchlist.lock")
        monkeypatch.setattr("api.portfolio.POSITIONS_LOCK", data_dir / "positions.lock")

        (rec_dir / "AAPL.json").write_text(json.dumps({
            "ticker": "AAPL",
            "name": "Apple",
            "analysis_date": "2026-01-01",
            "decision": "OVERWEIGHT",
            "quant_signal": "BUY",
            "llm_signal": "HOLD",
            "confidence": 0.75,
        }))

        from api.portfolio import get_recommendation

        result = get_recommendation("2026-01-01", "AAPL")

        assert result["contract_version"] == "v1alpha1"
        assert result["date"] == "2026-01-01"
        assert result["result"]["decision"] == "OVERWEIGHT"
        assert result["result"]["signals"]["quant"]["rating"] == "BUY"
        assert result["compat"]["confidence"] == 0.75


class TestConstants:
    """Verify named constants are defined instead of magic numbers."""

    def test_portfolio_pagination_constants(self):
        """Portfolio module must have pagination constants."""
        portfolio_path = Path(__file__).parent.parent / "api" / "portfolio.py"
        content = portfolio_path.read_text()

        assert "DEFAULT_PAGE_SIZE" in content
        assert "MAX_PAGE_SIZE" in content

    def test_portfolio_semaphore_constant(self):
        """Semaphore concurrency must use named constant."""
        portfolio_path = Path(__file__).parent.parent / "api" / "portfolio.py"
        content = portfolio_path.read_text()

        assert "MAX_CONCURRENT_YFINANCE_REQUESTS" in content
        assert "asyncio.Semaphore(MAX_CONCURRENT_YFINANCE_REQUESTS)" in content

    def test_portfolio_locking_has_windows_fallback(self):
        portfolio_path = Path(__file__).parent.parent / "api" / "portfolio.py"
        content = portfolio_path.read_text()

        assert "except ImportError" in content
        assert "msvcrt" in content


class TestAsyncPriceFetch:
    def test_fetch_price_throttled_uses_worker_thread(self, monkeypatch):
        from api import portfolio

        calls = []

        async def fake_to_thread(func, *args):
            calls.append((func, args))
            return 321.0

        monkeypatch.setattr(portfolio.asyncio, "to_thread", fake_to_thread)

        result = asyncio.run(portfolio._fetch_price_throttled("AAPL"))

        assert result == 321.0
        assert calls == [(portfolio._fetch_price, ("AAPL",))]
