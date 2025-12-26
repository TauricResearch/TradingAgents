# REST API Reference

TradingAgents provides a FastAPI backend for programmatic access to trading functionality.

## Overview

The REST API is built on FastAPI with:
- Async/await support for high performance
- JWT authentication for secure access
- SQLAlchemy 2.0 async ORM
- Pydantic validation for requests/responses
- OpenAPI documentation at `/docs`

## Running the API

```bash
# Start development server
uvicorn tradingagents.api.main:app --reload --port 8000

# Production (with gunicorn)
gunicorn tradingagents.api.main:app -w 4 -k uvicorn.workers.UvicornWorker
```

## Authentication

### Login

```http
POST /api/v1/auth/login
Content-Type: application/x-www-form-urlencoded

username=user@example.com&password=SecurePassword123
```

Response:
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9...",
  "token_type": "bearer"
}
```

### Using the Token

Include the token in subsequent requests:

```http
GET /api/v1/strategies
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9...
```

### Token Expiration

Tokens expire after 30 minutes by default. Configure via `JWT_EXPIRATION_MINUTES` environment variable.

## Endpoints

### Health Check

```http
GET /health
```

Response:
```json
{
  "status": "healthy",
  "version": "1.0.0"
}
```

### Strategies

#### List Strategies

```http
GET /api/v1/strategies
Authorization: Bearer <token>
```

Query parameters:
- `skip` (int): Pagination offset (default: 0)
- `limit` (int): Page size (default: 100, max: 1000)
- `active_only` (bool): Filter to active strategies only

Response:
```json
{
  "items": [
    {
      "id": 1,
      "name": "Moving Average Crossover",
      "description": "Simple MA crossover strategy",
      "parameters": {"fast_period": 10, "slow_period": 20},
      "is_active": true,
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-15T10:30:00Z"
    }
  ],
  "total": 1,
  "skip": 0,
  "limit": 100
}
```

#### Create Strategy

```http
POST /api/v1/strategies
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "RSI Mean Reversion",
  "description": "Buy oversold, sell overbought",
  "parameters": {
    "rsi_period": 14,
    "oversold": 30,
    "overbought": 70
  },
  "is_active": true
}
```

Response (201 Created):
```json
{
  "id": 2,
  "name": "RSI Mean Reversion",
  "description": "Buy oversold, sell overbought",
  "parameters": {
    "rsi_period": 14,
    "oversold": 30,
    "overbought": 70
  },
  "is_active": true,
  "created_at": "2024-01-15T11:00:00Z",
  "updated_at": "2024-01-15T11:00:00Z"
}
```

#### Get Strategy

```http
GET /api/v1/strategies/{id}
Authorization: Bearer <token>
```

#### Update Strategy

```http
PUT /api/v1/strategies/{id}
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "Updated Strategy Name",
  "parameters": {"new_param": 42}
}
```

#### Delete Strategy

```http
DELETE /api/v1/strategies/{id}
Authorization: Bearer <token>
```

Response (204 No Content)

## Error Responses

All errors return JSON with consistent structure:

```json
{
  "detail": "Error message here"
}
```

### Common Status Codes

| Code | Description |
|------|-------------|
| 400 | Bad Request - Invalid input |
| 401 | Unauthorized - Invalid or missing token |
| 403 | Forbidden - Insufficient permissions |
| 404 | Not Found - Resource doesn't exist |
| 409 | Conflict - Duplicate resource |
| 422 | Validation Error - Failed Pydantic validation |
| 500 | Internal Server Error |

### Validation Errors

```json
{
  "detail": [
    {
      "loc": ["body", "name"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./tradingagents.db` | Database connection string |
| `JWT_SECRET_KEY` | Required | Secret key for JWT signing |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `JWT_EXPIRATION_MINUTES` | `30` | Token expiration time |
| `CORS_ORIGINS` | `["*"]` | Allowed CORS origins |
| `SQLALCHEMY_ECHO` | `false` | Log SQL queries |

## Database Migrations

The API uses Alembic for database migrations:

```bash
# Create new migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

## OpenAPI Documentation

Interactive API documentation is available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

## Python Client Example

```python
import httpx

async def main():
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        # Login
        response = await client.post("/api/v1/auth/login", data={
            "username": "user@example.com",
            "password": "password123"
        })
        token = response.json()["access_token"]

        headers = {"Authorization": f"Bearer {token}"}

        # List strategies
        response = await client.get("/api/v1/strategies", headers=headers)
        strategies = response.json()["items"]

        # Create strategy
        response = await client.post("/api/v1/strategies", headers=headers, json={
            "name": "New Strategy",
            "description": "Test",
            "parameters": {},
        })
        new_strategy = response.json()

        print(f"Created strategy: {new_strategy['id']}")

import asyncio
asyncio.run(main())
```

## See Also

- [Authentication Guide](../guides/authentication.md)
- [Database Models](../api/database-models.md)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
