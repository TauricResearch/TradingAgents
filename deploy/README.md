# Deploying the assistant

The assistant is an **always-on process**, not a website. The dashboard is
incidental; the scheduler is the product. Every hosting decision below follows
from that one fact.

## What can and cannot host this

| Option | Verdict | Why |
|---|---|---|
| **Oracle Cloud Always Free VM** | ✅ **use this** | A real VM: persistent disk, a long-running process, cron-accurate scheduling. Free with no expiry. |
| Cloudflare Workers / Pages | ❌ cannot host | Workers are request-scoped with a CPU ceiling. There is no persistent process to run APScheduler in, and Pyodide will not carry pandas + langgraph + the SQLAlchemy async stack. |
| Cloudflare D1 | ❌ not a drop-in | D1 speaks HTTP; SQLAlchemy + aiosqlite need the SQLite *file* protocol. Swapping it is a data-layer rewrite, not a config change. |
| **Cloudflare Tunnel** | ✅ **use this** | The genuinely useful Cloudflare piece: HTTPS to the VM with **zero inbound ports open**, plus Zero Trust auth in front of a dashboard that has none. |
| Your own Windows box + Tunnel | ✅ viable, zero setup | Free and already paid for. It stops when the machine sleeps — which is exactly how a month of observations gets lost. |

**Cloudflare fronts the app. Oracle runs it.**

## Measured footprint

Taken from the running app, not estimated:

| Resource | Measured |
|---|---|
| RAM, steady state | **~336 MB** |
| `assistant.db` | 0.34 MB, growing **~3 MB/year** |
| `~/.tradingagents` total | 26 MB |
| Cold start | ~35s (pandas + langgraph imports) |

It fits the 1 GB AMD micro. Prefer an **Ampere A1** shape if capacity allows, so
a backtest can run without competing with the scheduler for memory.

## Runbook

### 1. Create the VM (one time)

- Shape: `VM.Standard.A1.Flex` (Arm), **2 OCPU / 12 GB — not 4/24**. Oracle
  halved the Always Free Ampere allowance in June 2026 and stops instances that
  exceed it. If you already own a larger A1, resize it now; it costs nothing.
  Fall back to `VM.Standard.E2.1.Micro` (AMD, 1 GB) if you hit *"Out of host
  capacity"* — Ampere is frequently exhausted in popular regions, and that error
  means Oracle has no stock, not that you misconfigured something.
- Image: **Ubuntu 24.04, aarch64** — ships Python 3.12, so no deadsnakes needed.
- Boot volume: 50 GB (the venv is 1–2 GB; the default is plenty).
- Save the SSH private key at creation. It is not retrievable afterwards.
- **Do not add an ingress rule.** The default (SSH only) is correct — the app is
  reached through the tunnel, not through an open port.

### 2. Prepare the OS (one time)

```bash
sudo apt update
# Ubuntu 24.04 already ships Python 3.12 as `python3` — do NOT add deadsnakes.
python3 --version                       # expect 3.12.x
sudo apt install -y python3-venv python3-pip git sqlite3

# Swap. Resolving pandas + langchain + langgraph at once spikes well past idle,
# and pip gets OOM-killed on the 1 GB AMD shape without it.
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### 3. Install the app (one time)

**Use `venv` on the server, not conda** — even if you use conda locally. Conda
adds a ~400 MB installer and its own resolver for zero benefit here: every
dependency is a plain PyPI wheel, and the systemd unit points at a fixed
interpreter path. `venv` keeps that path stable and obvious.

```bash
git clone <your-fork> ~/TradingAgents && cd ~/TradingAgents
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e ".[dev,assistant]"
```

> Private fork? Either use a deploy key (`ssh-keygen` on the VM, add the public
> key to the repo's Deploy Keys) or clone over HTTPS with a personal access
> token. A plain `git clone` of a private repo will hang on a password prompt.

Copy your `.env` across — **never commit it**:

```bash
# from your Windows machine, in the repo directory
scp .env ubuntu@<vm-ip>:~/TradingAgents/.env
ssh ubuntu@<vm-ip> 'chmod 600 ~/TradingAgents/.env'
```

### 3b. Bring your existing history across (one time) — DO NOT SKIP

The app creates a **fresh, empty** database on first run. Deploy without this
step and you silently restart the experiment from zero: the July–August
paper-trading history, all six seeded books, the signal record, and the equity
snapshots that the whole scoreboard is computed from.

Stop the local app first — copying a live SQLite file can capture a torn page.

```bash
# on Windows, with the local app STOPPED
sqlite3 "$HOME/.tradingagents/assistant.db" ".backup 'assistant-migrate.db'"
scp assistant-migrate.db ubuntu@<vm-ip>:/tmp/

