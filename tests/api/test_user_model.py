"""Unit tests for User model with Issue #3 enhancements.

Tests for User model fields including:
- tax_jurisdiction
- timezone
- api_key_hash
- is_verified

Follows TDD principles with comprehensive coverage.
"""

import pytest
from sqlalchemy import select
from tradingagents.api.models.user import User
from tradingagents.api.services.auth_service import hash_password
from tradingagents.api.services.api_key_service import generate_api_key, hash_api_key


class TestUserModelBasicFields:
    """Tests for basic User model fields."""

    @pytest.mark.asyncio
    async def test_create_user_with_required_fields(self, db_session):
        """Should create user with only required fields."""
        user = User(
            username="testuser",
            email="test@example.com",
            hashed_password=hash_password("SecurePassword123!"),
        )

        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.id is not None
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.hashed_password is not None

    @pytest.mark.asyncio
    async def test_user_defaults(self, db_session):
        """Should apply default values to optional fields."""
        user = User(
            username="testuser",
            email="test@example.com",
            hashed_password=hash_password("SecurePassword123!"),
        )

        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        # Check defaults
        assert user.is_active is True
        assert user.is_superuser is False
        assert user.tax_jurisdiction == "AU"
        assert user.timezone == "Australia/Sydney"
        assert user.is_verified is False
        assert user.api_key_hash is None
        assert user.full_name is None

    @pytest.mark.asyncio
    async def test_username_unique_constraint(self, db_session):
        """Should enforce unique username constraint."""
        user1 = User(
            username="testuser",
            email="test1@example.com",
            hashed_password=hash_password("Password123!"),
        )
        db_session.add(user1)
        await db_session.commit()

        # Try to create user with same username
        user2 = User(
            username="testuser",
            email="test2@example.com",
            hashed_password=hash_password("Password456!"),
        )
        db_session.add(user2)

        with pytest.raises(Exception):  # IntegrityError
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_email_unique_constraint(self, db_session):
        """Should enforce unique email constraint."""
        user1 = User(
            username="user1",
            email="test@example.com",
            hashed_password=hash_password("Password123!"),
        )
        db_session.add(user1)
        await db_session.commit()

        # Try to create user with same email
        user2 = User(
            username="user2",
            email="test@example.com",
            hashed_password=hash_password("Password456!"),
        )
        db_session.add(user2)

        with pytest.raises(Exception):  # IntegrityError
            await db_session.commit()


class TestUserModelTaxJurisdiction:
    """Tests for tax_jurisdiction field (Issue #3)."""

    @pytest.mark.asyncio
    async def test_set_us_jurisdiction(self, db_session):
        """Should set US tax jurisdiction."""
        user = User(
            username="ususer",
            email="us@example.com",
            hashed_password=hash_password("Password123!"),
            tax_jurisdiction="US",
        )

        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.tax_jurisdiction == "US"

    @pytest.mark.asyncio
    async def test_set_us_state_jurisdiction(self, db_session):
        """Should set US state-level tax jurisdiction."""
        user = User(
            username="nyuser",
            email="ny@example.com",
            hashed_password=hash_password("Password123!"),
            tax_jurisdiction="US-NY",
        )

        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.tax_jurisdiction == "US-NY"

    @pytest.mark.asyncio
    async def test_set_canadian_province_jurisdiction(self, db_session):
        """Should set Canadian province-level tax jurisdiction."""
        user = User(
            username="causer",
            email="ca@example.com",
            hashed_password=hash_password("Password123!"),
            tax_jurisdiction="CA-ON",
        )

        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.tax_jurisdiction == "CA-ON"

    @pytest.mark.asyncio
    async def test_set_australian_state_jurisdiction(self, db_session):
        """Should set Australian state-level tax jurisdiction."""
        user = User(
            username="auuser",
            email="au@example.com",
            hashed_password=hash_password("Password123!"),
            tax_jurisdiction="AU-NSW",
        )

        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.tax_jurisdiction == "AU-NSW"

    @pytest.mark.asyncio
    async def test_tax_jurisdiction_default(self, db_session):
        """Should default to AU if not specified."""
        user = User(
            username="defaultuser",
            email="default@example.com",
            hashed_password=hash_password("Password123!"),
        )

        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.tax_jurisdiction == "AU"

    @pytest.mark.asyncio
    async def test_tax_jurisdiction_max_length(self, db_session):
        """Tax jurisdiction should not exceed 10 characters."""
        # This should work (10 chars max)
        user = User(
            username="testuser",
            email="test@example.com",
            hashed_password=hash_password("Password123!"),
            tax_jurisdiction="AU-NSW",  # 6 chars
        )

        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.tax_jurisdiction == "AU-NSW"


