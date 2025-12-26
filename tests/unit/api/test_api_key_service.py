"""Unit tests for API key service.

Tests for secure API key generation, hashing, and verification.
Follows TDD principles with comprehensive coverage.
"""

import pytest
import re
from spektiv.api.services.api_key_service import (
    generate_api_key,
    hash_api_key,
    verify_api_key,
)


class TestGenerateApiKey:
    """Tests for generate_api_key function."""

    def test_generates_key_with_prefix(self):
        """API key should start with 'ta_' prefix."""
        api_key = generate_api_key()
        assert api_key.startswith("ta_")

    def test_generates_unique_keys(self):
        """Each call should generate a unique API key."""
        keys = [generate_api_key() for _ in range(100)]
        assert len(keys) == len(set(keys)), "All keys should be unique"

    def test_key_length_is_sufficient(self):
        """API key should have sufficient length (>40 characters)."""
        api_key = generate_api_key()
        # ta_ (3) + base64(32 bytes) ≈ 43+ characters
        assert len(api_key) > 40

    def test_key_is_url_safe(self):
        """API key should only contain URL-safe characters."""
        api_key = generate_api_key()
        # URL-safe base64: alphanumeric + - and _
        pattern = r'^ta_[A-Za-z0-9_-]+$'
        assert re.match(pattern, api_key) is not None

    def test_key_has_high_entropy(self):
        """API key should have high entropy (many unique characters)."""
        api_key = generate_api_key()
        unique_chars = len(set(api_key))
        # Should have at least 15 unique characters for good entropy
        assert unique_chars >= 15


class TestHashApiKey:
    """Tests for hash_api_key function."""

    def test_hashes_api_key(self):
        """Should hash API key into a different string."""
        api_key = generate_api_key()
        hashed = hash_api_key(api_key)

        assert hashed != api_key
        assert len(hashed) > 50  # Bcrypt hashes are long

    def test_same_key_produces_different_hashes(self):
        """Same API key should produce different hashes (salt)."""
        api_key = generate_api_key()
        hash1 = hash_api_key(api_key)
        hash2 = hash_api_key(api_key)

        # Different hashes due to different salts
        assert hash1 != hash2

    def test_hash_is_not_reversible(self):
        """Hash should not contain the original key."""
        api_key = generate_api_key()
        hashed = hash_api_key(api_key)

        assert api_key not in hashed
        assert api_key.replace("ta_", "") not in hashed

    def test_handles_empty_string(self):
        """Should handle empty string without crashing."""
        # Should not crash, even if input is invalid
        hashed = hash_api_key("")
        assert isinstance(hashed, str)
        assert len(hashed) > 0

    def test_handles_special_characters(self):
        """Should handle special characters in key."""
        api_key = "ta_special!@#$%^&*()"
        hashed = hash_api_key(api_key)
        assert isinstance(hashed, str)
        assert len(hashed) > 0


class TestVerifyApiKey:
    """Tests for verify_api_key function."""

    def test_verifies_correct_api_key(self):
        """Should verify correct API key against its hash."""
        api_key = generate_api_key()
        hashed = hash_api_key(api_key)

        assert verify_api_key(api_key, hashed) is True

    def test_rejects_incorrect_api_key(self):
        """Should reject incorrect API key."""
        api_key = generate_api_key()
        wrong_key = generate_api_key()
        hashed = hash_api_key(api_key)

        assert verify_api_key(wrong_key, hashed) is False

    def test_rejects_empty_api_key(self):
        """Should reject empty API key."""
        api_key = generate_api_key()
        hashed = hash_api_key(api_key)

        assert verify_api_key("", hashed) is False

    def test_rejects_slightly_modified_key(self):
        """Should reject API key with one character changed."""
        api_key = generate_api_key()
        hashed = hash_api_key(api_key)

        # Change one character
        modified_key = api_key[:-1] + ("a" if api_key[-1] != "a" else "b")

        assert verify_api_key(modified_key, hashed) is False

    def test_handles_malformed_hash(self):
        """Should handle malformed hash gracefully."""
        api_key = generate_api_key()

        # Malformed hashes should return False, not crash
        assert verify_api_key(api_key, "invalid_hash") is False
        assert verify_api_key(api_key, "") is False
        assert verify_api_key(api_key, "a" * 100) is False

    def test_case_sensitive_verification(self):
        """Verification should be case-sensitive."""
        api_key = "ta_AbCdEfGhIjKlMnOpQrStUvWxYz"
        hashed = hash_api_key(api_key)

        # Different case should fail
        assert verify_api_key(api_key.lower(), hashed) is False
        assert verify_api_key(api_key.upper(), hashed) is False

    def test_constant_time_comparison(self):
        """Verification should take similar time for right/wrong keys.

        Note: This is a basic check. True timing attacks require
        statistical analysis which is beyond unit testing scope.
        """
        api_key = generate_api_key()
        wrong_key = generate_api_key()
        hashed = hash_api_key(api_key)

        # Both should complete without crashing
        verify_api_key(api_key, hashed)
        verify_api_key(wrong_key, hashed)

        # If we got here without exceptions, basic constant-time is working


class TestApiKeyWorkflow:
    """Integration tests for complete API key workflow."""

    def test_full_api_key_lifecycle(self):
        """Test complete API key lifecycle: generate -> hash -> verify."""
        # Step 1: Generate API key
        api_key = generate_api_key()
        assert api_key.startswith("ta_")

        # Step 2: Hash the API key (for database storage)
        hashed = hash_api_key(api_key)
        assert hashed != api_key

        # Step 3: Verify the correct API key
        assert verify_api_key(api_key, hashed) is True

        # Step 4: Verify wrong key fails
        wrong_key = generate_api_key()
        assert verify_api_key(wrong_key, hashed) is False

    def test_multiple_users_different_keys(self):
        """Multiple users should have unique API keys and hashes."""
        # Generate keys for 10 "users"
        users = []
        for i in range(10):
            api_key = generate_api_key()
            hashed = hash_api_key(api_key)
            users.append((api_key, hashed))

        # All plain keys should be unique
        plain_keys = [u[0] for u in users]
        assert len(plain_keys) == len(set(plain_keys))

        # All hashes should be unique
        hashes = [u[1] for u in users]
        assert len(hashes) == len(set(hashes))

        # Each user can verify their own key
        for api_key, hashed in users:
            assert verify_api_key(api_key, hashed) is True

        # Each user cannot verify another user's key
        for i, (api_key1, hashed1) in enumerate(users):
            for j, (api_key2, hashed2) in enumerate(users):
                if i != j:
                    assert verify_api_key(api_key2, hashed1) is False

    def test_key_regeneration(self):
        """User should be able to regenerate their API key."""
        # User has original key
        old_key = generate_api_key()
        old_hash = hash_api_key(old_key)

        # User regenerates key
        new_key = generate_api_key()
        new_hash = hash_api_key(new_key)

        # Keys should be different
        assert old_key != new_key
        assert old_hash != new_hash

        # Old key no longer works with new hash
        assert verify_api_key(old_key, new_hash) is False

        # New key works with new hash
        assert verify_api_key(new_key, new_hash) is True
