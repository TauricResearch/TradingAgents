# TradingAgents — Operations Reference

Living document. Paste relevant sections back to Claude when asking it
to deploy, upgrade, or troubleshoot the NAS deployment.

**Repo:** https://github.com/mrh335/TradingAgents
**Upstream:** https://github.com/TauricResearch/TradingAgents
**NAS deployment target:** `/volume1/docker/tradingagents/` on `192.168.2.34`

## Architecture (current)

Three services in one Docker compose stack:

| Service | Port | Purpose |
|---|---|---|
| `web` | 3000 | **Next.js frontend** — React UI, primary user interface |
| `api` | 8000 | **FastAPI backend** — REST + WebSockets; powers the web UI |
| `gui` | 8501 | **Streamlit (legacy)** — gated behind the `legacy` compose profile, only run when wanted as a fallback |

Browser → `http://192.168.2.34:3000/` (web) → talks to `api:8000` over the Docker bridge network. Persistent data (SQLite, archives, exports, memory log) bind-mounted from `/volume1/docker/tradingagents/data/` into all three. CLI runs from the `tradingagents` service still work and share the same data dir.

---

## Layout on the NAS

```
/volume1/docker/tradingagents/        ← git clone of the fork
├── docker-compose.yml
├── Dockerfile
├── .env                              ← API keys, chmod 600 (NEVER committed)
├── data/                             ← bind-mounted into the container
│   ├── gui_config.json
│   ├── gui.db                        ← SQLite (runs, notes, chats, briefs)
│   ├── logs/<TICKER>/...             ← run archives
│   ├── exports/<TICKER>/...          ← md / html / pdf / json
│   ├── memory/trading_memory.md
│   └── cache/                        ← yfinance + LangGraph
└── (everything else — committed source)
```

Everything that should survive a container rebuild lives under `data/`.
Everything else is pulled fresh from git.

---

## Credential pattern

Claude operates the NAS via scripts that source `scripts/nas/credentials.local`.
That file is git-ignored and Claude is instructed never to read its
contents. The scripts read it themselves and pass env vars through to
SSH commands.

**Setting it up (one time):**

```bash
cp scripts/nas/credentials.local.example scripts/nas/credentials.local
chmod 600 scripts/nas/credentials.local
# edit and fill in NAS_HOST, NAS_USER, plus EITHER NAS_SSH_KEY or NAS_PASSWORD
```

SSH-key auth is recommended:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/nas_tradingagents -N ""
# Paste the contents of ~/.ssh/nas_tradingagents.pub into DSM →
# Control Panel → Terminal & SNMP → Advanced → Authorized Keys.
```

Then set `NAS_SSH_KEY=~/.ssh/nas_tradingagents` in `credentials.local`.

**Verify the pattern works** before asking Claude to deploy:

```bash
scripts/nas/nas-cmd.sh 'echo hello from $HOSTNAME'
```

Should print `hello from <your-NAS-name>`.

---

## Scripts at a glance

| Script | When to use |
|---|---|
| `scripts/nas/deploy.sh` | First-time deploy on a fresh NAS |
| `scripts/nas/upgrade.sh` | Pull latest, rebuild, restart (the routine) |
| `scripts/nas/restart.sh` | Kick the container without rebuilding (for `.env` changes) |
| `scripts/nas/status.sh` | Check what's running, what version, how much data |
| `scripts/nas/logs.sh` | Tail container logs |
| `scripts/nas/rollback.sh <sha>` | Roll back to a prior commit if an upgrade goes sideways |
| `scripts/nas/nas-cmd.sh "<cmd>"` | Run any ad-hoc command on the NAS |

---

## How to ask Claude

Sample prompts that map directly to a script:

> "Deploy the latest version to the NAS."
→ Claude runs `scripts/nas/deploy.sh` (first time) or `scripts/nas/upgrade.sh` (subsequent).

> "Pull the latest and restart the GUI on the NAS."
→ `scripts/nas/upgrade.sh`.

> "Show me the status of the GUI container."
→ `scripts/nas/status.sh`.

> "Tail the logs."
→ `scripts/nas/logs.sh --tail=100`.

> "I just edited `.env` on the NAS — apply the change."
→ `scripts/nas/restart.sh`.

> "The last upgrade broke things. Roll back to the previous version."
→ `scripts/nas/rollback.sh previous`.

If you need something the scripts don't cover:

> "Run `<some-command>` on the NAS and show me the output."
→ Claude runs `scripts/nas/nas-cmd.sh "<some-command>"`.

---

## First deploy — the actual flow

1. Fill in `scripts/nas/credentials.local` (see above).
2. Create `.env` on the NAS from the template (Claude's `deploy.sh` will
   create it from `.env.example` and abort if it's still empty — you
   then fill in API keys via `nano /volume1/docker/tradingagents/.env`
   and rerun `deploy.sh`).
3. Tell Claude: *"Deploy to the NAS."*
4. When deploy.sh finishes, open `http://192.168.2.34:8501/` in a
   browser. Confirm:
   - Home page loads
   - Settings page shows API keys (env-set ones marked "env")
   - Run page kicks off a real analysis end-to-end

---

## Routine maintenance

After Claude makes changes to the code (which land on
`mrh335/TradingAgents@main` via `git push`), promote them to the NAS:

> *"Pull and rebuild on the NAS."*

That runs `upgrade.sh`, which:
- Pulls the latest from `origin/main`
- Skips the rebuild if there are no new commits
- Otherwise rebuilds the gui image and restarts the container
- Shows the last 30 log lines so you can sanity-check

---

## Troubleshooting recipes

**Container won't start / unhealthy**

