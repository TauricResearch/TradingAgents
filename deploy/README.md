# Deploying the assistant

The assistant is an **always-on process**, not a website. The dashboard is
incidental; the scheduler is the product. Every hosting decision below follows
from that one fact.

## What can and cannot host this

| Option | Verdict | Why |
|---|---|---|
| **Oracle Cloud Always Free VM** | ✅ **use this** | A real VM: persistent disk, a long-running process, cron-accurate scheduling. Free with no expiry. |
| Cloudflare Workers / Pages | ❌ cannot host | Workers are request-scoped with a CPU ceiling. There is no persistent process to run APScheduler in, and Pyodide will not carry pandas + langgraph + lightgbm. |
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
| Cold start | ~35s (pandas + langgraph + lightgbm imports) |

It fits the 1 GB AMD micro. Prefer an **Ampere A1** shape if capacity allows, so
a backtest can run without competing with the scheduler for memory.

## Runbook

### 1. Create the VM (one time)

- Shape: `VM.Standard.A1.Flex` (Arm), 1–2 OCPU / 6–12 GB. Fall back to
  `VM.Standard.E2.1.Micro` (AMD, 1 GB) if you hit *"Out of host capacity"* —
  Ampere is frequently exhausted in popular regions.
- Image: Ubuntu 24.04.
- Boot volume: 50 GB (the venv is 1–2 GB; the default is plenty).
- Save the SSH private key at creation. It is not retrievable afterwards.

### 2. Prepare the OS (one time)

```bash
sudo apt update && sudo apt install -y python3.12 python3.12-venv python3-pip git sqlite3
# The 1GB AMD shape needs swap or pip will OOM while building wheels.
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### 3. Install the app (one time)

```bash
git clone <your-fork> ~/TradingAgents && cd ~/TradingAgents
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev,assistant]"
```

Copy your `.env` across — **never commit it**:

```bash
scp .env ubuntu@<vm-ip>:~/TradingAgents/.env
ssh ubuntu@<vm-ip> 'chmod 600 ~/TradingAgents/.env'
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

### Updating (repeated)

```bash
cd ~/TradingAgents && git pull && .venv/bin/pip install -e ".[dev,assistant]"
sudo systemctl restart tradingagents
```

State lives in `~/.tradingagents/`, so it survives updates untouched.

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
