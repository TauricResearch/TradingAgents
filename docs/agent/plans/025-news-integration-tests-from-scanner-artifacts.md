# Plan 025: Integration Tests for News Contract Using Live Scanner Artifacts

**Status**: Ready for Implementation  
**Priority**: Medium  
**Effort**: 2-3 hours  
**Dependencies**: Plan 024 (news contract normalization)

## Context

Plan 024 added comprehensive **unit test coverage** for news contract normalization with fully mocked components (mock evidence stores, mock LLM responses). These unit tests validate individual component behavior in isolation.

We now need **integration tests** that validate the **end-to-end pipeline** using:
- Real scanner report artifacts from past runs (as fixtures)
- Real tool execution (prefetch, evidence store operations, rendering)
- Real state propagation through analyst → fact-checker → context formatter
- **Mocked LLM responses** (to avoid non-deterministic API calls and costs)

## Objectives

1. Create integration test suite that uses **real scanner artifacts** as test fixtures
2. Test full pipeline: analyst prefetch → LLM invoke (mocked) → fact-checker → context formatter
3. Validate contract propagation with realistic payloads (not synthetic minimal mocks)
4. Use cassettes/fixtures from actual scanning runs to ensure tests match production behavior
5. Cover happy path, partial failures, and edge cases with realistic data

## Background: Existing Test Infrastructure

### Current Test Organization

```
tests/
├── unit/                          # Pure unit tests (all mocked)
│   ├── test_output_validation.py  # ✅ 10 tests for normalizer
│   ├── test_news_fact_checker.py  # ✅ 9 tests for fact-checker branches
│   ├── test_summary_context.py    # ✅ 6 tests for context formatter
│   └── agents/
│       └── test_analyst_agents.py # ✅ 3 tests for analyst error handling
├── integration/                   # Integration tests (some real components)
│   ├── test_analyst_graph_integration.py
│   ├── test_dataflows_integration.py
│   └── test_report_lifecycle_integration.py
├── e2e/                          # End-to-end tests (real runs)
│   ├── test_full_trading_run.py
│   └── test_scanner_run.py
└── cassettes/                    # VCR cassettes for HTTP mocking
    └── ...
```

### Available Scanner Artifacts

Scanner runs produce structured artifacts that can be used as test fixtures:

```
reports/daily/YYYY-MM-DD/
├── scan_results.json          # Contains scanner payloads
├── scanner_context.json       # Scanner context with macro regime, sectors
└── [ticker]_scan_report.md    # Individual ticker scan results

artifacts/live-tests/
├── scanner_outputs/
│   ├── 2026-03-31_NVDA_scan.json
│   ├── 2026-04-02_MRVL_scan.json
│   └── ...
```

**Key insight**: Scanner outputs include the **exact prefetch context** that would be available to the news analyst in a real run.

## Problem Statement

Current unit tests use synthetic minimal payloads:

```python
# Unit test - minimal synthetic payload
state = {
    "news_report_structured": {
        "ticker": "MRVL",
        "claims": [{"claim": "Test claim", "source": "Test", ...}],
    }
}
```

**Integration tests should use**:

```python
# Integration test - real scanner artifact
scanner_artifact = load_fixture("artifacts/live-tests/scanner_outputs/2026-04-02_MRVL_scan.json")
prefetch_context = scanner_artifact["pre_loaded_news_feeds"]
evidence_records = scanner_artifact["news_evidence_records"]
```

This validates:
- Real-world complexity (varied claim structures, multiple sources, edge cases)
- Actual prefetch context shapes from production tools
- Evidence store behavior with realistic record counts
- Contract normalization with production-like payloads

## Implementation Plan

### Step 1: Create Test Fixture Infrastructure

**Goal**: Establish reusable scanner artifact fixtures

**Tasks**:
1. Create `tests/integration/fixtures/scanner_artifacts/` directory
2. Copy representative scanner outputs from `artifacts/live-tests/` or `reports/daily/`:
   - **Happy path**: MRVL 2026-04-02 (3+ claims, valid evidence)
   - **Partial failure**: Ticker with missing evidence records
   - **Edge case**: Ticker with all claims removed during sanitization
   - **Complex case**: 10+ claims with multiple sources
3. Create fixture loader utility `tests/integration/conftest.py`:
   ```python
   @pytest.fixture
   def scanner_artifact_mrvl_2026_04_02():
       """Load MRVL scanner artifact with real news evidence."""
       return load_json_fixture("scanner_artifacts/mrvl_2026_04_02.json")
   
   @pytest.fixture
   def mock_llm_from_scanner_output():
       """Create MockLLM that returns scanner's actual analyst output."""
       def _factory(scanner_artifact):
           analyst_output = scanner_artifact["news_analyst_output"]
           return MockLLM([AIMessage(content=analyst_output)])
       return _factory
   ```

