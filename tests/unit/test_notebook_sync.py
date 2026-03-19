import json
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from tradingagents.notebook_sync import sync_to_notebooklm

@pytest.fixture
def mock_nlm_path(tmp_path):
    nlm = tmp_path / "nlm"
    nlm.touch(mode=0o755)
    return str(nlm)

def test_sync_skips_when_no_notebook_id():
    """Should return silently if NOOTEBOOKLM_ID is not set."""
    with patch.dict(os.environ, {}, clear=True):
        # Should not raise or call anything
        sync_to_notebooklm(Path("test.md"), "2026-03-19")

def test_sync_skips_when_nlm_not_found():
    """Should warn and skip if nlm binary is not in PATH."""
    with patch.dict(os.environ, {"NOTEBOOKLM_ID": "test-id"}):
        with patch("shutil.which", return_value=None):
            with patch("tradingagents.notebook_sync.Path.exists", return_value=False):
                sync_to_notebooklm(Path("test.md"), "2026-03-19")

def test_sync_performs_delete_then_add(mock_nlm_path):
    """Should find existing source, delete it, then add new one."""
    notebook_id = "test-notebook-id"
    source_id = "existing-source-id"
    digest_path = Path("digest.md")
    content = "# Daily Digest"
    
    # Mock file reading
    with patch.object(Path, "read_text", return_value=content):
        with patch.dict(os.environ, {"NOTEBOOKLM_ID": notebook_id}):
            with patch("shutil.which", return_value=mock_nlm_path):
                with patch("subprocess.run") as mock_run:
                    # 1. Mock 'source list' finding an existing source
                    list_result = MagicMock()
                    list_result.returncode = 0
                    list_result.stdout = json.dumps([{"id": source_id, "title": "Daily Trading Digest (2026-03-19)"}])
                    
                    # 2. Mock 'source delete' success
                    delete_result = MagicMock()
                    delete_result.returncode = 0
                    
                    # 3. Mock 'source add' success
                    add_result = MagicMock()
                    add_result.returncode = 0
                    
                    mock_run.side_effect = [list_result, delete_result, add_result]
                    
                    sync_to_notebooklm(digest_path, "2026-03-19")
                    
                    # Verify calls
                    assert mock_run.call_count == 3
                    
                    # Check list call
                    args, kwargs = mock_run.call_args_list[0]
                    assert "list" in args[0]
                    assert notebook_id in args[0]
                    
                    # Check delete call
                    args, kwargs = mock_run.call_args_list[1]
                    assert "delete" in args[0]
                    assert source_id in args[0]
                    
                    # Check add call
                    args, kwargs = mock_run.call_args_list[2]
                    assert "add" in args[0]
                    assert "--text" in args[0]
                    assert content in args[0]

def test_sync_adds_directly_when_none_exists(mock_nlm_path):
    """Should add new source directly if no existing one is found."""
    notebook_id = "test-notebook-id"
    digest_path = Path("digest.md")
    content = "# New Digest"
    
    with patch.object(Path, "read_text", return_value=content):
        with patch.dict(os.environ, {"NOTEBOOKLM_ID": notebook_id}):
            with patch("shutil.which", return_value=mock_nlm_path):
                with patch("subprocess.run") as mock_run:
                    # 1. Mock 'source list' returning empty list
                    list_result = MagicMock()
                    list_result.returncode = 0
                    list_result.stdout = "[]"
                    
                    # 2. Mock 'source add' success
                    add_result = MagicMock()
                    add_result.returncode = 0
                    
                    mock_run.side_effect = [list_result, add_result]
                    
                    sync_to_notebooklm(digest_path, "2026-03-19")
                    
                    # Verify only 2 calls (no delete)
                    assert mock_run.call_count == 2
                    assert "list" in mock_run.call_args_list[0][0][0]
                    assert "add" in mock_run.call_args_list[1][0][0]

def test_handles_json_error_gracefully(mock_nlm_path):
    """Should skip delete and attempt add if JSON list parsing fails."""
    with patch.object(Path, "read_text", return_value="content"):
        with patch.dict(os.environ, {"NOTEBOOKLM_ID": "id"}):
            with patch("shutil.which", return_value=mock_nlm_path):
                with patch("subprocess.run") as mock_run:
                    # Mock invalid JSON
                    list_result = MagicMock()
                    list_result.stdout = "invalid json"
                    
                    add_result = MagicMock()
                    add_result.returncode = 0
                    
                    mock_run.side_effect = [list_result, add_result]
                    
                    sync_to_notebooklm(Path("test.md"), "2026-03-19")
                    
                    assert mock_run.call_count == 2
                    assert "add" in mock_run.call_args_list[1][0][0]
