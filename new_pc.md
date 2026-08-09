# Moving TradingAgents to another PC

Follow this end to end and the assistant resumes on the new machine with the **same
paper-trading history, same watchlist, same schedule, same open positions** — not a
fresh start.

> **The one thing that goes wrong:** point the app at a missing database and SQLAlchemy
> silently creates an empty one. The dashboard renders, the scheduler starts, health
> says `ok` — and a month of history is gone. Phase 7 exists to catch exactly that.

Related docs: [`README.md`](README.md) (framework), [`app/README.md`](app/README.md)
(assistant service), [`deploy/README.md`](deploy/README.md) (Oracle Cloud VM — a
*different* target from this guide).

---

## Prompt for Claude on the new machine

Open Claude Code **inside the repo** (`cd` to the folder holding `pyproject.toml`, then
run `claude`) so it picks up `CLAUDE.md` automatically, and paste this:

```text
Set this machine up to resume the TradingAgents assistant. Read new_pc.md and follow it
from Phase 2 onward — Phase 1 was already completed on the old PC, so data/ is populated
and .env already has the path overrides.

What you need to know before you start:

- This is a LIVE paper-trading experiment being resumed, not a fresh install. data/assistant.db
  holds about a month of history — six books, real balances, open positions. It must survive.
- The failure mode to defend against is silent: if the app cannot find data/assistant.db it
  creates an empty one, and the dashboard renders, the scheduler starts, and /health returns ok
  while the history is gone. Six books at exactly $10,000 with zero trades means it happened.
- Run `python scripts/verify_migration.py` BEFORE starting uvicorn and again after. It must
  report data\assistant.db (not a path under ~/.tradingagents), 8 populated tables, and the
  strategic and tactical books holding cash other than exactly 10,000.00.
- uvicorn must be launched from the repo root — .env uses relative paths so the drive works
  under any letter, which also means the wrong working directory silently opens the wrong DB.
- The drive letter WILL differ from the old machine. Never hardcode it.

Do the work, then report back: the drive letter you used, whether ~/.oci/config's key_file
line needed correcting for this username, the verify_migration output, and the /health job
count (expect 12, or 13 if ASSISTANT_HEARTBEAT_URL is set).

Ask me before installing anything system-wide or modifying .env. Do not run
scripts/migrate_to_repo.py on this machine — it copies FROM ~/.tradingagents INTO data/ and
would overwrite the history I just brought over with whatever empty state exists here.
```

That last instruction matters: `migrate_to_repo.py` is a one-way old-PC→drive tool. On a
fresh machine `~/.tradingagents` either doesn't exist (the script exits safely) or holds an
unrelated empty database (it would overwrite your real one).

---

## 0. What travels, and what does not

| What | Lives at | On the drive today? |
|---|---|---|
| Code / repo | `<DRIVE>:\Repos\Finance\TradingAgents` | yes |
| `.env` — all API keys, Telegram, OCI OCIDs | repo root | yes (gitignored, but physically present) |
| **`assistant.db`** — every book, trade, signal, snapshot | `~/.tradingagents/` | **no** |
| Reports (~811 files, 19.7 MB) | `~/.tradingagents/logs/` | **no** |
| Reflection memory (feeds self-learning) | `~/.tradingagents/memory/` | **no** |
| Vendor cache (~59 files, 6 MB) | `~/.tradingagents/cache/` | **no** |
| `baseline_snapshot_2026-07-03.json` | `~/.tradingagents/` | **no** |
| Python environment (31,172 files, 488 MB) | `~/anaconda3/envs/tradingagents` | **no** — rebuilt, never copied |
| OCI API key + config | `~/.oci/` | **no** |
| SSH keypair for the Oracle VM | `~/.ssh/oci_ta`, `oci_ta.pub` | **no** |

Phase 1 moves rows 3–8 onto the drive permanently, so this is a one-time cost. After
that, every future move is just "unplug, plug in, start".

**Drive letter does not matter.** All paths below are relative to the repo root, so the
drive can mount as `O:`, `E:`, or `/media/usb` and nothing breaks — *provided you always
start the app from the repo root*. That single requirement is what makes it portable.

---

## Phase 1 — On the OLD PC, before unplugging

### 1.1 Stop the service

Ctrl-C the `uvicorn` window. Confirm it is actually down:

