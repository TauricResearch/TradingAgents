# src — Production TypeScript

All production TypeScript code lives here. Everything in `src/` must pass
`just check` (strict types, Biome lint, no raw Database instances).

## Structure

```
src/
├── server/         # Hono dashboard server
│   ├── index.tsx   # Entry point
│   ├── routes/     # HTTP route handlers
│   ├── views/      # HTMX + JSX views
│   ├── static/     # CSS, fonts, client-side JS
│   └── lib/        # Server-only modules (NOT imported outside src/server/)
├── cli/            # TypeScript CLI
│   ├── main.ts     # Entry point
│   ├── commands/   # Subcommands (plan, help, ...)
│   └── lib/        # CLI helpers
└── lib/            # Shared production modules
    ├── db.ts       # DatabaseFactory (singleton, WAL, pragmas)
    └── ...         # Anything imported by both server/ and cli/
```

## Boundary Rules

| Directory | Can Import From | Cannot Import From |
|-----------|---------------|-------------------|
| `src/server/` | `src/lib/`, `src/server/lib/` | `scripts/`, `cli/` (Python) |
| `src/cli/` | `src/lib/`, `src/cli/lib/` | `scripts/`, `src/server/lib/` |
| `src/lib/` | Nothing lower (leaf node) | `src/server/lib/`, `src/cli/lib/` |
| `src/server/lib/` | `src/lib/` | `src/cli/`, `scripts/` |
| `scripts/` | `src/lib/` | Nothing — support code only |

## Promotion Path

```
scripts/lab/foo.ts      # Experiment (Tier 0)
    ↓ (proven, add types)
scripts/foo.ts          # Internal tool (Tier 1)
    ↓ (enforced strict, add tests)
src/lib/foo.ts          # Production module (Tier 2)
```

## Checking

```bash
just check    # tsc + biome + database-usage gate
```

## Running the Server

```bash
just serve        # Development mode (port 3000)
just serve-test   # Test mode (test_portfolio.db)
just start        # Background daemon (logs to ~/.tradingagents/server.log)
```

## Running the CLI

```bash
bun run trading plan AAPL --platform ig --mode shares
```
