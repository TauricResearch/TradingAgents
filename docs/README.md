# TradingAgents Documentation

Welcome to the TradingAgents documentation. This guide will help you understand, use, and extend the TradingAgents multi-agent financial trading framework.

## Overview

TradingAgents is a multi-agent trading framework that mirrors the dynamics of real-world trading firms. By deploying specialized LLM-powered agents - from fundamental analysts, sentiment experts, and technical analysts, to traders and risk management teams - the platform collaboratively evaluates market conditions and informs trading decisions.

## Documentation Structure

### Getting Started

- **[Quick Start Guide](QUICKSTART.md)** - Get up and running quickly with TradingAgents
- **[Development Setup](development/setup.md)** - Set up your development environment
- **[Configuration Guide](guides/configuration.md)** - Configure LLM providers, data vendors, and system settings

### Architecture

Understand the system design and how components interact:

- **[Multi-Agent System](architecture/multi-agent-system.md)** - Agent roles, responsibilities, and collaboration patterns
- **[Data Flow](architecture/data-flow.md)** - How data moves through the system
- **[LLM Integration](architecture/llm-integration.md)** - Provider abstraction and model selection

### API Reference

Detailed API documentation for developers:

- **[TradingGraph API](api/trading-graph.md)** - Core orchestration API
- **[Agents API](api/agents.md)** - Agent interfaces and implementations
- **[Data Flows API](api/dataflows.md)** - Data vendor integrations

### Guides

Step-by-step tutorials for common tasks:

- **[Adding a New Analyst](guides/adding-new-analyst.md)** - Extend the framework with custom analyst agents
- **[Adding an LLM Provider](guides/adding-llm-provider.md)** - Integrate new language model providers
- **[Configuration Options](guides/configuration.md)** - Comprehensive configuration reference

### Testing

Learn about the testing infrastructure:

- **[Testing Overview](testing/README.md)** - Testing philosophy and structure
- **[Running Tests](testing/running-tests.md)** - How to run the test suite
- **[Writing Tests](testing/writing-tests.md)** - Guidelines for writing new tests

### Development

Contributing and development guidelines:

- **[Development Setup](development/setup.md)** - Set up your development environment
- **[Contributing Guide](development/contributing.md)** - How to contribute to TradingAgents

## Key Concepts

### Multi-Agent Architecture

TradingAgents decomposes complex trading tasks into specialized roles:

- **Analyst Team**: Fundamentals, Sentiment, News, and Technical analysts
- **Researcher Team**: Bull and Bear researchers who debate insights
- **Trader Agent**: Makes trading decisions based on comprehensive analysis
- **Risk Management**: Evaluates portfolio risk and validates strategies
- **Portfolio Manager**: Final approval and execution oversight

### LangGraph Framework

Built on LangGraph for:
- State management across agent workflows
- Tool orchestration for data access
- Conditional routing based on agent outputs
- Memory persistence for context retention

### Data Vendor Abstraction

Flexible data sourcing through configurable vendors:
- **yfinance**: Stock prices and technical indicators
- **Alpha Vantage**: Fundamental data and news
- **Google News**: Alternative news sources
- **Local**: Offline backtesting data

## Quick Links

- [Installation Instructions](QUICKSTART.md#installation)
- [API Keys Setup](QUICKSTART.md#required-apis)
- [First Analysis](QUICKSTART.md#your-first-analysis)
- [Configuration Options](guides/configuration.md)
- [GitHub Repository](https://github.com/TauricResearch/TradingAgents)
- [Research Paper](https://arxiv.org/abs/2412.20138)

## Support

- **Discord**: [Join our community](https://discord.com/invite/hk9PGKShPK)
- **GitHub Issues**: [Report bugs or request features](https://github.com/TauricResearch/TradingAgents/issues)
- **Twitter**: [@TauricResearch](https://x.com/TauricResearch)

## License

TradingAgents is released under the MIT License. See the [LICENSE](../LICENSE) file for details.

## Disclaimer

TradingAgents is designed for research and educational purposes. It is not intended as financial, investment, or trading advice. Trading performance may vary based on many factors including model selection, data quality, and market conditions. See [Tauric AI Disclaimer](https://tauric.ai/disclaimer/) for full details.
