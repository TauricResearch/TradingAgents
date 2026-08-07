# Repository operating safeguards

- Never print, log, paste, or return secret values, database URLs, connection
  strings, bearer tokens, webhook URLs, or raw environment variables. Report
  only secret names, presence booleans, digests, and fixed-vocabulary outcomes.
- Do not run `fly mpg status --json` (or emit raw `fly mpg status` output).
  Current flyctl responses can contain plaintext Managed Postgres credentials.
  Use `fly status`, `fly checks list`, `fly releases`, `fly secrets list`, and
  sanitized projections of `fly mpg users list --json` instead.
- If a Fly or database diagnostic could return credentials, parse and redact it
  inside the same process before emitting any output. Never inspect the raw
  response in an agent transcript.
- Production collector deployments must use `scripts/deploy_collector.sh` from
  a clean committed tree. Never bypass the release preflight or health gate.
- Never run a provider-fetching command for diagnosis when a read-only audit,
  stats command, or isolated database/network probe can answer the question.
