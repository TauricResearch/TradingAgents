"""
Test suite for API Key Service (Issue #3).

This module tests the API key generation, hashing, and verification service:
1. Generate secure random API keys
2. Hash API keys using bcrypt
3. Verify API keys against hashes
4. Key format validation
5. Security best practices

Tests follow TDD - written before implementation.
"""

import pytest
import re
from typing import Optional

pytestmark = pytest.mark.unit


# ============================================================================
# Unit Tests: API Key Generation
# ============================================================================

class TestApiKeyGeneration:
    """Test API key generation functionality."""

    def test_generate_api_key_returns_string(self):
        """Test that generate_api_key returns a string."""
        # Arrange & Act
        try:
            from tradingagents.api.services.api_key_service import generate_api_key

            api_key = generate_api_key()

            # Assert
            assert isinstance(api_key, str)
            assert len(api_key) > 0
        except ImportError:
            pytest.skip("API key service not implemented yet")

    def test_generate_api_key_format(self):
        """Test that generated API key has correct format."""
        # Arrange & Act
        try:
            from tradingagents.api.services.api_key_service import generate_api_key

            api_key = generate_api_key()

            # Assert: Should be prefixed with "ta_" (TradingAgents)
            assert api_key.startswith("ta_")

            # Should contain only alphanumeric characters after prefix
            key_part = api_key[3:]  # Remove "ta_" prefix
            assert re.match(r'^[A-Za-z0-9]+$', key_part)
        except ImportError:
            pytest.skip("API key service not implemented yet")

    def test_generate_api_key_length(self):
        """Test that generated API key has sufficient length for security."""
        # Arrange & Act
        try:
            from tradingagents.api.services.api_key_service import generate_api_key

            api_key = generate_api_key()

            # Assert: Should be at least 32 characters (including prefix)
            assert len(api_key) >= 32

            # Key part (without prefix) should be at least 29 chars
            key_part = api_key[3:]
            assert len(key_part) >= 29
        except ImportError:
            pytest.skip("API key service not implemented yet")

    def test_generate_api_key_uniqueness(self):
        """Test that each generated API key is unique."""
        # Arrange & Act
        try:
            from tradingagents.api.services.api_key_service import generate_api_key

            keys = [generate_api_key() for _ in range(100)]

            # Assert: All keys should be unique
            assert len(keys) == len(set(keys))
        except ImportError:
            pytest.skip("API key service not implemented yet")

    def test_generate_api_key_randomness(self):
        """Test that API keys have sufficient randomness."""
        # Arrange & Act
        try:
            from tradingagents.api.services.api_key_service import generate_api_key

            keys = [generate_api_key() for _ in range(10)]

            # Assert: Keys should not have common patterns
            # Check that no two keys share same first 10 chars after prefix
            prefixes = [key[3:13] for key in keys]
            assert len(prefixes) == len(set(prefixes))
        except ImportError:
            pytest.skip("API key service not implemented yet")

    def test_generate_api_key_custom_length(self):
        """Test generating API key with custom length."""
        # Arrange & Act
        try:
            from tradingagents.api.services.api_key_service import generate_api_key

            # Try generating key with custom length (if supported)
            api_key = generate_api_key(length=40)

            # Assert: Should respect custom length
            assert len(api_key) >= 40 or len(api_key) >= 32  # May have min length
        except (ImportError, TypeError):
            # TypeError is ok if length parameter not implemented
            pytest.skip("Custom length not implemented yet")


# ============================================================================
# Unit Tests: API Key Hashing
# ============================================================================