**Files to create**:
- `tests/integration/fixtures/scanner_artifacts/mrvl_2026_04_02.json`
- `tests/integration/fixtures/scanner_artifacts/nvda_2026_03_31.json`
- `tests/integration/fixtures/scanner_artifacts/partial_evidence_failure.json`
- `tests/integration/conftest.py` (fixture loader utilities)

**Expected fixture structure**:
```json
{
  "run_id": "scan_2026_04_02_12_34_56",
  "ticker": "MRVL",
  "trade_date": "2026-04-02",
  "pre_loaded_news_feeds": {
    "Company-Specific News (Last 7 Days)": "..."
  },
  "news_evidence_records": [
    {
      "evidence_id": "art_reuters_001",
      "source": "Reuters",
      "published_at": "2026-04-02",
      "title": "...",
      "summary": "...",
      "ticker": "MRVL",
      "section_label": "Company-Specific News (Last 7 Days)",
      "ordinal": 1
    }
  ],
  "news_analyst_output": "{\"ticker\": \"MRVL\", \"claims\": [...]}",
  "expected_contract_status": "completed",
  "expected_claim_count": 3
}
```

### Step 2: Create Integration Test Suite

**Goal**: Test full news analyst → fact-checker → context formatter pipeline

**File**: `tests/integration/test_news_contract_integration.py`

**Test Cases**:

```python
class TestNewsContractIntegration:
    """Integration tests for news contract with real scanner artifacts."""
    
    def test_happy_path_mrvl_with_real_evidence(
        self, 
        scanner_artifact_mrvl_2026_04_02,
        mock_llm_from_scanner_output
    ):
        """Test complete pipeline with real MRVL scanner artifact."""
        # Setup real evidence store with fixture records
        store = NewsEvidenceStore(db_path=":memory:")
        for record_dict in scanner_artifact_mrvl_2026_04_02["news_evidence_records"]:
            store._insert_record(NewsEvidenceRecord(**record_dict))
        
        # Create analyst with mocked LLM (using real scanner output)
        llm = mock_llm_from_scanner_output(scanner_artifact_mrvl_2026_04_02)
        analyst = create_news_analyst(llm, evidence_store=store)
        
        # Create fact-checker with same store
        fact_checker = create_news_fact_checker(evidence_store=store)
        
        # Build state from fixture
        state = {
            "run_id": scanner_artifact_mrvl_2026_04_02["run_id"],
            "company_of_interest": "MRVL",
            "trade_date": "2026-04-02",
            "messages": [HumanMessage(content="Analyze MRVL.")],
        }
        
        # Run analyst
        analyst_result = analyst(state)
        
        # Validate analyst output
        assert "news_report" in analyst_result
        assert "news_report_structured" in analyst_result
        
        # Run fact-checker
        fact_checker_state = {**state, **analyst_result}
        result = fact_checker(fact_checker_state)
        
        # Validate canonical contract
        contract = result["news_report_structured"]
        assert contract["status"] == scanner_artifact_mrvl_2026_04_02["expected_contract_status"]
        assert contract["contract_version"] == "news_report_v1"
        assert contract["key_metrics"]["claim_count"] == scanner_artifact_mrvl_2026_04_02["expected_claim_count"]
        assert contract["ticker"] == "MRVL"
        
        # Validate context formatter behavior
        research_packet = build_research_packet(result)
        assert "## News Structured Contract" in research_packet
        assert "status: completed" in research_packet
        assert "## News Report" in research_packet  # Raw report included for completed status
    
    def test_partial_evidence_failure_with_real_artifact(
        self,
        scanner_artifact_partial_evidence
    ):
        """Test pipeline when some evidence records are missing."""
        # Setup store with incomplete records (some evidence_ids referenced in claims don't exist)
        store = NewsEvidenceStore(db_path=":memory:")
        # Only insert half the records
        for record_dict in scanner_artifact_partial_evidence["news_evidence_records"][:2]:
            store._insert_record(NewsEvidenceRecord(**record_dict))
        
        # ... rest of test validates sanitization removes unverified claims
    
    def test_all_claims_removed_during_sanitization(self):
        """Test when all claims are removed due to missing evidence."""
        # Use fixture where analyst produced claims but no evidence records exist
        ...
    
    def test_contract_propagation_to_debate_brief(self):
        """Test contract flows correctly to debate evidence brief."""
        # Run full pipeline, then validate build_debate_evidence_brief
        ...
    
    def test_research_manager_fallback_with_invalid_status(self):
        """Test fallback text generation with non-completed status."""
        # Use fixture that produces invalid_structured_payload status
        # Validate build_research_manager_fallback gates claim iteration
        ...
```

