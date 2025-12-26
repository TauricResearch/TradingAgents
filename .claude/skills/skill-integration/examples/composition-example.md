# Skill Composition Example

Real-world example of combining multiple skills for a complex task.

## Task: Implement Secure User Authentication API

**Requirement**: Add JWT-based authentication with secure password storage, comprehensive tests, and API documentation.

## Skills Involved

This task requires **7 different skills** working together:

1. **api-design** - REST API patterns
2. **security-patterns** - Authentication, JWT, password hashing
3. **database-design** - User table schema, query optimization
4. **python-standards** - Code style, type hints
5. **testing-guide** - Security testing patterns
6. **documentation-guide** - API documentation standards
7. **observability** - Authentication logging

## Progressive Disclosure in Action

### Context Load (Startup)

```
Agent context:
├── implementer agent prompt: ~500 tokens
├── 21 skill metadata: ~1,050 tokens
├── Task description: ~200 tokens
└── Total: ~1,750 tokens (< 1% of budget)
```

### Stage 1: API Design (Minutes 0-5)

**Agent thinks**: "Need to design authentication endpoints"

**Skill activates**: api-design (~4,000 tokens)

```python
# Agent designs endpoints following api-design skill
@app.post("/auth/login")
async def login(credentials: LoginRequest) -> TokenResponse:
    pass

@app.post("/auth/refresh")
async def refresh_token(refresh: RefreshRequest) -> TokenResponse:
    pass

@app.get("/auth/me")
async def get_current_user(user: User = Depends(get_current_user)) -> User:
    pass
```

**Context**: ~5,750 tokens

### Stage 2: Security Implementation (Minutes 5-10)

**Agent thinks**: "Need JWT validation and password hashing"

**Skill activates**: security-patterns (~6,000 tokens)

```python
# Agent implements security following security-patterns skill
from passlib.context import CryptContext
from jose import JWTError, jwt

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
```

**Context**: ~11,750 tokens

### Stage 3: Database Schema (Minutes 10-15)

**Skill activates**: database-design (~3,500 tokens)

```python
# Agent designs schema following database-design skill
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_email_active", "email", "is_active"),
    )
```

**Context**: ~15,250 tokens

### Stage 4: Code Style (Minutes 15-20)

**Skill already loaded**: python-standards (loaded at startup due to agent reference)

```python
# Agent applies python-standards throughout implementation
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

def authenticate_user(
    db: Session, email: str, password: str
) -> Optional[User]:
    """Authenticate user with email and password.

    Args:
        db: Database session
        email: User email address
        password: Plain text password

    Returns:
        User object if authentication successful, None otherwise
    """
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user
```

**Context**: ~15,250 tokens (skill already loaded)

### Stage 5: Testing (Minutes 20-30)

**Skill activates**: testing-guide (~5,000 tokens)

```python
# Agent writes tests following testing-guide skill
import pytest
from fastapi.testclient import TestClient

def test_login_success(client: TestClient, test_user):
    """Test successful user login returns access token."""
    response = client.post(
        "/auth/login",
        json={"email": test_user.email, "password": "testpass123"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"

def test_login_invalid_password(client: TestClient, test_user):
    """Test login with invalid password returns 401."""
    response = client.post(
        "/auth/login",
        json={"email": test_user.email, "password": "wrongpassword"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"

def test_access_protected_endpoint_without_token(client: TestClient):
    """Test accessing protected endpoint without token returns 401."""
    response = client.get("/auth/me")
    assert response.status_code == 401
```

**Context**: ~20,250 tokens

### Stage 6: Documentation (Minutes 30-35)

**Skill activates**: documentation-guide (~4,000 tokens)

```python
# Agent adds API documentation following documentation-guide skill
@app.post(
    "/auth/login",
    response_model=TokenResponse,
    summary="User login",
    description="""
    Authenticate user with email and password.

    Returns access token (15-minute expiry) and refresh token (7-day expiry).

    **Authentication**: None required

    **Rate limiting**: 10 requests per minute per IP

    **Example request**:
    ```json
    {
        "email": "user@example.com",
        "password": "securepassword123"
    }
    ```

    **Example response**:
    ```json
    {
        "access_token": "eyJhbGc...",
        "refresh_token": "eyJhbGc...",
        "token_type": "bearer"
    }
    ```
    """
)
async def login(credentials: LoginRequest) -> TokenResponse:
    pass
```

**Context**: ~24,250 tokens

### Stage 7: Observability (Minutes 35-40)

**Skill activates**: observability (~3,000 tokens)

```python
# Agent adds logging following observability skill
import logging
from opentelemetry import trace

tracer = trace.get_tracer(__name__)
logger = logging.getLogger(__name__)

@app.post("/auth/login")
async def login(credentials: LoginRequest) -> TokenResponse:
    with tracer.start_as_current_span("auth.login") as span:
        span.set_attribute("user.email", credentials.email)

        user = authenticate_user(db, credentials.email, credentials.password)

        if not user:
            logger.warning(
                "Failed login attempt",
                extra={"email": credentials.email, "ip": request.client.host}
            )
            raise HTTPException(status_code=401, detail="Incorrect email or password")

        logger.info(
            "Successful login",
            extra={"user_id": user.id, "ip": request.client.host}
        )

        return create_tokens(user)
```

**Context**: ~27,250 tokens

## Total Token Usage

### Without Progressive Disclosure

If all 7 skills loaded upfront:
```
Agent prompt: 500 tokens
+ 7 skills × 5,000 tokens: 35,000 tokens
+ Task: 200 tokens
= 35,700 tokens before work starts!
```

### With Progressive Disclosure

Skills load as needed throughout implementation:
```
Startup: 1,750 tokens
+ Stage 1 (api-design): +4,000 tokens
+ Stage 2 (security-patterns): +6,000 tokens
+ Stage 3 (database-design): +3,500 tokens
+ Stage 5 (testing-guide): +5,000 tokens
+ Stage 6 (documentation-guide): +4,000 tokens
+ Stage 7 (observability): +3,000 tokens
= ~27,250 tokens total

Savings: 8,450 tokens (24% reduction)
```

## Key Observations

### Skill Coordination

Skills work together naturally:
- **api-design** provides endpoint structure
- **security-patterns** provides authentication implementation
- **database-design** provides schema
- **python-standards** ensures code quality throughout
- **testing-guide** ensures comprehensive testing
- **documentation-guide** ensures clear API docs
- **observability** ensures production monitoring

### No Conflicts

Skills complement each other:
- Each covers different domain
- No contradictory guidance
- Natural layering (design → implement → test → document)

### Efficient Loading

Progressive disclosure loads skills just-in-time:
- Not all at once (would exceed context)
- Not too late (available when needed)
- Automatic (agent doesn't manage loading)

## Summary

This example demonstrates:
- **7 skills working together** for complex task
- **Progressive loading** keeps context efficient
- **No conflicts** between skills
- **24% token savings** vs loading all upfront
- **Natural workflow** through implementation stages

**Key takeaway**: Trust progressive disclosure. Reference all relevant skills, let the system load them efficiently as needed.
