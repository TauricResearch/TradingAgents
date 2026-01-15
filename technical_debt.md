# Technical Debt & Clean-up Tracker

## Phase 1: The Foundation (Post-Implementation)

### [MEDIUM] FactLedger Schema Strictness
- **Issue:** `agent_states.py` currently allows `Union[str, Dict[str, Any]]` for data payloads (Price, News, Insider). This was done to accommodate CSV strings from YFinance/Alpaca.
- **Goal:** The Ledger should be strictly JSON/Dict.
- **Fix:** Update `DataRegistrar` to parse all CSV strings into Lists of Dictionaries *before* freezing them into the Ledger.
- **Impact:** Ensures downstream analysts handle uniform JSON data, simplifying the logic.

### [LOW] DataRegistrar Exception Handling Optimization
- **Issue:** `DataRegistrar._safe_invoke` catches exceptions and returns "Error: ..." strings. The validator (`_validate_price_data`) then checks for these strings to re-raise functionality exceptions.
- **Goal:** Use native Exception bubbling or a `Result` type (Ok/Err).
- **Fix:** Remove the string-masking in `_safe_invoke`. Allow `concurrent.futures` to capture the Exception and handle it in the `exectutor.result()` call.
- **Impact:** Cleaner logs and less "String Parsing" for control flow.