**Files to create**:
- `tests/integration/test_news_contract_integration.py` (~200 lines)

**Expected test count**: 6-8 integration tests

### Step 3: Add Integration Tests for Prefetch Health Gates

**Goal**: Test analyst prefetch failure scenarios with realistic conditions

**File**: `tests/integration/test_news_analyst_prefetch_integration.py`

**Test Cases**:

```python
class TestNewsAnalystPrefetchIntegration:
    """Integration tests for news analyst prefetch and health gates."""
    
    def test_total_prefetch_failure_aborts_before_llm_invoke(self):
        """Test analyst aborts when both prefetch feeds fail."""
        # Mock prefetch_tools_parallel to return empty dict (total failure)
        with patch("tradingagents.agents.analysts.news_analyst.prefetch_tools_parallel", return_value={}):
            store = NewsEvidenceStore(db_path=":memory:")
            analyst = create_news_analyst(MockLLM([]), evidence_store=store)
            
            result = analyst(test_state)
            
            # Should abort before LLM invoke
            assert result["news_report_structured"]["status"] == "aborted"
            assert "Total prefetch failure" in result["news_report_structured"]["abort_reason"]
    
    def test_single_feed_success_passes_health_gate(self):
        """Test analyst proceeds when at least one feed succeeds."""
        # Mock partial prefetch success
        with patch("tradingagents.agents.analysts.news_analyst.prefetch_tools_parallel", 
                   return_value={"Company-Specific News (Last 7 Days)": "Some context"}):
            # ... validate analyst proceeds
    
    def test_evidence_ingestion_from_real_prefetch(self):
        """Test evidence store ingestion with real prefetch output shapes."""
        # Use real prefetch tool output (cached) to validate ingestion
        ...
```

**Files to create**:
- `tests/integration/test_news_analyst_prefetch_integration.py` (~150 lines)

**Expected test count**: 3-4 integration tests

### Step 4: Extract Scanner Artifacts from Real Runs

**Goal**: Create reusable fixture files from actual scanner runs

**Tasks**:
1. Run scanner on known dates: `python -m cli.main scan --date 2026-04-02`
2. Extract artifacts from `reports/daily/2026-04-02/`:
   - Load `scan_results.json`
   - For each ticker with news evidence, extract:
     - `pre_loaded_news_feeds` (from analyst input)
     - `news_evidence_records` (from NewsEvidenceStore query)
     - `news_analyst_output` (raw LLM response)
     - `fact_checker_output` (canonical contract)
3. Sanitize and save as fixture JSON:
   ```bash
   python scripts/extract_scanner_fixtures.py \
       --run-date 2026-04-02 \
       --ticker MRVL \
       --output tests/integration/fixtures/scanner_artifacts/mrvl_2026_04_02.json
   ```

**Files to create**:
- `scripts/extract_scanner_fixtures.py` (~100 lines)
  - Load scanner run artifacts
  - Extract relevant fields for fixture
  - Sanitize/redact sensitive data
  - Save as reusable JSON fixture

**Alternative**: If no recent scanner runs available, use existing artifacts from `artifacts/live-tests/scanner_outputs/` directly

### Step 5: Update Test Documentation

**Goal**: Document integration test patterns for future contributors

**Files to update**:
- `docs/testing.md`: Add section on "Integration Tests with Scanner Artifacts"
- `tests/integration/README.md`: Create if doesn't exist, document fixture structure

**Content**:
```markdown
## Integration Tests with Scanner Artifacts

Integration tests validate end-to-end behavior using real scanner artifacts as fixtures.

### Fixture Structure

Scanner artifact fixtures are stored in `tests/integration/fixtures/scanner_artifacts/`:
- Each fixture represents a real scanner run for a specific ticker/date
- Contains: prefetch context, evidence records, analyst output, expected contract
- Validates production-like complexity without requiring API calls

### Creating New Fixtures

```bash
# Extract fixture from recent scanner run
python scripts/extract_scanner_fixtures.py \
    --run-date YYYY-MM-DD \
    --ticker SYMBOL \
    --output tests/integration/fixtures/scanner_artifacts/ticker_date.json
```

### Running Integration Tests

```bash
# Run all integration tests
pytest tests/integration/ -v

# Run news contract integration tests
pytest tests/integration/test_news_contract_integration.py -v
```
```

## Testing Strategy

### What to Test (Integration)

**✅ Integration tests should validate**:
- Full pipeline flow with realistic payloads
- Evidence store operations with production-like record counts
- Contract normalization with varied claim structures
- Context formatter behavior with real contract shapes
- Prefetch → ingestion → sanitization → rendering chain

**❌ Integration tests should NOT**:
- Make real LLM API calls (mock LLM responses)
- Make real HTTP requests to external APIs (use cached prefetch)
- Test individual function logic in isolation (use unit tests)
- Validate low-level parsing logic (use unit tests)