# on the VM, BEFORE the first service start
mkdir -p ~/.tradingagents
mv /tmp/assistant-migrate.db ~/.tradingagents/assistant.db
sqlite3 ~/.tradingagents/assistant.db "pragma integrity_check;"   # expect: ok
sqlite3 ~/.tradingagents/assistant.db \
  "select label, round(cash,2) from paper_account;"               # expect 6 books
```

Optionally bring the markdown reports too — they are only read for display, so
losing them costs history, not correctness:

```bash
scp -r "$HOME/.tradingagents/logs" ubuntu@<vm-ip>:~/.tradingagents/
```

### 4. Run it as a service (one time)

```bash
sudo cp ~/TradingAgents/deploy/tradingagents.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tradingagents
systemctl status tradingagents
journalctl -u tradingagents -f
```

The unit binds to **127.0.0.1 only**. Nothing is reachable from the internet
yet, which is deliberate.

**Verify it actually works before moving on** — a service that starts and then
errors on every run looks identical to a healthy one from `systemctl status`:

```bash
# 1. process is up and listening
curl -s localhost:8000/health | python3 -m json.tool | head -20

# 2. all six books survived the migration, with their history
curl -s localhost:8000/portfolio \
  | python3 -c "import json,sys; d=json.load(sys.stdin); \
    [print(f\"{b['label']:<12} \${b['equity_usd'] or 0:>10,.2f}  {b['return_pct']}\") for b in d['books']]"

# 3. the LLM is reachable from the VM (this is the step that catches a
#    missing or mis-copied .env — the app starts fine without API keys)
cd ~/TradingAgents && .venv/bin/python scripts/smoke_structured_output.py google

# 4. scheduler registered its jobs
journalctl -u tradingagents --since "5 min ago" | grep -i "scheduled slot"
```

**How to read step 2.** The four `core_*` books legitimately start at exactly
$10,000 — they are new arms and hold nothing until the first sweep runs. The
tell is the two older books:

| Book | Fresh DB (migration skipped) | Migrated correctly |
|---|---|---|
| `strategic` | $10,000.00 | your real equity (**not** a round number) |
| `tactical` | $10,000.00 | your real equity |
| `core_*` ×4 | $10,000.00 | $10,000.00 — **expected either way** |

If `strategic` and `tactical` both read exactly $10,000.00, you are looking at a
fresh database: stop the service, redo step 3b, start again. A faster check that
does not depend on reading equity:

```bash
sqlite3 ~/.tradingagents/assistant.db \
  "select (select count(*) from signals) as signals,
          (select count(*) from trades) as trades,
          (select count(*) from equity_snapshots) as snapshots;"
```

All three zero means a fresh database.

### 5. Expose it via Cloudflare Tunnel (one time)

```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64 \
  -o cloudflared && chmod +x cloudflared && sudo mv cloudflared /usr/local/bin/
