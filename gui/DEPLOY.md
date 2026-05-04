# Deploying TradingAgents GUI to a Synology NAS

This walks through running the Streamlit GUI as a Docker service on a
Synology NAS via Container Manager (DSM 7.2+). It assumes you have:

- Docker package / Container Manager installed on DSM
- A user with admin rights, SSH enabled (for the one-time permission step)
- Optional but recommended: a reverse proxy + DNS entry for HTTPS

The same `docker-compose.yml` works on QNAP, unRAID, or a plain Linux
host — the only Synology-specific bit is Container Manager's UI flow.

---

## 1. Lay out the project on the NAS

Clone (or `git pull`) this repo into a project directory under
`/volume1/docker/`:

```bash
ssh admin@<your-nas>
sudo mkdir -p /volume1/docker/tradingagents
sudo chown $USER:users /volume1/docker/tradingagents
cd /volume1/docker/tradingagents
git clone https://github.com/mrh335/TradingAgents.git .
```

The persistent data directory:

```bash
mkdir -p /volume1/docker/tradingagents/data
```

`data/` is what gets bind-mounted into the container at
`/home/appuser/.tradingagents/`. Everything the GUI writes — API keys,
SQLite database, run archives, exports, the rolling memory log,
yfinance + LangGraph caches — lives there. It survives container
rebuilds and can be backed up alongside the rest of `/volume1/docker/`.

---

## 2. Permissions (the one Synology gotcha)

The container runs as UID/GID 1000. Synology's default admin user is
1024–1026, so a fresh bind mount won't be writable. Fix it once:

```bash
sudo chown -R 1000:1000 /volume1/docker/tradingagents/data
```

If you'd rather use your own Synology user instead, edit the
`Dockerfile` to match — change `--uid 1000 --gid 1000` to your actual
UID/GID and rebuild.

---

## 3. API keys

Drop a `.env` file at the repo root. Use `.env.example` as a template:

```bash
cd /volume1/docker/tradingagents
cp .env.example .env
nano .env   # paste in keys for whichever providers you use
chmod 600 .env
```

The GUI reads keys from this `.env` first, then from
`~/.tradingagents/gui_config.json` inside the container (which you can
also edit live from the **Settings** page once the GUI is up).

---

## 4. Build + start via Container Manager

**DSM 7.2+ Container Manager** has a "Project" workflow that's
equivalent to `docker compose up`:

1. Open **Container Manager** → **Project** → **Create**
2. Project name: `tradingagents`
3. Path: `/volume1/docker/tradingagents`
4. Source: **"Use existing docker-compose.yml"** (it'll detect the file)
5. Click **Next** through the validation steps
6. On the last screen, leave only the **`gui`** service enabled
   (uncheck `tradingagents`, `ollama`, `tradingagents-ollama` unless
   you want them too)
7. **Build** then **Start**

Or via SSH:

```bash
cd /volume1/docker/tradingagents
docker compose build gui
docker compose up -d gui
docker compose logs -f gui   # tail the startup
```

When you see `Uvicorn server started on 0.0.0.0:8501`, point a browser
at `http://<your-nas-ip>:8501/`.

---

## 5. Reverse proxy + HTTPS (recommended)

Synology's built-in reverse proxy handles this cleanly. **Control
Panel → Login Portal → Advanced → Reverse Proxy**:

| Field | Value |
|---|---|
| Source protocol | HTTPS |
| Source hostname | `tradingagents.<your-domain>` |
| Source port | 443 |
| Destination protocol | HTTP |
| Destination hostname | `localhost` |
| Destination port | `8501` |

Under **Custom Header**, add **WebSocket** entries (Streamlit needs
them):

| Header | Value |
|---|---|
| Upgrade | `$http_upgrade` |
| Connection | `$connection_upgrade` |

Then issue a Let's Encrypt cert against `tradingagents.<your-domain>`
(**Control Panel → Security → Certificate**).

---

## 6. Pulling updates

```bash
cd /volume1/docker/tradingagents
git pull
docker compose build gui
docker compose up -d gui
```

The `data/` directory is untouched by rebuilds — your runs, notes,
chats, and briefs persist across versions.

---

## 7. Backups

The simplest backup is a snapshot of `/volume1/docker/tradingagents/`.
The two important pieces:

- **`./data/`** — all your run archives, SQLite, config, exports
- **`./.env`** — your API keys

If you use Synology's Hyper Backup or Snapshot Replication, point it
at `/volume1/docker/tradingagents/` and you're covered.

---

## 8. Troubleshooting

**Container starts but UI is unreachable.**
Check that `data/` is readable+writable by UID 1000:
```bash
ls -la /volume1/docker/tradingagents/data
```
If owner shows as your Synology user, run the chown step from §2.

**"Health check failed".**
Streamlit takes ~30-60s to fully boot on first start. The healthcheck
gives it 60s of grace period. If it's still failing after that, check
`docker compose logs gui` — usually a missing API key in `.env`.

**Models default to `gpt-5.4-mini`.**
That's a placeholder name from upstream. Open **Settings** in the GUI
and pick a real model your provider offers (e.g. `gpt-4o-mini`,
`claude-haiku-4-5`, `gemini-2.5-flash`).

**"No module named 'gui'".**
Older versions of the upstream image didn't include the GUI extras.
Make sure `pyproject.toml` has the `[gui]` extras and the Dockerfile
installs with `pip install '.[gui]'`. (This fork's main always does.)

**Want a different port.**
Set `TRADINGAGENTS_GUI_PORT` in `.env` (e.g. `TRADINGAGENTS_GUI_PORT=8502`)
and `docker compose up -d gui`.