```bash
curl -s http://127.0.0.1:8000/health || echo "stopped"
```

Do not skip this. The database uses `journal_mode=delete` (no `-wal`/`-shm` sidecars), so
a copy taken while stopped is atomic and safe — but a copy taken *while running* can
capture a half-written page.

### 1.2 Take a fingerprint

```bash
cd /o/Repos/Finance/TradingAgents
python scripts/verify_migration.py --json > before_move.json
python scripts/verify_migration.py          # eyeball it too
```

Keep `before_move.json`. Phase 7 diffs against it.

### 1.3 Move runtime data into the repo

```bash
cd /o/Repos/Finance/TradingAgents
mkdir -p data
cp -r "$USERPROFILE/.tradingagents/." data/
ls data/          # expect: assistant.db  baseline_snapshot_2026-07-03.json  cache  logs  memory
```

`data/` is already in `.gitignore`, so none of this can be committed by accident.

### 1.4 Copy the credentials that live outside the repo

Only needed if you want the **Oracle capacity watch** to keep working. Skip if you don't
care about it — the app runs fine without, it just self-disables.

```bash
mkdir -p data/secrets/oci data/secrets/ssh
cp "$USERPROFILE/.oci/config"                 data/secrets/oci/
cp "$USERPROFILE/.oci/oci_api_key.pem"        data/secrets/oci/
cp "$USERPROFILE/.oci/oci_api_key_public.pem" data/secrets/oci/
cp "$USERPROFILE/.ssh/oci_ta"                 data/secrets/ssh/
cp "$USERPROFILE/.ssh/oci_ta.pub"             data/secrets/ssh/
```

> **Security — read this once.** The drive is **exFAT, which has no file permissions.**
> Anyone who plugs it into any machine can read `data/secrets/oci_api_key.pem`,
> `data/secrets/ssh/oci_ta`, and every API key in `.env`. That is already true of `.env`
> today. If the drive leaving your possession is a realistic risk, either skip 1.4 and
> regenerate keys on the new PC (Phase 6, Option B), or put the drive behind BitLocker To
> Go. Treat losing this drive as "rotate every credential".

### 1.5 Add the four path overrides to `.env`

Append these to the repo's `.env`. Order matters — do this **after** 1.3, so the app never
starts against an empty `data/`.

```
ASSISTANT_DB_URL=sqlite+aiosqlite:///data/assistant.db
TRADINGAGENTS_RESULTS_DIR=data/logs
TRADINGAGENTS_CACHE_DIR=data/cache
TRADINGAGENTS_MEMORY_LOG_PATH=data/memory/trading_memory.md
```

The three slashes in the SQLite URL mean **relative path** — that is what makes it
drive-letter independent. Four slashes would make it absolute and defeat the purpose.

> **Windows gotcha:** never write `.env` with PowerShell's `-Encoding utf8` — PS 5.1 adds
> a BOM that corrupts the first key. Use Git Bash, VS Code, or
> `[IO.File]::WriteAllText()`. Appending in Git Bash is safe:
> ```bash
> printf '%s\n' \
>   'ASSISTANT_DB_URL=sqlite+aiosqlite:///data/assistant.db' \
>   'TRADINGAGENTS_RESULTS_DIR=data/logs' \
>   'TRADINGAGENTS_CACHE_DIR=data/cache' \
>   'TRADINGAGENTS_MEMORY_LOG_PATH=data/memory/trading_memory.md' \
>   >> .env
> ```

If you copied credentials in 1.4, add this one too:

```
OCI_SSH_PUBLIC_KEY_PATH=data/secrets/ssh/oci_ta.pub
```

### 1.6 Prove it on the old PC first

Debug on the machine that already works, not the one that might not.

```bash
cd /o/Repos/Finance/TradingAgents
python scripts/verify_migration.py
```

The `database :` line must now read `data\assistant.db`, **not** the one under
`C:\Users\...`. Row counts must match `before_move.json`. Then:

```bash
uvicorn app.main:app
curl -s http://127.0.0.1:8000/health
```

Expect `scheduler_running: true` and **12 jobs**. Open the dashboard and confirm your six
books show real balances. Then Ctrl-C.

### 1.7 Eject properly

Windows → Safely Remove Hardware. Yanking a USB drive with SQLite open is one of the few
ways to genuinely corrupt this database.

