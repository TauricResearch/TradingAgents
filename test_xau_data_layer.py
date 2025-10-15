"""
Test script for XAU data layer components.
Validates FRED API, COT data, ETF flows, and correlation tools.
"""

import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
print("Loaded environment variables:")
for key, value in os.environ.items():
    print(f"{key}={value}")

# Test dates
END_DATE = "2024-05-10"
START_DATE = "2024-01-01"

def test_fred_api():
    """Test FRED API integration."""
    print("\n" + "="*80)
    print("TESTING FRED API")
    print("="*80)

    try:
        from tradingagents.dataflows.fred_api import (
            get_fred_series,
            get_real_yields,
            get_inflation_data,
            get_dxy_data
        )

        # Test 1: Get DXY data
        print("\n1. Testing DXY (US Dollar Index)...")
        dxy_data = get_dxy_data(START_DATE, END_DATE)
        print("✓ DXY data retrieved successfully")
        print(f"Sample data:\n{dxy_data[:500]}...")

        # Test 2: Get 10Y Treasury Yield
        print("\n2. Testing 10Y Treasury Yield...")
        yield_data = get_fred_series("10Y_YIELD", START_DATE, END_DATE)
        print("✓ 10Y Yield data retrieved successfully")
        print(f"Sample data:\n{yield_data[:500]}...")

        # Test 3: Get Real Yields
        print("\n3. Testing Real Yields calculation...")
        real_yields = get_real_yields(START_DATE, END_DATE)
        print("✓ Real yields calculated successfully")
        print(f"Sample data:\n{real_yields[:500]}...")

        # Test 4: Get Inflation Data
        print("\n4. Testing Inflation indicators...")
        inflation_data = get_inflation_data(START_DATE, END_DATE)
        print("✓ Inflation data retrieved successfully")
        print(f"Sample data:\n{inflation_data[:500]}...")

        # Test 5: Get VIX
        print("\n5. Testing VIX (Volatility Index)...")
        vix_data = get_fred_series("VIX", START_DATE, END_DATE)
        print("✓ VIX data retrieved successfully")
        print(f"Sample data:\n{vix_data[:300]}...")

        print("\n✅ FRED API tests PASSED")
        return True

    except Exception as e:
        print(f"\n❌ FRED API tests FAILED: {e}")
        print("Make sure FRED_API_KEY is set in .env file")
        print("Get free API key at: https://fred.stlouisfed.org/docs/api/api_key.html")
        return False


def test_cot_data():
    """Test COT data parser."""
    print("\n" + "="*80)
    print("TESTING COT DATA PARSER")
    print("="*80)

    try:
        from tradingagents.dataflows.cot_data import (
            get_cot_positioning,
            analyze_cot_extremes
        )

        # Test 1: Get gold positioning
        print("\n1. Testing Gold COT positioning...")
        cot_data = get_cot_positioning("GOLD", START_DATE, END_DATE, lookback_weeks=20)
        print("✓ COT positioning data retrieved")
        print(f"Sample data:\n{cot_data[:800]}...")

        # Test 2: Analyze extremes
        print("\n2. Testing COT extremes analysis...")
        extremes = analyze_cot_extremes(END_DATE, lookback_years=2)
        print("✓ COT extremes analyzed")
        print(f"Analysis:\n{extremes}")

        print("\n✅ COT data tests PASSED")
        print("Note: Currently using simulated data. Production will use CFTC API.")
        return True

    except Exception as e:
        print(f"\n❌ COT data tests FAILED: {e}")
        return False


def test_etf_flows():
    """Test ETF flows scraper."""
    print("\n" + "="*80)
    print("TESTING ETF FLOWS SCRAPER")
    print("="*80)

    try:
        from tradingagents.dataflows.etf_flows import (
            get_gold_etf_flows,
            get_gold_etf_summary,
            analyze_etf_divergence
        )

        # Test 1: Get GLD flows
        print("\n1. Testing GLD ETF flows...")
        gld_flows = get_gold_etf_flows("GLD", START_DATE, END_DATE)
        print("✓ GLD flows retrieved")
        print(f"Sample data:\n{gld_flows[:600]}...")

        # Test 2: Get IAU flows
        print("\n2. Testing IAU ETF flows...")
        iau_flows = get_gold_etf_flows("IAU", START_DATE, END_DATE)
        print("✓ IAU flows retrieved")
        print(f"Sample data:\n{iau_flows[:600]}...")

        # Test 3: Get combined summary
        print("\n3. Testing combined ETF summary...")
        summary = get_gold_etf_summary(START_DATE, END_DATE)
        print("✓ ETF summary generated")
        print(f"Summary length: {len(summary)} characters")

        print("\n✅ ETF flows tests PASSED")
        return True

    except Exception as e:
        print(f"\n❌ ETF flows tests FAILED: {e}")
        return False


