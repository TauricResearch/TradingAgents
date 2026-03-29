# LLM Clients - Consistency Improvements

## Issues to Fix

### 1. `validate_model()` is never called
- Add validation call in `get_llm()` with warning (not error) for unknown models

### 2. ~~Inconsistent parameter handling~~ (Fixed)
- GoogleClient now accepts unified `api_key` and maps it to `google_api_key`
- Legacy `google_api_key` still works for backward compatibility

### 3. `base_url` accepted but ignored
- `AnthropicClient`: accepts `base_url` but never uses it
- `GoogleClient`: accepts `base_url` but never uses it (correct - Google doesn't support it)

**Fix:** Remove unused `base_url` from clients that don't support it

### 4. Update validators.py with models from CLI
- Sync `VALID_MODELS` dict with CLI model options after Feature 2 is complete