> "Show me the gui logs from the NAS."
→ `scripts/nas/logs.sh --tail=200`

Look for: missing API key, port conflict (DSM uses 5000/5001 by
default; we expose 8501), or a Python import error from a recent commit.

**Permission errors writing to `data/`**

The container runs as UID 1000. The bind mount must be owned by 1000:1000:

> "On the NAS, run `sudo chown -R 1000:1000 /volume1/docker/tradingagents/data` and restart the gui."
→ `nas-cmd.sh "sudo chown -R 1000:1000 /volume1/docker/tradingagents/data" && restart.sh`

**Disk filling up**

> "Show me what's using space under data/."
→ `nas-cmd.sh 'du -sh /volume1/docker/tradingagents/data/*'`

Big offenders are usually `data/cache/` (yfinance prices) or `data/logs/`
(per-run archives). Both safe to prune older entries.

**Need to see what's in the SQLite database**

> "On the NAS, dump the runs table from gui.db."
→ `nas-cmd.sh 'docker exec tradingagents-gui sqlite3 /home/appuser/.tradingagents/gui.db ".schema runs"'`

---

## Backups

Hyper Backup or Snapshot Replication on `/volume1/docker/tradingagents/`
covers everything that matters: the source clone (cheap; can be re-cloned
from GitHub), `.env` (your API keys), and `data/` (your runs/notes/chats).

Recommended retention: daily for 7 days, weekly for 4 weeks. The data
directory is < 1 GB for typical use.

---

## Reverse proxy (optional, for HTTPS)

DSM's built-in reverse proxy. **Control Panel → Login Portal → Advanced
→ Reverse Proxy → Create**:

- Source: HTTPS, hostname `tradingagents.<your-domain>`, port 443
- Destination: HTTP, `localhost`, port 8501
- Custom Headers: `Upgrade $http_upgrade`, `Connection $connection_upgrade`
  (Streamlit needs WebSockets)

Then issue a Let's Encrypt cert against `tradingagents.<your-domain>`
in Control Panel → Security → Certificate.

---

## Architecture notes (for the future pivot)

The Streamlit GUI is the current frontend. Long-term we plan to migrate
to a proper SPA + FastAPI service for richer interactivity (real-time
streams, calendars, portfolio tracking, multi-user). When that lands,
this same Docker workflow keeps working — only the image's `command`
and exposed services change. The persistent data layer (`data/`) is
already framework-independent.

---

## Synology / DSM 7 specifics learned during the first deploy

These are the gotchas that bit us once and shouldn't again. Folded in
here so future-me (or future-Claude) doesn't re-derive them.

**1. There is no "Authorized Keys" GUI in DSM 7.**
The earlier step that referenced "Terminal & SNMP → Advanced → Authorized
Keys" doesn't exist on DSM 7.2+. Add SSH keys via SSH instead:

```bash
# from the local machine, with password auth still enabled:
ssh <USER>@192.168.2.34
# on the NAS:
mkdir -p ~/.ssh
chmod 700 ~/.ssh
chmod 755 ~              # SSH refuses key auth if home is group-writable
nano ~/.ssh/authorized_keys     # paste your .pub line
chmod 600 ~/.ssh/authorized_keys
```

User Home service must also be enabled in **Control Panel → User &
Group → Advanced → User Home**.

**2. Non-interactive SSH sessions get a minimal PATH.**
The shell our scripts hit doesn't include `/usr/local/bin` where Docker
lives (`PATH=/usr/bin:/bin:/usr/sbin:/sbin`). The `nas-cmd.sh` wrapper
already handles this by re-running every remote command in `bash -lc`,
which sources login-profile fragments and gets the right PATH.

**3. Docker socket needs `chgrp docker` on every reboot.**
`/var/run/docker.sock` defaults to `root:root mode 660`. The user is in
the `docker` group (GID 65536) but the socket isn't. Manual fix:

```bash
sudo chgrp docker /var/run/docker.sock
sudo chmod 660 /var/run/docker.sock
```

For persistence across reboots, set up a Task Scheduler boot task
(see §"Persistence note" earlier in this doc).

**4. Build deps for native Python wheels.**
The slim Python image needs cairo system libraries to build `pycairo`
(transitive dep of `xhtml2pdf`). Already in the Dockerfile:
- builder stage: `gcc + libcairo2-dev + pkg-config`
- runtime stage: `libcairo2`

If the build fails on a future "Unknown compiler(s)" or "missing
header" error for some other native dep, the fix is the same shape —
add the compile-time deps to the builder stage and the runtime `.so`s
to the runtime stage.

**5. First-deploy can land into a non-empty directory.**
DSM (or you) may pre-create `/volume1/docker/tradingagents/` before the
deploy. `git clone` refuses to clone into a non-empty target, so
`deploy.sh` falls back to `git init + remote add + fetch + checkout`,
which coexists with the persistent `data/` subdir without overwriting it.

---

## Change log

- **2026-05-04** — Initial Docker deployment to Synology
  (`Dockerfile` with `[gui]` extras, `gui` compose service, deploy
  scripts, `OPERATIONS.md`).
- **2026-05-05** — First successful deploy to `192.168.2.34`. Hit and
  resolved: DSM 7 missing Authorized-Keys UI, non-interactive SSH PATH,
  Docker socket group ownership, pycairo native-build deps,
  `git clone` into non-empty directory.
- **2026-05-05** — Migrated from Streamlit-only to Next.js + FastAPI
  stack. New compose services `api` (8000) and `web` (3000); legacy
  Streamlit `gui` service moved to a `legacy` profile. Same persistent
  data dir, same SQLite schema, same archive format — UI is the only
  thing that changed.
