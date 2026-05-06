# Synology web-app deploy template

A reusable scaffold for deploying any Dockerized web project to a
Synology NAS with one command. Extracted from the TradingAgents
deployment so the same pattern works for the next project (and the one
after that) without re-deriving the SSH plumbing, port-binding gotchas,
or Container Manager quirks.

## What this gives you

- **`scripts/`** — seven SSH-driven scripts that handle deploy, upgrade,
  restart, rollback, status, logs, and arbitrary remote commands. They
  read project metadata from `synology-deploy.env` and credentials from
  `credentials.local`, so the same scripts work for any project once
  those two files are filled in.
- **`examples/`** — concrete Dockerfile / docker-compose / .gitignore /
  OPERATIONS.md examples you can copy into a new project and adapt.
- **`PROMPT.md`** — the prompt you paste to Claude when you want it to
  set up this deploy pattern in a new project.

## How to use it for a new project

You can drive this entirely by pasting `PROMPT.md` to Claude in a fresh
session, but here's the shape of what happens:

1. **Copy the scripts** into your new project at `scripts/nas/`:
   ```
   cp -r templates/synology-webapp-deploy/scripts your-new-project/scripts/nas
   ```

2. **Copy the metadata template** to the project root and fill it in:
   ```
   cp templates/synology-webapp-deploy/synology-deploy.env.example \
      your-new-project/scripts/nas/synology-deploy.env
   # Edit: PROJECT_NAME, NAS_REPO_PATH, NAS_DATA_PATH, DEPLOY_SERVICES, etc.
   ```

3. **Add Docker config** for your services. The `examples/` directory
   has working Dockerfiles for FastAPI + Next.js and a multi-service
   compose file you can crib from.

4. **Add to `.gitignore`** the snippet from `examples/.gitignore.snippet`
   so `credentials.local`, `data/`, `.env`, etc. don't get committed.

5. **Author `credentials.local`** with your NAS connection info (see
   `scripts/credentials.local.example`).

6. **Verify**:
   ```
   bash scripts/nas/nas-cmd.sh 'echo hello from $HOSTNAME'
   ```

7. **Deploy**:
   ```
   bash scripts/nas/deploy.sh
   ```

## The two configuration files

| File | Purpose | Committed? | Claude reads it? |
|---|---|---|---|
| `scripts/nas/synology-deploy.env` | Project metadata (paths, services, repo URL) | ✅ yes | ✅ yes |
| `scripts/nas/credentials.local` | NAS host + user + SSH key path | ❌ NO (gitignored) | ❌ NO (Claude is instructed not to) |

## Script index

| Script | Purpose |
|---|---|
| `nas-cmd.sh "<cmd>"` | Run any command on the NAS (used by all the others) |
| `deploy.sh` | First-time clone + build + start of all `DEPLOY_SERVICES` |
| `upgrade.sh` | Pull latest from git + rebuild + restart |
| `restart.sh` | Restart services without rebuilding (e.g. after `.env` edits) |
| `status.sh` | Compose ps + container health + git SHA + data dir size |
| `logs.sh [--tail=N] [--follow]` | Tail logs (override `SERVICE=foo` for a specific service) |
| `rollback.sh <sha\|previous>` | Roll back to a prior commit and rebuild |

All seven scripts source the same two files (`synology-deploy.env` and
`credentials.local`), so once those exist, the scripts "just work."

## Why this pattern

- **Scripts are project-agnostic.** Same scripts deploy TradingAgents,
  the next thing you build, the thing after that.
- **Claude can run scripts but never sees credentials.** The scripts
  source `credentials.local` themselves; credentials become env vars in
  the script's process and never reach Claude's tool output.
- **All state on the NAS is in one bind-mounted directory.** Backup is
  one Hyper Backup task pointed at `/volume1/docker/<project>/data/`.
- **Same conventions across projects** make ops fast: same scripts,
  same .env file shape, same OPERATIONS.md skeleton.

## Limitations

- **Synology-specific** — assumes `/volume1/docker/`, DSM 7+, Container
  Manager. Adapts trivially to any Linux Docker host but nothing here
  helps with Synology-quirks-on-other-NASes (QNAP/Asustor).
- **Single-host** — no swarm/k8s. The whole stack runs on one box.
- **LAN-only is the default.** Reverse proxy + HTTPS via DSM's built-in
  proxy is documented but not automated.
- **No secret rotation.** API keys go in `.env` on the NAS; rotation is
  a manual SSH-and-edit step.