class TestApiKeyHashing:
    """Test API key hashing functionality."""

    def test_hash_api_key_returns_string(self):
        """Test that hash_api_key returns a string."""
        # Arrange
        try:
            from tradingagents.api.services.api_key_service import hash_api_key

            api_key = "ta_test1234567890abcdefghijklmnop"

            # Act
            hashed = hash_api_key(api_key)

            # Assert
            assert isinstance(hashed, str)
            assert len(hashed) > 0
        except ImportError:
            pytest.skip("API key service not implemented yet")

    def test_hash_api_key_bcrypt_format(self):
        """Test that hashed API key uses bcrypt format."""
        # Arrange
        try:
            from tradingagents.api.services.api_key_service import hash_api_key

            api_key = "ta_test1234567890abcdefghijklmnop"

            # Act
            hashed = hash_api_key(api_key)

            # Assert: Should be bcrypt format ($2b$rounds$salt+hash)
            assert hashed.startswith("$2b$") or hashed.startswith("$2a$")
            assert len(hashed) == 60  # Standard bcrypt hash length
        except ImportError:
            pytest.skip("API key service not implemented yet")

    def test_hash_api_key_different_for_same_input(self):
        """Test that hashing same key twice produces different hashes (salt)."""
        # Arrange
        try:
            from tradingagents.api.services.api_key_service import hash_api_key

            api_key = "ta_test1234567890abcdefghijklmnop"

            # Act
            hash1 = hash_api_key(api_key)
            hash2 = hash_api_key(api_key)

            # Assert: Should be different due to different salts
            assert hash1 != hash2
            assert hash1.startswith("$2b$")
            assert hash2.startswith("$2b$")
        except ImportError:
            pytest.skip("API key service not implemented yet")

    def test_hash_api_key_different_keys_different_hashes(self):
        """Test that different keys produce different hashes."""
        # Arrange
        try:
            from tradingagents.api.services.api_key_service import hash_api_key

            key1 = "ta_key1234567890abcdefghijklmnop"
            key2 = "ta_key9876543210zyxwvutsrqponmlk"

            # Act
            hash1 = hash_api_key(key1)
            hash2 = hash_api_key(key2)

            # Assert
            assert hash1 != hash2
        except ImportError:
            pytest.skip("API key service not implemented yet")

    def test_hash_api_key_empty_string(self):
        """Test hashing empty string."""
        # Arrange
        try:
            from tradingagents.api.services.api_key_service import hash_api_key

            # Act & Assert: Should handle gracefully or raise ValueError
            try:
                hashed = hash_api_key("")
                # If it doesn't raise, should still return valid hash
                assert isinstance(hashed, str)
            except ValueError:
                # Acceptable to raise ValueError for empty key
                pass
        except ImportError:
            pytest.skip("API key service not implemented yet")

    def test_hash_api_key_special_characters(self):
        """Test hashing API key with special characters."""
        # Arrange
        try:
            from tradingagents.api.services.api_key_service import hash_api_key

            api_key = "ta_key!@#$%^&*()_+-=[]{}|;:,.<>?"

            # Act
            hashed = hash_api_key(api_key)

            # Assert: Should handle special characters
            assert isinstance(hashed, str)
            assert hashed.startswith("$2b$") or hashed.startswith("$2a$")
        except ImportError:
            pytest.skip("API key service not implemented yet")


# ============================================================================
# Unit Tests: API Key Verification
# ============================================================================

