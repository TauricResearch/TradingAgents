---
name: api-design
version: 1.0.0
type: knowledge
description: REST API design best practices, versioning strategies, error handling, pagination, and OpenAPI documentation. Use when designing or implementing REST APIs, HTTP endpoints, or API documentation.
keywords: api, rest, endpoint, http, json, openapi, swagger, versioning, pagination, api design
auto_activate: true
allowed-tools: [Read]
---

# API Design Skill

REST API design best practices, HTTP conventions, versioning, error handling, and documentation standards.

## When This Skill Activates

- Designing REST APIs
- Creating HTTP endpoints
- Writing API documentation
- Handling API errors
- Implementing pagination
- API versioning strategies
- Keywords: "api", "rest", "endpoint", "http", "json", "openapi"

---

## Core Concepts

### 1. REST Principles

RESTful resource design using nouns (not verbs), proper HTTP methods, and hierarchical URL structure.

**Key Principles**:
- Resources are nouns: `/users`, `/posts` (not `/getUsers`, `/createPost`)
- Use HTTP methods correctly: GET (read), POST (create), PUT (replace), PATCH (update), DELETE (remove)
- Hierarchical relationships: `/users/123/posts` for related resources
- Keep URLs shallow (max 3 levels)

**See**: `docs/rest-principles.md` for detailed examples and patterns

---

### 2. HTTP Status Codes

Proper status code usage for success (2xx), client errors (4xx), and server errors (5xx).

**Common Codes**:
- **200 OK**: Successful GET/PUT/PATCH
- **201 Created**: Successful POST (includes Location header)
- **204 No Content**: Successful DELETE
- **400 Bad Request**: Invalid input
- **401 Unauthorized**: Authentication required
- **403 Forbidden**: Authenticated but not allowed
- **404 Not Found**: Resource doesn't exist
- **422 Unprocessable**: Validation error
- **429 Too Many Requests**: Rate limit exceeded
- **500 Internal Server Error**: Server failure

**See**: `docs/http-status-codes.md` for complete reference and examples

---

### 3. Error Handling

RFC 7807 Problem Details format for consistent, structured error responses.

**Standard Format**:
```json
{
  "type": "https://example.com/errors/validation-error",
  "title": "Validation Error",
  "status": 422,
  "detail": "Email address is invalid",
  "instance": "/users",
  "errors": {
    "email": ["Must be a valid email address"]
  }
}
```

**See**: `docs/error-handling.md` for implementation patterns and best practices

---

### 4. Request/Response Format

JSON structure conventions for request bodies and response payloads.

**Best Practices**:
- Use `snake_case` for JSON keys
- Include metadata in responses (timestamps, IDs)
- Consistent field naming across endpoints
- Clear data types and structures

**See**: `docs/request-response-format.md` for detailed examples

---

### 5. Pagination

Offset-based and cursor-based pagination strategies for large datasets.

**Offset-Based** (simple, good for small datasets):
```bash
GET /users?page=2&limit=20
```

**Cursor-Based** (scalable, handles real-time updates):
```bash
GET /users?cursor=abc123&limit=20
```

**See**: `docs/pagination.md` for implementation details and trade-offs

---

### 6. API Versioning

URL path versioning (recommended) and header-based versioning strategies.

**URL Path Versioning**:
```bash
/v1/users
/v2/users
```

**When to Version**:
- Breaking changes (removing fields, changing behavior)
- New required fields
- Changed data types

**See**: `docs/versioning.md` for migration strategies and deprecation policies

---

### 7. Authentication & Authorization

API key and JWT authentication patterns for securing endpoints.

**API Key** (simple, good for service-to-service):
```http
Authorization: Bearer sk_live_abc123...
```

**JWT** (stateless, good for user authentication):
```http
Authorization: Bearer eyJhbGc...
```

**See**: `docs/authentication.md` for implementation patterns

---

### 8. Rate Limiting

Rate limit headers and strategies to prevent abuse.

**Standard Headers**:
```http
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1640995200
```

**See**: `docs/rate-limiting.md` for implementation strategies

---

### 9. Advanced Features

CORS configuration, filtering, sorting, and search patterns.