The old `~/.tradingagents` folder is now a backup. **Leave it there** until the new PC is
verified.

---

## Phase 2 — New PC prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | **3.12** | project needs ≥3.10; the current env is 3.12.13 |
| Conda *or* venv | any | conda matches the existing setup |
| Git | any | optional — only for future `git pull` |
| Internet | — | market data + LLM APIs are all remote |

Plug in the drive and note its letter. Everything below assumes you `cd` to the repo root
first.

Do **not** copy `~/anaconda3/envs/tradingagents`. Conda environments bake absolute paths
into every script; a copied env breaks the moment the path differs. Rebuilding takes a few
minutes and is the reliable path.

---

## Phase 3 — Python environment

```bash
conda create -n tradingagents python=3.12 -y
conda activate tradingagents

cd /e/Repos/Finance/TradingAgents      # adjust to the new drive letter
pip install -e ".[dev,assistant]"
```

`[assistant]` pulls FastAPI, uvicorn, APScheduler, SQLAlchemy async, aiosqlite, httpx,
aiosmtplib, pydantic-settings. `[dev]` pulls ruff and pytest. Both are needed.

Plain venv works identically if you prefer:

```bash
python -m venv .venv && source .venv/Scripts/activate && pip install -e ".[dev,assistant]"
```

Sanity check:

```bash
python -c "import fastapi, apscheduler, sqlalchemy, aiosqlite; print('deps ok')"
pytest -q
```

---

## Phase 4 — Restore the data

Nothing to do — it is already in `data/` on the drive, and `.env` already points at it.

If you skipped Phase 1 and only have a copy of the old `~/.tradingagents`, place it at
`<repo>/data/` now and add the four `.env` lines from step 1.5.

**No database migration is needed.** The schema travels inside the `.db` file, including
the widened `account_type` column that the four core books require.

---

## Phase 5 — Verify `.env`

`.env` came along on the drive, so all keys are present. Confirm it survived and contains
no absolute paths:

```bash
grep -nE '[A-Za-z]:[\\/]|Users' .env || echo "no absolute paths — portable"
```

Reference for what should be in there (values omitted):

| Group | Keys |
|---|---|
| LLM (assistant) | `ASSISTANT_LLM_PROVIDER`, `ASSISTANT_DEEP_MODEL`, `ASSISTANT_QUICK_MODEL` |
| LLM (framework) | `TRADINGAGENTS_LLM_PROVIDER`, `TRADINGAGENTS_DEEP_THINK_LLM`, `TRADINGAGENTS_QUICK_THINK_LLM`, `TRADINGAGENTS_LLM_FALLBACK_PROVIDER`, `TRADINGAGENTS_LLM_FALLBACK_MODEL` |
| API keys | `GOOGLE_API_KEY`, `NVIDIA_API_KEY`, `OPENROUTER_API_KEY`, `WORKERS_AI`, `HUGGINGFACE_API`, `ALPHA_VANTAGE_API_KEY`, `FRED_API_KEY` |
| Alerts | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `EMAIL_FROM`, `EMAIL_TO` |
| Budgets | `ASSISTANT_DAILY_RUN_BUDGET`, `ASSISTANT_WEEKLY_RUN_BUDGET`, `SCREENER_MAX_ADDS`, `SCREENER_SATELLITE_CAP` |
| Tactical book | `TACTICAL_RULE`, `TACTICAL_SIZE_PCT`, `TACTICAL_MAX_POSITIONS`, `TACTICAL_DAILY_LOSS_CAP_PCT` |
| Oracle watch | `OCI_COMPARTMENT_ID`, `OCI_SUBNET_ID` (+ optional `OCI_SHAPE`, `OCI_OCPUS`, `OCI_MEMORY_GB`, `OCI_DISPLAY_NAME`, `OCI_SSH_PUBLIC_KEY_PATH`) |
| Paths (added in 1.5) | `ASSISTANT_DB_URL`, `TRADINGAGENTS_RESULTS_DIR`, `TRADINGAGENTS_CACHE_DIR`, `TRADINGAGENTS_MEMORY_LOG_PATH` |

Two housekeeping notes:

- `COMPARTMENT_ID` and `SUBNET_ID` (no `OCI_` prefix) are unused leftovers — the watcher
  reads only the `OCI_`-prefixed pair. Safe to delete.
