# 🤖 Setup Anthropic (Claude) for TradingAgents

Your company VPN blocks OpenAI, but **Anthropic (Claude) works perfectly!** 🎉

## ✅ Test Results Summary

- **✅ Anthropic (Claude)** - Fully accessible and working
- **❌ Google (Gemini)** - Blocked by company proxy  
- **❌ OpenRouter** - Blocked by Zscaler firewall
- **❌ Ollama** - Not installed (local option)

## 🔑 Step 1: Get Anthropic API Key

1. Go to: **https://console.anthropic.com/**
2. Sign up or sign in
3. Navigate to **"API Keys"** section
4. Click **"Create Key"**
5. Copy your API key (starts with `sk-ant-...`)

## 📝 Step 2: Update .env File

Replace the placeholder in your `.env` file:

```bash
# Change this line:
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# To your actual key:
ANTHROPIC_API_KEY=sk-ant-your-actual-key-here
```

## 🧪 Step 3: Test Your Setup

Run the test script to verify everything works:

```bash
./test_ai_providers.py
```

You should see: `✅ Anthropic (Claude) - FULLY WORKING`

## 🚀 Step 4: Run TradingAgents

Start the TradingAgents CLI:

```bash
source venv/bin/activate.fish
python -c "from cli.main import app; app()"
```

When prompted, select:
- **LLM Provider**: `Anthropic`
- **Quick-Thinking Model**: `Claude Haiku 3.5`
- **Deep-Thinking Model**: `Claude Sonnet 3.5` or `Claude Sonnet 4`

## 💰 Pricing

Claude is very affordable:
- **Haiku 3.5**: ~$0.25 per 1M tokens
- **Sonnet 3.5**: ~$3 per 1M tokens
- **Opus 4**: ~$15 per 1M tokens

For typical trading analysis: **~$0.10-$0.50 per analysis**

## 🎯 Available Models

### Quick-Thinking (Fast):
- `claude-3-5-haiku-latest` - Fast and cost-effective
- `claude-3-5-sonnet-latest` - Balanced performance

### Deep-Thinking (Advanced):
- `claude-3-5-sonnet-latest` - High-quality analysis
- `claude-3-7-sonnet-latest` - Advanced reasoning
- `claude-sonnet-4-0` - Premium performance

## 🛠️ Troubleshooting

### If you see "Connection Error":
1. Check your API key is correctly set in `.env`
2. Restart your terminal/shell
3. Re-run the test script

### If you see "Invalid API Key":
1. Verify the key starts with `sk-ant-`
2. Make sure there are no extra spaces
3. Generate a new key if needed

### If TradingAgents won't start:
1. Make sure virtual environment is activated
2. Check that all dependencies are installed
3. Run `pip install -e .` to reinstall

## ✨ Success!

Once setup, you'll have:
- ✅ Full TradingAgents functionality
- ✅ High-quality AI analysis from Claude
- ✅ Works around company VPN restrictions
- ✅ Affordable pricing

**Ready to analyze some stocks! 📈** 