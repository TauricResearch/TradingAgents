# Paste-to-Claude prompt for using this deploy pattern in a new project

Copy everything below the `--- BEGIN PROMPT ---` line into a fresh
Claude session inside the new project's repo. Edit the bracketed fields
on the first three lines before pasting.

---

--- BEGIN PROMPT ---

I want to deploy this project to my Synology NAS at `192.168.2.34`
using the same script-driven pattern we built for TradingAgents.

**Project specifics (please read these and ask me if any are unclear before changing files):**
- Project name: **[FILL IN — e.g. `myproject`]**
- NAS path: **[default: `/volume1/docker/<project>`]**
- Services to deploy: **[FILL IN — e.g. `api web` or `app db` or just `app`]**
- Public web port (if any): **[FILL IN — e.g. `3001`. Avoid 3000, 8000, 8086, 8501 — those are taken on this NAS.]**

**Reference template:** the working pattern is documented at
`templates/synology-webapp-deploy/` in the TradingAgents repo
(https://github.com/mrh335/TradingAgents). Use the scripts there as the
source of truth. The pattern is summarised below; you don't need to
re-read every file.

**What I want you to do:**

1. **Copy the deploy scripts** into this project at `scripts/nas/`:
   - `nas-cmd.sh`, `deploy.sh`, `upgrade.sh`, `restart.sh`,
     `status.sh`, `logs.sh`, `rollback.sh`, `README.md`,
     `credentials.local.example`, `synology-deploy.env.example`
   - These are project-agnostic; they read project specifics from
     `synology-deploy.env`.

2. **Create `scripts/nas/synology-deploy.env`** populated with the
   project specifics above. Use the `.example` as a template.

3. **Create or adapt the Docker config** for this project:
   - `Dockerfile` (or `Dockerfile.api` + `Dockerfile.web` if multi-service)
   - `docker-compose.yml` with the services listed above. Use bind
     mounts for any persistent data at `./data:/path/inside/container`.
   - Pin runtime user to UID/GID 1000 for Synology bind-mount
     compatibility (see `templates/synology-webapp-deploy/examples/`
     for working Dockerfile patterns).

4. **Update `.gitignore`** with the snippet from
   `templates/synology-webapp-deploy/examples/.gitignore.snippet` so
   `scripts/nas/credentials.local`, `data/`, `.env`, and `*.local` don't
   get committed.

5. **Stop and ask me** to:
   - Author `scripts/nas/credentials.local` (you can't see it; same
     pattern as TradingAgents — `NAS_HOST`, `NAS_USER`, `NAS_SSH_KEY`).
   - Add API keys to `.env` on the NAS once `deploy.sh` creates the
     template there.

6. **After I confirm credentials are filled in,** run
   `bash scripts/nas/deploy.sh` and walk me through any errors. Common
   ones we hit on TradingAgents and the fixes are documented in
   `templates/synology-webapp-deploy/examples/OPERATIONS.md.example`
   (DSM 7 SSH PATH, docker.sock perms, port conflicts, etc.).

7. **Generate an `OPERATIONS.md`** at this project's root using the
   template at `templates/synology-webapp-deploy/examples/OPERATIONS.md.example`,
   filled in with this project's specifics.

8. **Commit each of the above steps as separate small commits** so
   I can review them individually. Don't open a PR yet.

**Hard constraints:**
- Never read `scripts/nas/credentials.local` — it's gitignored on
  purpose.
- Never put my API keys, NAS password, or SSH private key into any
  committed file.
- Don't push to git until I've reviewed the changes.
- If you hit a port conflict on the NAS, work around it by setting an
  override in `.env` (the docker-compose.yml uses `${NAME:-default}`
  fallbacks for ports). Don't pick ports for me silently — list the
  taken ports and propose options.

When you're done with steps 1–4, tell me what to do next. Don't run
`deploy.sh` until I've confirmed `credentials.local` is in place.

--- END PROMPT ---

## How this prompt is meant to be used

1. You paste it into a fresh Claude session in the *new* project's repo.
2. Claude copies the scripts and Docker examples in.
3. Claude pauses for you to fill in `credentials.local`.
4. You confirm; Claude runs `deploy.sh` and iterates with you on any
   environment-specific issues.
5. End state: one more `docker compose` stack on your NAS, deployable
   via `bash scripts/nas/upgrade.sh` from here on.

You can prepend additional project-specific instructions before the
`--- BEGIN PROMPT ---` line — e.g. "this is a Rust service that needs
sqlx-cli at build time" — without breaking the pattern.