- `ASSISTANT_HEARTBEAT_URL` is unset, so the dead-man's-switch job is not scheduled. That
  is why health shows 12 jobs, not 13. Set it to a healthchecks.io ping URL if you want to
  be told when the machine goes down.

---

## Phase 6 — Oracle Cloud (optional)

Skip entirely if you don't want the Ampere capacity watch. Without it the app logs one
line and disables the job — no crash, no Telegram spam.

### 6.1 Install the OCI CLI

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command `
  "iex ((New-Object System.Net.WebClient).DownloadString('https://raw.githubusercontent.com/oracle/oci-cli/master/scripts/install/install.ps1'))"
```

Accept the defaults. It installs to `%USERPROFILE%\bin\oci.exe`.

> **PATH note:** the watcher resolves the binary via `shutil.which("oci")` and *falls back
> to `~/bin/oci.exe`* — so it works even if PATH hasn't refreshed. That fallback exists
> because this exact problem (`WinError 2`) bit us on this machine.

### 6.2 Option A — reuse the existing key (fast)

```bash
mkdir -p "$USERPROFILE/.oci" "$USERPROFILE/.ssh"
cp data/secrets/oci/* "$USERPROFILE/.oci/"
cp data/secrets/ssh/oci_ta* "$USERPROFILE/.ssh/"
```

**Then edit `~/.oci/config` and fix the `key_file` line** — it holds an absolute path from
the old PC and will not resolve if your username differs:

```ini
[DEFAULT]
user        = ocid1.user.oc1..…
fingerprint = …
key_file    = C:\Users\<NEW_USERNAME>\.oci\oci_api_key.pem   # <- must be updated
tenancy     = ocid1.tenancy.oc1..…
region      = us-chicago-1
```

Nothing else in that file is machine-specific. The API key stays valid — it is tied to
your Oracle user, not to a computer.

### 6.3 Option B — fresh credentials (if you skipped 1.4, or want rotation)

```bash
oci setup config
```

Answers it needs: config location (accept default), **user OCID**, **tenancy OCID**,
region `us-chicago-1`, then "generate a new API key pair" → yes.

> **Passphrase trap:** when it asks for a passphrase, type the literal characters `N/A`.
> Pressing Enter for "empty" puts the prompt in an infinite loop. This cost us 20 minutes.

Then upload the public key: Oracle Console → profile icon → **My profile** → **API keys**
→ **Add API key** → *Paste public key* → paste the contents of
`~/.oci/oci_api_key_public.pem`.

Generate the VM's SSH keypair too:

```bash
ssh-keygen -t rsa -b 4096 -f "$USERPROFILE/.ssh/oci_ta" -N ""
```

### 6.4 Verify

```bash
oci iam region list --output table
```

Any successful listing means auth works. The watch then runs every 5 minutes from inside
the app and stays **silent** until capacity appears — by design. One Telegram sentence on
launch, one notice if it hits a permanent error, nothing otherwise.

---

## Phase 7 — Start and prove it resumed

### 7.1 Fingerprint before starting

```bash
cd /e/Repos/Finance/TradingAgents
python scripts/verify_migration.py --json > after_move.json
python scripts/verify_migration.py
```

Compare against `before_move.json`:

```bash
diff before_move.json after_move.json && echo "IDENTICAL — history intact"
```

Only `database` (the path) may differ. **Any row count that dropped means the copy
failed — stop and re-copy `data/` before starting the app.**

Fingerprint as of 2026-08-08 (yours will be larger if the experiment kept running):

| Table | Rows |
|---|---|
| `paper_account` | 6 |
| `positions` | 8 |
| `trades` | 18 |
| `signals` | 64 |
| `equity_snapshots` | 48 (2026-07-07 → 2026-08-08) |
| `watchlist` | 25 |
| `schedule_slots` | 6 |
| `screener_results` | 416 |

Books: `strategic` $8,129.32 cash · `tactical` $4,890.65 · `core_spy` / `core_trend` /
`core_2x` / `core_jepi` $10,000.00 each (they start fully in cash and get swept into their
ETF on the first weekday close — $10,000 is correct, not a failed migration).

### 7.2 Start

```bash
uvicorn app.main:app
```

Must be launched **from the repo root** — the relative paths depend on it.

### 7.3 Health check

```bash
curl -s http://127.0.0.1:8000/health
```

