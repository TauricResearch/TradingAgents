# OpenAI API Key Setup

## How to Get Your OpenAI API Key

1. **Go to OpenAI Platform**: https://platform.openai.com/signup

2. **Create Account**: Sign up with email or Google/Microsoft account

3. **Verify Phone**: Add phone number for verification

4. **Go to API Keys**: https://platform.openai.com/api-keys

5. **Create New Key**: Click "Create new secret key"

6. **Copy Key**: Save it somewhere safe (you won't see it again!)

7. **Add Credits**: Go to Billing and add at least $5 for testing

## Environment Variable

Add to your `.env` file:

```
OPENAI_API_KEY=sk-your-key-here
```

## Pricing (as of 2024)

- GPT-4o: $2.50 / 1M input tokens, $10 / 1M output tokens
- GPT-4o-mini: $0.15 / 1M input tokens, $0.60 / 1M output tokens
- GPT-3.5-turbo: $0.50 / 1M input tokens, $1.50 / 1M output tokens

For carry trade analysis, GPT-4o-mini is recommended for cost efficiency.

## Note

The system works WITHOUT OpenAI API key in dry_run mode. The API key is only needed for:
- LLM-powered market analysis
- Natural language trading signals
- Risk assessment reports
- Portfolio recommendations
