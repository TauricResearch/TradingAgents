# Using TradingAgents

## In the terminal

`tradingagents` starts a session. It opens with the version and the model in use, and a line of news: where to get a Tauric API key when there is none, what changed in a new version, or that a newer release is out. Type a question and press Enter; the plan, the tools it calls and the agents it briefs show as they run, and the thinking streams as it happens. Esc or Ctrl+C stops the running question. With nothing running, Ctrl+C, Ctrl+D on an empty line, or `/exit` leaves.

| Key                                               | Does                                                 |
| ------------------------------------------------- | ---------------------------------------------------- |
| Enter                                             | send (a question sent while one runs waits its turn) |
| Shift+Enter, Alt+Enter, Ctrl+J, or `\` then Enter | a new line                                           |
| Up, Down                                          | earlier questions                                    |
| Ctrl+R                                            | search earlier questions                             |
| Shift+Tab                                         | switch the mode: auto or plan                        |

| Command      | Does                                                                                              |
| ------------ | ------------------------------------------------------------------------------------------------- |
| `/help`      | commands and keys                                                                                 |
| `/status`    | the model, data, sync and session                                                                 |
| `/new`       | start a new session                                                                               |
| `/resume`    | resume an earlier session, here or in your Tauric account; Ctrl+D on one deletes it, after asking |
| `/model`     | choose the model this session and new ones run on                                                 |
| `/login`     | connect a provider, or add a Tauric API key                                                       |
| `/agents`    | the agents the main agent can ask, and where each comes from                                      |
| `/skills`    | the skills the main agent can load, and where each comes from                                     |
| `/export`    | save the last answer as a PDF report, the transcript as Markdown, or both                         |
| `/copy`      | copy the last answer to the clipboard                                                             |
| `/changelog` | what changed in this version                                                                      |
| `/exit`      | leave                                                                                             |

`/help` lists the commands and keys, and links to the project.

`/agents` and `/skills` list one row each, built-in first, then yours by the folder they come from. `/agents <name>` and `/skills <name>` show one in full.

`/export` asks what to save and where, offering `tradingagents-<session>` in the current directory. The PDF report sets the last answer out with its title, the date, the model, the question, the answer with its tables, and the numbered sources. `/export pdf [file]` and `/export md [file]` save one directly.

`/copy` copies the last answer as Markdown, with its sources. It works over SSH and inside tmux when the terminal lets programs set the clipboard; macOS Terminal and GNOME Terminal do not, and `/export md` is the way there.

The row under the input shows the mode (auto in green, plan in amber), the model and the version.

### Modes

In auto mode, the default, the agent decides how deep to go and which of its agents to ask. In plan mode it first replies with a research plan: what it will look at, which agents and skills it will use, and what the answer will cover. When a plan is ready, it asks in place of the input whether to run it: Run it runs the plan as it stands and switches the session to auto mode, and a change typed on the last row is answered with a revised plan, offered the same way. Esc leaves it for the input. Shift+Tab switches the mode for the next question; a resumed session goes on in the mode its last question was asked in, with a plan that was ready still offered.

## Sources

An answer marks each figure with the result it comes from, numbered in the order they appear: `[1]`, `[2]`. A list of sources follows the answer, one line each: the tool, what it was asked, where the data came from and its date.

```text
Sources:
[1] correlation AAPL, MSFT (returns) (computed, as of 2026-11-19)
[2] price_history AAPL 1y daily (Tauric, as of 2026-11-19)
```

`-p` prints the same list after the answer, and with `--json` the closing `turn.completed` event carries it as `sources`.

## One question

`tradingagents -p "question"` answers one question and prints the answer; warnings and the time and tokens it took go to standard error. With `--json`, every event is printed as a JSON line instead, for programs and other agents.

| Exit code | Meaning                                                               |
| --------- | --------------------------------------------------------------------- |
| 0         | answered                                                              |
| 1         | failed                                                                |
| 2         | wrong usage, or no model set                                          |
| 3         | stopped at a limit (time, steps or tokens); the answer may be partial |
| 130       | stopped (Ctrl+C or a termination signal)                              |

## Sessions

Every session is kept. `tradingagents sessions` lists them, newest first; `--continue` takes up the latest and `--resume <id>` a given one, in the terminal or with `-p`.

`tradingagents sessions delete <id>` deletes a session, here and, when sync is on, from your Tauric account. It asks first at a terminal; without one it needs `--yes`. An open session is never deleted.

## Agents and skills

The main agent answers with its own tools: data tools, compute tools for arithmetic, statistics, technical indicators, portfolio risk and weights over what it has read, a plan, memory, and the results it has recorded. For depth it briefs a specialist agent (`run_agent`), which researches the brief in its own context with its own tools and reports back with its sources; a broad question can go to several at once. For a known kind of research it loads a skill: the method it follows.

| Agent                      | Researches                                                                                                           |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| Equity Research (`equity`) | a company's business and results: statements and filings, estimates, valuation and peers, ownership, news and events |
| Macro Strategy (`macro`)   | the economy and markets as a whole: growth, inflation, rates and the yield curve, sectors, event odds, macro news    |
| Quant Research (`quant`)   | how instruments have traded: returns, volatility and drawdowns, correlation and beta, technicals, screens            |
| Risk Analysis (`risk`)     | what could make a position lose: drawdowns and tail risk, balance-sheet strength, the events ahead                   |

| Skill                  | Group     | For                                                                         |
| ---------------------- | --------- | --------------------------------------------------------------------------- |
| full-analysis          | Companies | a full analysis of one company, from every specialist, weighed into a view  |
| company-snapshot       | Companies | a quick picture of one stock                                                |
| earnings-preview       | Companies | what to expect from the next earnings report                                |
| earnings-review        | Companies | what the latest quarter showed                                              |
| filing-review          | Companies | what the latest 10-K or 10-Q says, and what changed                         |
| dcf-valuation          | Valuation | an intrinsic value from a discounted cash flow                              |
| relative-valuation     | Valuation | valuation against peers on multiples                                        |
| scenario-analysis      | Valuation | bull, base and bear cases, each with its drivers and what would show it     |
| market-brief           | Markets   | what moved markets in the latest session                                    |
| macro-outlook          | Markets   | the state of the US economy and markets' macro picture                      |
| sector-review          | Markets   | one sector against the market, its leaders and laggards, its valuations     |
| performance-comparison | Markets   | two to five instruments side by side                                        |
| technical-analysis     | Markets   | one instrument's trend, momentum, volatility and price levels               |
| risk-assessment        | Risk      | the risks of holding a stock or another instrument                          |
| portfolio-review       | Risk      | how a set of holdings behaves together, and how other weights would compare |
| thesis-review          | Risk      | a challenge to a view: the case against, a pre-mortem, what would break it  |

`/agents` and `/skills` list what a session has, and where each comes from.

## Your own agents and skills

Add your own agents and skills as Markdown files:

### Agents

Each agent is one file, `~/.tauric/tradingagents/agents/<name>.md`; a file named like a built-in agent replaces it. The settings go between `---` lines at the top, one `key: value` per line, and the instructions follow:

<!-- biome-ignore format: the example opens with front matter -->
```markdown
---
name: charts
label: Chart reader
description: How one stock has traded: trend, moving averages and momentum.
tools: [quote, price_history, technicals]
steps: 8
---

