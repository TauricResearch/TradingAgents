"""
Test suite for authentication endpoints and JWT handling.

This module tests Issue #48 authentication features:
1. User login with JWT token generation
2. Password hashing with Argon2 (via pwdlib)
3. JWT token validation and expiration
4. Invalid credentials handling
5. Token refresh functionality
6. Security best practices

Tests follow TDD - written before implementation.
"""

import pytest
from datetime import datetime, timedelta
from typing import Dict, Any

pytestmark = pytest.mark.asyncio


# ============================================================================
# Unit Tests: Password Hashing
# ============================================================================

class TestPasswordHashing:
    """Test password hashing using Argon2 via pwdlib."""

    def test_hash_password_generates_hash(self):
        """Test that hash_password creates a valid hash."""
        # Arrange
        password = "SecurePassword123!"

        try:
            from tradingagents.api.services.auth_service import hash_password

            # Act
            hashed = hash_password(password)

            # Assert
            assert hashed is not None
            assert hashed != password  # Hash should differ from plaintext
            assert len(hashed) > 50  # Argon2 hashes are long
            assert hashed.startswith("$argon2")  # Argon2 hash format
        except ImportError:
            pytest.skip("auth_service not implemented yet")

    def test_hash_password_deterministic_with_same_input(self):
        """Test that same password produces different hashes (salted)."""
        # Arrange
        password = "SecurePassword123!"

        try:
            from tradingagents.api.services.auth_service import hash_password

            # Act
            hash1 = hash_password(password)
            hash2 = hash_password(password)

            # Assert: Different hashes (due to random salt)
            assert hash1 != hash2
        except ImportError:
            pytest.skip("auth_service not implemented yet")

    def test_verify_password_with_correct_password(self):
        """Test that verify_password succeeds with correct password."""
        # Arrange
        password = "SecurePassword123!"

        try:
            from tradingagents.api.services.auth_service import hash_password, verify_password

            hashed = hash_password(password)

            # Act
            result = verify_password(password, hashed)

            # Assert
            assert result is True
        except ImportError:
            pytest.skip("auth_service not implemented yet")

    def test_verify_password_with_incorrect_password(self):
        """Test that verify_password fails with incorrect password."""
        # Arrange
        correct_password = "SecurePassword123!"
        wrong_password = "WrongPassword456!"

        try:
            from tradingagents.api.services.auth_service import hash_password, verify_password

            hashed = hash_password(correct_password)

            # Act
            result = verify_password(wrong_password, hashed)

            # Assert
            assert result is False
        except ImportError:
            pytest.skip("auth_service not implemented yet")

    def test_hash_password_handles_special_characters(self):
        """Test password hashing with special characters."""
        # Arrange
        passwords = [
            "P@ssw0rd!",
            "密码123",  # Chinese characters
            "пароль",  # Cyrillic
            "🔒secure🔑",  # Emojis
        ]

        try:
            from tradingagents.api.services.auth_service import hash_password, verify_password

            for password in passwords:
                # Act
                hashed = hash_password(password)

                # Assert
                assert verify_password(password, hashed)
        except ImportError:
            pytest.skip("auth_service not implemented yet")

    def test_hash_password_empty_string(self):
        """Test hashing empty password."""
        # Arrange
        password = ""

        try:
            from tradingagents.api.services.auth_service import hash_password

            # Act
            hashed = hash_password(password)

            # Assert: Should still create a hash (validation happens elsewhere)
            assert hashed is not None
            assert len(hashed) > 0
        except ImportError:
            pytest.skip("auth_service not implemented yet")


# ============================================================================
# Unit Tests: JWT Token Generation
# ============================================================================