| Field | Expected |
|---|---|
| `status` | `ok` |
| `scheduler_running` | `true` |
| `jobs` | 12 (13 with a heartbeat URL set) |
| `llm_provider` | `google` |
| `telegram_configured` | `true` |
| `email_configured` | `true` |
| `runs_this_week` | carried over, **not** 0 |

The 12 jobs: `stop_monitor`, `tactical`, `core_sweep`, `equity_snapshots`, `screener`,
`oci_capacity`, and `slot_1` … `slot_6`.

### 7.4 Eyeball the dashboard

`http://127.0.0.1:8000` — the six-book scoreboard should show your real balances and
history, not six identical $10,000 rows with no trades.

### 7.5 Only now, delete the old backup

Once 7.1–7.4 pass, `~/.tradingagents` on the old PC is safe to remove.

---

## Phase 8 — Keeping it running

The scheduler only fires while `uvicorn` is alive. Options:

| Approach | Trade-off |
|---|---|
| Leave the terminal open | simplest; dies on logout |
| Task Scheduler, "at logon", `-WindowStyle Hidden` | survives logout, no service overhead |
| [NSSM](https://nssm.cc) as a Windows service | starts before login; needs the drive mounted at boot |
| Oracle VM — see [`deploy/README.md`](deploy/README.md) | the real fix; blocked on Ampere capacity |

A slot missed while the machine sleeps still fires within the hour
(`misfire_grace_time`), so an overnight shutdown does not lose a day.

---

## Phase 9 — Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Dashboard shows six books at exactly $10,000 with no trades | App created a fresh DB — `data/assistant.db` not found | Check `.env` has `ASSISTANT_DB_URL`; confirm you launched from the repo root; run `verify_migration.py` |
| `verify_migration.py` prints a `C:\Users\...` path | The `.env` override is missing or unread | Re-add the four lines from 1.5; check for a BOM on the first key |
| First `.env` key ignored | PowerShell 5.1 wrote a UTF-8 BOM | Rewrite with Git Bash or `[IO.File]::WriteAllText` |
| `no such table: paper_account` | Empty/corrupt DB copy | Re-copy `data/assistant.db` with the service stopped |
| `WinError 2` from the capacity watch | `oci` not on PATH | Reinstall to `~/bin/oci.exe`, or open a new shell |
| Capacity watch: "could not list ADs" | stderr merged into stdout, corrupting JSON | Already fixed in `oci_capacity.py` — confirm you're on the current commit |
| One Telegram message then silence | Permanent OCI error → watch self-disabled | Check the server log, fix, restart |
| No Telegram at all | Token/chat ID lost | `curl "https://api.telegram.org/bot<TOKEN>/getMe"` |
| Scheduler starts, slots never fire | Machine asleep past the grace window | Expected; next slot picks up the stalest tickers |
| `ModuleNotFoundError: fastapi` | Installed without `[assistant]` | `pip install -e ".[dev,assistant]"` |
| App runs but reports go to the old location | `TRADINGAGENTS_RESULTS_DIR` missing | Add it; restart |
| SQLite "database is locked" | Two `uvicorn` instances | Kill all, start one |

---

## Appendix — complete inventory

Everything required, in one list. If all of these are true, the move is complete.

**On the drive (travels automatically):**

- [ ] `TradingAgents/` repo, current commit
- [ ] `.env` with all keys + the four path overrides
- [ ] `data/assistant.db`
- [ ] `data/baseline_snapshot_2026-07-03.json`
- [ ] `data/logs/` (reports)
- [ ] `data/memory/trading_memory.md` (reflection state)
- [ ] `data/cache/`
- [ ] `data/secrets/oci/{config,oci_api_key.pem,oci_api_key_public.pem}` *(optional)*
- [ ] `data/secrets/ssh/{oci_ta,oci_ta.pub}` *(optional)*

**Rebuilt on the new PC:**

- [ ] Python 3.12 + `pip install -e ".[dev,assistant]"`
- [ ] `~/.oci/` restored, `key_file` path corrected *(optional)*
- [ ] `~/.ssh/oci_ta*` restored *(optional)*
- [ ] OCI CLI installed *(optional)*

**Deliberately not moved:**

- Conda environment — always rebuilt
- `~/.tradingagents/` — superseded by `data/`; keep as backup until verified
