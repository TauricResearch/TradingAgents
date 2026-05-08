# ── hLedger: plain-text accounting ─────────────────────────────────────────
#   Holdings, cash, allocation, prices, backups.
#   Use: just hledger::<recipe>  or aliases: just hl, just hl-cash, etc.

# Default: show available hledger recipes
[group("hledger")]
default:
    @echo "=== hLedger recipes ==="
    @echo ""
    @echo "  just hledger::hl                 — holdings summary with market values"
    @echo "  just hledger::hl-holdings        — holdings only (excludes cash)"
    @echo "  just hledger::hl-cash             — cash balances per platform"
    @echo "  just hledger::hl-accounts         — all accounts defined in journal"
    @echo "  just hledger::hl-prices           — price history"
    @echo "  just hledger::hl-update-prices    — fetch latest prices from Yahoo Finance"
    @echo "  just hledger::hl-allocation      — allocation tree by account"
    @echo "  just hledger::hl-register TICKER  — transaction history for a ticker"
    @echo "  just hledger::hl-net-worth        — net worth over time"
    @echo "  just hledger::hl-backup           — backup hledger journal"
    @echo "  just hledger::hl-backup-verify    — verify latest backup integrity"
    @echo "  just hledger::hl-backup-restore FILE"
    @echo ""
    @echo "Or use aliases: just hl, just hl-cash, just hl-prices, ..."

# Holdings summary with market values
[group("hledger")]
hl:
    hledger -f "${HLEDGER_FILE:-~/.hledger.journal}" balance --tree --value end

# Holdings only (excludes cash)
[group("hledger")]
hl-holdings:
    hledger -f "${HLEDGER_FILE:-~/.hledger.journal}" balance assets: --tree

# Cash balances per platform
[group("hledger")]
hl-cash:
    hledger -f "${HLEDGER_FILE:-~/.hledger.journal}" balance assets: --tree | grep -E "(cash|EUR|USD)"

# All accounts defined in journal
[group("hledger")]
hl-accounts:
    hledger -f "${HLEDGER_FILE:-~/.hledger.journal}" accounts

# Backup hledger journal
[group("hledger")]
hl-backup:
    ~/.tradingagents/bin/backup-hledger.sh

# Verify latest backup integrity
[group("hledger")]
hl-backup-verify:
    ~/.tradingagents/bin/backup-hledger.sh --verify

# Restore hledger from a backup
[group("hledger")]
hl-backup-restore FILE:
    ~/.tradingagents/bin/backup-hledger.sh --restore {{FILE}}

# Price history
[group("hledger")]
hl-prices:
    hledger -f "${HLEDGER_FILE:-~/.hledger.journal}" prices

# Fetch latest prices from Yahoo Finance
[group("hledger")]
hl-update-prices:
    hledger -f "${HLEDGER_FILE:-~/.hledger.journal}" prices --auto

# Allocation tree by account
[group("hledger")]
hl-allocation:
    hledger -f "${HLEDGER_FILE:-~/.hledger.journal}" balance --tree --value end --depth 3

# Transaction history for a ticker
[group("hledger")]
hl-register TICKER:
    hledger -f "${HLEDGER_FILE:-~/.hledger.journal}" reg {{TICKER}}

# Net worth over time
[group("hledger")]
hl-net-worth:
    hledger -f "${HLEDGER_FILE:-~/.hledger.journal}" balance --tree --equity --monthly