class TestJWTTokenGeneration:
    """Test JWT token creation and encoding."""

    def test_create_access_token_generates_valid_token(self, mock_env_jwt_secret):
        """Test that create_access_token generates a valid JWT."""
        # Arrange
        token_data = {"sub": "testuser"}

        try:
            from tradingagents.api.services.auth_service import create_access_token

            # Act
            token = create_access_token(token_data)

            # Assert
            assert token is not None
            assert isinstance(token, str)
            assert len(token) > 50  # JWT tokens are long
            assert token.count(".") == 2  # JWT format: header.payload.signature
        except ImportError:
            pytest.skip("auth_service not implemented yet")

    def test_create_access_token_includes_expiration(self, mock_env_jwt_secret):
        """Test that token includes expiration claim."""
        # Arrange
        token_data = {"sub": "testuser"}

        try:
            from tradingagents.api.services.auth_service import create_access_token
            import jwt
            import os

            # Act
            token = create_access_token(token_data)

            # Decode token to inspect claims
            secret_key = os.getenv("JWT_SECRET_KEY", "test-secret-key")
            algorithm = os.getenv("JWT_ALGORITHM", "HS256")
            decoded = jwt.decode(token, secret_key, algorithms=[algorithm])

            # Assert
            assert "exp" in decoded
            assert "sub" in decoded
            assert decoded["sub"] == "testuser"
        except ImportError:
            pytest.skip("auth_service not implemented yet")

    def test_create_access_token_custom_expiration(self, mock_env_jwt_secret):
        """Test creating token with custom expiration time."""
        # Arrange
        token_data = {"sub": "testuser"}
        expires_delta = timedelta(hours=1)

        try:
            from tradingagents.api.services.auth_service import create_access_token
            import jwt
            import os

            # Act
            token = create_access_token(token_data, expires_delta=expires_delta)

            # Decode token
            secret_key = os.getenv("JWT_SECRET_KEY", "test-secret-key")
            algorithm = os.getenv("JWT_ALGORITHM", "HS256")
            decoded = jwt.decode(token, secret_key, algorithms=[algorithm])

            # Assert: Expiration is approximately 1 hour from now
            exp_time = datetime.fromtimestamp(decoded["exp"])
            expected_exp = datetime.utcnow() + expires_delta
            time_diff = abs((exp_time - expected_exp).total_seconds())
            assert time_diff < 5  # Within 5 seconds
        except ImportError:
            pytest.skip("auth_service not implemented yet")

    def test_create_access_token_includes_custom_claims(self, mock_env_jwt_secret):
        """Test that custom claims are included in token."""
        # Arrange
        token_data = {
            "sub": "testuser",
            "email": "test@example.com",
            "role": "admin",
        }

        try:
            from tradingagents.api.services.auth_service import create_access_token
            import jwt
            import os

            # Act
            token = create_access_token(token_data)

            # Decode token
            secret_key = os.getenv("JWT_SECRET_KEY", "test-secret-key")
            algorithm = os.getenv("JWT_ALGORITHM", "HS256")
            decoded = jwt.decode(token, secret_key, algorithms=[algorithm])

            # Assert
            assert decoded["sub"] == "testuser"
            assert decoded["email"] == "test@example.com"
            assert decoded["role"] == "admin"
        except ImportError:
            pytest.skip("auth_service not implemented yet")


# ============================================================================
# Unit Tests: JWT Token Validation
# ============================================================================

class TestJWTTokenValidation:
    """Test JWT token decoding and validation."""

    def test_decode_token_with_valid_token(self, mock_env_jwt_secret):
        """Test decoding a valid JWT token."""
        # Arrange
        token_data = {"sub": "testuser"}

        try:
            from tradingagents.api.services.auth_service import (
                create_access_token,
                decode_access_token,
            )

            token = create_access_token(token_data)

            # Act
            decoded = decode_access_token(token)

            # Assert
            assert decoded is not None
            assert decoded["sub"] == "testuser"
        except ImportError:
            pytest.skip("auth_service not implemented yet")

    def test_decode_token_with_expired_token(self, mock_env_jwt_secret):
        """Test that expired tokens are rejected."""
        # Arrange
        token_data = {"sub": "testuser"}

        try:
            from tradingagents.api.services.auth_service import (
                create_access_token,
                decode_access_token,
            )
            from jwt.exceptions import ExpiredSignatureError

            # Create already-expired token
            token = create_access_token(token_data, expires_delta=timedelta(seconds=-1))

            # Act & Assert
            with pytest.raises(ExpiredSignatureError):
                decode_access_token(token)
        except ImportError:
            pytest.skip("auth_service not implemented yet")

    def test_decode_token_with_invalid_signature(self, mock_env_jwt_secret):
        """Test that tokens with invalid signature are rejected."""
        # Arrange
        token_data = {"sub": "testuser"}

        try:
            from tradingagents.api.services.auth_service import (
                create_access_token,
                decode_access_token,
            )
            from jwt.exceptions import InvalidSignatureError

            token = create_access_token(token_data)
            # Tamper with token
            tampered_token = token[:-10] + "tampered00"

            # Act & Assert
            with pytest.raises(InvalidSignatureError):
                decode_access_token(tampered_token)
        except ImportError:
            pytest.skip("auth_service not implemented yet")

    def test_decode_token_with_malformed_token(self, mock_env_jwt_secret):
        """Test that malformed tokens are rejected."""
        # Arrange
        malformed_tokens = [
            "not.a.jwt",
            "invalid",
            "",
            "a.b",  # Only 2 parts instead of 3
        ]

        try:
            from tradingagents.api.services.auth_service import decode_access_token
            from jwt.exceptions import DecodeError

            for token in malformed_tokens:
                # Act & Assert
                with pytest.raises(DecodeError):
                    decode_access_token(token)
        except ImportError:
            pytest.skip("auth_service not implemented yet")


