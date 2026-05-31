# skill

## heavy run

`run` always saves to `<reports_dir>/<TICKER>/<DATE>_<MODEL>_<TS>/` and skips
the in-terminal report. Asset type is auto-detected from the ticker; backend
URL uses the provider's canonical endpoint.

```shell
uv run python -m cli.main run \
  --ticker {ticker} --date {analysis-date} \
    --analysts market,social,news,fundamentals \
    --depth 10 --language English \
    --provider anthropic \
    --deep-model claude-opus-4-8 --quick-model claude-haiku-4-8 \
    --checkpoint --clear-checkpoints
```
