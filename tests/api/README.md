# FastAPI Backend Tests (Issue #48)

This directory contains comprehensive test coverage for the FastAPI backend implementation following **Test-Driven Development (TDD)** principles.

## Test Status: RED Phase ✗

Tests have been written BEFORE implementation. Current status:
- **155 tests FAILING** (expected - no implementation yet)
- **37 tests SKIPPED** (waiting for imports)
- **16 tests PASSED** (placeholder tests)

## Test Structure

### Test Files

1. **test_auth.py** (41 tests)
   - Password hashing with Argon2 (via pwdlib)
   - JWT token generation and validation
   - Login endpoint (POST /api/v1/auth/login)
   - Protected endpoint authentication
   - Security tests (timing attacks, token leakage, rate limiting)

2. **test_strategies.py** (95 tests)
   - List strategies (GET /api/v1/strategies)
   - Create strategy (POST /api/v1/strategies)
   - Get single strategy (GET /api/v1/strategies/{id})
   - Update strategy (PUT /api/v1/strategies/{id})
   - Delete strategy (DELETE /api/v1/strategies/{id})
   - User isolation and authorization
   - Pagination and filtering
   - Edge cases (SQL injection, XSS, Unicode, concurrency)

3. **test_middleware.py** (48 tests)
   - Error handling (401, 404, 422, 500)
   - Request logging
   - CORS configuration
   - Request ID tracking
   - Rate limiting
   - Content negotiation
   - Security headers

4. **test_models.py** (45 tests)
   - User model (username, email, password, timestamps)
   - Strategy model (name, description, parameters, is_active)
   - Relationships (User -> Strategies)
   - Constraints (unique, foreign key)
   - Cascade delete
   - Complex queries

5. **test_config.py** (24 tests)
   - Settings loading from environment
   - JWT configuration
   - Database URL
   - CORS settings
   - Environment-specific config
   - Configuration validation

6. **test_migrations.py** (32 tests)
   - Alembic migration files
   - Migration execution (upgrade/downgrade)
   - Schema validation
   - Migration history
   - Edge cases

### Shared Fixtures (conftest.py)

- **Database fixtures**: `db_engine`, `db_session`, `clean_db`
- **FastAPI fixtures**: `test_app`, `client`
- **Auth fixtures**: `test_user`, `jwt_token`, `auth_headers`
- **Strategy fixtures**: `strategy_data`, `test_strategy`, `multiple_strategies`
- **Security fixtures**: `sample_sql_injection_payloads`, `sample_xss_payloads`

## Running Tests

### Run all API tests
```bash
pytest tests/api/ --tb=line -q
```

### Run specific test file
```bash
pytest tests/api/test_auth.py -v
```

### Run specific test class
```bash
pytest tests/api/test_auth.py::TestPasswordHashing -v
```

### Run with coverage
```bash
pytest tests/api/ --cov=tradingagents.api --cov-report=html
```

## Test Coverage Goals

Target: **80%+ coverage** across all modules

### Coverage Areas

- **Authentication**: Password hashing, JWT tokens, login flow
- **Authorization**: User isolation, token validation, protected endpoints
- **CRUD Operations**: Create, Read, Update, Delete for strategies
- **Database**: Models, relationships, constraints, migrations
- **Error Handling**: Consistent error responses, no stack trace leaks
- **Security**: SQL injection prevention, XSS prevention, rate limiting
- **Edge Cases**: Unicode, large payloads, concurrent requests

## Implementation Plan

After tests are written (current state), implementation will follow this order:

1. **Models** (`tradingagents/api/models/`)
   - User model
   - Strategy model
   - Base configuration

2. **Database** (`tradingagents/api/database.py`)
   - Async SQLAlchemy engine
   - Session management

3. **Configuration** (`tradingagents/api/config.py`)
   - Settings with Pydantic
   - Environment variable loading

4. **Services** (`tradingagents/api/services/`)
   - auth_service.py (password hashing, JWT)

5. **Routes** (`tradingagents/api/routes/`)
   - auth.py (login endpoint)
   - strategies.py (CRUD endpoints)

6. **Middleware** (`tradingagents/api/middleware/`)
   - Error handling
   - Request logging

7. **Dependencies** (`tradingagents/api/dependencies.py`)
   - Database session dependency
   - Current user dependency

8. **Main App** (`tradingagents/api/main.py`)
   - FastAPI application
   - Router registration
   - Middleware setup

9. **Alembic Migrations**
   - Initialize Alembic
   - Create initial migration
   - Test migration execution

## Expected Implementation Dependencies

```toml
[project.dependencies]
fastapi = ">=0.100.0"
uvicorn = ">=0.23.0"
sqlalchemy = ">=2.0.0"
asyncpg = ">=0.29.0"  # For PostgreSQL
aiosqlite = ">=0.19.0"  # For SQLite
alembic = ">=1.12.0"
pydantic = ">=2.0.0"
pydantic-settings = ">=2.0.0"
python-jose[cryptography] = ">=3.3.0"  # For JWT
pwdlib[argon2] = ">=0.2.0"  # For password hashing
python-multipart = ">=0.0.6"  # For form data
httpx = ">=0.24.0"  # For testing
pytest-asyncio = ">=0.21.0"
```

## TDD Workflow

1. **RED**: Write tests that fail (CURRENT STATE)
2. **GREEN**: Implement minimum code to pass tests
3. **REFACTOR**: Improve code quality while keeping tests green

## Next Steps

1. Run tests to verify RED phase: `pytest tests/api/ --tb=line -q`
2. Implement models and database setup
3. Implement authentication service
4. Implement API endpoints
5. Implement middleware
6. Run tests to achieve GREEN phase
7. Refactor for code quality

## Notes

- All async tests use `pytest.mark.asyncio`
- Tests use httpx.AsyncClient for API calls
- Database tests use SQLite in-memory for speed
- Security tests validate SQL injection and XSS prevention
- Edge case tests ensure robust error handling