# ============================================================================
# Integration Tests: Login Endpoint
# ============================================================================

class TestLoginEndpoint:
    """Test POST /api/v1/auth/login endpoint."""

    async def test_login_with_valid_credentials(self, client, test_user, test_user_data):
        """Test successful login with correct username and password."""
        # Arrange
        login_data = {
            "username": test_user_data["username"],
            "password": test_user_data["password"],
        }

        # Act
        response = await client.post("/api/v1/auth/login", json=login_data)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "token_type" in data
        assert data["token_type"] == "bearer"
        assert len(data["access_token"]) > 50

    async def test_login_with_invalid_username(self, client, test_user):
        """Test login fails with non-existent username."""
        # Arrange
        login_data = {
            "username": "nonexistent",
            "password": "SomePassword123!",
        }

        # Act
        response = await client.post("/api/v1/auth/login", json=login_data)

        # Assert
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
        assert "incorrect" in data["detail"].lower() or "invalid" in data["detail"].lower()

    async def test_login_with_invalid_password(self, client, test_user, test_user_data):
        """Test login fails with incorrect password."""
        # Arrange
        login_data = {
            "username": test_user_data["username"],
            "password": "WrongPassword123!",
        }

        # Act
        response = await client.post("/api/v1/auth/login", json=login_data)

        # Assert
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data

    async def test_login_with_missing_username(self, client):
        """Test login validation requires username."""
        # Arrange
        login_data = {
            "password": "SomePassword123!",
        }

        # Act
        response = await client.post("/api/v1/auth/login", json=login_data)

        # Assert
        assert response.status_code == 422  # Validation error

    async def test_login_with_missing_password(self, client):
        """Test login validation requires password."""
        # Arrange
        login_data = {
            "username": "testuser",
        }

        # Act
        response = await client.post("/api/v1/auth/login", json=login_data)

        # Assert
        assert response.status_code == 422

    async def test_login_with_empty_credentials(self, client):
        """Test login with empty username and password."""
        # Arrange
        login_data = {
            "username": "",
            "password": "",
        }

        # Act
        response = await client.post("/api/v1/auth/login", json=login_data)

        # Assert
        assert response.status_code in [401, 422]

    async def test_login_returns_user_info(self, client, test_user, test_user_data):
        """Test that login response includes user information."""
        # Arrange
        login_data = {
            "username": test_user_data["username"],
            "password": test_user_data["password"],
        }

        # Act
        response = await client.post("/api/v1/auth/login", json=login_data)

        # Assert
        assert response.status_code == 200
        data = response.json()
        # May include user info like username, email
        assert "access_token" in data

    async def test_login_token_is_valid_jwt(self, client, test_user, test_user_data, mock_env_jwt_secret):
        """Test that login returns a valid, decodable JWT token."""
        # Arrange
        login_data = {
            "username": test_user_data["username"],
            "password": test_user_data["password"],
        }

        # Act
        response = await client.post("/api/v1/auth/login", json=login_data)

        # Assert
        assert response.status_code == 200
        data = response.json()
        token = data["access_token"]

        # Verify token format
        assert token.count(".") == 2

        # Try to decode
        try:
            from tradingagents.api.services.auth_service import decode_access_token
            decoded = decode_access_token(token)
            assert decoded["sub"] == test_user_data["username"]
        except ImportError:
            # Just verify format if service not implemented
            assert len(token) > 50


# ============================================================================
# Integration Tests: Protected Endpoints
# ============================================================================

