# Data Layer Fix and Test Plan for Global Macro Analyzer

## Current State Assessment

- ✅ pyproject.toml configured correctly
- ✅ Removed stray scanner_tools.py files outside tradingagents/
- ✅ yfinance_scanner.py implements all required functions
- ✅ alpha_vantage_scanner.py implements fallback get_market_movers_alpha_vantage correctly
- ✅ scanner_tools.py wrappers properly use route_to_vendor for all scanner methods
- ✅ default_config.py updated with scanner_data vendor configuration
- ✅ All scanner tools import successfully without runtime errors

## Outstanding Issues

- CLI scan command not yet implemented in cli/main.py
- Scanner graph components (MacroScannerGraph) not yet created
- No end-to-end testing of the data layer functionality

## Fix Plan

### 1. Implement Scanner Graph Components

Create the following files in tradingagents/graph/:

- scanner_setup.py: Graph setup logic for scanner components
- scanner_conditional_logic.py: Conditional logic for scanner graph flow
- scanner_graph.py: Main MacroScannerGraph class

### 2. Add Scan Command to CLI

Modify cli/main.py to include:

- @app.command() def scan(): entry point
- Date prompt (default: today)
- LLM provider config prompt (reuse existing helpers)
- MacroScannerGraph instantiation and scan() method call
- Rich panel display for results
- Report saving to results/macro_scan/{date}/ directory

### 3. Create MacroScannerGraph

Implement the scanner graph that:

- Runs parallel Phase 1 scanners (geopolitical, market movers, sectors)
- Coordinates Phase 2 industry deep dive
- Produces Phase 3 macro synthesis output
- Uses ScannerState for state management

### 4. End-to-End Testing

Execute the scan command and verify:

- Rich panels display correctly for each report section
- Top-10 stock watchlist is generated and displayed
- Reports are saved to results/macro_scan/{date}/ directory
- No import or runtime errors occur

## Implementation Steps

1. [ ] Create scanner graph components (scanner_setup.py, scanner_conditional_logic.py, scanner_graph.py)
2. [ ] Add scan command to cli/main.py with proper argument handling
3. [ ] Implement MacroScannerGraph with proper node/edge connections
4. [ ] Test scan command functionality
5. [ ] Verify output formatting and file generation
6. [ ] Document test results and any issues found

## Verification Criteria

- ✅ All scanner tools can be imported and used
- ✅ CLI scan command executes without errors
- ✅ Rich panels display market movers, indices, sector performance, and news
- ✅ Top-10 stock watchlist is generated and displayed
- ✅ Reports saved to results/macro_scan/{date}/ directory
- ✅ No runtime exceptions or import errors

## Contingency

- If errors occur during scan execution, check:
  - Vendor routing configuration in default_config.py
  - Function implementations in yfinance_scanner.py and alpha_vantage_scanner.py
  - Graph node/edge connections in scanner graph components
  - Rich panel formatting and output generation logic