cloudflared tunnel login
cloudflared tunnel create tradingagents
cloudflared tunnel route dns tradingagents assistant.<your-domain>
sudo cloudflared service install   # survives reboot
```

**Then put Cloudflare Access in front of it.** The dashboard has **no
authentication** and displays your portfolio and can trigger LLM runs. A tunnel
without Access is a public URL. In Zero Trust → Access → Applications, add the
hostname and require a one-time PIN to your email.

*Simpler alternative:* Tailscale. Install on the VM and your laptop, reach the
dashboard over the private network, skip domains and Access entirely.

### 6. Liveness (one time, and the step people skip)

A dead process cannot tell you it died. Create a free check at
[healthchecks.io](https://healthchecks.io), then:

```bash
echo 'ASSISTANT_HEARTBEAT_URL=https://hc-ping.com/<your-uuid>' >> ~/TradingAgents/.env
sudo systemctl restart tradingagents
```

The scheduler pings every 5 minutes; the monitor emails you when pings **stop**.
Set the check's period to 15 minutes with a 5-minute grace.

### 7. Backups (one time)

```bash
chmod +x ~/TradingAgents/deploy/backup-db.sh
crontab -e
# 17 4 * * * /home/ubuntu/TradingAgents/deploy/backup-db.sh >> /home/ubuntu/backup.log 2>&1
```

Uses `sqlite3 .backup`, not `cp` — the monitor writes every 60 seconds and a
plain copy can capture a torn page that only fails when you try to restore it.

## What trades automatically, per book

Verified end-to-end against a copy of the live database — every path below was
executed, not inferred.

| Book | Buys | Sells | Core vehicle |
|---|---|---|---|
| `strategic` | LLM Buy/Overweight → `execute_signal` | LLM Sell/Underweight, stop-loss, price target | SPY |
| `tactical` | rule `signal==1` → `_tactical_buy` | rule `signal==0`, trailing stop | **VOO** |
| `core_spy` | sweep only | never (buy-and-hold control) | SPY |
| `core_trend` | sweep only | when SPY closes below its 200-day average | SPY |
| `core_2x` | sweep only | never | SSO |
| `core_jepi` | sweep only | never | JEPI |

**The core is protected from all three sell paths** — the stop ratchet skips it,
`_paper_sell` refuses it, and the rule's `held` set excludes it. Only
`ensure_cash` may sell core, and only to fund a satellite entry.

**Why tactical parks in VOO, not SPY.** Its rule trades SPY as a position. If
the core used SPY too, the sweep would refuse to add it (a conviction position
already owns the symbol) and the book would sit ~48% in idle cash — the exact
drag the core exists to remove. VOO tracks the same index, so exposure is
identical and the collision is impossible.

## Waiting for Ampere capacity

Oracle publishes no capacity signal, has no status page for it, and offers no
alerting. The only way to know a slot has opened is to attempt a launch and see
whether it errors — reports range from hours to several weeks.

The assistant does this itself: `app/services/oci_capacity.py` runs as a
scheduler job every 5 minutes whenever `OCI_COMPARTMENT_ID` and `OCI_SUBNET_ID`
are set in `.env`. No separate process to babysit — it starts and stops with
`uvicorn app.main:app`.

```bash
# in .env — get both from OCI Cloud Shell:
#   echo $OCI_TENANCY
#   oci network subnet list -c $OCI_TENANCY --query 'data[].{name:"display-name",id:id}' --output table
OCI_COMPARTMENT_ID=ocid1.tenancy.oc1..
OCI_SUBNET_ID=ocid1.subnet.oc1...
```

It requires the OCI CLI installed and configured (`oci setup config` — answer
**N/A** to the passphrase prompt, it does not accept an empty Enter, then upload
the generated public key under Identity → My profile → API keys).

**It stays quiet.** At 5-minute intervals that is ~288 checks a day; reporting
each one would bury the single message that matters. So: nothing while
unavailable, and one sentence when it lands —

> ✅ Oracle Ampere capacity found — your VM is now running in AD-2.

It tries every availability domain each pass, since capacity is per-AD. Oracle's
`TooManyRequests` throttling is treated as transient and retried. A permanent
error — a bad OCID, a zero service limit, an auth failure — sends one short
notice and then disables the job, because repeating a request that cannot
succeed just fills your phone with the same stack trace.

## Traps worth knowing before you start

| Trap | Why it bites |
|---|---|
| **`--workers >1`** | APScheduler runs *in-process*. A second worker double-fires every job — duplicate paper trades, duplicate alerts, double LLM spend. Exactly one worker, always. |
| **The `Dockerfile`** | Its `ENTRYPOINT` launches the analysis **CLI**, not the assistant service. `docker run` boots the wrong process with nothing listening. Use systemd + venv. |
| **Restart ≠ sleep** | `CLAUDE.md` says a missed slot fires within the hour — that's true for laptop *sleep*, where the process stays resident. After a **restart** the job store is rebuilt empty, so jobs missed while the service was down are **not** backfilled. Restart outside market hours when you can. |
| **A tunnel without Access** | is just a public URL. The dashboard has no auth and 14 mutating endpoints, one of which spends LLM quota. Add the Access policy in the same sitting. |
| **yfinance cache growth** | Refetches write new dated files rather than overwriting. `find ~/.tradingagents/cache -mtime +90 -delete` quarterly. |

### Updating (repeated)

```bash
cd ~/TradingAgents && git pull && .venv/bin/pip install -e ".[dev,assistant]"
sudo systemctl restart tradingagents
journalctl -u tradingagents --since "2 min ago" | tail -20   # confirm clean start
```

State lives in `~/.tradingagents/`, so it survives updates untouched. Prefer
restarting **outside market hours**: APScheduler rebuilds its job store empty on
start, so anything scheduled during the restart window is skipped, not backfilled.

## Failure modes

| What breaks | How you find out | Recovery |
|---|---|---|
| Process crashes | Heartbeat stops → email | systemd restarts it automatically |
| VM rebooted | Heartbeat gap | `systemctl enable` already handles it |
| **Oracle reclaims an idle instance** | Heartbeat stops | Recreate the VM; this is why backups exist |
| Gemini quota exhausted | Runs error in History | NVIDIA fallback takes over automatically |
| Tunnel down | Dashboard unreachable, scheduler unaffected | `systemctl restart cloudflared` |
| Disk full | Service fails to write | Reports grow slowly; `du -sh ~/.tradingagents` |

**Oracle idle reclamation is the real risk.** Oracle reclaims Always Free
compute that looks idle, and this app is I/O-bound and mostly asleep — close to
the profile they target. The heartbeat is what turns that from "discovered
weeks later" into "emailed within 15 minutes."

## Cost

Every component is free with no expiry: Oracle Always Free, Cloudflare Tunnel
and Access (free tier), healthchecks.io (free tier), Gemini Flash (free tier),
NVIDIA NIM (free credits).

The only way this starts costing money is if **you** attach billing to the
Google Cloud project — the same API key then bills at paid rates instead of
returning 429. Don't add a payment method and the ceiling stays a rate limit.