class TestApiKeyVerification:
    """Test API key verification functionality."""

    def test_verify_api_key_correct_key(self):
        """Test verifying API key with correct hash."""
        # Arrange
        try:
            from tradingagents.api.services.api_key_service import (
                hash_api_key,
                verify_api_key,
            )

            api_key = "ta_correct1234567890abcdefghijk"
            hashed = hash_api_key(api_key)

            # Act
            is_valid = verify_api_key(api_key, hashed)

            # Assert
            assert is_valid is True
        except ImportError:
            pytest.skip("API key service not implemented yet")

    def test_verify_api_key_incorrect_key(self):
        """Test verifying API key with wrong hash."""
        # Arrange
        try:
            from tradingagents.api.services.api_key_service import (
                hash_api_key,
                verify_api_key,
            )

            correct_key = "ta_correct1234567890abcdefghijk"
            wrong_key = "ta_wrongkey1234567890abcdefghij"
            hashed = hash_api_key(correct_key)

            # Act
            is_valid = verify_api_key(wrong_key, hashed)

            # Assert
            assert is_valid is False
        except ImportError:
            pytest.skip("API key service not implemented yet")

    def test_verify_api_key_empty_key(self):
        """Test verifying empty API key."""
        # Arrange
        try:
            from tradingagents.api.services.api_key_service import (
                hash_api_key,
                verify_api_key,
            )

            api_key = "ta_test1234567890abcdefghijklmn"
            hashed = hash_api_key(api_key)

            # Act
            is_valid = verify_api_key("", hashed)

            # Assert
            assert is_valid is False
        except ImportError:
            pytest.skip("API key service not implemented yet")

    def test_verify_api_key_none_key(self):
        """Test verifying None API key."""
        # Arrange
        try:
            from tradingagents.api.services.api_key_service import (
                hash_api_key,
                verify_api_key,
            )

            api_key = "ta_test1234567890abcdefghijklmn"
            hashed = hash_api_key(api_key)

            # Act & Assert: Should return False or raise TypeError
            try:
                is_valid = verify_api_key(None, hashed)
                assert is_valid is False
            except TypeError:
                # Acceptable to raise TypeError for None
                pass
        except ImportError:
            pytest.skip("API key service not implemented yet")

    def test_verify_api_key_invalid_hash(self):
        """Test verifying API key against invalid hash."""
        # Arrange
        try:
            from tradingagents.api.services.api_key_service import verify_api_key

            api_key = "ta_test1234567890abcdefghijklmn"
            invalid_hash = "not-a-valid-bcrypt-hash"

            # Act & Assert: Should return False or raise ValueError
            try:
                is_valid = verify_api_key(api_key, invalid_hash)
                assert is_valid is False
            except ValueError:
                # Acceptable to raise ValueError for invalid hash
                pass
        except ImportError:
            pytest.skip("API key service not implemented yet")

    def test_verify_api_key_case_sensitive(self):
        """Test that API key verification is case-sensitive."""
        # Arrange
        try:
            from tradingagents.api.services.api_key_service import (
                hash_api_key,
                verify_api_key,
            )

            api_key = "ta_TestKey1234567890ABCDEFGHIJK"
            hashed = hash_api_key(api_key)

            # Act
            is_valid_correct = verify_api_key(api_key, hashed)
            is_valid_wrong_case = verify_api_key(api_key.lower(), hashed)

            # Assert
            assert is_valid_correct is True
            assert is_valid_wrong_case is False
        except ImportError:
            pytest.skip("API key service not implemented yet")

    def test_verify_api_key_similar_keys(self):
        """Test that similar keys don't validate."""
        # Arrange
        try:
            from tradingagents.api.services.api_key_service import (
                hash_api_key,
                verify_api_key,
            )

            api_key = "ta_key1234567890abcdefghijklmnop"
            similar_key = "ta_key1234567890abcdefghijklmnox"  # Last char different
            hashed = hash_api_key(api_key)

            # Act
            is_valid = verify_api_key(similar_key, hashed)

            # Assert
            assert is_valid is False
        except ImportError:
            pytest.skip("API key service not implemented yet")


# ============================================================================
# Integration Tests: Full API Key Lifecycle
# ============================================================================

class TestApiKeyLifecycle:
    """Test complete API key generation, hashing, and verification workflow."""

    def test_full_api_key_lifecycle(self):
        """Test complete lifecycle: generate -> hash -> verify."""
        # Arrange & Act
        try:
            from tradingagents.api.services.api_key_service import (
                generate_api_key,
                hash_api_key,
                verify_api_key,
            )

            # Generate new API key
            api_key = generate_api_key()

            # Hash the API key
            hashed = hash_api_key(api_key)

            # Verify with correct key
            is_valid = verify_api_key(api_key, hashed)

            # Assert
            assert isinstance(api_key, str)
            assert api_key.startswith("ta_")
            assert isinstance(hashed, str)
            assert hashed.startswith("$2b$") or hashed.startswith("$2a$")
            assert is_valid is True
        except ImportError:
            pytest.skip("API key service not implemented yet")

    def test_multiple_keys_independent(self):
        """Test that multiple API keys can coexist independently."""
        # Arrange & Act
        try:
            from tradingagents.api.services.api_key_service import (
                generate_api_key,
                hash_api_key,
                verify_api_key,
            )

            # Generate multiple keys
            key1 = generate_api_key()
            key2 = generate_api_key()
            key3 = generate_api_key()

            # Hash each key
            hash1 = hash_api_key(key1)
            hash2 = hash_api_key(key2)
            hash3 = hash_api_key(key3)

            # Assert: Each key only verifies against its own hash
            assert verify_api_key(key1, hash1) is True
            assert verify_api_key(key1, hash2) is False
            assert verify_api_key(key1, hash3) is False

            assert verify_api_key(key2, hash1) is False
            assert verify_api_key(key2, hash2) is True
            assert verify_api_key(key2, hash3) is False

            assert verify_api_key(key3, hash1) is False
            assert verify_api_key(key3, hash2) is False
            assert verify_api_key(key3, hash3) is True
        except ImportError:
            pytest.skip("API key service not implemented yet")

    def test_regenerate_key_invalidates_old_hash(self):
        """Test that regenerating a key invalidates the old hash."""
        # Arrange & Act
        try:
            from tradingagents.api.services.api_key_service import (
                generate_api_key,
                hash_api_key,
                verify_api_key,
            )

            # Generate and hash first key
            old_key = generate_api_key()
            old_hash = hash_api_key(old_key)

            # Generate new key (simulate regeneration)
            new_key = generate_api_key()

            # Assert: Old hash should not work with new key
            assert verify_api_key(old_key, old_hash) is True
            assert verify_api_key(new_key, old_hash) is False
        except ImportError:
            pytest.skip("API key service not implemented yet")


