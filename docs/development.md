# Development Guide — DEXAgents

## Setup

```bash
git clone https://github.com/BrunoNatalicio/DEXAgents.git
cd DEXAgents

# Environment
uv venv
.venv\Scripts\activate       # Windows
source .venv/bin/activate    # macOS/Linux

uv pip install -r requirements.txt
uv pip install -e .

# Git hooks (auto-runs ruff + black before every commit)
uv run pre-commit install
```

---

## Branching Strategy

```
main                    # Production-stable
  └── feature/xxx       # Feature branches (via git worktree)
```

All work is done in **git worktrees** to avoid stashing WIP:

```bash
# Create a new isolated worktree
git worktree add .worktrees/my-feature -b feature/my-feature

# List active worktrees
git worktree list

# Remove when done
git worktree remove .worktrees/my-feature
```

---

## Test-Driven Development (TDD)

All new features follow **RED → GREEN → REFACTOR**:

1. **RED**: Write a failing test that defines the expected behaviour
2. **GREEN**: Write the minimum code to make it pass
3. **REFACTOR**: Clean up while keeping tests green

```bash
# Run all tests
uv run pytest tests/ -v

# Run a specific test file
uv run pytest tests/test_jupiter_executor.py -v

# Run with short traceback
uv run pytest tests/ --tb=short
```

### Testing Network Calls

All HTTP calls (Jupiter API, 1inch API, Solana RPC) are mocked using `unittest.mock.patch`.
Never write tests that make real network calls — they fail in CI and waste quota.

```python
@patch('tradingagents.execution.jupiter_executor.VersionedTransaction')
@patch('httpx.AsyncClient')
async def test_get_quote(mock_client, mock_tx):
    # Mock the response, not the real API
    mock_client.return_value.__aenter__.return_value.get.return_value = MagicMock(...)
```

---

## Code Quality

Pre-commit hooks run automatically on `git commit`:

| Tool | Purpose |
|---|---|
| `black` | Code formatting |
| `ruff` | Linting + import sorting |
| `trailing-whitespace` | Clean files |
| `end-of-file-fixer` | POSIX compliance |

Run manually:
```bash
uv run pre-commit run --all-files
```

---

## CI/CD (GitHub Actions)

On every `push` and `pull_request` to `main`:

1. Setup Python + `uv`
2. Install dependencies
3. Run `black --check`
4. Run `ruff check`

See `.github/workflows/ci.yml`.

---

## Adding a New Analyst

1. Create `tradingagents/agents/analysts/my_analyst.py`
2. Write a `create_my_analyst(llm, toolkit)` factory function
3. Write a prompt constant `MY_ANALYST_PROMPT`
4. Register in `tradingagents/graph/trading_graph.py`
5. Write tests in `tests/test_my_analyst.py`

---

## Adding a New Execution Engine

1. Create `tradingagents/execution/my_executor.py`
2. Inherit from `BaseExecutor`
3. Implement: `execute_swap`, `get_quote`, `get_wallet_balance`
4. Export from `tradingagents/execution/__init__.py`
5. Write tests with mocked HTTP and chain clients

```python
from tradingagents.execution.base_executor import BaseExecutor, TradeOrder, TradeResult

class MyExecutor(BaseExecutor):
    async def execute_swap(self, order: TradeOrder) -> TradeResult: ...
    async def get_quote(self, order: TradeOrder) -> dict: ...
    async def get_wallet_balance(self, token_address: str) -> float: ...
```

---

## Security Checklist

- [ ] `.env` is in `.gitignore` → never commit secrets
- [ ] Private keys read from env vars only, never hardcoded
- [ ] All user inputs validated before use
- [ ] No `print(private_key)` or similar logging of secrets
- [ ] `GOOGLE_SEARCH_DAILY_LIMIT` set to prevent runaway API costs
- [ ] Devnet/testnet first before mainnet execution
