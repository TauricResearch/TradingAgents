# NAS deploy + maintenance scripts

These scripts let Claude (or you) operate the TradingAgents GUI on a
remote Synology NAS *without* Claude ever seeing your credentials.

## How the credential pattern works

- ``credentials.local.example`` — the template, committed to the repo.
- ``credentials.local`` — your filled-in copy. Listed in `.gitignore`;
  Claude is instructed not to read its contents.
- The scripts here `source` `credentials.local` to get connection info,
  so the credentials become env vars in the script's process — not
  printed, not logged, not visible to Claude's tools (which see only
  the script's stdout).

When Claude needs to deploy or maintain, it runs one of these scripts
via the local Bash tool. The script SSHes to the NAS using your
credentials and reports back what it did, but the credentials never
leave the local machine.

## One-time setup

```bash
cp scripts/nas/credentials.local.example scripts/nas/credentials.local
chmod 600 scripts/nas/credentials.local
# edit scripts/nas/credentials.local in your editor; see comments inside.
```

If you choose SSH-key auth (recommended), generate a key:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/nas_tradingagents -N ""
cat ~/.ssh/nas_tradingagents.pub
# Paste the .pub line into DSM → Control Panel → Terminal & SNMP → Authorized Keys
# OR into ~/.ssh/authorized_keys via SSH (the first time you log in with a password).
```

Set `NAS_SSH_KEY=~/.ssh/nas_tradingagents` in `credentials.local`.

## Available scripts

| Script | What it does |
|---|---|
| `nas-cmd.sh "<cmd>"` | Run any command on the NAS (low-level helper used by the others) |
| `deploy.sh` | First-time deploy: clone, set up paths, build, start |
| `upgrade.sh` | Pull latest, rebuild gui image, restart |
| `restart.sh` | Restart the running container without rebuilding (fast — for .env changes) |
| `status.sh` | Compose ps + container health + image + git SHA + data dir size |
| `logs.sh` | Tail GUI logs (default: last 100 lines + follow) |
| `rollback.sh <sha\|previous>` | Roll back to a prior commit and rebuild |

All scripts read the same `credentials.local`, so once it's filled in
they all "just work."

## Quick verification

```bash
scripts/nas/nas-cmd.sh 'echo hello from $HOSTNAME'
```

If you see "hello from <your-NAS-name>", the credential pattern is
working and you can run any of the other scripts.

## When something feels stuck

- Container won't stay up → `scripts/nas/logs.sh` and look for the actual error
- Worked before, broken after upgrade → `scripts/nas/rollback.sh previous`
- Suspect bad data → check `scripts/nas/status.sh`; the `data/` size
  block tells you if archives are still being written