### Test Data Selection

Choose scanner artifacts that represent:
1. **Happy path**: 3-5 claims, all verified, completed status
2. **Partial failure**: Some claims removed during sanitization
3. **Edge case**: All claims removed → invalid status
4. **Complex**: 10+ claims, multiple sources, mixed evidence types
5. **Prefetch failure**: No evidence records → empty/aborted status

### Mocking Strategy

```python
# Mock LLM responses (use real scanner output)
llm = MockLLM([AIMessage(content=scanner_artifact["news_analyst_output"])])

# Use real evidence store (in-memory)
store = NewsEvidenceStore(db_path=":memory:")

# Use real tools (if cached/deterministic)
# Mock tools (if non-deterministic or require external APIs)
```

## Acceptance Criteria

**Implementation complete when**:
- ✅ 6-8 integration tests added to `tests/integration/test_news_contract_integration.py`
- ✅ 3-4 prefetch integration tests added to `tests/integration/test_news_analyst_prefetch_integration.py`
- ✅ 3-5 scanner artifact fixtures created from real runs
- ✅ Fixture loader utilities added to `tests/integration/conftest.py`
- ✅ Artifact extraction script created at `scripts/extract_scanner_fixtures.py`
- ✅ All integration tests pass consistently
- ✅ Documentation updated in `docs/testing.md`
- ✅ Tests validate end-to-end contract propagation (analyst → fact-checker → context formatter)
- ✅ Tests use realistic payloads (not minimal synthetic mocks)
- ✅ No real LLM API calls required to run tests

## Implementation Notes

### Fixture Reusability

Create fixtures that can be reused across multiple test scenarios:

```python
# Base fixture with full data
@pytest.fixture
def scanner_artifact_base():
    return load_json_fixture("scanner_artifacts/mrvl_2026_04_02.json")

# Derived fixture with partial evidence
@pytest.fixture
def scanner_artifact_partial_evidence(scanner_artifact_base):
    artifact = copy.deepcopy(scanner_artifact_base)
    artifact["news_evidence_records"] = artifact["news_evidence_records"][:2]
    return artifact
```

### Evidence Store Setup

Use in-memory SQLite for fast test execution:

```python
@pytest.fixture
def evidence_store_from_fixture(scanner_artifact):
    store = NewsEvidenceStore(db_path=":memory:")
    for record_dict in scanner_artifact["news_evidence_records"]:
        # Convert dict to NewsEvidenceRecord
        record = NewsEvidenceRecord(**record_dict)
        store._insert_record(record)
    return store
```

### Prefetch Context Mocking

When prefetch context is included in fixture:

```python
@pytest.fixture
def mock_prefetch_from_fixture(scanner_artifact):
    def _mock(*args, **kwargs):
        return scanner_artifact["pre_loaded_news_feeds"]
    return _mock
```

### Expected Outputs

Each fixture should include expected outputs for validation:

```json
{
  "expected_contract_status": "completed",
  "expected_claim_count": 3,
  "expected_evidence_ids": 3,
  "expected_removed_claims": 0,
  "expected_in_research_packet": true,
  "expected_in_debate_brief": true
}
```

## Success Metrics

**After implementation**:
- Integration tests catch realistic edge cases missed by unit tests
- Scanner artifacts provide regression protection for production payloads
- Tests run in <5 seconds (using in-memory stores, mocked LLMs)
- Future engineers can add new fixtures from scanner runs without code changes
- Contract propagation validated end-to-end with production-like complexity

## Risks and Mitigations

**Risk**: Scanner artifacts become stale as code evolves  
**Mitigation**: Include fixture refresh as part of quarterly testing review

**Risk**: Fixtures contain sensitive data (API keys, PII)  
**Mitigation**: Sanitization script strips sensitive fields before saving

**Risk**: Integration tests become slow  
**Mitigation**: Use in-memory stores, mock all I/O, limit fixture sizes

**Risk**: Fixtures too large for git  
**Mitigation**: Keep fixtures <100KB each, compress if needed, use git-lfs for larger files

## Next Steps After Completion

1. Add CI/CD integration test job (separate from unit tests)
2. Create fixture refresh workflow (monthly/quarterly)
3. Consider property-based testing for contract invariants
4. Add performance benchmarks using integration test fixtures
5. Extend pattern to other analysts (market, fundamentals, social)

## References

- Original implementation: Plan 024 (news contract normalization)
- Unit tests: `tests/unit/test_news_fact_checker.py`, `tests/unit/test_summary_context.py`
- Scanner architecture: `docs/graph_flows.md` (scanner graph section)
- Evidence store: `tradingagents/memory/news_evidence.py`
- Test patterns: `docs/testing.md`
