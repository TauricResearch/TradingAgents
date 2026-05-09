# Security

This document describes the automated security scanning that ships with this
repository, what those scans cover, what they do **not** cover, and how to
report a vulnerability. If you are new to open source: nothing here is a
substitute for understanding the threat model of running an LLM agent that
fetches market data and calls third-party APIs with your keys.

## Reporting a vulnerability

Please do not open a public GitHub issue for security problems. Use GitHub's
private vulnerability reporting on the repository's **Security** tab, or
contact the maintainers directly.

## What runs automatically

All scans live under [`.github/workflows/`](.github/workflows/) and have
matching local scripts under [`scripts/`](scripts/) so you can reproduce CI
results on your machine.

| Scan | Tool | When it runs | Local equivalent |
|---|---|---|---|
| Dependency CVE scan | [`pip-audit`](https://github.com/pypa/pip-audit) | Push to `main`, every PR, weekly (Mon 08:00 UTC) | `bash scripts/cve_scan_local.sh` |
| Broader dependency advisories | [`osv-scanner`](https://github.com/google/osv-scanner) `v2.2.3` | Push to `main`, every PR, weekly | `bash scripts/osv_scan_local.sh` |
| Static security analysis | [CodeQL](https://codeql.github.com/) (Python, `security-extended`) | Push to `main`, every PR, weekly | CI only — CodeQL CLI is heavy; results show in the Security tab |
| Container & Dockerfile scan | [`hadolint`](https://github.com/hadolint/hadolint) + [`trivy`](https://github.com/aquasecurity/trivy) (fs, CRITICAL/HIGH) | Push to `main`, every PR, weekly | `bash scripts/container_scan_local.sh` (requires Docker) |
| Secrets scan (full history) | [`gitleaks`](https://github.com/gitleaks/gitleaks) `v8.27.2` | Push to `main`/`claude/**`/`feature/**`, PRs to `main`, weekly | `bash scripts/secrets_scan_local.sh` |
| Secrets scan (staged files) | `gitleaks protect --staged` | Pre-commit git hook (opt-in) | Installed via `bash scripts/install_git_hooks.sh` |
| Lint | [`ruff`](https://docs.astral.sh/ruff/) check + format | Push to `main`, every PR | `bash scripts/lint_local.sh` |
| Unit tests | `pytest -m unit` | Push to `main`/`claude/**`/`feature/**`, PRs to `main`, Python 3.10/3.11/3.12 | `pytest -m unit` |

All security scans **fail the build** on findings (CodeQL on `error`-level
results; OSV / Trivy on any vulnerability at HIGH or above; Hadolint at
warning or above; gitleaks on any leak; pip-audit on any CVE). Branch
protection on `main` should require these checks before merge so the
gates actually enforce policy.

### Dependency CVE scan (`pip-audit`)

Defined in [`.github/workflows/cve-scan.yml`](.github/workflows/cve-scan.yml).
Builds an isolated venv, installs the project editable, and runs `pip-audit
--desc --skip-editable` against the resolved dependency tree from
`pyproject.toml`. Fails the build on any known CVE. Weekly schedule means
newly-disclosed CVEs in pinned deps surface within a week even on quiet
branches.

The local mirror in [`scripts/cve_scan_local.sh`](scripts/cve_scan_local.sh)
deliberately uses `.venv/cve-scan/` rather than your active venv so results
match CI.

### Broader dependency advisories (`osv-scanner`)

Defined in [`.github/workflows/osv-scan.yml`](.github/workflows/osv-scan.yml).
Runs Google's `osv-scanner` against `pyproject.toml`, `requirements.txt`,
and `uv.lock`. OSV.dev aggregates advisories from PyPI, GHSA, OSS-Fuzz, and
language-specific databases, so it catches vulnerabilities pip-audit's
narrower source list can miss. Run locally with
[`scripts/osv_scan_local.sh`](scripts/osv_scan_local.sh) — this downloads
the official binary into `.venv/osv-scanner-bin/` (no PATH pollution).

Both `pip-audit` and `osv-scanner` are kept on purpose. They overlap, but
each finds advisories the other misses; running both is cheap insurance.

### Static security analysis (CodeQL)

Defined in [`.github/workflows/codeql.yml`](.github/workflows/codeql.yml).
Runs GitHub's CodeQL with the Python `security-extended` query suite, which
includes checks for command injection, path traversal, unsafe deserialisation,
SSRF, and a large catalogue of insecure-API patterns. Findings upload to the
repository's **Security** tab. CI fails the job on any `error`-level result;
configure branch protection to require the "Analyze (Python)" check before
merge so this gate actually blocks merges. CodeQL runs in CI only — the CLI
is heavy and slow, so there is no local mirror script.

### Container & Dockerfile scan (`hadolint` + `trivy`)

Defined in
[`.github/workflows/container-scan.yml`](.github/workflows/container-scan.yml).
Two parallel jobs:

- **Hadolint** lints the `Dockerfile` for security and best-practice issues
  (root user, missing `--no-cache`, unpinned base images, etc.). Fails on
  warnings or higher.
- **Trivy** scans the project filesystem for vulnerable packages and known
  misconfigurations at `CRITICAL`/`HIGH` severity, ignoring unfixed CVEs.

Run locally with
[`scripts/container_scan_local.sh`](scripts/container_scan_local.sh), which
runs both tools in containers (so you only need Docker, not the binaries).

### Secrets scan (`gitleaks`)

Defined in
[`.github/workflows/secrets-scan.yml`](.github/workflows/secrets-scan.yml).
Walks the **full git history** with `fetch-depth: 0`, so a key committed and
later "deleted" still gets caught — once a secret reaches a public history,
treat it as compromised and rotate it.

A pre-commit hook (see
[`.git-hooks/pre-commit`](.git-hooks/pre-commit)) runs `gitleaks protect
--staged` against staged changes only, before the commit lands locally.
Install it once with:

```bash
bash scripts/install_git_hooks.sh
```

If `gitleaks` isn't on your PATH the hook prints a warning and exits 0 —
**it does not block the commit**. Install gitleaks (`brew install
gitleaks` or use the local script) to actually get protection.

### Lint (`ruff`) and unit tests (`pytest`)

These are **not** security tools. They are listed here only so you know what
the green checkmark on a PR represents: style/format conformance and
functional regression coverage. They will not catch insecure code patterns.

## What the scans do NOT cover

Knowing the remaining gaps matters more than knowing the coverage. The
scans above still will not catch:

- **Malicious or typosquatted dependencies.** `pip-audit` and `osv-scanner`
  both know about CVEs filed against *legitimate* packages. A malicious
  package masquerading as a real one is invisible to advisory-based scans.
  The mitigation is hash-pinned requirements (`pip-compile
  --generate-hashes` + `pip install --require-hashes`); this project does
  not use them today because the maintenance friction is high.
- **License audit.** No SPDX scan; transitive licenses are not checked.
  This is a legal-risk concern, not a hack-risk concern.
- **LLM-specific risks.** TradingAgents pipes scraped news, social content,
  and tool output back into LLM context. Prompt-injection from that content,
  unintended tool calls, and exfiltration via tool arguments are not
  covered by any automated scan, and are an open research problem in the
  field. Mitigations are defensive code (treating tool output as untrusted,
  bounded tool surfaces, output validation), not CI gates. **For an
  individual TradingAgents user, this is the highest-likelihood realistic
  attack vector.**
- **Runtime / network behavior.** No egress monitoring. The agent talks to
  yfinance, Alpha Vantage, and whichever LLM provider you configured, using
  the API keys in your `.env`. If a dependency or a remote endpoint is
  compromised, scans run at commit time will not help.
- **Secrets after they leave your machine.** Gitleaks only inspects the
  git repo. Keys logged to stdout, written to checkpoint SQLite files
  under `~/.tradingagents/`, or echoed by an LLM into a saved report are
  not protected.

## Practical hardening for new users

These are not enforced by the project; they are recommendations.

1. **Use a dedicated, low-limit API key per provider.** Set spend caps where
   the provider supports them. The biggest realistic loss for an individual
   user is a leaked key being abused, not code execution.
2. **Keep keys in `.env`, never in arguments or committed config.** `.env`
   is gitignored; `.env.example` and `.env.enterprise.example` are the
   templates.
3. **Install the pre-commit hook.** `bash scripts/install_git_hooks.sh`.
   This is the single highest-value step you can take in 10 seconds.
4. **Run the scans locally before pushing.** CI will catch them anyway, but
   local runs are faster and stop secrets before they reach a remote.
5. **Be skeptical of agent output that came from scraped sources.** Treat
   it like email: useful, untrusted. Don't paste agent-suggested commands
   into a shell unread.
6. **Pin or audit before upgrading.** When `pip-audit` flags a CVE, read the
   advisory before bumping — sometimes the fix introduces breaking changes
   or a different vulnerability.
7. **Rotate any key that has ever appeared in a log, screenshot, or commit.**
   Even if the commit was force-pushed away, assume it was scraped.

## CI failure behavior

- `cve-scan` fails the build on any flagged CVE. Fix by upgrading the
  affected dependency in `pyproject.toml` (or `requirements.txt` if you
  pin there) and re-running.
- `secrets-scan` fails the build on any gitleaks finding. Because the scan
  walks full history, **rewriting history alone does not undo a leak** —
  rotate the key first, then clean the history if you want to.
- `lint` and `tests` failing does not indicate a security problem; treat
  them as quality gates.
