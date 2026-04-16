# Orchestrator Configuration Validation

Status: implemented (2026-04-16)
Audience: orchestrator users, backend maintainers
Scope: LLMRunner configuration validation and error classification

## Change Log

**2026-04-16**: Refactored provider validation to centralize patterns in `factory.py`
- Moved `_PROVIDER_BASE_URL_PATTERNS` from `llm_runner.py` to `ProviderSpec.base_url_patterns` in `factory.py`
- Added `validate_provider_base_url()` function in factory for reusable validation
- Split ollama and openrouter into separate `ProviderSpec` entries (previously shared openai's spec)
- Reduced `llm_runner.py` from 45 lines to 13 lines for validation logic
- All 21 tests pass, including 6 provider mismatch tests

## Overview

`orchestrator/llm_runner.py` implements three layers of configuration validation to catch errors before expensive graph initialization or API calls:

1. **Provider × Base URL Matrix Validation** - detects provider/endpoint mismatches
2. **Timeout Configuration Validation** - warns when timeouts may be insufficient
3. **Runtime Error Classification** - categorizes failures into actionable reason codes

## 1. Provider × Base URL Matrix Validation

### Purpose

Prevent wasted initialization time and API calls when provider and base_url are incompatible.

### Implementation

`LLMRunner._detect_provider_mismatch()` validates provider × base_url combinations using a pattern matrix:

```python
_PROVIDER_BASE_URL_PATTERNS = {
    "anthropic": [r"api\.anthropic\.com", r"api\.minimaxi\.com/anthropic"],
    "openai": [r"api\.openai\.com"],
    "google": [r"generativelanguage\.googleapis\.com"],
    "xai": [r"api\.x\.ai"],
    "ollama": [r"localhost:\d+", r"127\.0\.0\.1:\d+", r"ollama"],
    "openrouter": [r"openrouter\.ai"],
}
```

### Validation Logic

1. Extract `llm_provider` and `backend_url` from `trading_agents_config`
2. Look up expected URL patterns for the provider
3. Check if `backend_url` matches any expected pattern (regex)
4. If no match found, return mismatch details before graph initialization

### Error Response

When mismatch detected, `get_signal()` returns:

```python
Signal(
    degraded=True,
    reason_code="provider_mismatch",
    metadata={
        "data_quality": {
            "state": "provider_mismatch",
            "provider": "google",
            "backend_url": "https://api.openai.com/v1",
            "expected_patterns": [r"generativelanguage\.googleapis\.com"],
        }
    }
)
```

### Examples

**Valid configurations:**
- `anthropic` + `https://api.minimaxi.com/anthropic` ✓
- `openai` + `https://api.openai.com/v1` ✓
- `ollama` + `http://localhost:11434` ✓

**Invalid configurations (detected):**
- `google` + `https://api.openai.com/v1` → `provider_mismatch`
- `xai` + `https://api.minimaxi.com/anthropic` → `provider_mismatch`
- `ollama` + `https://api.openai.com/v1` → `provider_mismatch`

### Design Notes

- Uses **original provider name** (not canonical) for validation
  - `ollama`, `openrouter`, and `openai` share the same canonical provider (`openai`) but have different URL patterns
  - Validation must distinguish between them
- Validation runs **before** `TradingAgentsGraph` initialization
  - Saves ~5-10s of initialization time on mismatch
  - Avoids confusing error messages from LangChain/provider SDKs

## 2. Timeout Configuration Validation

### Purpose

Warn users when timeout settings may be insufficient for their analyst profile, preventing unexpected research degradation.

### Implementation

`LLMRunner._validate_timeout_config()` checks timeout sufficiency based on analyst count:

```python
_RECOMMENDED_TIMEOUTS = {
    1: {"analyst": 75.0, "research": 30.0},   # single analyst
    2: {"analyst": 90.0, "research": 45.0},   # two analysts
    3: {"analyst": 105.0, "research": 60.0},  # three analysts
    4: {"analyst": 120.0, "research": 75.0},  # four analysts
}
```

### Validation Logic

1. Extract `selected_analysts` from `trading_agents_config` (default: 4 analysts)
2. Extract `analyst_node_timeout_secs` and `research_node_timeout_secs`
3. Compare against recommended thresholds for analyst count
4. Log `WARNING` if configured timeout < recommended threshold

### Warning Example

```
LLMRunner: analyst_node_timeout_secs=75.0s may be insufficient for 4 analyst(s) (recommended: 120.0s)
```

### Design Notes

- **Non-blocking validation** - logs warning but does not prevent initialization
  - Different LLM providers have vastly different speeds (MiniMax vs OpenAI)
  - Users may have profiled their specific setup and chosen lower timeouts intentionally
- **Conservative recommendations** - thresholds assume slower providers
  - Based on real profiling data from MiniMax Anthropic-compatible endpoint
  - Users with faster providers can safely ignore warnings
- **Runs at `__init__` time** - warns early, before any API calls

### Timeout Calculation Rationale

Multi-analyst execution is **serial** for analysts, **parallel** for research:

```
Total time ≈ (analyst_count × analyst_timeout) + research_timeout + trading + risk + portfolio
```

For 4 analysts with 75s timeout each:
- Analyst phase: ~300s (serial)
- Research phase: ~30s (parallel bull/bear)
- Trading phase: ~15s
- Risk phase: ~10s
- Portfolio phase: ~10s
- **Total: ~365s** (6+ minutes)

Recommended 120s per analyst assumes:
- Some analysts may timeout and degrade
- Degraded path still completes within timeout
- Total execution stays under reasonable bounds (~8-10 minutes)

## 3. Runtime Error Classification

### Purpose

Categorize runtime failures into actionable reason codes for debugging and monitoring.

### Error Taxonomy

Defined in `orchestrator/contracts/error_taxonomy.py`:

```python
class ReasonCode(str, Enum):
    CONFIG_INVALID = "config_invalid"
    PROVIDER_MISMATCH = "provider_mismatch"
    PROVIDER_AUTH_FAILED = "provider_auth_failed"
    LLM_INIT_FAILED = "llm_init_failed"
    LLM_SIGNAL_FAILED = "llm_signal_failed"
    LLM_UNKNOWN_RATING = "llm_unknown_rating"
    # ... (quant-related codes omitted)
```

### Classification Logic

`LLMRunner.get_signal()` catches exceptions from `propagate()` and classifies them:

1. **Provider mismatch** (pre-initialization)
   - Detected by `_detect_provider_mismatch()` before graph creation
   - Returns `provider_mismatch` immediately

2. **Provider auth failure** (runtime)
   - Detected by `_looks_like_provider_auth_failure()` heuristic
   - Markers: `"authentication_error"`, `"login fail"`, `"invalid api key"`, `"unauthorized"`, `"error code: 401"`
   - Returns `provider_auth_failed`

3. **Generic LLM failure** (runtime)
   - Any other exception from `propagate()`
   - Returns `llm_signal_failed`

### Error Response Structure

All error signals include:

```python
Signal(
    degraded=True,
    reason_code="<reason_code>",
    direction=0,
    confidence=0.0,
    metadata={
        "error": "<exception message>",
        "data_quality": {
            "state": "<state>",
            # ... additional context
        }
    }
)
```

### Design Notes

- **Fail-fast on config errors** - mismatch detected before expensive operations
- **Heuristic auth detection** - no API call overhead, relies on error message patterns
- **Structured metadata** - `data_quality.state` mirrors `reason_code` for consistency

## 4. Testing

### Test Coverage

`orchestrator/tests/test_llm_runner.py` includes:

**Provider matrix validation:**
- `test_detect_provider_mismatch_google_with_openai_url`
- `test_detect_provider_mismatch_xai_with_anthropic_url`
- `test_detect_provider_mismatch_ollama_with_openai_url`
- `test_detect_provider_mismatch_valid_anthropic_minimax`
- `test_detect_provider_mismatch_valid_openai`

**Timeout validation:**
- `test_timeout_validation_warns_for_multiple_analysts_low_timeout`
- `test_timeout_validation_no_warn_for_single_analyst`
- `test_timeout_validation_no_warn_for_sufficient_timeout`

**Error classification:**
- `test_get_signal_classifies_provider_auth_failure`
- `test_get_signal_returns_provider_mismatch_before_graph_init`
- `test_get_signal_returns_reason_code_on_propagate_failure`

### Running Tests

```bash
cd /path/to/TradingAgents
python -m pytest orchestrator/tests/test_llm_runner.py -v
```

## 5. Maintenance

### Adding New Providers

When adding a new provider to `tradingagents/llm_clients/factory.py`:

1. Add a new `ProviderSpec` entry to `_PROVIDER_SPECS` tuple with `base_url_patterns`
2. Add test cases for valid and invalid configurations in `orchestrator/tests/test_llm_runner.py`
3. Update this documentation

**Example:**
```python
ProviderSpec(
    canonical_name="newprovider",
    aliases=("newprovider",),
    builder=lambda model, base_url=None, **kwargs: NewProviderClient(model, base_url, **kwargs),
    base_url_patterns=(r"api\.newprovider\.com",),
)
```

### Adjusting Timeout Recommendations

If profiling shows different timeout requirements:

1. Update `_RECOMMENDED_TIMEOUTS` in `llm_runner.py`
2. Document rationale in this file
3. Update test expectations if needed

### Extending Error Classification

To add new reason codes:

1. Add to `ReasonCode` enum in `contracts/error_taxonomy.py`
2. Add detection logic in `LLMRunner.get_signal()`
3. Add test case in `test_llm_runner.py`
4. Update this documentation

## 6. Known Limitations

### API Key Validation

Current implementation does **not** validate API key validity before graph initialization:

- **Limitation**: Expired/invalid keys are only detected during first `propagate()` call
- **Impact**: ~5-10s wasted on graph initialization before auth failure
- **Rationale**: Lightweight key validation would require provider-specific API calls, adding latency and complexity
- **Mitigation**: Auth failures are still classified correctly as `provider_auth_failed`

### Provider Pattern Maintenance

~~URL patterns must be manually kept in sync with provider changes:~~

**UPDATE (2026-04-16)**: Provider URL patterns have been moved to `tradingagents/llm_clients/factory.py` as part of `ProviderSpec`. This centralizes validation logic with provider definitions.

**Current implementation:**
- Each `ProviderSpec` includes optional `base_url_patterns` tuple
- `validate_provider_base_url()` function provides validation logic
- `LLMRunner._detect_provider_mismatch()` delegates to factory validation
- Patterns are co-located with provider builders, reducing maintenance burden

**Benefits:**
- Single source of truth for provider configuration
- Easier to keep patterns in sync when adding/updating providers
- Factory can be tested independently of orchestrator
- Reduced code duplication

**Remaining considerations:**
- **Risk**: Provider changes base URL structure (e.g., API versioning)
- **Mitigation**: Validation is non-blocking; mismatches are logged but don't prevent operation

### Timeout Recommendations

Recommendations are based on MiniMax profiling and may not generalize:

- **Risk**: Faster providers (OpenAI GPT-4) may trigger unnecessary warnings
- **Mitigation**: Warnings are advisory only; users can ignore if they've profiled their setup
- **Future**: Consider provider-specific timeout recommendations

## 7. Related Documentation

- `docs/contracts/result-contract-v1alpha1.md` - Signal contract structure
- `docs/architecture/research-provenance.md` - Research degradation semantics
- `docs/migration/rollback-notes.md` - Backend migration status
- `orchestrator/contracts/error_taxonomy.py` - Complete reason code list
