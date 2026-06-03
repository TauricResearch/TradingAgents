# CLAUDE.md

## Generated Report Markdown

- Do not recursively scan or read generated report Markdown under `docs/**/*.md`
  into Claude Code context.
- Project settings deny direct `Read` access to `docs/*.md` and
  `docs/**/*.md`; this is intentional so report bodies stay out of model
  context.
- Treat `docs/index.md`, `docs/<TICKER>/index.md`, and
  `docs/<TICKER>/<YYYYMMDD>_*/**/*.md` as generated report output.
- For report refreshes, use `python scripts/report_workflow.py --analysis-date
  YYYYMMDD` instead of hand-editing generated docs. The workflow validates docs;
  the repo-local pre-commit hook compiles `_site/`.
- For docs verification, prefer bounded commands that return counts or invariant
  failures, such as `rg -n "n/a" docs/index.md` or the workflow validators,
  rather than dumping report contents.