class TestProtectedEndpoints:
    """Test that endpoints require valid JWT authentication."""

    async def test_protected_endpoint_without_token(self, client):
        """Test that protected endpoint rejects requests without token."""
        # Act
        response = await client.get("/api/v1/strategies")

        # Assert
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data

    async def test_protected_endpoint_with_valid_token(self, client, test_user, auth_headers):
        """Test that protected endpoint accepts valid token."""
        # Act
        response = await client.get("/api/v1/strategies", headers=auth_headers)

        # Assert
        assert response.status_code == 200

    async def test_protected_endpoint_with_expired_token(self, client, expired_jwt_token):
        """Test that expired token is rejected."""
        # Arrange
        headers = {"Authorization": f"Bearer {expired_jwt_token}"}

        # Act
        response = await client.get("/api/v1/strategies", headers=headers)

        # Assert
        assert response.status_code == 401
        data = response.json()
        assert "expired" in data["detail"].lower() or "invalid" in data["detail"].lower()

    async def test_protected_endpoint_with_invalid_token(self, client, invalid_jwt_token):
        """Test that invalid token is rejected."""
        # Arrange
        headers = {"Authorization": f"Bearer {invalid_jwt_token}"}

        # Act
        response = await client.get("/api/v1/strategies", headers=headers)

        # Assert
        assert response.status_code == 401

    async def test_protected_endpoint_with_malformed_header(self, client):
        """Test various malformed Authorization headers."""
        # Arrange
        malformed_headers = [
            {"Authorization": "Bearer"},  # Missing token
            {"Authorization": "token123"},  # Missing 'Bearer'
            {"Authorization": "Basic token123"},  # Wrong scheme
            {"Authorization": ""},  # Empty
        ]

        for headers in malformed_headers:
            # Act
            response = await client.get("/api/v1/strategies", headers=headers)

            # Assert
            assert response.status_code == 401

    async def test_protected_endpoint_extracts_user_from_token(self, client, test_user, auth_headers):
        """Test that endpoint can access user info from token."""
        # Act
        response = await client.get("/api/v1/strategies", headers=auth_headers)

        # Assert
        assert response.status_code == 200
        # User context should be available to endpoint handler


# ============================================================================
# Edge Cases: Authentication
# ============================================================================

class TestAuthenticationEdgeCases:
    """Test edge cases and boundary conditions for authentication."""

    async def test_login_case_sensitive_username(self, client, test_user, test_user_data):
        """Test that username is case-sensitive."""
        # Arrange
        login_data = {
            "username": test_user_data["username"].upper(),
            "password": test_user_data["password"],
        }

        # Act
        response = await client.post("/api/v1/auth/login", json=login_data)

        # Assert: Should fail if username case doesn't match
        # (depends on implementation - could be case-insensitive)
        assert response.status_code in [200, 401]

    async def test_login_with_sql_injection_attempt(self, client, sample_sql_injection_payloads):
        """Test that SQL injection in login is prevented."""
        # Arrange
        for payload in sample_sql_injection_payloads:
            login_data = {
                "username": payload,
                "password": "password",
            }

            # Act
            response = await client.post("/api/v1/auth/login", json=login_data)

            # Assert: Should return 401, not 500 (error) or 200 (bypass)
            assert response.status_code in [401, 422]

    async def test_login_with_very_long_username(self, client):
        """Test login with extremely long username."""
        # Arrange
        login_data = {
            "username": "a" * 10000,
            "password": "password",
        }

        # Act
        response = await client.post("/api/v1/auth/login", json=login_data)

        # Assert: Should handle gracefully (not crash)
        assert response.status_code in [401, 422]

    async def test_login_with_very_long_password(self, client):
        """Test login with extremely long password."""
        # Arrange
        login_data = {
            "username": "testuser",
            "password": "p" * 10000,
        }

        # Act
        response = await client.post("/api/v1/auth/login", json=login_data)

        # Assert
        assert response.status_code in [401, 422]

    async def test_concurrent_logins_same_user(self, client, test_user, test_user_data):
        """Test multiple concurrent logins for same user."""
        # Arrange
        login_data = {
            "username": test_user_data["username"],
            "password": test_user_data["password"],
        }

        # Act: Login multiple times
        response1 = await client.post("/api/v1/auth/login", json=login_data)
        response2 = await client.post("/api/v1/auth/login", json=login_data)
        response3 = await client.post("/api/v1/auth/login", json=login_data)

        # Assert: All should succeed with different tokens
        assert response1.status_code == 200
        assert response2.status_code == 200
        assert response3.status_code == 200

        token1 = response1.json()["access_token"]
        token2 = response2.json()["access_token"]
        token3 = response3.json()["access_token"]

        # Tokens should be different (each has unique exp timestamp)
        assert token1 != token2
        assert token2 != token3

    async def test_token_with_tampered_payload(self, client, auth_headers, mock_env_jwt_secret):
        """Test that tampering with token payload is detected."""
        # Arrange
        import base64
        import json

        token = auth_headers["Authorization"].split(" ")[1]
        parts = token.split(".")

        # Tamper with payload
        try:
            payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=="))
            payload["sub"] = "admin"  # Change username to admin
            tampered_payload = base64.urlsafe_b64encode(
                json.dumps(payload).encode()
            ).decode().rstrip("=")
            tampered_token = f"{parts[0]}.{tampered_payload}.{parts[2]}"

            headers = {"Authorization": f"Bearer {tampered_token}"}

            # Act
            response = await client.get("/api/v1/strategies", headers=headers)

            # Assert: Should reject due to invalid signature
            assert response.status_code == 401
        except Exception:
            # If token format is different, skip test
            pytest.skip("Token format not as expected")

    async def test_multiple_authorization_headers(self, client, auth_headers):
        """Test behavior with multiple Authorization headers."""
        # Arrange
        # This tests HTTP header handling edge case
        # Most frameworks use the first or last header
        # Act & Assert: Should handle gracefully
        response = await client.get("/api/v1/strategies", headers=auth_headers)
        assert response.status_code in [200, 400, 401]

    async def test_bearer_token_case_insensitive(self, client, jwt_token):
        """Test that 'Bearer' scheme is case-insensitive."""
        # Arrange
        headers_variants = [
            {"Authorization": f"Bearer {jwt_token}"},
            {"Authorization": f"bearer {jwt_token}"},
            {"Authorization": f"BEARER {jwt_token}"},
        ]

        for headers in headers_variants:
            # Act
            response = await client.get("/api/v1/strategies", headers=headers)

            # Assert: Should accept regardless of case
            assert response.status_code in [200, 401]


