# NAS deploy + maintenance scripts

These scripts let Claude (or you) operate a Dockerized project on a
Synology NAS over SSH without ever exposing your credentials.

## Configuration files

| File | What it holds | Committed? |
|---|---|---|
| `synology-deploy.env` | project metadata (paths, services, repo URL) | ✅ yes |
| `credentials.local` | NAS host + SSH connection info | ❌ no — gitignored, Claude is told never to read it |

## One-time setup (per project)

```bash
# 1. Copy the templates
cp synology-deploy.env.example synology-deploy.env
cp credentials.local.example credentials.local

# 2. Edit synology-deploy.env with project specifics
# 3. Edit credentials.local with NAS connection info

# 4. Make scripts executable (only needed on Linux/macOS hosts)
chmod +x *.sh

# 5. Verify
bash nas-cmd.sh 'echo hello from $HOSTNAME'
```

If you choose SSH-key auth (recommended), generate one once:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/nas_<project> -N ""
# Paste the .pub line into ~/.ssh/authorized_keys on the NAS via
# an SSH session (DSM 7+ has no GUI for this).
```

Set `NAS_SSH_KEY=~/.ssh/nas_<project>` in `credentials.local`.

## Scripts

| Script | When to use |
|---|---|
| `nas-cmd.sh "<cmd>"` | Run any command on the NAS (other scripts use this) |
| `deploy.sh` | First-time deploy: clone, build, start |
| `upgrade.sh` | Pull latest, rebuild, restart (the routine) |
| `restart.sh` | Restart without rebuilding (e.g. after `.env` edits) |
| `status.sh` | Compose ps + container health + version + disk usage |
| `logs.sh [--tail=N]` | Tail logs (override `SERVICE=` for non-default service) |
| `rollback.sh <sha\|previous>` | Roll back if an upgrade goes sideways |

## Common Synology / DSM 7 gotchas

These bit us once on the first project; the scripts already work
around them, but worth knowing if you debug.

### Non-interactive SSH PATH excludes /usr/local/bin

`nas-cmd.sh` wraps every remote command in `bash -lc` so the user's
login profile runs and PATH picks up Synology-package additions
(including the docker binary).

### Docker socket needs chgrp on every reboot

`/var/run/docker.sock` defaults to `root:root mode 660`. After every
NAS reboot, your user (in the `docker` group) loses access. Fix once:

```bash
sudo chgrp docker /var/run/docker.sock
sudo chmod 660 /var/run/docker.sock
```

For persistence, set up a Task Scheduler boot task in DSM:
- **Control Panel → Task Scheduler → Create → Triggered Task**
- User: `root`, Event: `Boot-up`
- Run command:
  ```
  /bin/sh -c 'sleep 60; chgrp docker /var/run/docker.sock; chmod 660 /var/run/docker.sock'
  ```

### Bind-mount permissions

The default Docker images in `examples/` create a user with UID:GID 1000.
Synology bind mounts must be writable by that user. After `mkdir`,
chown once:

```bash
sudo chown -R 1000:1000 /volume1/docker/<project>/data
```

`deploy.sh` tries this automatically (without sudo) and warns if it
fails. If the container can't write, run the manual chown above.

### Port conflicts

Synology ships with services on common ports (5000/5001 for DSM, 8000
sometimes for backup tools, etc). Other Docker projects on the host may
hold 3000, 8080, etc. Use `${PORT_NAME:-default}` in compose `ports:`
and override in `.env` if there's a conflict.

## What if the credential pattern doesn't work?

If `bash nas-cmd.sh 'echo hi'` doesn't print `hi`, walk down:

1. **Permission denied**: SSH key isn't installed in
   `~/.ssh/authorized_keys` on the NAS (or perms are wrong on
   `~/.ssh` / home dir — needs `chmod 700` and `chmod 755 ~`).

2. **`Could not find sshpass`**: install sshpass locally, or switch to
   key auth.

3. **`sh: -c: line 0: unexpected EOF`**: you're on Windows and used
   single quotes in CMD. Switch to Git Bash, or use double quotes.

4. **Times out**: NAS_HOST in `credentials.local` is wrong, or SSH is
   disabled in DSM (Control Panel → Terminal & SNMP → Terminal).
