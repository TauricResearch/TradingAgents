"""
Shared pytest fixtures for API tests.

This module provides fixtures for testing the FastAPI backend:
- Test database with SQLAlchemy async engine
- Test FastAPI client with httpx.AsyncClient
- Test users and JWT tokens
- Mock authentication dependencies
- Database session fixtures

All fixtures follow TDD principles - they define the expected API
before implementation exists.
"""

import os
import pytest
import asyncio
from typing import AsyncGenerator, Generator, Dict, Any
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta


# ============================================================================
# Pytest Configuration
# ============================================================================

@pytest.fixture(scope="session")
def event_loop_policy():
    """Set event loop policy for async tests."""
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture(scope="session")
def event_loop(event_loop_policy):
    """Create event loop for session scope."""
    loop = event_loop_policy.new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# Database Fixtures
# ============================================================================

@pytest.fixture
async def db_engine():
    """
    Create async SQLAlchemy engine for testing.

    Uses SQLite in-memory database for fast, isolated tests.
    Creates all tables before test, drops after test.

    Yields:
        AsyncEngine: SQLAlchemy async engine

    Example:
        async def test_database(db_engine):
            async with db_engine.begin() as conn:
                result = await conn.execute(text("SELECT 1"))
                assert result.scalar() == 1
    """
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine

    # Create in-memory SQLite database
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
    )

    # Import models to ensure they're registered
    try:
        from tradingagents.api.models import Base

        # Create all tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except ImportError:
        # Models don't exist yet (TDD - tests written first)
        pass

    yield engine

    # Cleanup
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine):
    """
    Create async database session for testing.

    Provides a database session that rolls back after each test
    to ensure test isolation.

    Args:
        db_engine: Test database engine fixture

    Yields:
        AsyncSession: SQLAlchemy async session

    Example:
        async def test_create_user(db_session):
            user = User(username="test", email="test@example.com")
            db_session.add(user)
            await db_session.commit()
            assert user.id is not None
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    # Create session factory
    async_session = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Create session
    async with async_session() as session:
        yield session
        # Rollback any uncommitted changes
        await session.rollback()


@pytest.fixture
async def clean_db(db_session):
    """
    Ensure database is clean before test.

    Deletes all data from all tables to ensure test isolation.

    Args:
        db_session: Database session fixture

    Example:
        async def test_with_clean_db(clean_db, db_session):
            # Database is guaranteed to be empty
            result = await db_session.execute(select(User))
            assert len(result.scalars().all()) == 0
    """
    try:
        from tradingagents.api.models import User, Strategy
        from sqlalchemy import delete

        # Delete all strategies first (foreign key constraint)
        await db_session.execute(delete(Strategy))
        await db_session.execute(delete(User))
        await db_session.commit()
    except ImportError:
        # Models don't exist yet
        pass

    yield


# ============================================================================
# FastAPI Client Fixtures
# ============================================================================

@pytest.fixture
async def test_app():
    """
    Create FastAPI test application.

    Returns the FastAPI app instance configured for testing.
    Database dependency is overridden to use test database.

    Yields:
        FastAPI: Test application instance

    Example:
        async def test_root_endpoint(test_app):
            assert test_app is not None
            assert hasattr(test_app, "routes")
    """
    try:
        from tradingagents.api.main import app
        yield app
    except ImportError:
        # App doesn't exist yet (TDD)
        from fastapi import FastAPI

        # Create minimal app for testing
        app = FastAPI(title="TradingAgents API (Test)", version="0.1.0")

        @app.get("/")
        async def root():
            return {"message": "TradingAgents API"}

        yield app


@pytest.fixture
async def client(test_app, db_session):
    """
    Create async HTTP client for API testing.

    Uses httpx.AsyncClient to test FastAPI endpoints.
    Overrides database dependency to use test database.

    Args:
        test_app: FastAPI test application
        db_session: Test database session

    Yields:
        AsyncClient: HTTP client for making requests

    Example:
        async def test_api_endpoint(client):
            response = await client.get("/api/v1/strategies")
            assert response.status_code == 200
    """
    import httpx
    from httpx import AsyncClient

    # Override database dependency
    async def override_get_db():
        yield db_session

    try:
        from tradingagents.api.dependencies import get_db
        test_app.dependency_overrides[get_db] = override_get_db
    except ImportError:
        # Dependency doesn't exist yet
        pass

    async with AsyncClient(transport=httpx.ASGITransport(app=test_app), base_url="http://test") as ac:
        yield ac

    # Clear overrides
    test_app.dependency_overrides.clear()


# ============================================================================
# Authentication Fixtures
# ============================================================================

@pytest.fixture
def test_user_data() -> Dict[str, Any]:
    """
    Test user data for registration/login.

    Returns:
        dict: User data with username, email, password

    Example:
        def test_user_creation(test_user_data):
            assert test_user_data["username"] == "testuser"
            assert "password" in test_user_data
    """
    return {
        "username": "testuser",
        "email": "test@example.com",
        "password": "SecurePassword123!",
        "full_name": "Test User",
        "timezone": "America/New_York",  # Issue #3
        "tax_jurisdiction": "US-NY",  # Issue #3
    }


@pytest.fixture
def second_user_data() -> Dict[str, Any]:
    """
    Second test user for testing user isolation.

    Returns:
        dict: Second user's data
    """
    return {
        "username": "otheruser",
        "email": "other@example.com",
        "password": "AnotherPassword456!",
        "full_name": "Other User",
        "timezone": "America/Los_Angeles",  # Issue #3
        "tax_jurisdiction": "US-CA",  # Issue #3
    }


@pytest.fixture
async def test_user(db_session, test_user_data):
    """
    Create test user in database.

    Creates a user with hashed password for authentication testing.

    Args:
        db_session: Database session
        test_user_data: Test user data

    Yields:
        User: Created user model instance

    Example:
        async def test_with_user(test_user):
            assert test_user.username == "testuser"
            assert test_user.id is not None
    """
    try:
        from tradingagents.api.models import User
        from tradingagents.api.services.auth_service import hash_password

        user = User(
            username=test_user_data["username"],
            email=test_user_data["email"],
            hashed_password=hash_password(test_user_data["password"]),
            full_name=test_user_data.get("full_name"),
        )

        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        yield user
    except ImportError:
        # Models/services don't exist yet
        yield None


@pytest.fixture
async def second_user(db_session, second_user_data):
    """
    Create second test user in database.

    Used for testing user isolation and authorization.

    Args:
        db_session: Database session
        second_user_data: Second user data

    Yields:
        User: Created user model instance
    """
    try:
        from tradingagents.api.models import User
        from tradingagents.api.services.auth_service import hash_password

        user = User(
            username=second_user_data["username"],
            email=second_user_data["email"],
            hashed_password=hash_password(second_user_data["password"]),
            full_name=second_user_data.get("full_name"),
        )

        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        yield user
    except ImportError:
        yield None


@pytest.fixture
def jwt_token(test_user_data) -> str:
    """
    Generate valid JWT token for testing.

    Creates a JWT token for authenticated requests.

    Args:
        test_user_data: Test user data

    Returns:
        str: JWT access token

    Example:
        async def test_protected_endpoint(client, jwt_token):
            response = await client.get(
                "/api/v1/strategies",
                headers={"Authorization": f"Bearer {jwt_token}"}
            )
            assert response.status_code == 200
    """
    try:
        from tradingagents.api.services.auth_service import create_access_token

        token_data = {"sub": test_user_data["username"]}
        token = create_access_token(token_data)
        return token
    except ImportError:
        # Auth service doesn't exist yet
        return "test-jwt-token-placeholder"


@pytest.fixture
def expired_jwt_token(test_user_data) -> str:
    """
    Generate expired JWT token for testing.

    Creates an expired JWT token to test token expiration handling.

    Returns:
        str: Expired JWT access token

    Example:
        async def test_expired_token(client, expired_jwt_token):
            response = await client.get(
                "/api/v1/strategies",
                headers={"Authorization": f"Bearer {expired_jwt_token}"}
            )
            assert response.status_code == 401
    """
    try:
        from tradingagents.api.services.auth_service import create_access_token

        token_data = {"sub": test_user_data["username"]}
        # Create token that expired 1 hour ago
        token = create_access_token(
            token_data,
            expires_delta=timedelta(hours=-1)
        )
        return token
    except ImportError:
        return "expired-jwt-token-placeholder"


@pytest.fixture
def invalid_jwt_token() -> str:
    """
    Generate invalid JWT token for testing.

    Returns:
        str: Invalid/malformed JWT token

    Example:
        async def test_invalid_token(client, invalid_jwt_token):
            response = await client.get(
                "/api/v1/strategies",
                headers={"Authorization": f"Bearer {invalid_jwt_token}"}
            )
            assert response.status_code == 401
    """
    return "invalid.jwt.token"


@pytest.fixture
def auth_headers(jwt_token) -> Dict[str, str]:
    """
    Create authorization headers with JWT token.

    Args:
        jwt_token: Valid JWT token

    Returns:
        dict: Headers with Authorization bearer token

    Example:
        async def test_authenticated_request(client, auth_headers):
            response = await client.get("/api/v1/strategies", headers=auth_headers)
            assert response.status_code == 200
    """
    return {"Authorization": f"Bearer {jwt_token}"}


# ============================================================================
# Strategy Fixtures
# ============================================================================

@pytest.fixture
def strategy_data() -> Dict[str, Any]:
    """
    Test strategy data for creation.

    Returns:
        dict: Strategy data with required fields

    Example:
        async def test_create_strategy(client, auth_headers, strategy_data):
            response = await client.post(
                "/api/v1/strategies",
                json=strategy_data,
                headers=auth_headers
            )
            assert response.status_code == 201
    """
    return {
        "name": "Moving Average Crossover",
        "description": "Simple moving average crossover strategy",
        "parameters": {
            "fast_period": 10,
            "slow_period": 20,
            "symbol": "AAPL",
        },
        "is_active": True,
    }


@pytest.fixture
def strategy_data_minimal() -> Dict[str, Any]:
    """
    Minimal strategy data (only required fields).

    Returns:
        dict: Minimal strategy data
    """
    return {
        "name": "Minimal Strategy",
        "description": "A minimal test strategy",
    }


@pytest.fixture
async def test_strategy(db_session, test_user, strategy_data):
    """
    Create test strategy in database.

    Creates a strategy owned by test_user.

    Args:
        db_session: Database session
        test_user: Owner user
        strategy_data: Strategy data

    Yields:
        Strategy: Created strategy model instance

    Example:
        async def test_with_strategy(test_strategy):
            assert test_strategy.name == "Moving Average Crossover"
            assert test_strategy.user_id is not None
    """
    if test_user is None:
        yield None
        return

    try:
        from tradingagents.api.models import Strategy

        strategy = Strategy(
            name=strategy_data["name"],
            description=strategy_data["description"],
            parameters=strategy_data.get("parameters", {}),
            is_active=strategy_data.get("is_active", True),
            user_id=test_user.id,
        )

        db_session.add(strategy)
        await db_session.commit()
        await db_session.refresh(strategy)

        yield strategy
    except ImportError:
        yield None


@pytest.fixture
async def multiple_strategies(db_session, test_user):
    """
    Create multiple test strategies for list/pagination testing.

    Creates 5 strategies with different names and parameters.

    Args:
        db_session: Database session
        test_user: Owner user

    Yields:
        list[Strategy]: List of created strategies
    """
    if test_user is None:
        yield []
        return

    try:
        from tradingagents.api.models import Strategy

        strategies = []
        for i in range(5):
            strategy = Strategy(
                name=f"Strategy {i+1}",
                description=f"Test strategy number {i+1}",
                parameters={"index": i},
                is_active=i % 2 == 0,  # Alternate active/inactive
                user_id=test_user.id,
            )
            db_session.add(strategy)
            strategies.append(strategy)

        await db_session.commit()

        # Refresh all strategies
        for strategy in strategies:
            await db_session.refresh(strategy)

        yield strategies
    except ImportError:
        yield []


# ============================================================================
# Mock Environment Fixtures
# ============================================================================

@pytest.fixture
def mock_env_jwt_secret():
    """
    Mock environment with JWT secret key.

    Sets required environment variables for JWT authentication.

    Yields:
        None

    Example:
        def test_jwt_config(mock_env_jwt_secret):
            assert os.getenv("JWT_SECRET_KEY") is not None
    """
    with patch.dict(os.environ, {
        "JWT_SECRET_KEY": "test-secret-key-for-jwt-signing-very-secure-123",
        "JWT_ALGORITHM": "HS256",
        "JWT_EXPIRATION_MINUTES": "30",
    }, clear=False):
        yield


@pytest.fixture
def mock_env_database():
    """
    Mock environment with database URL.

    Sets database connection string for testing.

    Yields:
        None
    """
    with patch.dict(os.environ, {
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
    }, clear=False):
        yield


# ============================================================================
# Utility Fixtures
# ============================================================================

@pytest.fixture
def sample_sql_injection_payloads() -> list[str]:
    """
    Sample SQL injection attack payloads for security testing.

    Returns:
        list[str]: Common SQL injection patterns

    Example:
        async def test_sql_injection_prevention(client, sample_sql_injection_payloads):
            for payload in sample_sql_injection_payloads:
                response = await client.get(f"/api/v1/strategies/{payload}")
                assert response.status_code in [400, 404]  # Not 500
    """
    return [
        "1' OR '1'='1",
        "1; DROP TABLE users--",
        "' OR 1=1--",
        "admin'--",
        "' UNION SELECT * FROM users--",
        "1' AND '1'='1",
    ]


@pytest.fixture
def sample_xss_payloads() -> list[str]:
    """
    Sample XSS attack payloads for security testing.

    Returns:
        list[str]: Common XSS patterns
    """
    return [
        "<script>alert('XSS')</script>",
        "javascript:alert('XSS')",
        "<img src=x onerror=alert('XSS')>",
        "<svg onload=alert('XSS')>",
    ]


# ============================================================================
# Issue #3 Fixtures: API Keys, Timezones, Tax Jurisdictions
# ============================================================================

@pytest.fixture
def verified_user_data() -> Dict[str, Any]:
    """
    Test user data for verified user (Issue #3).

    Returns:
        dict: Verified user data with all Issue #3 fields

    Example:
        async def test_verified_user(verified_user_data):
            assert verified_user_data["is_verified"] is True
    """
    return {
        "username": "verifieduser",
        "email": "verified@example.com",
        "password": "VerifiedPassword123!",
        "full_name": "Verified User",
        "timezone": "UTC",
        "tax_jurisdiction": "US",
        "is_verified": True,
    }


@pytest.fixture
async def verified_user(db_session, verified_user_data):
    """
    Create verified test user in database (Issue #3).

    Creates a verified user with timezone and tax jurisdiction.

    Args:
        db_session: Database session
        verified_user_data: Verified user data

    Yields:
        User: Created verified user model instance
    """
    try:
        from tradingagents.api.models import User
        from tradingagents.api.services.auth_service import hash_password

        user = User(
            username=verified_user_data["username"],
            email=verified_user_data["email"],
            hashed_password=hash_password(verified_user_data["password"]),
            full_name=verified_user_data.get("full_name"),
            timezone=verified_user_data.get("timezone"),
            tax_jurisdiction=verified_user_data.get("tax_jurisdiction"),
            is_verified=verified_user_data.get("is_verified", True),
        )

        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        yield user
    except ImportError:
        yield None


@pytest.fixture
async def user_with_api_key(db_session, test_user_data):
    """
    Create test user with API key in database (Issue #3).

    Creates a user with a hashed API key.

    Args:
        db_session: Database session
        test_user_data: Test user data

    Yields:
        tuple[User, str]: (Created user, plain API key)
    """
    try:
        from tradingagents.api.models import User
        from tradingagents.api.services.auth_service import hash_password
        from tradingagents.api.services.api_key_service import (
            generate_api_key,
            hash_api_key,
        )

        # Generate API key
        plain_api_key = generate_api_key()
        hashed_api_key = hash_api_key(plain_api_key)

        user = User(
            username=test_user_data["username"],
            email=test_user_data["email"],
            hashed_password=hash_password(test_user_data["password"]),
            full_name=test_user_data.get("full_name"),
            api_key_hash=hashed_api_key,
            timezone=test_user_data.get("timezone"),
            tax_jurisdiction=test_user_data.get("tax_jurisdiction"),
        )

        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        yield (user, plain_api_key)
    except ImportError:
        yield (None, None)


@pytest.fixture
def valid_timezones() -> list[str]:
    """
    List of valid IANA timezones for testing (Issue #3).

    Returns:
        list[str]: Valid timezone identifiers

    Example:
        def test_timezones(valid_timezones):
            for tz in valid_timezones:
                assert validate_timezone(tz) is True
    """
    return [
        "UTC",
        "GMT",
        "America/New_York",
        "America/Los_Angeles",
        "America/Chicago",
        "America/Denver",
        "Europe/London",
        "Europe/Paris",
        "Europe/Berlin",
        "Asia/Tokyo",
        "Asia/Shanghai",
        "Asia/Hong_Kong",
        "Australia/Sydney",
        "Australia/Melbourne",
        "Pacific/Auckland",
    ]


@pytest.fixture
def invalid_timezones() -> list[str]:
    """
    List of invalid timezones for testing (Issue #3).

    Returns:
        list[str]: Invalid timezone identifiers

    Example:
        def test_invalid_timezones(invalid_timezones):
            for tz in invalid_timezones:
                assert validate_timezone(tz) is False
    """
    return [
        "PST",
        "EST",
        "CST",
        "MST",
        "America/InvalidCity",
        "Europe/FakePlace",
        "Random/Stuff",
        "america/new_york",  # Wrong case
        "123456",
        "!@#$%",
    ]


@pytest.fixture
def valid_tax_jurisdictions() -> list[str]:
    """
    List of valid tax jurisdictions for testing (Issue #3).

    Returns:
        list[str]: Valid tax jurisdiction codes

    Example:
        def test_jurisdictions(valid_tax_jurisdictions):
            for jurisdiction in valid_tax_jurisdictions:
                assert validate_tax_jurisdiction(jurisdiction) is True
    """
    return [
        "US",
        "CA",
        "GB",
        "DE",
        "FR",
        "JP",
        "AU",
        "US-CA",
        "US-NY",
        "US-TX",
        "US-FL",
        "CA-ON",
        "CA-QC",
        "CA-BC",
    ]


@pytest.fixture
def invalid_tax_jurisdictions() -> list[str]:
    """
    List of invalid tax jurisdictions for testing (Issue #3).

    Returns:
        list[str]: Invalid tax jurisdiction codes

    Example:
        def test_invalid_jurisdictions(invalid_tax_jurisdictions):
            for jurisdiction in invalid_tax_jurisdictions:
                assert validate_tax_jurisdiction(jurisdiction) is False
    """
    return [
        "InvalidFormat",
        "US_CA",  # Wrong separator
        "US/CA",  # Wrong separator
        "USCA",  # No separator
        "us-ca",  # Lowercase
        "XX-YY",  # Invalid country code
        "123",
        "!@#",
        "",
    ]