You are a chart reader. Study how the stock has traded and report what the numbers show...
```

| Setting       | Means                                                                                                            |
| ------------- | ---------------------------------------------------------------------------------------------------------------- |
| `name`        | lowercase letters, digits, `-` or `_`                                                                            |
| `label`       | what the transcript calls the agent while it works                                                               |
| `description` | when to ask it; the main agent reads this                                                                        |
| `tools`       | the data tools it may call, by name or with `*` (`price_*`); none for an agent that argues from what it is given |
| `skills`      | skills whose methods are added to its instructions                                                               |
| `steps`       | its step limit (default 15)                                                                                      |
| `tier`        | `quick` (default) or `deep`                                                                                      |

Every agent also has the compute tools and can read recorded results. An agent is offered when every tool it names has a source in the session; `/agents` marks one that is not.

### Skills

Skills follow the Agent Skills standard, so a skill written for another agent client works here too. A skill is a directory with a `SKILL.md`, read from these places, the first of a name winning:

1. `~/.tauric/tradingagents/skills/<name>/`
2. `~/.agents/skills/<name>/`, shared between agent clients
3. the built-in skills

`SKILL.md` starts with YAML frontmatter: `name` (lowercase letters, digits and single hyphens, the directory's name) and `description` (what the skill does and when to use it), and optionally `license`, `compatibility`, `metadata` and `allowed-tools`, which is accepted but does not limit the tools. The method follows in Markdown. Text files under `references/` and `assets/` go with the skill, and the main agent reads them when the method calls for them. Files under `scripts/` are not run: TradingAgents has no shell.

A skill that departs from the standard still loads, with a warning; one without a description, or whose frontmatter is not valid YAML, is skipped. A file that cannot be used is named at start with the reason, as is a skill that takes the place of another.

## Sync

With a Tauric API key, sessions can be copied to your Tauric account as they are saved. Sync is off until you turn it on: the app asks once, after it opens, with Turn on or Keep off; Esc leaves the question for the next start.

```bash
tradingagents sync on        # or: off, status
```

A synced copy holds your questions, the answers, the tools' arguments and results, the agents' work, and anything recalled from memory. The complete data behind a result is copied only for Tauric's own data; for other sources, and for a result too large to sync, only the text the model read. Turning sync on copies the current session from its start; turning it off deletes nothing already copied. Copies count toward your account's storage allowance.

With sync on, sessions in your account that are not on this computer show in `/resume` and in `tradingagents sessions`, marked as in your account. Opening one (from `/resume`, or with `--resume <id>`) copies it here and continues it, and it keeps syncing as any session does. A copy holds what was synced, so results from other sources, and results too large to sync, come back as the text the model read. A session on both computers is the one here; if its copy in your account differs, sync pauses for that session and says so.

Deleting a session (`/resume`, then Ctrl+D, or `tradingagents sessions delete <id>`) deletes its copy too, and works on one that is only in your account.

## Limits

A question runs until it is answered or you stop it. By default only steps are capped, to keep a run from looping: 30 for the main agent, and each agent's own. Set limits in `config.json` under `limits`, or for one run with `--limit`:

```bash
tradingagents -p "Full analysis of AAPL" --limit question.time=20m --limit question.tokens=2000000
```

| Key                                       | Limits                                                                  |
| ----------------------------------------- | ----------------------------------------------------------------------- |
| `question.steps`                          | the main agent's steps                                                  |
| `question.tokens`, `question.time`        | the whole question, agents included                                     |
| `agents.<name>.steps`, `.tokens`, `.time` | one agent, by name                                                      |
| `subagentsPerQuestion`                    | how many agent runs a question may start                                |
| `output.stepTokens`, `output.finalTokens` | what one step may write, and the answer written once a limit is reached |
| `modelStall`                              | how long the model may send nothing before the request is ended         |

Times are durations such as `90s`, `20m` or `2h`. With a time limit, research stops early enough to leave time to write the answer from what was gathered. A model's own output limit always holds.