**Topics**:
- CORS headers for browser-based clients
- Query parameter filtering
- Multi-field sorting
- Full-text search

**See**: `docs/advanced-features.md` for detailed patterns

---

### 10. Documentation

OpenAPI/Swagger documentation for API discoverability.

**Auto-Generated** (FastAPI):
```python
@app.get("/users/{user_id}", response_model=User)
def get_user(user_id: int):
    """Get user by ID"""
    return db.get_user(user_id)
```

**See**: `docs/documentation.md` for OpenAPI specifications

---

### 11. Design Patterns

Idempotency, content negotiation, HATEOAS, bulk operations, and webhooks.

**Topics**:
- Idempotency keys for safe retries
- Content negotiation (JSON, XML, etc.)
- HATEOAS for discoverable APIs
- Bulk operations for batch processing
- Webhooks for event notifications

**See**: `docs/idempotency-content-negotiation.md` and `docs/patterns-checklist.md`

---

## Quick Reference

| Pattern | Use Case | Details |
|---------|----------|---------|
| REST Principles | Resource-based URLs | `docs/rest-principles.md` |
| Status Codes | HTTP response codes | `docs/http-status-codes.md` |
| Error Handling | RFC 7807 errors | `docs/error-handling.md` |
| Pagination | Large datasets | `docs/pagination.md` |
| Versioning | Breaking changes | `docs/versioning.md` |
| Authentication | API security | `docs/authentication.md` |
| Rate Limiting | Abuse prevention | `docs/rate-limiting.md` |
| Documentation | OpenAPI/Swagger | `docs/documentation.md` |

---

## API Design Checklist

**Before Launch**:
- [ ] Use RESTful resource naming (nouns, not verbs)
- [ ] Implement proper HTTP status codes
- [ ] Add RFC 7807 error responses
- [ ] Include pagination for collections
- [ ] Add API versioning strategy
- [ ] Implement authentication
- [ ] Add rate limiting
- [ ] Configure CORS (if browser clients)
- [ ] Generate OpenAPI documentation
- [ ] Test idempotency for POST/PUT/DELETE

**See**: `docs/patterns-checklist.md` for complete checklist

---

## Progressive Disclosure

This skill uses progressive disclosure to prevent context bloat:

- **Index** (this file): High-level concepts and quick reference (<500 lines)
- **Detailed docs**: `docs/*.md` files with implementation details (loaded on-demand)

**Available Documentation**:
- `docs/rest-principles.md` - RESTful design patterns
- `docs/http-status-codes.md` - Complete status code reference
- `docs/error-handling.md` - Error response patterns
- `docs/request-response-format.md` - JSON structure conventions
- `docs/pagination.md` - Pagination strategies
- `docs/versioning.md` - API versioning patterns
- `docs/authentication.md` - Authentication methods
- `docs/rate-limiting.md` - Rate limiting implementation
- `docs/advanced-features.md` - CORS, filtering, sorting
- `docs/documentation.md` - OpenAPI/Swagger
- `docs/idempotency-content-negotiation.md` - Advanced patterns
- `docs/patterns-checklist.md` - Design checklist and common patterns

---

## Cross-References

**Related Skills**:
- **error-handling-patterns** - Error handling best practices
- **security-patterns** - API security hardening
- **documentation-guide** - Documentation standards
- **python-standards** - Python API implementation

**Related Libraries**:
- FastAPI - Python API framework with auto-documentation
- Pydantic - Data validation and serialization
- JWT libraries - Token-based authentication

---

## Key Takeaways

1. **Resources are nouns**: `/users`, not `/getUsers`
2. **Use HTTP methods correctly**: GET (read), POST (create), PUT (replace), DELETE (remove)
3. **Return proper status codes**: 200 (success), 201 (created), 404 (not found), 422 (validation error)
4. **Structured errors**: Use RFC 7807 format
5. **Paginate collections**: Offset or cursor-based
6. **Version your API**: URL path versioning (e.g., `/v1/users`)
7. **Secure endpoints**: API keys or JWT
8. **Rate limit**: Prevent abuse
9. **Document thoroughly**: OpenAPI/Swagger
10. **Test idempotency**: Safe retries for POST/PUT/DELETE
