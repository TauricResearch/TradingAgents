---
title: "Just Command Runner Best Practices"
author: "Christopher Hicks"
site: "Christopher Hicks"
published: 2025-11-30T00:00:00Z
source: "https://www.chicks.net/reference/file_formats/just/"
domain: "chicks.net"
language: "en"
description: "What is Just? Just is a handy way to save and run project-specific commands. Think of it as make but without the headaches—no .PHONY recipes needed, actual cross-platform support, and error messages that don’t make you want to throw your keyboard. I’ve been using just for a while now on this site, and it’s become indispensable for managing Hugo builds, git workflows, and various automation tasks. The learning curve is minimal if you’ve ever touched make, but the payoff is substantial."
word_count: 1536
---

## What is Just?

Just is a handy way to save and run project-specific commands. Think of it as `make` but without the headaches—no `.PHONY` recipes needed, actual cross-platform support, and error messages that don’t make you want to throw your keyboard.

I’ve been using just for a while now on this site, and it’s become indispensable for managing Hugo builds, git workflows, and various automation tasks. The learning curve is minimal if you’ve ever touched make, but the payoff is substantial.

## Why Not Make?

Make was designed for building software from source files. Just is designed for running commands. That subtle distinction matters:

- Just works the same on Linux, macOS, and Windows without extra dependencies
- Error messages tell you what’s actually wrong with your justfile
- Unknown recipes and circular dependencies get caught before anything runs
- You don’t need to mark everything as `.PHONY`

## Basic Syntax

Commands live in a `justfile` with make-inspired syntax. The basic pattern:

```just
# comment describing what this does
recipe-name:
    command to run
    another command
```

Run it with `just recipe-name` from anywhere in your project.

## Recipe Fundamentals

### Comments Matter

Always put a comment above each recipe. These show up in `just --list` output, which is how people (including future you) discover what’s available:

```just
# build the Hugo site
hugo:
    TZ=America/Los_Angeles hugo
```

### Parameters

Recipes accept command-line arguments:

```just
# create a new blog post
post branchname:
    hugo new content "content/posts/{{branchname}}.md"
```

Call it: `just post my-great-idea`

Parameters can have defaults:

```just
# build with optional force flag
hugo force='':
    #!/usr/bin/env bash
    if [[ -n "{{force}}" ]]; then
        echo "Forcing rebuild..."
    fi
```

### Dependencies

Recipes can depend on other recipes:

```just
# create PR after running checks
pr: _has_commits && pr_checks
    gh pr create --title "Update" --body "..."
```

The `&&` syntax means both dependencies must succeed before `pr` runs.

### Multi-line Recipes

For anything non-trivial, use a shebang:

```just
# complex bash logic
process:
    #!/usr/bin/env bash
    set -euo pipefail # strict mode

    for file in *.txt; do
        echo "Processing $file"
    done
```

This is way more readable than trying to chain commands with `&&` or semicolons.

## Recipe Attributes

Attributes modify how recipes behave. Stack them above the recipe:

```just
[group('Process')]
[no-cd]
_on_a_branch:
    #!/bin/bash
    if [[ $(git rev-parse --abbrev-ref HEAD) == "main" ]]; then
        exit 100
    fi
```

### Essential Attributes

**`[group('NAME')]`** — Organize recipes into logical groups for `just --list`:

```just
[group('Hugo')]
server:
    hugo server
```

**`[private]`** — Hide recipes from listings. Useful for helpers:

```just
[private]
_internal_helper:
    echo "Not shown in just --list"
```

Or just prefix with underscore—same effect:

```just
# this is also private
_another_helper:
    echo "Also hidden"
```

**`[no-cd]`** — Don’t change to justfile’s directory before running. Essential for recipes that operate on the current working directory:

```just
[no-cd]
_has_commits:
    git cherry -v main HEAD
```

**`[confirm]`** — Require confirmation before running:

```just
[confirm]
deploy:
    git push production main
```

Override with `just --yes deploy`.

### Platform-Specific Attributes

Run recipes only on certain operating systems:

```just
[macos]
install-deps:
    brew install hugo

[linux]
install-deps:
    apt-get install hugo
```

Available: `[linux]`, `[macos]`, `[unix]`, `[windows]`

### Other Useful Attributes

**`[parallel]`** — Run dependencies in parallel instead of sequentially.

