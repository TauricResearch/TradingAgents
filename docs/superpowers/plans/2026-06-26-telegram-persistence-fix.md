# Telegram Notifier Persistence Fix — Implementation Plan

> **For agentic workers:** Each task is a single file edit with verification. No tests exist for the notifier subsystem, so verification is manual (curl + restart).

**Goal:** Ensure Telegram notification parameters persist between sessions and are visible to all code paths immediately after saving.

**Architecture:** Fix gaps in the existing dual-write persistence (`.env` + `notifier.json`) by syncing `os.environ` on write and adding env-var-name bridges in all read paths.

**Tech Stack:** Python 3.12+, FastAPI, python-telegram-bot v21+

**Branch:** `telegram-persistence-fix` (created from `main-with-dashboard`)

---

### Task 1: Sync `os.environ` in `write_notifier_config()`

**Files:**
- Modify: `web/server/storage.py:660-681`

After writing to `.env` and `notifier.json`, also sync the values to `os.environ` so code paths that read directly from environment variables see the saved values immediately (no restart needed).

- [ ] **Edit `storage.py` — add os.environ sync**

In `write_notifier_config()`, add `os.environ` updates after the `_write_env()` call:

<｜｜DSML｜｜tool_calls>
<｜｜DSML｜｜invoke name="edit">
<｜｜DSML｜｜parameter name="filePath" string="true">C:\Users\Ido\Desktop\Projects\agents\TradingAgents\web\server\storage.py