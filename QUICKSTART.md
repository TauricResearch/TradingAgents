# 🚀 TradingAgents Quick Start - Get Trading in 5 Minutes

**Too impatient to read the full docs?** We feel you. Let's get you up and running FAST.

## The 30-Second Version

```bash
# 1. Clone and enter
git clone https://github.com/TauricResearch/TradingAgents.git
cd TradingAgents

# 2. Set up environment
cp .env.example .env
nano .env  # Add your API keys (we'll help below)

# 3. Run with Docker (easiest)
docker-compose up

# 4. Open http://localhost:8000 and start trading! 🎉
```

**That's it.** Seriously. Now go analyze some stocks!

---

## The 5-Minute Version (For When Things Don't "Just Work")

### Step 1: Get Your API Keys (2 minutes)

You need TWO things minimum:

**1. An LLM Provider** (pick one):
- **Anthropic Claude** (Recommended - best reasoning)
  - Sign up: https://console.anthropic.com/
  - Get key: Settings → API Keys
  - Free tier: $5 credit

- **OpenAI** (Also great)
  - Sign up: https://platform.openai.com/
  - Get key: API Keys → Create new
  - Note: Costs ~$0.10-0.20 per analysis

- **Google Gemini** (Budget option)
  - Sign up: https://makersuite.google.com/
  - Free tier available!

**2. Market Data**
- **Alpha Vantage** (Free!)
  - Get key: https://www.alphavantage.co/support/#api-key
  - Just enter your email, instant key
  - 500 requests/day free tier

**Optional but Fun:**
- **Alpaca** (For paper trading)
  - Sign up: https://alpaca.markets/
  - Get $100,000 virtual money
  - Practice trading risk-free!

### Step 2: Configure Environment (1 minute)

Edit `.env`:

```bash
# Pick your AI brain
ANTHROPIC_API_KEY=sk-ant-...     # If using Claude
# OR
OPENAI_API_KEY=sk-...            # If using OpenAI

# Market data (required)
ALPHA_VANTAGE_API_KEY=YOUR_KEY_HERE

# Paper trading (optional but recommended)
ALPACA_API_KEY=PK...
ALPACA_SECRET_KEY=...
ALPACA_PAPER_TRADING=true        # Keep this true!
```

**Common Mistakes:**
- ❌ Quotes around keys ("sk-...") - Don't use quotes!
- ❌ Spaces before/after equals - Keep it tight: `KEY=value`
- ❌ Forgetting to save the file - We've all done it

### Step 3: Choose Your Adventure (2 minutes)

**Option A: Docker** (Recommended - Zero hassle)
```bash
docker-compose up
# Wait for "Application startup complete"
# Open http://localhost:8000
# Done! 🎉
```

**Option B: Local Install** (If you hate containers)
```bash
pip install -r requirements.txt
chainlit run web_app.py -w
# Open http://localhost:8000
```

**Option C: Command Line** (Old school)
```bash
pip install -e .
python examples/use_claude.py  # or use_openai.py
```

---

## Your First Analysis

Once the web UI is open:

```
Type: analyze NVDA
```

Wait 60-90 seconds while our AI agents:
- 📊 Analyze market trends
- 💰 Check fundamentals
- 📰 Read recent news
- 🤖 Debate the best strategy
- ✅ Give you a signal: BUY, SELL, or HOLD

Pretty cool, right?

---

## What Now?

**Paper Trading:**
```
connect               # Link to Alpaca
buy NVDA 5           # Buy 5 shares (fake money!)
portfolio            # See your positions
```

**Change AI Models:**
```
provider anthropic   # Switch to Claude
provider openai      # Switch to GPT-4
```

**Get Help:**
```
help                 # See all commands
```

---

## When Things Go Wrong

**"Analysis failed: API quota limits"**
- You ran out of API credits
- Solution: Check your API provider dashboard
- Anthropic/OpenAI: Add payment method

**"Connection failed: Invalid credentials"**
- Your API key is wrong
- Solution: Double-check .env file
- No spaces, no quotes, correct key

**"Market is closed"**
- Alpaca paper trading follows real market hours
- Solution: Try between 9:30 AM - 4 PM ET, Monday-Friday
- Or use `time_in_force=gtc` for after-hours orders

**"ModuleNotFoundError"**
- Missing dependencies
- Solution: `pip install -r requirements.txt`

**"Docker won't start"**
- Port 8000 already in use
- Solution: `docker-compose down` then `docker-compose up`

---

## Next Steps

- 📖 Read [FEATURES.md](FEATURES.md) for full feature list
- 🐳 Check [DOCKER.md](DOCKER.md) for deployment options
- 📈 Try [examples/](examples/) for code examples
- 🤝 Join our community (GitHub Discussions)

**Most importantly:** Have fun! This is YOUR trading assistant. Experiment, learn, and (with paper trading) make all your mistakes risk-free.

Happy trading! 🚀

---

## Pro Tips

💡 Start with paper trading. Get confident before risking real money.
💡 Claude (Anthropic) is better for complex analysis, GPT-4 is faster.
💡 Check the logs if something weird happens: `docker-compose logs`
💡 The AI isn't always right. Use it as one input, not the only input.

---

**Warning:** This software is for educational purposes. Past performance doesn't guarantee future results. Don't invest more than you can afford to lose. Seriously.
