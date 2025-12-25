"""
Integration test specific fixtures for TradingAgents.

This module provides fixtures specific to integration tests:
- Live ChromaDB instances for database integration testing
- Integration-specific temporary directories

These fixtures are only available in tests/integration/ directory.
For shared fixtures, see tests/conftest.py.

Scope:
- session: Expensive operations created once per test session
- function: Default scope for isolation between tests
"""

import pytest
import tempfile
import shutil
from pathlib import Path


# ============================================================================
# ChromaDB Integration Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def live_chromadb():
    """
    Create a live ChromaDB instance for integration testing.

    Provides an actual ChromaDB client (not mocked) for testing
    real database interactions. Uses in-memory or temporary storage.

    WARNING: This makes actual ChromaDB calls. Use sparingly and
    only for integration tests that validate database behavior.

    Scope: session (created once, shared across all integration tests)

    Yields:
        chromadb.Client: Live ChromaDB client instance

    Example:
        def test_chromadb_integration(live_chromadb):
            collection = live_chromadb.get_or_create_collection("test_collection")
            collection.add(ids=["1"], documents=["test"])
            assert collection.count() == 1
    """
    try:
        import chromadb
        # Create ephemeral in-memory client for testing
        client = chromadb.Client()
        yield client
    except ImportError:
        pytest.skip("ChromaDB not installed - skipping integration test")


# ============================================================================
# Integration Temporary Directory Fixtures
# ============================================================================

@pytest.fixture
def integration_temp_dir():
    """
    Create a temporary directory for integration test artifacts.

    Provides a temporary directory for integration tests that need
    to write files, create databases, or store test artifacts.
    Automatically cleaned up after test completes.

    Scope: function (default)

    Yields:
        Path: Path to temporary directory

    Example:
        def test_file_workflow(integration_temp_dir):
            db_path = integration_temp_dir / "test.db"
            # Create database, write files, etc.
            assert integration_temp_dir.exists()
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="tradingagents_integration_"))
    try:
        yield temp_dir
    finally:
        # Cleanup: Remove temporary directory and all contents
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