**`[doc('description')]`** — Set documentation separately from comments.

**`[working-directory('path')]`** — Change working directory for this recipe.

**`[positional-arguments]`** — Enable positional argument handling.

## Variables

Set variables at the top of your justfile:

```just
release_branch := "main"

sync:
    git checkout "{{ release_branch }}"
    git pull
```

Use `{{variable}}` to reference them in recipes.

## Organizing justfiles

### Start Simple

One justfile per project. Don’t over-engineer from day one.

### Scale with Imports

When your justfile gets unwieldy, split it into logical modules:

```just
import? '.just/hugo.just'
import? '.just/gh-process.just'
import? '.just/utility.just'
```

The `?` makes imports optional—useful if you’re sharing justfiles across projects where some modules might not exist.

### Module Structure

I keep specialized functionality in `.just/` directory:

```text
justfile                    # main orchestration
.just/
  hugo.just                 # Hugo-specific commands
  gh-process.just          # Git/GitHub workflow
  pr-hook.just             # PR automation
  utility.just             # Helper functions
```

Each module focuses on one domain. The root justfile stays clean.

### The Default Recipe

Make the first recipe in your justfile show help:

```just
# list recipes (default works without naming it)
list:
    just --list
```

Now `just` with no arguments shows what’s available.

## Patterns I’ve Found Useful

### Timestamped Branches

```just
# start a new branch
branch branchname: _main_branch
    #!/usr/bin/env bash
    NOW=$(just utcdate)
    git checkout -b "$USER/$NOW-{{ branchname }}"

# print UTC date in ISO format
[no-cd]
@utcdate:
    TZ=UTC date +"%Y-%m-%d"
```

Every branch gets an ISO date prefix automatically. Useful for tracking when work started.

### Sanity Checks

Private recipes that error out if preconditions aren’t met:

```just
# error if not on a git branch
[no-cd]
_on_a_branch:
    #!/bin/bash
    if [[ $(git rev-parse --abbrev-ref HEAD) == "main" ]]; then
        echo "You are on the main branch, not a feature branch"
        exit 100
    fi
```

Use as dependencies: `pr: _on_a_branch`

### PR Workflow

```just
# create PR
pr: _has_commits && pr_checks
    #!/usr/bin/env bash
    set -euo pipefail

    # run optional pre-pr hook
    if [[ -e ".just/pr-hook.just" ]]; then
        just _pr-hook
    fi

    git push -u origin HEAD

    # generate PR body from commits
    FIRST_COMMIT=$(git log --format=%s -1)
    gh pr create --title "$FIRST_COMMIT" --body "..."
```

This pattern handles the entire PR creation flow with sanity checks.

### Environment-Specific Setup

```just
# run hugo server
server:
    #!/usr/bin/env bash
    TZ=America/Los_Angeles hugo server
    just hugo # cleanup after server!
```

Set timezone consistently for Hugo’s date handling.

## Best Practices

### Formatting

- Use 4 spaces for indentation
- Run `just --unstable --fmt` to auto-format your justfile
- Add `.editorconfig` entry for justfiles

### Shell Selection

Default is `sh` which means POSIX syntax. For bash-specific features, use shebang recipes:

```just
process:
    #!/usr/bin/env bash
    # now you can use bash arrays, etc.
```

### Error Handling

In bash recipes, use strict mode:

```bash
#!/usr/bin/env bash
set -euo pipefail
```

This catches errors early instead of letting commands fail silently.

### Quote Arguments

Always quote recipe parameters:

```just
post branchname:
    hugo new "content/posts/{{ branchname }}.md"
```

Prevents issues with spaces or special characters.

### Built-in Functions Over Shell Commands

