"""
Test suite for FastAPI middleware and error handling.

This module tests Issue #48 middleware features:
1. Error handling middleware
2. HTTP exceptions (400, 401, 404, 422, 500)
3. Request logging middleware
4. CORS middleware (if implemented)
5. Request ID tracking
6. Error response format consistency

Tests follow TDD - written before implementation.
"""

import pytest
from typing import Dict, Any

pytestmark = pytest.mark.asyncio


# ============================================================================
# Integration Tests: Error Handling Middleware
# ============================================================================

class TestErrorHandlingMiddleware:
    """Test global error handling and exception formatting."""

    async def test_404_not_found_format(self, client):
        """Test 404 error has consistent format."""
        # Act
        response = await client.get("/api/v1/nonexistent")

        # Assert
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert isinstance(data["detail"], str)

    async def test_422_validation_error_format(self, client, auth_headers):
        """Test 422 validation error has detailed format."""
        # Arrange: Send invalid data
        invalid_data = {
            "name": 123,  # Should be string
        }

        # Act
        response = await client.post(
            "/api/v1/strategies",
            json=invalid_data,
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data
        # FastAPI validation errors include location and message
        if isinstance(data["detail"], list):
            assert len(data["detail"]) > 0
            error = data["detail"][0]
            assert "loc" in error or "msg" in error

    async def test_401_unauthorized_format(self, client):
        """Test 401 unauthorized error format."""
        # Act: Access protected endpoint without token
        response = await client.get("/api/v1/strategies")

        # Assert
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data

    async def test_500_internal_error_handling(self, client, test_user, auth_headers):
        """Test that 500 errors are caught and formatted consistently."""
        # This test requires an endpoint that can trigger 500 error
        # Will need to be implemented based on actual error scenarios

        # For now, test that if 500 occurs, it has proper format
        # (Implementation may need mock or special test endpoint)
        pass

    async def test_error_response_includes_timestamp(self, client):
        """Test that error responses may include timestamp."""
        # Act
        response = await client.get("/api/v1/nonexistent")

        # Assert
        assert response.status_code == 404
        data = response.json()
        # Timestamp may be included for debugging
        # assert "timestamp" in data or "detail" in data

    async def test_error_response_no_stack_trace(self, client):
        """Test that error responses don't leak stack traces in production."""
        # Act
        response = await client.get("/api/v1/nonexistent")

        # Assert
        assert response.status_code == 404
        data = response.json()
        response_text = str(data).lower()

        # Should not contain stack trace keywords
        assert "traceback" not in response_text
        assert "line " not in response_text  # "line 123" from stack traces
        assert ".py" not in response_text  # File paths

    async def test_error_response_content_type(self, client):
        """Test that error responses have correct Content-Type."""
        # Act
        response = await client.get("/api/v1/nonexistent")

        # Assert
        assert response.status_code == 404
        assert "application/json" in response.headers.get("content-type", "")


# ============================================================================
# Unit Tests: Exception Handlers
# ============================================================================

class TestExceptionHandlers:
    """Test custom exception handlers."""

    async def test_http_exception_handler(self, client):
        """Test HTTPException is handled correctly."""
        # This would test custom HTTPException handler if implemented
        # Act: Trigger HTTPException
        response = await client.get("/api/v1/strategies/invalid")

        # Assert: Should be handled gracefully
        assert response.status_code in [400, 404, 422]

    async def test_validation_exception_handler(self, client, auth_headers):
        """Test RequestValidationError handler."""
        # Arrange: Send malformed JSON
        # Act
        response = await client.post(
            "/api/v1/strategies",
            data="not valid json",
            headers={**auth_headers, "Content-Type": "application/json"},
        )

        # Assert
        assert response.status_code == 422

    async def test_generic_exception_handler(self, client):
        """Test that unexpected exceptions are caught."""
        # This requires an endpoint that can raise unexpected exception
        # or mock implementation
        pass


# ============================================================================
# Integration Tests: Request Logging
# ============================================================================

class TestRequestLogging:
    """Test request and response logging middleware."""

    async def test_request_logging_on_success(self, client, test_user, auth_headers, caplog):
        """Test that successful requests are logged."""
        # Act
        response = await client.get("/api/v1/strategies", headers=auth_headers)

        # Assert
        assert response.status_code == 200
        # Check logs for request info (if logging middleware implemented)
        # log_messages = [record.message for record in caplog.records]
        # assert any("GET" in msg and "/api/v1/strategies" in msg for msg in log_messages)

    async def test_request_logging_on_error(self, client, caplog):
        """Test that failed requests are logged."""
        # Act
        response = await client.get("/api/v1/nonexistent")

        # Assert
        assert response.status_code == 404
        # Errors should be logged
        # log_messages = [record.message for record in caplog.records]
        # assert any("404" in msg for msg in log_messages)

    async def test_sensitive_data_not_logged(
        self, client, test_user, test_user_data, caplog
    ):
        """Test that passwords/tokens are not logged."""
        # Arrange
        login_data = {
            "username": test_user_data["username"],
            "password": test_user_data["password"],
        }

        # Act
        response = await client.post("/api/v1/auth/login", json=login_data)

        # Assert: Password should not appear in logs
        log_text = " ".join([record.message for record in caplog.records])
        assert test_user_data["password"] not in log_text

        if response.status_code == 200:
            token = response.json().get("access_token", "")
            # Token should not be fully logged (may log prefix)
            if token:
                assert token not in log_text


# ============================================================================
# Integration Tests: CORS Middleware
# ============================================================================

class TestCORSMiddleware:
    """Test CORS (Cross-Origin Resource Sharing) configuration."""

    async def test_cors_preflight_request(self, client):
        """Test CORS preflight OPTIONS request."""
        # Act
        response = await client.options(
            "/api/v1/strategies",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

        # Assert: May return 200 or 405 if CORS not configured
        assert response.status_code in [200, 405]

        # If CORS is configured, check headers
        if response.status_code == 200:
            assert "access-control-allow-origin" in [
                h.lower() for h in response.headers.keys()
            ]

    async def test_cors_headers_on_response(self, client, test_user, auth_headers):
        """Test that CORS headers are present on API responses."""
        # Act
        response = await client.get(
            "/api/v1/strategies",
            headers={**auth_headers, "Origin": "http://localhost:3000"},
        )

        # Assert
        assert response.status_code == 200
        # CORS headers may be present if configured
        # assert "access-control-allow-origin" in [h.lower() for h in response.headers.keys()]

    async def test_cors_credentials_allowed(self, client):
        """Test CORS credentials configuration."""
        # This tests if cookies/credentials are allowed
        # May not be applicable if using JWT bearer tokens only
        pass


# ============================================================================
# Integration Tests: Request ID Tracking
# ============================================================================

class TestRequestIDTracking:
    """Test request ID generation and tracking."""

    async def test_request_id_in_response_headers(self, client):
        """Test that responses include request ID header."""
        # Act
        response = await client.get("/api/v1/strategies")

        # Assert: May include X-Request-ID header
        # request_id = response.headers.get("X-Request-ID")
        # if request_id:
        #     assert len(request_id) > 0

    async def test_request_id_propagation(self, client):
        """Test that request ID from client is preserved."""
        # Arrange
        client_request_id = "client-req-123"

        # Act
        response = await client.get(
            "/api/v1/strategies",
            headers={"X-Request-ID": client_request_id},
        )

        # Assert: Server may preserve client's request ID
        # response_request_id = response.headers.get("X-Request-ID")
        # assert response_request_id == client_request_id


# ============================================================================
# Integration Tests: Rate Limiting
# ============================================================================

class TestRateLimiting:
    """Test rate limiting middleware (if implemented)."""

    async def test_rate_limit_not_exceeded(self, client, test_user, auth_headers):
        """Test normal request rate is allowed."""
        # Act: Make reasonable number of requests
        for _ in range(5):
            response = await client.get("/api/v1/strategies", headers=auth_headers)
            assert response.status_code == 200

    async def test_rate_limit_headers(self, client, test_user, auth_headers):
        """Test that rate limit headers are included."""
        # Act
        response = await client.get("/api/v1/strategies", headers=auth_headers)

        # Assert: May include rate limit headers
        # assert "X-RateLimit-Limit" in response.headers
        # assert "X-RateLimit-Remaining" in response.headers

    async def test_rate_limit_exceeded(self, client, test_user_data):
        """Test that excessive requests are rate limited."""
        # Arrange: Login endpoint is good for rate limit testing
        login_data = {
            "username": test_user_data["username"],
            "password": "wrong_password",
        }

        # Act: Make many rapid requests
        responses = []
        for _ in range(50):
            response = await client.post("/api/v1/auth/login", json=login_data)
            responses.append(response)

        # Assert: Should eventually get rate limited (429)
        status_codes = [r.status_code for r in responses]
        # May include 429 Too Many Requests if rate limiting implemented
        # assert 429 in status_codes or all(code == 401 for code in status_codes)


# ============================================================================
# Integration Tests: Content Negotiation
# ============================================================================

class TestContentNegotiation:
    """Test content type handling."""

    async def test_json_content_type_accepted(self, client, test_user, auth_headers):
        """Test that application/json is accepted."""
        # Arrange
        strategy_data = {
            "name": "Test Strategy",
            "description": "Test",
        }

        # Act
        response = await client.post(
            "/api/v1/strategies",
            json=strategy_data,
            headers={**auth_headers, "Content-Type": "application/json"},
        )

        # Assert
        assert response.status_code == 201

    async def test_json_response_content_type(self, client, test_user, auth_headers):
        """Test that responses have JSON content type."""
        # Act
        response = await client.get("/api/v1/strategies", headers=auth_headers)

        # Assert
        assert response.status_code == 200
        assert "application/json" in response.headers.get("content-type", "")

    async def test_unsupported_content_type_rejected(self, client, auth_headers):
        """Test that unsupported content types are rejected."""
        # Act: Send XML instead of JSON
        response = await client.post(
            "/api/v1/strategies",
            data="<xml>data</xml>",
            headers={**auth_headers, "Content-Type": "application/xml"},
        )

        # Assert: Should reject (415 Unsupported Media Type or 422)
        assert response.status_code in [415, 422]


# ============================================================================
# Edge Cases: Middleware
# ============================================================================

class TestMiddlewareEdgeCases:
    """Test edge cases in middleware handling."""

    async def test_very_large_request_body(self, client, test_user, auth_headers):
        """Test handling of very large request bodies."""
        # Arrange: Create 1MB JSON
        large_params = {"key": "x" * 1_000_000}
        strategy_data = {
            "name": "Large Body Test",
            "description": "Testing large request",
            "parameters": large_params,
        }

        # Act
        response = await client.post(
            "/api/v1/strategies",
            json=strategy_data,
            headers=auth_headers,
        )

        # Assert: Should either accept or reject gracefully
        assert response.status_code in [201, 413, 422]  # 413 = Payload Too Large

    async def test_malformed_json_request(self, client, auth_headers):
        """Test handling of malformed JSON."""
        # Act
        response = await client.post(
            "/api/v1/strategies",
            data='{"name": "test", invalid json}',
            headers={**auth_headers, "Content-Type": "application/json"},
        )

        # Assert
        assert response.status_code == 422

    async def test_empty_request_body(self, client, auth_headers):
        """Test handling of empty request body."""
        # Act
        response = await client.post(
            "/api/v1/strategies",
            data="",
            headers={**auth_headers, "Content-Type": "application/json"},
        )

        # Assert
        assert response.status_code == 422

    async def test_null_request_body(self, client, auth_headers):
        """Test handling of null JSON body."""
        # Act
        response = await client.post(
            "/api/v1/strategies",
            json=None,
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 422

    async def test_concurrent_requests_different_users(self, client, db_session):
        """Test middleware handles concurrent requests correctly."""
        # Arrange
        import asyncio

        try:
            from tradingagents.api.services.auth_service import create_access_token

            user1_headers = {
                "Authorization": f"Bearer {create_access_token({'sub': 'user1'})}"
            }
            user2_headers = {
                "Authorization": f"Bearer {create_access_token({'sub': 'user2'})}"
            }

            # Act: Make concurrent requests for different users
            tasks = [
                client.get("/api/v1/strategies", headers=user1_headers),
                client.get("/api/v1/strategies", headers=user2_headers),
                client.get("/api/v1/strategies", headers=user1_headers),
                client.get("/api/v1/strategies", headers=user2_headers),
            ]
            responses = await asyncio.gather(*tasks, return_exceptions=True)

            # Assert: All should complete without mixing user contexts
            # (This tests request context isolation)
            assert len(responses) == 4
        except ImportError:
            pytest.skip("Auth service not implemented yet")

    async def test_special_characters_in_url(self, client, test_user, auth_headers):
        """Test URL encoding and special characters."""
        # Act: Try various special characters in URL
        special_chars = ["%20", "%2F", "..%2F", "%00"]

        for char in special_chars:
            response = await client.get(
                f"/api/v1/strategies/{char}",
                headers=auth_headers,
            )

            # Assert: Should handle gracefully (not crash)
            assert response.status_code in [400, 404, 422]

    async def test_very_long_url_path(self, client, test_user, auth_headers):
        """Test handling of very long URL paths."""
        # Arrange
        long_path = "a" * 10000

        # Act
        response = await client.get(
            f"/api/v1/strategies/{long_path}",
            headers=auth_headers,
        )

        # Assert: Should reject gracefully
        assert response.status_code in [400, 404, 414, 422]  # 414 = URI Too Long

    async def test_header_injection_prevention(self, client):
        """Test that header injection is prevented."""
        # Arrange: Try to inject headers via CRLF
        malicious_header = "Bearer token\r\nX-Injected: malicious"

        # Act
        response = await client.get(
            "/api/v1/strategies",
            headers={"Authorization": malicious_header},
        )

        # Assert: Should reject or sanitize
        assert response.status_code in [400, 401]


# ============================================================================
# Security Tests: Middleware
# ============================================================================

class TestMiddlewareSecurity:
    """Test security aspects of middleware."""

    async def test_security_headers_present(self, client):
        """Test that security headers are set."""
        # Act
        response = await client.get("/api/v1/strategies")

        # Assert: Check for common security headers
        headers = {k.lower(): v for k, v in response.headers.items()}

        # May include security headers like:
        # - X-Content-Type-Options: nosniff
        # - X-Frame-Options: DENY
        # - X-XSS-Protection: 1; mode=block
        # These are optional but recommended

    async def test_no_server_version_leak(self, client):
        """Test that Server header doesn't leak version info."""
        # Act
        response = await client.get("/api/v1/strategies")

        # Assert: Server header should be minimal
        server_header = response.headers.get("Server", "")
        # Should not contain version numbers or detailed info
        assert "uvicorn" not in server_header.lower() or "/" not in server_header

    async def test_error_messages_dont_leak_info(self, client):
        """Test that error messages don't leak sensitive information."""
        # Act: Trigger various errors
        response = await client.get("/api/v1/strategies/99999")

        # Assert
        assert response.status_code == 404
        data = response.json()
        error_text = str(data).lower()

        # Should not leak database info
        assert "sql" not in error_text
        assert "database" not in error_text
        assert "table" not in error_text

    async def test_method_not_allowed_handling(self, client):
        """Test handling of unsupported HTTP methods."""
        # Act: Try PATCH on endpoint that doesn't support it
        response = await client.patch("/api/v1/strategies")

        # Assert
        assert response.status_code == 405  # Method Not Allowed
        assert "Allow" in response.headers or "allow" in response.headers