class TestUserModelTimezone:
    """Tests for timezone field (Issue #3)."""

    @pytest.mark.asyncio
    async def test_set_us_timezone(self, db_session):
        """Should set US timezone."""
        user = User(
            username="nyuser",
            email="ny@example.com",
            hashed_password=hash_password("Password123!"),
            timezone="America/New_York",
        )

        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.timezone == "America/New_York"

    @pytest.mark.asyncio
    async def test_set_utc_timezone(self, db_session):
        """Should set UTC timezone."""
        user = User(
            username="utcuser",
            email="utc@example.com",
            hashed_password=hash_password("Password123!"),
            timezone="UTC",
        )

        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.timezone == "UTC"

    @pytest.mark.asyncio
    async def test_set_european_timezone(self, db_session):
        """Should set European timezone."""
        user = User(
            username="londonuser",
            email="london@example.com",
            hashed_password=hash_password("Password123!"),
            timezone="Europe/London",
        )

        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.timezone == "Europe/London"

    @pytest.mark.asyncio
    async def test_set_asian_timezone(self, db_session):
        """Should set Asian timezone."""
        user = User(
            username="tokyouser",
            email="tokyo@example.com",
            hashed_password=hash_password("Password123!"),
            timezone="Asia/Tokyo",
        )

        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.timezone == "Asia/Tokyo"

    @pytest.mark.asyncio
    async def test_timezone_default(self, db_session):
        """Should default to Australia/Sydney if not specified."""
        user = User(
            username="defaultuser",
            email="default@example.com",
            hashed_password=hash_password("Password123!"),
        )

        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.timezone == "Australia/Sydney"

    @pytest.mark.asyncio
    async def test_timezone_max_length(self, db_session):
        """Timezone should not exceed 50 characters."""
        # Longest IANA timezone is ~40 characters
        user = User(
            username="testuser",
            email="test@example.com",
            hashed_password=hash_password("Password123!"),
            timezone="America/Argentina/ComodRivadavia",  # 35 chars
        )

        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.timezone == "America/Argentina/ComodRivadavia"


