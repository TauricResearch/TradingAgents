"""
Tests for stock holdings management functionality.
"""

import json
import tempfile
from pathlib import Path
import pytest

# Import the modules we're testing
from scripts.fetch_holdings import HoldingsManager
from tradingagents.holdings_api import HoldingsAPI


class TestHoldingsManager:
    """Test cases for HoldingsManager class."""
    
    @pytest.fixture
    def temp_holdings_file(self):
        """Create a temporary holdings file for testing."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            test_data = {
                "holdings": [
                    {
                        "id": 1,
                        "symbol": "AAPL",
                        "company_name": "Apple Inc.",
                        "quantity": 100,
                        "purchase_price": 150.0,
                        "current_price": 180.0,
                        "purchase_date": "2024-01-15",
                        "sector": "Technology",
                        "status": "active"
                    }
                ],
                "portfolio_summary": {}
            }
            json.dump(test_data, f)
            temp_path = f.name
        
        yield temp_path
        
        # Cleanup
        Path(temp_path).unlink(missing_ok=True)
    
    def test_load_holdings(self, temp_holdings_file):
        """Test loading holdings from file."""
        manager = HoldingsManager(temp_holdings_file)
        holdings = manager.get_all_holdings()
        
        assert len(holdings) == 1
        assert holdings[0]["symbol"] == "AAPL"
    
    def test_calculate_portfolio_summary(self, temp_holdings_file):
        """Test portfolio summary calculation."""
        manager = HoldingsManager(temp_holdings_file)
        summary = manager.calculate_portfolio_summary()
        
        assert summary["total_holdings"] == 1
        assert summary["total_quantity"] == 100
        assert summary["total_invested"] == 15000.0
        assert summary["total_current_value"] == 18000.0
        assert summary["total_gain_loss"] == 3000.0
        assert summary["gain_loss_percentage"] == 20.0
    
    def test_add_holding(self, temp_holdings_file):
        """Test adding a new holding."""
        manager = HoldingsManager(temp_holdings_file)
        
        new_holding = manager.add_holding(
            symbol="MSFT",
            company_name="Microsoft",
            quantity=50,
            purchase_price=300.0,
            current_price=350.0,
            purchase_date="2024-02-01",
            sector="Technology"
        )
        
        assert new_holding["symbol"] == "MSFT"
        assert new_holding["quantity"] == 50
        
        all_holdings = manager.get_all_holdings()
        assert len(all_holdings) == 2
    
    def test_update_holding_price(self, temp_holdings_file):
        """Test updating a holding's current price."""
        manager = HoldingsManager(temp_holdings_file)
        
        result = manager.update_holding_price("AAPL", 200.0)
        assert result is True
        
        updated_holding = manager.get_holding_by_symbol("AAPL")
        assert updated_holding["current_price"] == 200.0
    
    def test_get_holding_by_symbol(self, temp_holdings_file):
        """Test retrieving a holding by symbol."""
        manager = HoldingsManager(temp_holdings_file)
        
        holding = manager.get_holding_by_symbol("AAPL")
        assert holding is not None
        assert holding["symbol"] == "AAPL"
        assert holding["company_name"] == "Apple Inc."
    
    def test_get_nonexistent_holding(self, temp_holdings_file):
        """Test retrieving a non-existent holding."""
        manager = HoldingsManager(temp_holdings_file)
        
        holding = manager.get_holding_by_symbol("NONEXISTENT")
        assert holding is None


class TestHoldingsAPI:
    """Test cases for HoldingsAPI class."""
    
    @pytest.fixture
    def temp_api(self):
        """Create a temporary API instance for testing."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            test_data = {
                "holdings": [
                    {
                        "id": 1,
                        "symbol": "AAPL",
                        "company_name": "Apple Inc.",
                        "quantity": 100,
                        "purchase_price": 150.0,
                        "current_price": 180.0,
                        "purchase_date": "2024-01-15",
                        "sector": "Technology",
                        "status": "active"
                    },
                    {
                        "id": 2,
                        "symbol": "XOM",
                        "company_name": "ExxonMobil",
                        "quantity": 50,
                        "purchase_price": 100.0,
                        "current_price": 110.0,
                        "purchase_date": "2024-02-01",
                        "sector": "Energy",
                        "status": "active"
                    }
                ],
                "portfolio_summary": {
                    "total_holdings": 2,
                    "total_quantity": 150,
                    "total_invested": 20000.0,
                    "total_current_value": 23500.0,
                    "total_gain_loss": 3500.0,
                    "gain_loss_percentage": 17.5
                }
            }
            json.dump(test_data, f)
            temp_path = f.name
        
        api = HoldingsAPI(temp_path)
        yield api
        
        # Cleanup
        Path(temp_path).unlink(missing_ok=True)
    
    def test_get_all_holdings(self, temp_api):
        """Test getting all holdings."""
        holdings = temp_api.get_all_holdings()
        assert len(holdings) == 2
    
    def test_get_holding_by_symbol(self, temp_api):
        """Test getting holding by symbol."""
        holding = temp_api.get_holding_by_symbol("AAPL")
        assert holding is not None
        assert holding["symbol"] == "AAPL"
    
    def test_get_holdings_by_sector(self, temp_api):
        """Test getting holdings by sector."""
        tech_holdings = temp_api.get_holdings_by_sector("Technology")
        energy_holdings = temp_api.get_holdings_by_sector("Energy")
        
        assert len(tech_holdings) == 1
        assert len(energy_holdings) == 1
        assert tech_holdings[0]["symbol"] == "AAPL"
        assert energy_holdings[0]["symbol"] == "XOM"
    
    def test_calculate_individual_return(self, temp_api):
        """Test calculating individual holding return."""
        return_data = temp_api.calculate_individual_return("AAPL")
        
        assert return_data is not None
        assert return_data["symbol"] == "AAPL"
        assert return_data["total_invested"] == 15000.0
        assert return_data["total_current_value"] == 18000.0
        assert return_data["gain_loss"] == 3000.0
        assert return_data["return_percent"] == 20.0
    
    def test_get_top_performers(self, temp_api):
        """Test getting top performers."""
        performers = temp_api.get_top_performers(limit=2)
        
        assert len(performers) <= 2
        assert performers[0]["symbol"] == "AAPL"  # 20% return
        assert performers[1]["symbol"] == "XOM"   # 10% return
    
    def test_get_sector_distribution(self, temp_api):
        """Test getting sector distribution."""
        distribution = temp_api.get_sector_distribution()
        
        assert "Technology" in distribution
        assert "Energy" in distribution
        # AAPL: 18000, XOM: 5500, total: 23500
        # Tech: 18000/23500 = 76.6%
        # Energy: 5500/23500 = 23.4%
        assert 76.0 < distribution["Technology"] < 77.0
        assert 23.0 < distribution["Energy"] < 24.0
    
    def test_get_stats(self, temp_api):
        """Test getting comprehensive statistics."""
        stats = temp_api.get_stats()
        
        assert stats["total_holdings"] == 2
        assert stats["total_quantity"] == 150
        assert "portfolio_summary" in stats
        assert "sector_distribution" in stats
        assert "top_performers" in stats


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
