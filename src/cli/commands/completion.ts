#!/usr/bin/env bun
/**
 * Generate shell completion scripts.
 *
 * Usage: trading completion <bash|zsh|fish>
 */

import { defineCommand } from "citty"

const COMMANDS = [
  "plan",
  "execute",
  "ig",
  "portfolio",
  "watchlist",
  "signals",
  "trades",
  "prices",
  "config",
  "seed",
  "sync",
  "backup",
  "analyze",
  "summarize",
  "completion",
  "help",
]

const IG_SUBCOMMANDS = ["login", "accounts", "search", "prices", "positions", "buy", "sell"]

const CONFIG_SUBCOMMANDS = ["get", "set", "list", "delete", "path"]

function bashCompletion(): string {
  const cmdList = COMMANDS.join(" ")
  const igList = IG_SUBCOMMANDS.join(" ")
  const cfgList = CONFIG_SUBCOMMANDS.join(" ")
  return `#!/bin/bash
# trading CLI bash completion
_trading_completions() {
    local cur=\${COMP_WORDS[COMP_CWORD]}
    local prev=\${COMP_WORDS[COMP_CWORD-1]}

    if [ $COMP_CWORD -eq 1 ]; then
        COMPREPLY=($(compgen -W "${cmdList}" -- "$cur"))
        return 0
    fi

    if [ "$prev" = "ig" ]; then
        COMPREPLY=($(compgen -W "${igList}" -- "$cur"))
        return 0
    fi

    if [ "$prev" = "config" ]; then
        COMPREPLY=($(compgen -W "${cfgList}" -- "$cur"))
        return 0
    fi

    return 0
}
complete -F _trading_completions trading
`
}

function zshCompletion(): string {
  const _cmdList = COMMANDS.join(" ")
  const _igList = IG_SUBCOMMANDS.join(" ")
  const _cfgList = CONFIG_SUBCOMMANDS.join(" ")
  return `#!/bin/zsh
# trading CLI zsh completion
_trading() {
    local curcontext="$curcontext" state line
    typeset -A opt_args

    _arguments -C \\
        '1: :->command' \\
        '*:: :->args'

    case "$state" in
        command)
            _values 'trading command' \\
                ${COMMANDS.map((c) => `"${c}"`).join(" \\\n                ")}
            ;;
        args)
            case "$line[1]" in
                ig)
                    _values 'ig subcommand' \\
                        ${IG_SUBCOMMANDS.map((c) => `"${c}"`).join(" \\\n                        ")}
                    ;;
                config)
                    _values 'config subcommand' \\
                        ${CONFIG_SUBCOMMANDS.map((c) => `"${c}"`).join(" \\\n                        ")}
                    ;;
            esac
            ;;
    esac
}
compdef _trading trading
`
}

function fishCompletion(): string {
  const lines: string[] = []
  for (const cmd of COMMANDS) {
    lines.push(`complete -c trading -f -n "__fish_use_subcommand" -a "${cmd}"`)
  }
  for (const sub of IG_SUBCOMMANDS) {
    lines.push(`complete -c trading -f -n "__fish_seen_subcommand_from ig" -a "${sub}"`)
  }
  for (const sub of CONFIG_SUBCOMMANDS) {
    lines.push(`complete -c trading -f -n "__fish_seen_subcommand_from config" -a "${sub}"`)
  }
  return `#!/bin/fish
# trading CLI fish completion
${lines.join("\n")}
`
}

export const completionCommand = defineCommand({
  meta: {
    name: "completion",
    description: "Generate shell completion script",
  },
  args: {
    shell: {
      type: "positional",
      description: "Shell type (bash, zsh, fish)",
      required: true,
    },
  },
  run: ({ args }) => {
    const shell = args.shell.toLowerCase()

    switch (shell) {
      case "bash":
        console.log(bashCompletion())
        break
      case "zsh":
        console.log(zshCompletion())
        break
      case "fish":
        console.log(fishCompletion())
        break
      default:
        console.error(`❌ Unknown shell: ${shell}. Supported: bash, zsh, fish`)
        process.exit(1)
    }

    console.error("")
    console.error(`# To enable completions, add this to your shell config:`)
    console.error(`#   bash: eval "$(trading completion bash)" >> ~/.bashrc`)
    console.error(`#   zsh:  eval "$(trading completion zsh)" >> ~/.zshrc`)
    console.error(`#   fish: trading completion fish > ~/.config/fish/completions/trading.fish`)
  },
})