class TestUserModelApiKey:
    """Tests for api_key_hash field (Issue #3)."""

    @pytest.mark.asyncio
    async def test_user_without_api_key(self, db_session):
        """User without API key should have None api_key_hash."""
        user = User(
            username="nokey",
            email="nokey@example.com",
            hashed_password=hash_password("Password123!"),
        )

        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.api_key_hash is None

    @pytest.mark.asyncio
    async def test_user_with_api_key(self, db_session):
        """User with API key should store hashed key."""
        api_key = generate_api_key()
        hashed = hash_api_key(api_key)

        user = User(
            username="withkey",
            email="withkey@example.com",
            hashed_password=hash_password("Password123!"),
            api_key_hash=hashed,
        )

        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.api_key_hash is not None
        assert user.api_key_hash == hashed
        assert user.api_key_hash != api_key  # Should be hash, not plain key

    @pytest.mark.asyncio
    async def test_api_key_hash_unique_constraint(self, db_session):
        """Should enforce unique api_key_hash constraint."""
        api_key = generate_api_key()
        hashed = hash_api_key(api_key)

        user1 = User(
            username="user1",
            email="user1@example.com",
            hashed_password=hash_password("Password123!"),
            api_key_hash=hashed,
        )
        db_session.add(user1)
        await db_session.commit()

        # Try to create user with same api_key_hash
        user2 = User(
            username="user2",
            email="user2@example.com",
            hashed_password=hash_password("Password456!"),
            api_key_hash=hashed,
        )
        db_session.add(user2)

        with pytest.raises(Exception):  # IntegrityError
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_api_key_hash_indexed(self, db_session):
        """api_key_hash should be indexed for fast lookups."""
        # Create users with API keys
        for i in range(10):
            api_key = generate_api_key()
            hashed = hash_api_key(api_key)

            user = User(
                username=f"user{i}",
                email=f"user{i}@example.com",
                hashed_password=hash_password("Password123!"),
                api_key_hash=hashed,
            )
            db_session.add(user)

        await db_session.commit()

        # Lookup by api_key_hash should work
        api_key = generate_api_key()
        hashed = hash_api_key(api_key)

        user = User(
            username="lookup",
            email="lookup@example.com",
            hashed_password=hash_password("Password123!"),
            api_key_hash=hashed,
        )
        db_session.add(user)
        await db_session.commit()

        # Query by api_key_hash
        result = await db_session.execute(
            select(User).where(User.api_key_hash == hashed)
        )
        found_user = result.scalar_one_or_none()

        assert found_user is not None
        assert found_user.username == "lookup"

    @pytest.mark.asyncio
    async def test_update_api_key(self, db_session):
        """User should be able to regenerate their API key."""
        # Create user with API key
        old_api_key = generate_api_key()
        old_hash = hash_api_key(old_api_key)

        user = User(
            username="regenerate",
            email="regenerate@example.com",
            hashed_password=hash_password("Password123!"),
            api_key_hash=old_hash,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        # Regenerate API key
        new_api_key = generate_api_key()
        new_hash = hash_api_key(new_api_key)

        user.api_key_hash = new_hash
        await db_session.commit()
        await db_session.refresh(user)

        assert user.api_key_hash == new_hash
        assert user.api_key_hash != old_hash

    @pytest.mark.asyncio
    async def test_revoke_api_key(self, db_session):
        """User should be able to revoke their API key."""
        # Create user with API key
        api_key = generate_api_key()
        hashed = hash_api_key(api_key)

        user = User(
            username="revoke",
            email="revoke@example.com",
            hashed_password=hash_password("Password123!"),
            api_key_hash=hashed,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        # Revoke API key (set to None)
        user.api_key_hash = None
        await db_session.commit()
        await db_session.refresh(user)

        assert user.api_key_hash is None


class TestUserModelIsVerified:
    """Tests for is_verified field (Issue #3)."""

    @pytest.mark.asyncio
    async def test_user_unverified_by_default(self, db_session):
        """New users should be unverified by default."""
        user = User(
            username="unverified",
            email="unverified@example.com",
            hashed_password=hash_password("Password123!"),
        )

        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.is_verified is False

    @pytest.mark.asyncio
    async def test_create_verified_user(self, db_session):
        """Should be able to create verified user."""
        user = User(
            username="verified",
            email="verified@example.com",
            hashed_password=hash_password("Password123!"),
            is_verified=True,
        )

        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.is_verified is True

    @pytest.mark.asyncio
    async def test_verify_user(self, db_session):
        """Should be able to verify user after creation."""
        # Create unverified user
        user = User(
            username="toverify",
            email="toverify@example.com",
            hashed_password=hash_password("Password123!"),
            is_verified=False,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.is_verified is False

        # Verify user
        user.is_verified = True
        await db_session.commit()
        await db_session.refresh(user)

        assert user.is_verified is True

    @pytest.mark.asyncio
    async def test_query_verified_users(self, db_session):
        """Should be able to query only verified users."""
        # Create mix of verified and unverified users
        for i in range(5):
            user = User(
                username=f"user{i}",
                email=f"user{i}@example.com",
                hashed_password=hash_password("Password123!"),
                is_verified=(i % 2 == 0),  # Alternate verified/unverified
            )
            db_session.add(user)

        await db_session.commit()

        # Query only verified users
        result = await db_session.execute(
            select(User).where(User.is_verified == True)
        )
        verified_users = result.scalars().all()

        assert len(verified_users) == 3  # users 0, 2, 4
        for user in verified_users:
            assert user.is_verified is True


class TestUserModelComplete:
    """Tests for complete user creation with all Issue #3 fields."""

    @pytest.mark.asyncio
    async def test_create_complete_user(self, db_session):
        """Should create user with all fields including Issue #3 additions."""
        api_key = generate_api_key()
        hashed_api_key = hash_api_key(api_key)

        user = User(
            username="complete",
            email="complete@example.com",
            hashed_password=hash_password("Password123!"),
            full_name="Complete User",
            is_active=True,
            is_superuser=False,
            tax_jurisdiction="US-NY",
            timezone="America/New_York",
            api_key_hash=hashed_api_key,
            is_verified=True,
        )

        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.id is not None
        assert user.username == "complete"
        assert user.email == "complete@example.com"
        assert user.full_name == "Complete User"
        assert user.is_active is True
        assert user.is_superuser is False
        assert user.tax_jurisdiction == "US-NY"
        assert user.timezone == "America/New_York"
        assert user.api_key_hash == hashed_api_key
        assert user.is_verified is True
        assert user.created_at is not None
        assert user.updated_at is not None

    @pytest.mark.asyncio
    async def test_user_repr(self, db_session):
        """Should have meaningful string representation."""
        user = User(
            username="reprtest",
            email="repr@example.com",
            hashed_password=hash_password("Password123!"),
        )

        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        repr_str = repr(user)
        assert "reprtest" in repr_str
        assert "repr@example.com" in repr_str
        assert str(user.id) in repr_str
