# ❓ Frequently Asked Questions

**The questions everyone asks (so you don't have to)**

---

## General

**Q: Is this free?**

A: The software is free and open source. You pay for:
- LLM API usage (~$0.10-0.20 per analysis with Claude/GPT-4)
- Free options exist (Google Gemini, Alpaca paper trading)

**Q: Is this actually AI-powered or just buzzwords?**

A: Actually AI-powered. Multiple LLM agents (using Claude/GPT-4) debate and analyze stocks. It's like having a team of analysts arguing about your trades.

**Q: Will this make me rich?**

A: No. This is a tool, not a crystal ball. Use it to inform decisions, not make them for you.

**Q: Can I use this for real trading?**

A: Yes, but start with paper trading! The Alpaca integration supports both.

---

## Setup

**Q: Which LLM provider should I use?**

A:
- **Claude (Anthropic)**: Best reasoning, great for complex analysis
- **GPT-4 (OpenAI)**: Faster, well-tested, slightly cheaper
- **Gemini (Google)**: Free tier available, good for experimentation

**Q: Do I need to know Python?**

A: Not for basic use! The web interface is point-and-click. Python knowledge helps for customization.

**Q: Docker or local install?**

A: Docker is easier (one command). Local install gives you more control.

**Q: What's in the .env file?**

A: Your API credentials. These are secrets - never commit to git. Use `.env.example` as a template and fill in your actual keys.

---

## Features

**Q: What's multi-agent analysis?**

A: Instead of one AI opinion, you get multiple specialized agents:
- Market Analyst (trends, technicals)
- Fundamentals Expert (financials, ratios)
- News Analyst (sentiment, events)
- Trader (synthesizes everything into a decision)

They literally debate the trade before giving you a signal.

**Q: How accurate are the predictions?**

A: We don't make predictions - we provide analysis. Accuracy depends on market conditions, which LLM you use, and what data is available. Backtest your strategies first!

**Q: Can I customize the analysis?**

A: Yes! Edit the agent prompts, add new analysts, change the debate process. It's all Python code.

**Q: What stocks can I analyze?**

A: Any US stock. Just provide the ticker symbol (NVDA, AAPL, TSLA, etc.). International stocks coming soon!

---

## Paper Trading

**Q: What is paper trading?**

A: Simulated trading with fake money but REAL market prices. Practice without risk.

**Q: Does Alpaca paper trading cost money?**

A: No! Completely free. You get $100,000 virtual dollars to play with.

**Q: Can I test my strategy without paper trading?**

A: Yes - use the backtesting framework. Simulate months of trading in seconds.

**Q: How do I switch from paper to live trading?**

A: Set `ALPACA_PAPER_TRADING=false` in your .env file. But seriously - practice more first!

---

## Technical

**Q: What's the difference between the brokers?**

A:
- **Alpaca**: Free paper trading, easy API, US stocks only
- **Interactive Brokers** (coming soon): Professional platform, global markets

**Q: How do I add a new LLM provider?**

A: Check `tradingagents/llm_factory.py` - add your provider following the existing pattern. PRs welcome!

**Q: Can I run this on a server?**

A: Yes! Docker makes it easy. Check [DOCKER.md](DOCKER.md) for deployment guides.

**Q: How much does it cost to run?**

A: Mostly LLM API costs. One analysis:
- Claude: ~$0.15
- GPT-4: ~$0.10
- Gemini: Free (with limits)

Running 24/7 with frequent analyses: Budget $50-200/month.

**Q: Does this support real-time data?**

A: Currently batch processing. Real-time streaming is on the roadmap!

**Q: Can I integrate with other brokers?**

A: Currently Alpaca and Interactive Brokers. Want to add another? Submit a PR or open an issue!

---

## Troubleshooting

**Q: "API quota exceeded" - what do I do?**

A: You hit your LLM provider's limit. Wait for reset or upgrade your plan.

**Q: Analysis takes forever**

A: Normal! Deep analysis with multiple agents takes 60-90 seconds. Grab coffee. It's worth the wait.

**Q: My trades aren't executing**

A: Check:
1. Market is open (9:30 AM - 4 PM ET, Mon-Fri)
2. Broker is connected (`connect` command)
3. You have buying power
4. Ticker symbol is valid

**Q: Docker container keeps restarting**

A: Check logs: `docker-compose logs`. Usually a missing .env or invalid API key.

**Q: "Connection refused" on localhost:8000**

A: Port 8000 is already in use. Try:
```bash
lsof -i :8000  # Find what's using it
docker-compose down && docker-compose up  # Restart containers
```

**Q: I see "ModuleNotFoundError"**

A: Dependencies missing. Run:
```bash
pip install -r requirements.txt
```

**Q: Web UI is slow or freezing**

A: Likely waiting for AI analysis. Check browser console for errors. Restart if needed: `docker-compose restart`

---

## Safety & Security

**Q: Is my API key safe?**

A: Yes - stored in .env which is gitignored. Never committed to repos. Good practice: rotate keys periodically.

**Q: Can someone hack my trading account?**

A: Use paper trading first! For live trading, use Alpaca's security features (2FA, IP whitelist).

**Q: What data do you collect?**

A: We don't collect anything. All analysis happens locally or via your API keys. Read our privacy policy for details.

**Q: Is the code audited?**

A: It's open source - you can audit it yourself! We encourage security reviews. Found a vulnerability? Report it responsibly.

---

## Contributing

**Q: Can I contribute?**

A: Please do! We need:
- New broker integrations
- Better UI/UX
- Strategy templates
- Documentation improvements

**Q: I found a bug - where do I report it?**

A: GitHub Issues: https://github.com/TauricResearch/TradingAgents/issues

**Q: Can I fork this for my own use?**

A: Absolutely! It's open source. Just follow the license terms.

**Q: How do I run tests?**

A: Check the contributing guide. Generally:
```bash
pytest tests/
```

---

## Advanced

**Q: Can I backtest strategies?**

A: Yes! Check `examples/backtest_example.py` for details.

**Q: How do I add custom indicators?**

A: Add them to `tradingagents/indicators/` and reference in your agents.

**Q: Can I trade crypto?**

A: Not yet. Stocks only for now. Crypto support is on the roadmap.

**Q: Mobile app?**

A: On the roadmap! Web app works great on mobile for now.

**Q: Can I use this in production?**

A: It's production-ready for personal use. For commercial use, consult your legal team.

**Q: How do I scale this?**

A: Docker deployment handles most scaling. For enterprise needs, check [DOCKER.md](DOCKER.md).

---

## Mistakes & Learning

**Q: I made a bad trade with paper money - does it matter?**

A: Nope! That's the whole point of paper trading. Make mistakes, learn, improve. Zero consequences.

**Q: The AI recommended something stupid - should I blame it?**

A: Nah. AI is a tool, not infallible. It's trained on data with limitations. Always do your own research.

**Q: Can I see what the AI is thinking?**

A: Yes! The analysis output shows each agent's reasoning. You're not flying blind.

**Q: How do I get better at this?**

A:
1. Start with paper trading
2. Analyze real trades with the AI
3. Compare AI analysis to your own
4. Backtest strategies
5. Read the code and understand the logic
6. Iterate and improve

---

## Performance & Optimization

**Q: How fast is the analysis?**

A: Typically 60-90 seconds for multi-agent analysis. Depends on LLM provider and market data availability.

**Q: Can I speed it up?**

A: Yes:
- Use GPT-4 (faster than Claude for some queries)
- Reduce the number of agents
- Cache historical data
- Use paper trading vs live (no latency)

**Q: Does it work offline?**

A: No - requires API access to LLMs and market data. But you could cache results for offline review.

---

## Getting Help

**Didn't find your answer?**
- Check the docs: [FEATURES.md](FEATURES.md), [DOCKER.md](DOCKER.md)
- Ask on GitHub Discussions
- Read the code (it's well-commented!)
- Check the examples in `examples/`

**Still stuck?**
- Open a GitHub issue with:
  - What you tried
  - Error message (if any)
  - Your setup (Docker/local, Python version, OS)
  - Relevant logs

We're here to help! 🤝

---

**Last Updated:** November 2025
**Have a question not listed?** Open an issue and we'll add it here!