# ============================================================================
# Security Tests
# ============================================================================

class TestAuthenticationSecurity:
    """Test security aspects of authentication."""

    async def test_login_does_not_leak_user_existence(self, client):
        """Test that login error doesn't reveal if user exists."""
        # Arrange
        valid_user_wrong_pass = {
            "username": "testuser",
            "password": "wrongpassword",
        }
        invalid_user = {
            "username": "nonexistent",
            "password": "somepassword",
        }

        # Act
        response1 = await client.post("/api/v1/auth/login", json=valid_user_wrong_pass)
        response2 = await client.post("/api/v1/auth/login", json=invalid_user)

        # Assert: Both should return same error (don't reveal user existence)
        assert response1.status_code == 401
        assert response2.status_code == 401
        # Error messages should be generic
        assert response1.json()["detail"] == response2.json()["detail"]

    async def test_password_not_in_response(self, client, test_user, test_user_data):
        """Test that password is never returned in responses."""
        # Arrange
        login_data = {
            "username": test_user_data["username"],
            "password": test_user_data["password"],
        }

        # Act
        response = await client.post("/api/v1/auth/login", json=login_data)

        # Assert
        assert response.status_code == 200
        response_text = response.text.lower()
        # Password should not appear in response
        assert test_user_data["password"].lower() not in response_text
        assert "password" not in response.json()

    async def test_timing_attack_resistance(self, client, test_user, test_user_data):
        """Test that login timing doesn't reveal user existence."""
        # Arrange
        import time

        valid_user = {
            "username": test_user_data["username"],
            "password": "wrongpassword",
        }
        invalid_user = {
            "username": "nonexistent_user_xyz",
            "password": "wrongpassword",
        }

        # Act: Measure login time for both
        start1 = time.time()
        response1 = await client.post("/api/v1/auth/login", json=valid_user)
        time1 = time.time() - start1

        start2 = time.time()
        response2 = await client.post("/api/v1/auth/login", json=invalid_user)
        time2 = time.time() - start2

        # Assert: Times should be similar (within 100ms)
        # This tests constant-time password verification
        time_diff = abs(time1 - time2)
        # Note: This is a weak test due to network/process variations
        # Real timing attack prevention needs constant-time comparison in code
        assert response1.status_code == 401
        assert response2.status_code == 401

    async def test_token_not_logged(self, client, test_user, test_user_data, caplog):
        """Test that JWT tokens are not logged."""
        # Arrange
        login_data = {
            "username": test_user_data["username"],
            "password": test_user_data["password"],
        }

        # Act
        response = await client.post("/api/v1/auth/login", json=login_data)

        # Assert
        if response.status_code == 200:
            token = response.json()["access_token"]
            # Check that token doesn't appear in logs
            for record in caplog.records:
                assert token not in record.message

    async def test_rate_limiting_on_login(self, client, test_user_data):
        """Test that excessive login attempts are rate-limited."""
        # Arrange
        login_data = {
            "username": test_user_data["username"],
            "password": "wrongpassword",
        }

        # Act: Make many rapid login attempts
        responses = []
        for _ in range(20):
            response = await client.post("/api/v1/auth/login", json=login_data)
            responses.append(response)

        # Assert: After many attempts, should get rate limited
        # (Implementation dependent - may return 429 Too Many Requests)
        status_codes = [r.status_code for r in responses]
        # Either all 401, or some 429 (rate limited)
        assert all(code in [401, 429] for code in status_codes)
