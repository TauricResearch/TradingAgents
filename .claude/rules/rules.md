# Coding Rules

## General
- Write clear, readable code over clever code.
- Keep functions small and focused — one responsibility per function.
- Avoid deep nesting; prefer early returns.
- Delete dead code; don't comment it out.
- No magic numbers — use named constants.

## Python
- Target Python 3.11+; use modern syntax (match/case, `X | Y` unions, etc.).
- Use type hints on all public functions and methods.
- Prefer `pathlib.Path` over `os.path`.
- Use f-strings for string formatting.
- Use `dataclasses` or `pydantic` for structured data, not plain dicts.
- Raise specific exceptions, never bare `except:` or `except Exception:` silently.
- Use `logging` instead of `print` for anything that isn't direct user output.

## Naming
- `snake_case` for variables, functions, modules.
- `PascalCase` for classes.
- `UPPER_SNAKE_CASE` for module-level constants.
- Prefix private helpers with `_`.
- Boolean variables/functions should read as predicates: `is_ready`, `has_error`.

## Project Layout (Domain Driven Design)
Organize code by domain, not by layer. Each domain is a self-contained vertical slice.

```
src/silvie_agent/
├── domain/                  # Pure business logic — no I/O, no frameworks
│   └── <domain>/
│       ├── models.py        # Entities and value objects
│       ├── repository.py    # Abstract repository interfaces (ABC)
│       └── services.py      # Domain services (pure logic)
├── application/             # Use cases / orchestration — coordinates domain + infra
│   └── <domain>/
│       ├── commands.py      # Command objects (write intents)
│       ├── queries.py       # Query objects (read intents)
│       └── handlers.py      # Use case handlers
├── infrastructure/          # Concrete implementations of domain interfaces
│   └── <domain>/
│       ├── repository.py    # DB / API / file-backed repository implementations
│       └── adapters.py      # External service adapters
└── interfaces/              # Entry points (CLI, API, etc.)
    └── <domain>/
        └── routes.py        # HTTP routes, CLI commands, event consumers

tests/
└── <domain>/
    ├── test_models.py
    ├── test_services.py
    ├── test_handlers.py
    └── test_repository.py
```

**Rules:**
- `domain/` has zero dependencies on `infrastructure/` or `interfaces/` — dependency flows inward.
- Entities and value objects in `domain/models.py` are plain Python (`dataclass` or `pydantic`).
- Repository interfaces live in `domain/`; their implementations live in `infrastructure/`.
- Application layer depends on domain abstractions, never on concrete infrastructure.
- Cross-domain communication goes through application-layer interfaces, not direct imports.
- Name folders after the bounded context (e.g., `agent/`, `memory/`, `tasks/`), not generic layers.

## Testing
- Every public function should have at least one test.
- Test file naming: `test_<module>.py`.
- Use `pytest` fixtures for shared setup; avoid global state in tests.
- Prefer real behavior over mocks; only mock at I/O boundaries (network, disk, time).
- Run tests before committing: `pytest --tb=short`.

## Git
- Commit messages use imperative mood: "Add feature" not "Added feature".
- One logical change per commit.
- Never commit secrets, `.env` files, or credentials.
- Branch names: `feat/`, `fix/`, `chore/` prefixes.

## Dependencies
- Pin direct dependencies with minimum versions (`>=`), not exact pins, in `pyproject.toml`.
- Add new dependencies to `[project.dependencies]` (runtime) or `[project.optional-dependencies] dev` (dev-only).
- Keep `environment.yml` in sync when adding conda-managed packages.

## Security
- Never log or print sensitive data (tokens, passwords, PII).
- Validate all external input at the boundary (API responses, user input, file content).
- Use `secrets` module for generating tokens, not `random`.
