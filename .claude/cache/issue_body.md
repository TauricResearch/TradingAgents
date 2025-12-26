## Summary

Add OpenRouter as a third LLM provider option alongside OpenAI and Anthropic, leveraging OpenRouter's OpenAI-compatible API to enable access to multiple model providers through a single endpoint.

## What Does NOT Work

**Pattern: Direct OpenRouter SDK Integration**
- OpenRouter does not have a dedicated SDK
- Attempting to create a separate OpenRouter client class fails because OpenRouter is OpenAI-compatible and should reuse the OpenAI SDK
- Using a custom client breaks LangChain integration patterns

**Pattern: Hardcoding Model Names**
- Hardcoding specific OpenRouter model names in config files fails because OpenRouter's model catalog changes frequently
- Model names should be configurable via environment variables, not hardcoded defaults

**Pattern: Separate API Key Validation**
- Creating OpenRouter-specific validation logic fails because OpenRouter uses the same OpenAI SDK authentication pattern
- Validation should reuse existing OpenAI patterns with different base URL

## Scenarios

### Fresh Install
- User runs Spektiv for the first time
- No .env file exists
- System should:
  - Create .env from .env.example with OPENROUTER_API_KEY= template
  - Default to openai provider if OPENROUTER_API_KEY not set
  - Show clear error message if user selects openrouter without API key

### Update/Upgrade - Valid Existing Data
- User has existing .env with OPENAI_API_KEY or ANTHROPIC_API_KEY
- System should:
  - Preserve existing configuration
  - Add OPENROUTER_API_KEY= to .env.example (user must manually add to .env)
  - Not overwrite existing llm_provider setting
  - Display info message about new OpenRouter option

### Update/Upgrade - User Customizations
- User has custom llm_provider, backend_url, or model settings
- System must:
  - Never overwrite user's custom backend_url
  - Never change user's selected llm_provider
  - Only update .env.example, not .env

## Implementation Approach

**File 1: spektiv/default_config.py**

Add OpenRouter to GENAI_PROVIDERS and genai_config section with llm_provider, backend_url, and model options.

**File 2: spektiv/graph/trading_graph.py**

Add elif branch for openrouter provider using ChatOpenAI with:
- base_url: https://openrouter.ai/api/v1
- api_key from OPENROUTER_API_KEY env var
- default_headers with HTTP-Referer and X-Title

**File 3: .env.example**

Add OPENROUTER_API_KEY template and LLM_PROVIDER, LLM_MODEL, BACKEND_URL options.

**File 4: main.py**

Add OpenRouter configuration example in comments.

**File 5: README.md**

Update LLM configuration section with all three providers (OpenAI, Anthropic, OpenRouter).

## Test Scenarios

1. **Fresh Install - No API Keys**: Error message requesting API key for selected provider
2. **Switch from OpenAI to OpenRouter**: System uses OpenRouter, preserves OpenAI key
3. **Custom Backend URL**: System uses custom URL instead of default OpenRouter URL
4. **Invalid OpenRouter Model**: Clear error from OpenRouter API with docs link
5. **Missing API Key**: Immediate error before any API calls
6. **Update Preserves Custom Config**: .env unchanged, only .env.example updated

## Acceptance Criteria

### Fresh Install
- [ ] .env.example includes OPENROUTER_API_KEY= template
- [ ] .env.example includes LLM configuration examples for all three providers
- [ ] System defaults to openai if no provider specified
- [ ] Error message shown if user selects openrouter without API key

### Updates
- [ ] Existing .env files are never modified
- [ ] Only .env.example is updated with new template
- [ ] Existing llm_provider setting is preserved
- [ ] Existing backend_url customizations are preserved
- [ ] README updated with OpenRouter configuration examples

### Functionality
- [ ] OpenRouter works with default model
- [ ] OpenRouter works with custom LLM_MODEL setting
- [ ] OpenRouter works with custom BACKEND_URL setting
- [ ] LangChain integration uses ChatOpenAI with custom base_url
- [ ] HTTP headers include referer and title for OpenRouter tracking

### Validation
- [ ] Clear error if OPENROUTER_API_KEY missing
- [ ] Clear error if invalid llm_provider specified
- [ ] Error messages include documentation links
- [ ] Config validation happens before first API call

### Security
- [ ] API keys never logged or printed
- [ ] API keys only read from environment variables
- [ ] No hardcoded API keys in any file
- [ ] .env file remains in .gitignore

### Documentation
- [ ] README shows all three provider configurations
- [ ] README links to OpenRouter model catalog
- [ ] README explains model name format (provider/model-name)
- [ ] Comments in code explain OpenRouter OpenAI-compatibility

## Environment Requirements

- Python 3.8+
- LangChain 0.1.0+
- OpenAI SDK (already required for OpenAI provider)

## Source of Truth

- OpenRouter API documentation: https://openrouter.ai/docs
- Proven implementation pattern from anyclaude
- Verified: 2024-12-25
