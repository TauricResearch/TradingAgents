# Run Evidence: f4edc7b4-95f8-448b-90dc-d9e0f98919e7

Generated: 2026-04-30 (UTC)

## Scope

This document captures auditable evidence for a real TradingAgents shadow run
executed through the service API and worker pipeline.

## Run Identity

- `run_id`: `f4edc7b4-95f8-448b-90dc-d9e0f98919e7`
- `ticker`: `NVDA`
- `trade_date`: `2026-01-21`
- `selected_analysts`: `["market","news"]`
- `status`: `succeeded`
- `created_at`: `2026-04-30T10:27:51.763796Z`
- `updated_at`: `2026-04-30T10:30:17.562917Z`

## API Receipts

### GET /v1/shadow-runs/{run_id}

```json
{
  "run_id": "f4edc7b4-95f8-448b-90dc-d9e0f98919e7",
  "ticker": "NVDA",
  "trade_date": "2026-01-21",
  "selected_analysts": ["market", "news"],
  "status": "succeeded",
  "created_at": "2026-04-30T10:27:51.763796Z",
  "updated_at": "2026-04-30T10:30:17.562917Z",
  "provider": null,
  "model_name": null,
  "error_message": null
}
```

### GET /v1/shadow-runs/{run_id}/events

```json
{
  "run_id": "f4edc7b4-95f8-448b-90dc-d9e0f98919e7",
  "events": [
    {
      "sequence": 1,
      "event_type": "running",
      "timestamp": "2026-04-30T10:27:52.590275Z",
      "payload": {"worker_id": "3d209440ddf5"}
    },
    {
      "sequence": 2,
      "event_type": "succeeded",
      "timestamp": "2026-04-30T10:30:17.592663Z"
    }
  ]
}
```

### GET /v1/shadow-runs/{run_id}/decision

- `final_rating`: `Hold`
- `provider`: `ollama`
- `deep_model`: `llama3.2:latest`
- `quick_model`: `llama3.2:latest`
- `state_log_dir`: `/home/appuser/app/output/logs/NVDA/TradingAgentsStrategy_logs`
- `memory_log_path`: `/home/appuser/app/output/memory/trading_memory.md`

Decision markdown was returned in full by the endpoint and persisted to DB.

### GET /v1/shadow-runs/{run_id}/artifacts

Manifest entries (sha256 and size):

1. `memory_log`
   - `uri`: `file:///home/appuser/app/output/memory/trading_memory.md`
   - `sha256`: `a463ca6a1ba27a74095b40620448942d94ea65af9e625423e8d13c861714442f`
   - `bytes`: `5800`
   - `content_type`: `text/markdown`
2. `state_log`
   - `uri`: `file:///home/appuser/app/output/logs/NVDA/TradingAgentsStrategy_logs/full_states_log_2026-01-15.json`
   - `sha256`: `559c4c88164ef9a68a3532d5555d5935b724375b267b53aec06d0f68a749e036`
   - `bytes`: `42983`
   - `content_type`: `application/json`
3. `state_log`
   - `uri`: `file:///home/appuser/app/output/logs/NVDA/TradingAgentsStrategy_logs/full_states_log_2026-01-21.json`
   - `sha256`: `151bced1e62d8f90b3e99fe4785ec915d845c61cca56158297de39f4b40bc7af`
   - `bytes`: `45811`
   - `content_type`: `application/json`

## DB Cross-Checks

Postgres rows confirm API-reported run status and timeline:

- `shadow_runs`:
  - `id=f4edc7b4-95f8-448b-90dc-d9e0f98919e7`
  - `ticker=NVDA`
  - `trade_date=2026-01-21`
  - `status=succeeded`
  - `created_at=2026-04-30 10:27:51.763796+00`
  - `updated_at=2026-04-30 10:30:17.562917+00`
- `shadow_run_events` ordered by `sequence`:
  - `1 running  2026-04-30 10:27:52.590275+00`
  - `2 succeeded 2026-04-30 10:30:17.592663+00`

## Worker Runtime Evidence

Worker log lines for this run include structured-output fallback behavior:

- `Research Manager: structured-output invocation failed (...) retrying once as free text`
- `Portfolio Manager: structured-output invocation failed (...) retrying once as free text`

This indicates adaptive fallback in agent-stage generation, while overall run
still completed with `succeeded`.

## Conclusion

Evidence supports that this was a real end-to-end run (not seeded):

- queued -> running -> succeeded lifecycle persisted,
- real provider/model metadata (`ollama`, `llama3.2:latest`) captured,
- decision + artifacts emitted with hashes and byte counts,
- DB and API views are consistent.
