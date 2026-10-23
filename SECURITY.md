# Security Policy

## Supported Versions

Security fixes are applied to the latest release line only.

## Reporting a Vulnerability

Please report security vulnerabilities privately via [GitHub security advisories](https://github.com/TauricResearch/TradingAgents/security/advisories/new).

Do **not** open a public issue for security reports. Include, if you can:

- a minimal reproduction or proof of concept,
- the affected component (CLI, data layer, graph, web, ...),
- potential impact.

We aim to acknowledge reports within 72 hours and will keep reporters updated as fixes progress.

## Committing Safely

This repository scans for accidentally committed credentials:

- locally via [detect-secrets](https://github.com/Yelp/detect-secrets) through [pre-commit](https://pre-commit.com) (see `.pre-commit-config.yaml`),
- in CI on every pull request against the committed baseline (`.secrets.baseline`).

If a scan flags something you are about to commit, remove the secret, rotate it if it ever left your machine, and use environment variables or a local `.env` file (already git-ignored) instead. If the finding is a false positive, regenerate the baseline:

    pip install detect-secrets
    detect-secrets scan --update .secrets.baseline

and commit the updated baseline in the same PR.
