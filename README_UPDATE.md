# Updated README Sections

## Section to Replace "Required APIs"

Replace the "Required APIs" section in README.md with this:

---

### Required APIs

#### Data APIs
You will need [Alpha Vantage API](https://www.alphavantage.co/support/#api-key) for fundamental and news data (default configuration).

```bash
export ALPHA_VANTAGE_API_KEY=$YOUR_ALPHA_VANTAGE_API_KEY
```

**Note:** We are happy to partner with Alpha Vantage to provide robust API support for TradingAgents. You can get a free AlphaVantage API [here](https://www.alphavantage.co/support/#api-key), TradingAgents-sourced requests also have increased rate limits to 60 requests per minute with no daily limits. Typically the quota is sufficient for performing complex tasks with TradingAgents thanks to Alpha Vantage's open-source support program. If you prefer to use OpenAI for these data sources instead, you can modify the data vendor settings in `tradingagents/default_config.py`.

#### LLM Provider APIs

🎉 **NEW: Multi-Provider AI Support!** TradingAgents now supports multiple AI/LLM providers:

- ✅ **OpenAI** (GPT-4, GPT-4o, GPT-3.5-turbo) - Default
- ✅ **Ollama** (Local models - **FREE!** Llama 3.2, Mistral, etc.)
- ✅ **Anthropic** (Claude 3 Opus, Sonnet, Haiku)
- ✅ **Google** (Gemini Pro, Gemini Flash)
- ✅ **Groq** (Fast inference)
- ✅ **OpenRouter** (Multi-provider access)
- ✅ **Azure OpenAI**, **Together AI**, **HuggingFace**

**For OpenAI (Default):**
```bash
export OPENAI_API_KEY=$YOUR_OPENAI_API_KEY
```

**For Ollama (Free & Local):**
```bash
# No API key needed! Just install Ollama and pull models
ollama pull llama3.2  # Recommended - supports tool calling
```

**For Other Providers:**
```bash
# Anthropic
export ANTHROPIC_API_KEY=sk-ant-your-key-here

# Google Gemini
export GOOGLE_API_KEY=your-google-key-here

# Groq
export GROQ_API_KEY=gsk-your-groq-key

# See docs/LLM_PROVIDER_GUIDE.md for complete setup
```

Alternatively, you can create a `.env` file in the project root with your API keys (see `.env.example` for reference):
```bash
cp .env.example .env
# Edit .env with your actual API keys
```

📚 **[Complete Provider Setup Guide](docs/LLM_PROVIDER_GUIDE.md)** | **[Quick Examples](docs/MULTI_PROVIDER_SUPPORT.md)**

---

## Instructions

1. Open `README.md` in your editor
2. Find the section starting with `### Required APIs`
3. Replace it with the content above
4. Save the file
5. Follow the git commands in GIT_COMMANDS.md to commit and push