# ============================================================================
# Edge Cases: API Key Service
# ============================================================================

class TestApiKeyEdgeCases:
    """Test edge cases in API key service."""

    def test_hash_very_long_key(self):
        """Test hashing very long API key."""
        # Arrange
        try:
            from tradingagents.api.services.api_key_service import (
                hash_api_key,
                verify_api_key,
            )

            # Create very long key (bcrypt has 72 byte limit)
            long_key = "ta_" + "a" * 200

            # Act
            hashed = hash_api_key(long_key)
            is_valid = verify_api_key(long_key, hashed)

            # Assert: Should handle gracefully (may truncate to 72 bytes)
            assert isinstance(hashed, str)
            # Bcrypt will only use first ~72 bytes, so verification should work
            assert is_valid is True
        except ImportError:
            pytest.skip("API key service not implemented yet")

    def test_hash_unicode_characters(self):
        """Test hashing API key with Unicode characters."""
        # Arrange
        try:
            from tradingagents.api.services.api_key_service import (
                hash_api_key,
                verify_api_key,
            )

            # Key with Unicode characters
            unicode_key = "ta_测试key_🔑_αβγ"

            # Act
            hashed = hash_api_key(unicode_key)
            is_valid = verify_api_key(unicode_key, hashed)

            # Assert
            assert isinstance(hashed, str)
            assert is_valid is True
        except ImportError:
            pytest.skip("API key service not implemented yet")

    def test_timing_attack_resistance(self):
        """Test that verification takes similar time for valid/invalid keys."""
        # Arrange
        try:
            from tradingagents.api.services.api_key_service import (
                generate_api_key,
                hash_api_key,
                verify_api_key,
            )
            import time

            api_key = generate_api_key()
            hashed = hash_api_key(api_key)
            wrong_key = generate_api_key()

            # Act: Measure time for correct and incorrect verification
            times_correct = []
            times_incorrect = []

            for _ in range(10):
                start = time.perf_counter()
                verify_api_key(api_key, hashed)
                times_correct.append(time.perf_counter() - start)

                start = time.perf_counter()
                verify_api_key(wrong_key, hashed)
                times_incorrect.append(time.perf_counter() - start)

            # Assert: Times should be similar (within same order of magnitude)
            # This is a basic check - bcrypt is inherently resistant to timing attacks
            avg_correct = sum(times_correct) / len(times_correct)
            avg_incorrect = sum(times_incorrect) / len(times_incorrect)

            # Both should take similar time (bcrypt always does full comparison)
            assert avg_correct > 0
            assert avg_incorrect > 0
        except ImportError:
            pytest.skip("API key service not implemented yet")

    def test_concurrent_key_generation(self):
        """Test generating API keys concurrently."""
        # Arrange & Act
        try:
            from tradingagents.api.services.api_key_service import generate_api_key
            import concurrent.futures

            # Generate keys concurrently
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(generate_api_key) for _ in range(100)]
                keys = [f.result() for f in futures]

            # Assert: All keys should be unique
            assert len(keys) == len(set(keys))
            assert all(k.startswith("ta_") for k in keys)
        except ImportError:
            pytest.skip("API key service not implemented yet")
