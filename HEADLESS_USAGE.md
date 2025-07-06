# Headless Mode Usage Guide

TradingAgents now supports headless operation for automated trading analysis without interactive prompts.

## Quick Start

```bash
# Basic headless analysis
python -m cli.main --ticker TSLA --headless

# Full configuration example
python -m cli.main \
  --ticker TSLA \
  --date 2024-05-10 \
  --analysts market,social,news,fundamentals \
  --depth deep \
  --llm-provider openai \
  --shallow-model gpt-4o-mini \
  --deep-model o1-mini \
  --output-dir ./reports \
  --headless \
  --quiet
```

## Command-Line Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--ticker` | `-t` | Stock ticker symbol (required in headless mode) | None |
| `--date` | `-d` | Analysis date (YYYY-MM-DD) | Today's date |
| `--analysts` | `-a` | Comma-separated analysts list | `market,social,news,fundamentals` |
| `--depth` | | Research depth (`shallow`, `medium`, `deep`) | `medium` |
| `--llm-provider` | | LLM provider (`openai`, `anthropic`, `google`) | `openai` |
| `--backend-url` | | LLM backend URL | `https://api.openai.com/v1` |
| `--shallow-model` | | Model for quick thinking | `gpt-4o-mini` |
| `--deep-model` | | Model for deep thinking | `o1-mini` |
| `--output-dir` | `-o` | Output directory for reports | `./results` |
| `--config` | `-c` | Configuration file path | None |
| `--headless` | | Enable headless mode | Interactive mode |
| `--quiet` | `-q` | Suppress verbose output | Verbose output |

## Configuration File

Create a JSON configuration file for complex setups:

```json
{
  "llm_provider": "openai",
  "deep_think_llm": "o1-mini",
  "quick_think_llm": "gpt-4o-mini",
  "backend_url": "https://api.openai.com/v1",
  "max_debate_rounds": 3,
  "max_risk_discuss_rounds": 3,
  "online_tools": true,
  "results_dir": "./results"
}
```

Use with: `python -m cli.main --config config.json --ticker AAPL --headless`

## Output Structure

Reports are saved in: `{output_dir}/{ticker}/{date}/`

- `reports/` - Individual analyst reports as markdown files
- `complete_report.md` - Combined analysis report
- `decision.json` - Final trading decision in JSON format

## Examples

### Automated Pipeline
```bash
# Run daily analysis for multiple stocks
for ticker in AAPL TSLA NVDA; do
  python -m cli.main --ticker $ticker --headless --quiet > results_$ticker.json
done
```

### CI/CD Integration
```bash
# Quick analysis for deployment
python -m cli.main \
  --ticker SPY \
  --analysts market,news \
  --depth shallow \
  --headless \
  --quiet
```

### Custom Analysis
```bash
# Deep research with custom models
python -m cli.main \
  --ticker MSFT \
  --depth deep \
  --llm-provider anthropic \
  --shallow-model claude-3-5-haiku-latest \
  --deep-model claude-sonnet-4-0 \
  --headless
```

## Error Handling

- Missing `--ticker` in headless mode: Command will fail with clear error message
- Invalid analyst names: Command will list valid options
- Invalid date format: Must be YYYY-MM-DD format
- Missing API keys: Will fail during analysis (set environment variables)

## Environment Variables

Required for analysis:
```bash
export OPENAI_API_KEY=your_openai_key
export FINNHUB_API_KEY=your_finnhub_key
```

## Integration with Scripts

The headless mode is designed for:
- Automated trading systems
- Batch processing workflows
- CI/CD pipelines
- Scheduled analysis jobs
- API integrations

Return codes:
- 0: Success
- 1: Error (invalid arguments, missing keys, etc.)