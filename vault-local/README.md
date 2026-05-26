# Local Persistent Vault (Separate Stack)

This folder runs Vault as a separate Docker Compose project so app rebuilds do not modify Vault data.

## Start

```bash
docker compose -f vault-local/docker-compose.yml up -d
```

## Initialize/Unseal + Seed Keys

```powershell
./scripts/vault_local_bootstrap.ps1
```

Bootstrap stores local-only files in repo root:
- .vault_unseal_key.local
- .vault_root_token.local

These files are gitignored.

## Stop (keep data)

```bash
docker compose -f vault-local/docker-compose.yml down
```

## Data Persistence

Vault data is stored under:
- vault-local/data

As long as this folder remains, restarts and rebuilds keep secrets.