Just has built-in functions that work consistently across platforms. Prefer these over shelling out when possible. Check the [official manual](https://just.systems/man/en/) for the complete list.

### Don’t Hardcode Values

Use parameters or variables instead:

```just
# bad
deploy:
    ssh server1 "systemctl restart app"

# good
deploy server:
    ssh {{ server }} "systemctl restart app"
```

### Comment Everything

Future you (and your teammates) will thank you:

```just
# merge PR and return to main branch
merge: _on_a_branch && sync
    gh pr merge -s -d
```

## Color Output

Just provides built-in ANSI color constants (v1.37.0+) that work out of the box—no need to define them yourself:

```just
# example recipe using built-in constants
build:
    echo "{{GREEN}}Building...{{NORMAL}}"
    echo "{{BLUE}}Processing files...{{NORMAL}}"
    echo "{{RED}}Error occurred!{{NORMAL}}"
```

Available color constants:

**Foreground colors:** `BLACK`, `RED`, `GREEN`, `YELLOW`, `BLUE`, `MAGENTA`, `CYAN`, `WHITE`

**Background colors:** `BG_BLACK`, `BG_RED`, `BG_GREEN`, `BG_YELLOW`, `BG_BLUE`, `BG_MAGENTA`, `BG_CYAN`, `BG_WHITE`

**Text attributes:** `NORMAL` (reset), `BOLD`, `ITALIC`, `UNDERLINE`, `INVERT`, `HIDE`, `STRIKETHROUGH`

**Utility:** `CLEAR` (clears screen)

These are just ANSI escape sequences under the hood, so they work wherever your terminal supports color. Use `NORMAL` to reset formatting back to defaults.

## Built-in Constants

Beyond colors, just provides other useful constants (v1.27.0+):

**String constants:**

- `HEX` or `HEXLOWER` — `"0123456789abcdef"`
- `HEXUPPER` — `"0123456789ABCDEF"`

**Path constants (v1.41.0+):**

- `PATH_SEP` — `"/"` on Unix, `"\"` on Windows
- `PATH_VAR_SEP` — `":"` on Unix, `";"` on Windows

Useful for writing cross-platform recipes:

```just
# works on both Unix and Windows
build-path:
    echo "{{justfile_directory()}}{{PATH_SEP}}build"
```

## Testing and Debugging

### Dry Run

See what would execute without running it:

```bash
just --dry-run recipe-name
```

### List Recipes

Show all available recipes:

```bash
just --list
```

Group them for better organization with `[group('name')]` attributes.

### Evaluate Variables

Check variable values:

```bash
just --evaluate
```

### Verbose Output

See every command before it runs:

```bash
just --verbose recipe-name
```

## Version Management

If you’re using just across multiple projects or in a team, consider pinning the version. I’ve found that just’s backwards compatibility is solid, but explicit versions prevent surprises.

Options:

- mise (formerly rtx)
- asdf
- Specify in your project’s README

## Common Gotchas

### Shellcheck Warnings

Shellcheck doesn’t understand just’s template syntax. Disable warnings for template variables:

```just
process force='':
    #!/usr/bin/env bash
    # force variable is replaced by just
    # shellcheck disable=SC2157
    if [[ -n "{{force}}" ]]; then
        echo "Forcing..."
    fi
```

### Tab vs Spaces

Just works with tabs or spaces, as long as you use them consistently in the same file.

### Working Directory

By default, just changes to the justfile’s directory before running recipes. Use `[no-cd]` if you need to stay in the invocation directory.

## Real Example from This Site

Here’s how I use just for Hugo site management:

```just
import? '.just/hugo.just'
import? '.just/gh-process.just'

# list recipes (default)
list:
    just --list

# start a new post
[group('Process')]
post branchname: _main_branch
    #!/usr/bin/env bash
    NOW=$(just utcdate)
    git co -b "chicks/post/$NOW-{{ branchname }}"
    hugo new content "content/posts/$NOW-{{ branchname }}.md"
```

The imported modules handle Hugo builds, git workflows, and PR creation. The root justfile stays focused on high-level orchestration.

## More Information

The official manual is comprehensive and well-written:

- [Just Programmer’s Manual](https://just.systems/man/en/) — Complete documentation
- [GitHub repository](https://github.com/casey/just) — Source code and issue tracker
- [Attributes reference](https://just.systems/man/en/attributes.html) — All recipe attributes

Just has transformed how I manage project automation. It’s one of those tools that gets out of your way and just works. Start simple, add complexity as needed, and you’ll wonder how you managed without it.

Sources:

- [Just Programmer’s Manual](https://just.systems/man/en/)
- [GitHub - casey/just: 🤖 Just a command runner](https://github.com/casey/just)
- [Attributes - Just Programmer’s Manual](https://just.systems/man/en/attributes.html)
- [Constants - Just Programmer’s Manual](https://just.systems/man/en/constants.html)
- [Shared Tooling for Diverse Systems with just · Field Notes](https://www.stuartellis.name/articles/just-task-runner/)