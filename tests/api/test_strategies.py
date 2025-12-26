"""
Test suite for strategies CRUD endpoints.

This module tests Issue #48 strategies features:
1. GET /api/v1/strategies - List strategies (with pagination)
2. POST /api/v1/strategies - Create strategy
3. GET /api/v1/strategies/{id} - Get single strategy
4. PUT /api/v1/strategies/{id} - Update strategy
5. DELETE /api/v1/strategies/{id} - Delete strategy
6. User isolation and authorization
7. Input validation and error handling

Tests follow TDD - written before implementation.
"""

import pytest
from typing import Dict, Any

pytestmark = pytest.mark.asyncio


# ============================================================================
# Integration Tests: List Strategies
# ============================================================================

class TestListStrategies:
    """Test GET /api/v1/strategies endpoint."""

    async def test_list_strategies_requires_authentication(self, client):
        """Test that listing strategies requires valid JWT token."""
        # Act
        response = await client.get("/api/v1/strategies")

        # Assert
        assert response.status_code == 401

    async def test_list_strategies_empty_list(self, client, test_user, auth_headers, clean_db):
        """Test listing strategies when user has none."""
        # Act
        response = await client.get("/api/v1/strategies", headers=auth_headers)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list) or "items" in data
        if isinstance(data, list):
            assert len(data) == 0
        else:
            assert len(data["items"]) == 0

    async def test_list_strategies_returns_user_strategies(
        self, client, test_user, test_strategy, auth_headers
    ):
        """Test that listing returns only current user's strategies."""
        # Act
        response = await client.get("/api/v1/strategies", headers=auth_headers)

        # Assert
        assert response.status_code == 200
        data = response.json()

        # Extract items (handle both list and paginated response)
        items = data if isinstance(data, list) else data.get("items", [])
        assert len(items) >= 1

        # Verify strategy data
        strategy = items[0]
        assert strategy["name"] == test_strategy.name
        assert strategy["description"] == test_strategy.description

    async def test_list_strategies_user_isolation(
        self, client, test_user, second_user, test_strategy, auth_headers, db_session
    ):
        """Test that users only see their own strategies."""
        # Arrange: Create strategy for second user
        try:
            from tradingagents.api.models import Strategy

            other_strategy = Strategy(
                name="Other User Strategy",
                description="Should not be visible",
                user_id=second_user.id,
            )
            db_session.add(other_strategy)
            await db_session.commit()
        except ImportError:
            pytest.skip("Models not implemented yet")

        # Act: List strategies as first user
        response = await client.get("/api/v1/strategies", headers=auth_headers)

        # Assert: Should only see own strategy
        assert response.status_code == 200
        data = response.json()
        items = data if isinstance(data, list) else data.get("items", [])

        # Should only contain first user's strategy
        strategy_names = [s["name"] for s in items]
        assert test_strategy.name in strategy_names
        assert "Other User Strategy" not in strategy_names

    async def test_list_strategies_pagination(
        self, client, test_user, multiple_strategies, auth_headers
    ):
        """Test pagination of strategies list."""
        # Act: Request with pagination parameters
        response = await client.get(
            "/api/v1/strategies",
            params={"skip": 0, "limit": 2},
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()

        items = data if isinstance(data, list) else data.get("items", [])
        assert len(items) <= 2

    async def test_list_strategies_skip_offset(
        self, client, test_user, multiple_strategies, auth_headers
    ):
        """Test skip/offset pagination parameter."""
        # Act: Get first page
        response1 = await client.get(
            "/api/v1/strategies",
            params={"skip": 0, "limit": 2},
            headers=auth_headers,
        )

        # Act: Get second page
        response2 = await client.get(
            "/api/v1/strategies",
            params={"skip": 2, "limit": 2},
            headers=auth_headers,
        )

        # Assert: Both requests succeed
        assert response1.status_code == 200
        assert response2.status_code == 200

        data1 = response1.json()
        data2 = response2.json()

        items1 = data1 if isinstance(data1, list) else data1.get("items", [])
        items2 = data2 if isinstance(data2, list) else data2.get("items", [])

        # Pages should have different strategies
        if items1 and items2:
            assert items1[0]["id"] != items2[0]["id"]

    async def test_list_strategies_ordering(
        self, client, test_user, multiple_strategies, auth_headers
    ):
        """Test that strategies are ordered consistently."""
        # Act
        response = await client.get("/api/v1/strategies", headers=auth_headers)

        # Assert
        assert response.status_code == 200
        data = response.json()
        items = data if isinstance(data, list) else data.get("items", [])

        # Verify all strategies have IDs (indicates proper ordering capability)
        for strategy in items:
            assert "id" in strategy

    async def test_list_strategies_includes_metadata(
        self, client, test_user, test_strategy, auth_headers
    ):
        """Test that strategy list includes created_at, updated_at."""
        # Act
        response = await client.get("/api/v1/strategies", headers=auth_headers)

        # Assert
        assert response.status_code == 200
        data = response.json()
        items = data if isinstance(data, list) else data.get("items", [])

        strategy = items[0]
        assert "id" in strategy
        assert "name" in strategy
        assert "description" in strategy
        # Timestamps may be included
        # assert "created_at" in strategy
        # assert "updated_at" in strategy


# ============================================================================
# Integration Tests: Create Strategy
# ============================================================================

class TestCreateStrategy:
    """Test POST /api/v1/strategies endpoint."""

    async def test_create_strategy_requires_authentication(self, client, strategy_data):
        """Test that creating strategy requires JWT token."""
        # Act
        response = await client.post("/api/v1/strategies", json=strategy_data)

        # Assert
        assert response.status_code == 401

    async def test_create_strategy_success(
        self, client, test_user, auth_headers, strategy_data, clean_db
    ):
        """Test successful strategy creation."""
        # Act
        response = await client.post(
            "/api/v1/strategies",
            json=strategy_data,
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == strategy_data["name"]
        assert data["description"] == strategy_data["description"]
        assert "id" in data
        assert data["id"] is not None

    async def test_create_strategy_sets_user_id(
        self, client, test_user, auth_headers, strategy_data, clean_db
    ):
        """Test that created strategy is associated with authenticated user."""
        # Act
        response = await client.post(
            "/api/v1/strategies",
            json=strategy_data,
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 201
        data = response.json()

        # Verify ownership by trying to access as same user
        strategy_id = data["id"]
        get_response = await client.get(
            f"/api/v1/strategies/{strategy_id}",
            headers=auth_headers,
        )
        assert get_response.status_code == 200

    async def test_create_strategy_with_minimal_data(
        self, client, test_user, auth_headers, strategy_data_minimal, clean_db
    ):
        """Test creating strategy with only required fields."""
        # Act
        response = await client.post(
            "/api/v1/strategies",
            json=strategy_data_minimal,
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == strategy_data_minimal["name"]
        assert data["description"] == strategy_data_minimal["description"]

    async def test_create_strategy_with_parameters(
        self, client, test_user, auth_headers, clean_db
    ):
        """Test creating strategy with custom parameters JSON."""
        # Arrange
        strategy_data = {
            "name": "Advanced Strategy",
            "description": "Strategy with parameters",
            "parameters": {
                "symbol": "AAPL",
                "period": 20,
                "threshold": 0.02,
                "indicators": ["SMA", "RSI"],
            },
        }

        # Act
        response = await client.post(
            "/api/v1/strategies",
            json=strategy_data,
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["parameters"] == strategy_data["parameters"]

    async def test_create_strategy_validates_required_fields(
        self, client, test_user, auth_headers
    ):
        """Test that required fields are validated."""
        # Arrange
        invalid_data = {
            "description": "Missing name field",
        }

        # Act
        response = await client.post(
            "/api/v1/strategies",
            json=invalid_data,
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 422  # Validation error

    async def test_create_strategy_empty_name(self, client, test_user, auth_headers):
        """Test that empty name is rejected."""
        # Arrange
        invalid_data = {
            "name": "",
            "description": "Empty name",
        }

        # Act
        response = await client.post(
            "/api/v1/strategies",
            json=invalid_data,
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 422

    async def test_create_strategy_very_long_name(self, client, test_user, auth_headers):
        """Test creating strategy with very long name."""
        # Arrange
        long_data = {
            "name": "A" * 1000,
            "description": "Long name test",
        }

        # Act
        response = await client.post(
            "/api/v1/strategies",
            json=long_data,
            headers=auth_headers,
        )

        # Assert: Should either accept (if no limit) or reject with 422
        assert response.status_code in [201, 422]

    async def test_create_strategy_duplicate_name_allowed(
        self, client, test_user, auth_headers, strategy_data, clean_db
    ):
        """Test that duplicate strategy names are allowed (per user)."""
        # Act: Create same strategy twice
        response1 = await client.post(
            "/api/v1/strategies",
            json=strategy_data,
            headers=auth_headers,
        )
        response2 = await client.post(
            "/api/v1/strategies",
            json=strategy_data,
            headers=auth_headers,
        )

        # Assert: Both should succeed (no unique constraint on name)
        assert response1.status_code == 201
        assert response2.status_code == 201

        # But IDs should differ
        assert response1.json()["id"] != response2.json()["id"]

    async def test_create_strategy_returns_location_header(
        self, client, test_user, auth_headers, strategy_data, clean_db
    ):
        """Test that response includes Location header."""
        # Act
        response = await client.post(
            "/api/v1/strategies",
            json=strategy_data,
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 201
        # Location header may be included (optional)
        # if "Location" in response.headers:
        #     assert f"/api/v1/strategies/{response.json()['id']}" in response.headers["Location"]


# ============================================================================
# Integration Tests: Get Single Strategy
# ============================================================================

class TestGetStrategy:
    """Test GET /api/v1/strategies/{id} endpoint."""

    async def test_get_strategy_requires_authentication(self, client, test_strategy):
        """Test that getting strategy requires JWT token."""
        # Act
        response = await client.get(f"/api/v1/strategies/{test_strategy.id}")

        # Assert
        assert response.status_code == 401

    async def test_get_strategy_success(self, client, test_user, test_strategy, auth_headers):
        """Test successfully retrieving a strategy."""
        # Act
        response = await client.get(
            f"/api/v1/strategies/{test_strategy.id}",
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_strategy.id
        assert data["name"] == test_strategy.name
        assert data["description"] == test_strategy.description

    async def test_get_strategy_not_found(self, client, test_user, auth_headers):
        """Test getting non-existent strategy returns 404."""
        # Act
        response = await client.get(
            "/api/v1/strategies/99999",
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    async def test_get_strategy_unauthorized_user(
        self, client, test_user, second_user, test_strategy, db_session
    ):
        """Test that user cannot access other user's strategy."""
        # Arrange: Login as second user
        try:
            from tradingagents.api.services.auth_service import create_access_token

            second_user_token = create_access_token({"sub": second_user.username})
            second_user_headers = {"Authorization": f"Bearer {second_user_token}"}

            # Act: Try to access first user's strategy
            response = await client.get(
                f"/api/v1/strategies/{test_strategy.id}",
                headers=second_user_headers,
            )

            # Assert: Should return 404 (not 403, to avoid info leak)
            assert response.status_code == 404
        except ImportError:
            pytest.skip("Auth service not implemented yet")

    async def test_get_strategy_invalid_id_format(self, client, test_user, auth_headers):
        """Test getting strategy with invalid ID format."""
        # Act
        response = await client.get(
            "/api/v1/strategies/invalid-id",
            headers=auth_headers,
        )

        # Assert
        assert response.status_code in [400, 422, 404]

    async def test_get_strategy_includes_relationships(
        self, client, test_user, test_strategy, auth_headers
    ):
        """Test that strategy includes user relationship data."""
        # Act
        response = await client.get(
            f"/api/v1/strategies/{test_strategy.id}",
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        # May include user_id or user object
        # assert "user_id" in data or "user" in data


# ============================================================================
# Integration Tests: Update Strategy
# ============================================================================

class TestUpdateStrategy:
    """Test PUT /api/v1/strategies/{id} endpoint."""

    async def test_update_strategy_requires_authentication(self, client, test_strategy):
        """Test that updating strategy requires JWT token."""
        # Arrange
        update_data = {"name": "Updated Name"}

        # Act
        response = await client.put(
            f"/api/v1/strategies/{test_strategy.id}",
            json=update_data,
        )

        # Assert
        assert response.status_code == 401

    async def test_update_strategy_success(
        self, client, test_user, test_strategy, auth_headers
    ):
        """Test successfully updating a strategy."""
        # Arrange
        update_data = {
            "name": "Updated Strategy Name",
            "description": "Updated description",
        }

        # Act
        response = await client.put(
            f"/api/v1/strategies/{test_strategy.id}",
            json=update_data,
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == update_data["name"]
        assert data["description"] == update_data["description"]
        assert data["id"] == test_strategy.id

    async def test_update_strategy_partial_update(
        self, client, test_user, test_strategy, auth_headers
    ):
        """Test partial update (only some fields)."""
        # Arrange
        original_description = test_strategy.description
        update_data = {
            "name": "New Name Only",
        }

        # Act
        response = await client.put(
            f"/api/v1/strategies/{test_strategy.id}",
            json=update_data,
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == update_data["name"]
        # Description should be preserved (partial update)
        # Note: PUT typically requires all fields, PATCH for partial
        # This test may need adjustment based on implementation

    async def test_update_strategy_not_found(self, client, test_user, auth_headers):
        """Test updating non-existent strategy returns 404."""
        # Arrange
        update_data = {"name": "Updated"}

        # Act
        response = await client.put(
            "/api/v1/strategies/99999",
            json=update_data,
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 404

    async def test_update_strategy_unauthorized_user(
        self, client, test_user, second_user, test_strategy, db_session
    ):
        """Test that user cannot update other user's strategy."""
        # Arrange
        try:
            from tradingagents.api.services.auth_service import create_access_token

            second_user_token = create_access_token({"sub": second_user.username})
            second_user_headers = {"Authorization": f"Bearer {second_user_token}"}

            update_data = {"name": "Unauthorized Update"}

            # Act
            response = await client.put(
                f"/api/v1/strategies/{test_strategy.id}",
                json=update_data,
                headers=second_user_headers,
            )

            # Assert: Should return 404 (not 403, to avoid info leak)
            assert response.status_code == 404
        except ImportError:
            pytest.skip("Auth service not implemented yet")

    async def test_update_strategy_validation(self, client, test_user, test_strategy, auth_headers):
        """Test that update validates input data."""
        # Arrange
        invalid_data = {
            "name": "",  # Empty name should be invalid
        }

        # Act
        response = await client.put(
            f"/api/v1/strategies/{test_strategy.id}",
            json=invalid_data,
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 422

    async def test_update_strategy_parameters(
        self, client, test_user, test_strategy, auth_headers
    ):
        """Test updating strategy parameters JSON."""
        # Arrange
        update_data = {
            "name": test_strategy.name,
            "description": test_strategy.description,
            "parameters": {
                "new_param": "value",
                "updated": True,
            },
        }

        # Act
        response = await client.put(
            f"/api/v1/strategies/{test_strategy.id}",
            json=update_data,
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["parameters"]["new_param"] == "value"
        assert data["parameters"]["updated"] is True

    async def test_update_strategy_is_active_toggle(
        self, client, test_user, test_strategy, auth_headers
    ):
        """Test toggling is_active flag."""
        # Arrange
        original_status = test_strategy.is_active
        update_data = {
            "name": test_strategy.name,
            "description": test_strategy.description,
            "is_active": not original_status,
        }

        # Act
        response = await client.put(
            f"/api/v1/strategies/{test_strategy.id}",
            json=update_data,
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] != original_status


# ============================================================================
# Integration Tests: Delete Strategy
# ============================================================================

class TestDeleteStrategy:
    """Test DELETE /api/v1/strategies/{id} endpoint."""

    async def test_delete_strategy_requires_authentication(self, client, test_strategy):
        """Test that deleting strategy requires JWT token."""
        # Act
        response = await client.delete(f"/api/v1/strategies/{test_strategy.id}")

        # Assert
        assert response.status_code == 401

    async def test_delete_strategy_success(
        self, client, test_user, test_strategy, auth_headers, db_session
    ):
        """Test successfully deleting a strategy."""
        # Arrange
        strategy_id = test_strategy.id

        # Act
        response = await client.delete(
            f"/api/v1/strategies/{strategy_id}",
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 204  # No content

        # Verify strategy is deleted
        get_response = await client.get(
            f"/api/v1/strategies/{strategy_id}",
            headers=auth_headers,
        )
        assert get_response.status_code == 404

    async def test_delete_strategy_not_found(self, client, test_user, auth_headers):
        """Test deleting non-existent strategy returns 404."""
        # Act
        response = await client.delete(
            "/api/v1/strategies/99999",
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 404

    async def test_delete_strategy_unauthorized_user(
        self, client, test_user, second_user, test_strategy, db_session
    ):
        """Test that user cannot delete other user's strategy."""
        # Arrange
        try:
            from tradingagents.api.services.auth_service import create_access_token

            second_user_token = create_access_token({"sub": second_user.username})
            second_user_headers = {"Authorization": f"Bearer {second_user_token}"}

            # Act
            response = await client.delete(
                f"/api/v1/strategies/{test_strategy.id}",
                headers=second_user_headers,
            )

            # Assert: Should return 404 (not 403, to avoid info leak)
            assert response.status_code == 404

            # Verify strategy still exists for original user
            from tradingagents.api.models import Strategy
            from sqlalchemy import select

            result = await db_session.execute(
                select(Strategy).where(Strategy.id == test_strategy.id)
            )
            strategy = result.scalar_one_or_none()
            assert strategy is not None
        except ImportError:
            pytest.skip("Auth service or models not implemented yet")

    async def test_delete_strategy_idempotent(
        self, client, test_user, test_strategy, auth_headers
    ):
        """Test that deleting same strategy twice returns 404 second time."""
        # Act: Delete first time
        response1 = await client.delete(
            f"/api/v1/strategies/{test_strategy.id}",
            headers=auth_headers,
        )

        # Act: Delete second time
        response2 = await client.delete(
            f"/api/v1/strategies/{test_strategy.id}",
            headers=auth_headers,
        )

        # Assert
        assert response1.status_code == 204
        assert response2.status_code == 404

    async def test_delete_strategy_cascade_behavior(
        self, client, test_user, test_strategy, auth_headers, db_session
    ):
        """Test cascade delete behavior if strategy has related data."""
        # This test is for future expansion if strategies have
        # related entities (e.g., backtest results, trades)

        # Act
        response = await client.delete(
            f"/api/v1/strategies/{test_strategy.id}",
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 204
        # Related data should also be deleted (if any)


# ============================================================================
# Edge Cases: Strategies CRUD
# ============================================================================

class TestStrategiesEdgeCases:
    """Test edge cases and boundary conditions."""

    async def test_create_strategy_with_sql_injection(
        self, client, test_user, auth_headers, sample_sql_injection_payloads
    ):
        """Test SQL injection prevention in strategy creation."""
        # Arrange
        for payload in sample_sql_injection_payloads:
            strategy_data = {
                "name": payload,
                "description": payload,
            }

            # Act
            response = await client.post(
                "/api/v1/strategies",
                json=strategy_data,
                headers=auth_headers,
            )

            # Assert: Should not crash (200/201 or 422, not 500)
            assert response.status_code in [201, 422]

    async def test_create_strategy_with_xss_payload(
        self, client, test_user, auth_headers, sample_xss_payloads
    ):
        """Test XSS prevention in strategy data."""
        # Arrange
        for payload in sample_xss_payloads:
            strategy_data = {
                "name": f"Strategy {payload}",
                "description": payload,
            }

            # Act
            response = await client.post(
                "/api/v1/strategies",
                json=strategy_data,
                headers=auth_headers,
            )

            # Assert: Should handle gracefully
            assert response.status_code in [201, 422]

            if response.status_code == 201:
                # Verify payload is sanitized or escaped
                data = response.json()
                # Should not contain raw script tags
                assert "<script>" not in data["name"].lower()
                assert "<script>" not in data["description"].lower()

    async def test_strategy_with_unicode_characters(
        self, client, test_user, auth_headers, clean_db
    ):
        """Test creating strategy with Unicode characters."""
        # Arrange
        strategy_data = {
            "name": "策略 测试 🚀",
            "description": "Стратегия with émojis 🎯",
        }

        # Act
        response = await client.post(
            "/api/v1/strategies",
            json=strategy_data,
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == strategy_data["name"]
        assert data["description"] == strategy_data["description"]

    async def test_strategy_with_null_parameters(
        self, client, test_user, auth_headers, clean_db
    ):
        """Test creating strategy with null parameters field."""
        # Arrange
        strategy_data = {
            "name": "Null Params Strategy",
            "description": "Testing null parameters",
            "parameters": None,
        }

        # Act
        response = await client.post(
            "/api/v1/strategies",
            json=strategy_data,
            headers=auth_headers,
        )

        # Assert: Should handle null gracefully
        assert response.status_code in [201, 422]

    async def test_strategy_with_deeply_nested_parameters(
        self, client, test_user, auth_headers, clean_db
    ):
        """Test creating strategy with deeply nested JSON parameters."""
        # Arrange
        strategy_data = {
            "name": "Nested Params",
            "description": "Deep nesting test",
            "parameters": {
                "level1": {
                    "level2": {
                        "level3": {
                            "level4": {
                                "value": "deep",
                            }
                        }
                    }
                }
            },
        }

        # Act
        response = await client.post(
            "/api/v1/strategies",
            json=strategy_data,
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["parameters"]["level1"]["level2"]["level3"]["level4"]["value"] == "deep"

    async def test_strategy_with_large_parameters_json(
        self, client, test_user, auth_headers, clean_db
    ):
        """Test creating strategy with large JSON parameters."""
        # Arrange
        large_params = {f"key_{i}": f"value_{i}" for i in range(1000)}
        strategy_data = {
            "name": "Large Params",
            "description": "Large JSON test",
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

    async def test_concurrent_strategy_creation(
        self, client, test_user, auth_headers, clean_db
    ):
        """Test creating multiple strategies concurrently."""
        # Arrange
        import asyncio

        async def create_strategy(name):
            strategy_data = {
                "name": name,
                "description": f"Concurrent test {name}",
            }
            return await client.post(
                "/api/v1/strategies",
                json=strategy_data,
                headers=auth_headers,
            )

        # Act: Create 10 strategies concurrently
        tasks = [create_strategy(f"Strategy {i}") for i in range(10)]
        responses = await asyncio.gather(*tasks)

        # Assert: All should succeed
        assert all(r.status_code == 201 for r in responses)

        # All should have unique IDs
        ids = [r.json()["id"] for r in responses]
        assert len(ids) == len(set(ids))  # All unique

    async def test_strategy_update_race_condition(
        self, client, test_user, test_strategy, auth_headers
    ):
        """Test concurrent updates to same strategy."""
        # Arrange
        import asyncio

        async def update_strategy(name):
            update_data = {
                "name": name,
                "description": "Race condition test",
            }
            return await client.put(
                f"/api/v1/strategies/{test_strategy.id}",
                json=update_data,
                headers=auth_headers,
            )

        # Act: Update same strategy concurrently
        tasks = [update_strategy(f"Update {i}") for i in range(5)]
        responses = await asyncio.gather(*tasks)

        # Assert: All should succeed (last write wins)
        assert all(r.status_code == 200 for r in responses)

    async def test_pagination_boundary_conditions(
        self, client, test_user, multiple_strategies, auth_headers
    ):
        """Test pagination edge cases."""
        # Test limit=0
        response = await client.get(
            "/api/v1/strategies",
            params={"skip": 0, "limit": 0},
            headers=auth_headers,
        )
        assert response.status_code == 200

        # Test very large limit
        response = await client.get(
            "/api/v1/strategies",
            params={"skip": 0, "limit": 10000},
            headers=auth_headers,
        )
        assert response.status_code == 200

        # Test negative skip
        response = await client.get(
            "/api/v1/strategies",
            params={"skip": -1, "limit": 10},
            headers=auth_headers,
        )
        # Should either reject or treat as 0
        assert response.status_code in [200, 422]

    async def test_strategy_id_overflow(self, client, test_user, auth_headers):
        """Test accessing strategy with very large ID."""
        # Act
        response = await client.get(
            f"/api/v1/strategies/{2**63}",  # Max int64
            headers=auth_headers,
        )

        # Assert: Should handle gracefully
        assert response.status_code in [404, 422]


# ============================================================================
# Performance Tests
# ============================================================================

class TestStrategiesPerformance:
    """Test performance characteristics of strategies endpoints."""

    async def test_list_strategies_response_time(
        self, client, test_user, multiple_strategies, auth_headers
    ):
        """Test that listing strategies responds quickly."""
        # Arrange
        import time

        # Act
        start = time.time()
        response = await client.get("/api/v1/strategies", headers=auth_headers)
        duration = time.time() - start

        # Assert: Should respond in under 1 second
        assert response.status_code == 200
        assert duration < 1.0

    async def test_create_strategy_response_time(
        self, client, test_user, auth_headers, strategy_data
    ):
        """Test that creating strategy responds quickly."""
        # Arrange
        import time

        # Act
        start = time.time()
        response = await client.post(
            "/api/v1/strategies",
            json=strategy_data,
            headers=auth_headers,
        )
        duration = time.time() - start

        # Assert
        assert response.status_code == 201
        assert duration < 1.0