def test_correlation_tools():
    """Test correlation analysis tools."""
    print("\n" + "="*80)
    print("TESTING CORRELATION TOOLS")
    print("="*80)

    try:
        from tradingagents.dataflows.correlation_tools import (
            calculate_asset_correlation,
            analyze_gold_macro_correlations,
            check_correlation_regime,
            get_rolling_correlations
        )
        from tradingagents.dataflows.fred_api import get_dxy_data, get_fred_series
        from tradingagents.dataflows.y_finance import get_YFin_data_online

        # Get sample data
        print("\n1. Fetching sample data for correlation analysis...")
        gold_data = get_YFin_data_online("GC=F", START_DATE, END_DATE)
        dxy_data = get_dxy_data(START_DATE, END_DATE)
        yields_data = get_fred_series("10Y_YIELD", START_DATE, END_DATE)
        vix_data = get_fred_series("VIX", START_DATE, END_DATE)
        print("✓ Sample data fetched")

        # Test 2: Calculate Gold-DXY correlation
        print("\n2. Testing Gold-DXY correlation...")
        gold_dxy_corr = calculate_asset_correlation(gold_data, dxy_data, window_days=90)
        print("✓ Correlation calculated")
        print(f"Result:\n{gold_dxy_corr}")

        # Test 3: Comprehensive macro analysis
        print("\n3. Testing comprehensive macro correlation analysis...")
        macro_analysis = analyze_gold_macro_correlations(
            gold_data, dxy_data, yields_data, vix_data
        )
        print("✓ Macro analysis completed")
        print(f"Analysis:\n{macro_analysis}")

        # Test 4: Correlation regime check
        print("\n4. Testing correlation regime change detection...")
        regime_check = check_correlation_regime(gold_data, dxy_data)
        print("✓ Regime analysis completed")
        print(f"Result:\n{regime_check}")

        # Test 5: Rolling correlations
        print("\n5. Testing rolling correlations...")
        rolling_corr = get_rolling_correlations(
            gold_data, dxy_data, windows=[30, 60, 90]
        )
        print("✓ Rolling correlations calculated")
        print(f"Sample output:\n{rolling_corr[:600]}...")

        print("\n✅ Correlation tools tests PASSED")
        return True

    except Exception as e:
        print(f"\n❌ Correlation tools tests FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_integration():
    """Test integration of all data sources."""
    print("\n" + "="*80)
    print("INTEGRATION TEST - XAU DATA PIPELINE")
    print("="*80)

    try:
        from tradingagents.dataflows.fred_api import get_dxy_data, get_real_yields
        from tradingagents.dataflows.cot_data import get_cot_positioning
        from tradingagents.dataflows.etf_flows import get_gold_etf_flows
        from tradingagents.dataflows.correlation_tools import calculate_asset_correlation
        from tradingagents.dataflows.y_finance import get_YFin_data_online

        print("\nSimulating a complete XAU analysis workflow...")

        # Step 1: Get gold price
        print("1. Fetching gold price data...")
        gold_price = get_YFin_data_online("GC=F", START_DATE, END_DATE)
        print(f"✓ Gold price: {len(gold_price)} characters")

        # Step 2: Get macro factors
        print("2. Fetching macro factors (DXY, Real Yields)...")
        dxy = get_dxy_data(START_DATE, END_DATE)
        real_yields = get_real_yields(START_DATE, END_DATE)
        print(f"✓ DXY: {len(dxy)} characters")
        print(f"✓ Real Yields: {len(real_yields)} characters")

        # Step 3: Get positioning data
        print("3. Fetching positioning data (COT, ETF flows)...")
        cot_data = get_cot_positioning("GOLD", START_DATE, END_DATE)
        gld_flows = get_gold_etf_flows("GLD", START_DATE, END_DATE)
        print(f"✓ COT: {len(cot_data)} characters")
        print(f"✓ GLD flows: {len(gld_flows)} characters")

        # Step 4: Calculate correlations
        print("4. Calculating key correlations...")
        gold_dxy_corr = calculate_asset_correlation(gold_price, dxy)
        print(f"✓ Gold-DXY correlation calculated")

        # Summary
        print("\n📊 INTEGRATION TEST SUMMARY:")
        print(f"  ✓ Gold Price Data: Available")
        print(f"  ✓ DXY Data: Available")
        print(f"  ✓ Real Yields: Available")
        print(f"  ✓ COT Positioning: Available")
        print(f"  ✓ ETF Flows: Available")
        print(f"  ✓ Correlations: Calculated")

        print("\n✅ INTEGRATION TEST PASSED")
        print("All data sources are working and can be combined for XAU analysis!")
        return True

    except Exception as e:
        print(f"\n❌ INTEGRATION TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("XAU DATA LAYER COMPREHENSIVE TEST SUITE")
    print("="*80)
    print(f"Test Period: {START_DATE} to {END_DATE}")
    print("="*80)

    results = {}

    # Run tests
    results['FRED API'] = test_fred_api()
    results['COT Data'] = test_cot_data()
    results['ETF Flows'] = test_etf_flows()
    results['Correlation Tools'] = test_correlation_tools()
    results['Integration'] = test_integration()

    # Final summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)

    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name:.<40} {status}")

    total_passed = sum(results.values())
    total_tests = len(results)

    print("="*80)
    print(f"OVERALL: {total_passed}/{total_tests} test suites passed")

    if total_passed == total_tests:
        print("\n🎉 ALL TESTS PASSED! XAU data layer is ready for use.")
        print("\nNext steps:")
        print("1. Create XAU-specific analyst agents")
        print("2. Integrate these tools into agent workflows")
        print("3. Build XAU configuration and graph")
    else:
        print("\n⚠️  Some tests failed. Please review errors above.")
        print("\nCommon issues:")
        print("- FRED_API_KEY not set (get free key at https://fred.stlouisfed.org/)")
        print("- Network connectivity issues")
        print("- Missing dependencies (pip install -r requirements.txt)")

    print("="*80 + "\n")


if __name__ == "__main__":
    main()
