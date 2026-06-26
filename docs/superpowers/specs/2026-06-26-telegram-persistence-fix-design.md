# Telegram Notifier Persistence Fix

## Problem

Telegram notification parameters (bot token, chat ID, enabled flag) don't reliably persist between application sessions. Three root causes:

1. **`write_notifier_config()` never updates `os.environ`** — After saving via the dashboard UI, the `.env` file is updated but `os.environ` is not. Code paths that read directly from environment variables (`notifier.py`, `notifier_bot.py`, fallbacks in `app.py`) don't see the new values until the process restarts.

2. **Env var naming mismatch** — `storage.py` writes `TRADINGAGENTS_TELEGRAM_BOT_TOKEN` / `TRADINGAGENTS_TELEGRAM_CHAT_ID` to `.env`, but `notifier.py` and `notifier_bot.py` only read the legacy `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` names from `os.environ`. No bridge exists between the two naming conventions.

3. **`app.py` fallbacks have the same blind spot** — `_get_notifier()` and `test_notifier()` fall back to `os.environ.get("TELEGRAM_BOT_TOKEN")` without checking the `TRADINGAGENTS_TELEGRAM_*` variants.

## Design

### Files Changed

| File | Change |
|------|--------|
| `web/server/storage.py` | After writing to `.env`, sync values to `os.environ` |
| `web/server/notifier.py` | Check `TRADINGAGENTS_TELEGRAM_*` before legacy `TELEGRAM_*` in env |
| `web/server/notifier_bot.py` | Check `TRADINGAGENTS_TELEGRAM_CHAT_ID` as fallback for access control |
| `web/server/app.py` | Add `TRADINGAGENTS_TELEGRAM_*` fallbacks in `_get_notifier()` and `test_notifier()` |

### Storage Layer (`storage.py`)

In `write_notifier_config()`, after the existing `.env` file write, add:

```python
os.environ[_NOTIFIER_ENV_TOKEN] = token  # (if not None)
os.environ[_NOTIFIER_ENV_CHAT_ID] = str(chat_id)  # (if not None)
os.environ[_NOTIFIER_ENV_ENABLED] = "1" if enabled else "0"
```

### Notifier Library (`notifier.py`)

In `TelegramNotifier.__init__()`, change fallback order:

```python
self._token = token or os.environ.get("TRADINGAGENTS_TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
self._chat_id = str(chat_id) if chat_id else (os.environ.get("TRADINGAGENTS_TELEGRAM_CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID", ""))
```

### Interactive Bot (`notifier_bot.py`)

In `create_telegram_application()`, change access-control lookup:

```python
allowed = os.getenv("TRADINGAGENTS_TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID")
```

### Dashboard API (`app.py`)

In `_get_notifier()` and `test_notifier()`, expand fallbacks to check both naming conventions.

## Testing

No existing tests for the notifier subsystem. Manual verification:
1. Save Telegram config via dashboard UI
2. Reload page — config should still be populated
3. Send test message — should succeed
4. Restart the server — config should persist and test should still work
