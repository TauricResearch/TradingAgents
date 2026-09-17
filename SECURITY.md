# Security Policy

## Reporting a vulnerability

Please report security vulnerabilities **privately**, through GitHub's private
vulnerability reporting: open the repository's **Security** tab and choose
**Report a vulnerability**, or go straight to
[the reporting form](https://github.com/TauricResearch/TradingAgents/security/advisories/new).
The report stays between you and the maintainers.

Please do not open a public issue, pull request, or Discord message for a
vulnerability before it has been addressed — a public report puts every user
running the framework at risk in the window before a fix ships.

**Do not include secrets in your report.** No API keys, no `.env` contents, and
no unredacted saved reports or cache files. If a key of yours was exposed while
finding the issue, rotate it at the provider first. A redacted excerpt is
always enough to demonstrate an issue.

A useful report includes:

- the version or commit you were running
- the relevant configuration — LLM provider, configured data vendors, whether
  the run was live or historical
- steps to reproduce, ideally the smallest case that shows the behaviour
- what an attacker gains, and what they need in order to reach it

You are welcome to include a suggested fix, but it is not expected.

## What happens next

The maintainers will acknowledge your report, let you know whether it is
accepted, and keep you posted as a fix is prepared. If a fix ships, you will be
credited in the advisory and the changelog unless you would rather stay
anonymous.

Please give the maintainers a reasonable opportunity to address the issue before
disclosing it publicly.

## Supported versions

TradingAgents is pre-1.0 and develops on a single line. Security fixes land on
`main` and ship in the next release; only the most recent release receives them.
If you are running an older release, upgrading is the fix.

## Scope

In scope — the kinds of issue this policy is for:

- **Credential exposure**: API keys reaching logs, saved reports, the on-disk
  cache, the memory log, or an outbound request they do not belong in
- **Path traversal or unintended writes**: anything escaping the configured
  results, cache, or memory directories, including through a crafted ticker
  symbol or configuration value
- **Code execution or injection** through data the framework fetches — a news
  article, social post, market-data response, or an LLM's tool-call arguments
- **Prompt injection with a security consequence**: content in a fetched
  article or post that makes the framework leak credentials, write outside its
  directories, or reach an endpoint it should not. Prompt injection that only
  skews an analyst's opinion belongs under "out of scope" below
- **Vulnerable dependencies** pinned by this project

Out of scope:

- **The quality of a trading decision.** TradingAgents is a research framework
  and [is not intended as financial, investment, or trading
  advice](https://tauric.ai/disclaimer/). A losing recommendation, a poor
  analysis, or a model that talks itself into a bad call is a model-quality
  matter — please open a regular issue
- Vendor outages, rate limits, quota exhaustion, or a missing API key
- Vulnerabilities in third-party LLM providers or data vendors themselves —
  report those to the vendor; we will help coordinate if this project's use of
  the vendor is what exposes you
- Automated scanner output with no demonstrated impact on this project
- Anything requiring an attacker who already controls the machine, the Python
  environment, or the user's `.env`

## Hardening your own runs

Not vulnerabilities, but worth knowing if you run this framework:

- Keys are read from the environment. Keep `.env` out of version control — it
  is already in `.gitignore`, and `.env.example` is the file meant to be shared
- Saved reports, the cache, and the memory log are written under
  `~/.tradingagents` by default and are not encrypted. They can contain the
  tickers you researched and the decisions you reached
- Analyst agents consume live third-party content. Treat what a run produces as
  influenced by that content, not as an independent judgement of it
