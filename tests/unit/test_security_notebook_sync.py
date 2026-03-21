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

def test_security_argument_injection(mock_nlm_path, tmp_path):
    """
    Test that positional arguments starting with a hyphen are handled safely
    and that content is passed via file to avoid ARG_MAX issues and injection.
    """
    # Malicious notebook_id that looks like a flag
    notebook_id = "--some-flag"
    digest_path = tmp_path / "malicious.md"
    digest_path.write_text("Some content")
    date = "2026-03-19"

    with patch.dict(os.environ, {"NOTEBOOKLM_ID": notebook_id}):
        with patch("shutil.which", return_value=mock_nlm_path):
            with patch("subprocess.run") as mock_run:
                # Mock 'source list'
                list_result = MagicMock()
                list_result.returncode = 0
                list_result.stdout = "[]"

                # Mock 'source add'
                add_result = MagicMock()
                add_result.returncode = 0

                mock_run.side_effect = [list_result, add_result]

                sync_to_notebooklm(digest_path, date)

                # 1. Check 'source list' call
                # Expected: [nlm, "source", "list", "--json", "--", notebook_id]
                list_args = mock_run.call_args_list[0][0][0]
                assert list_args[0] == mock_nlm_path
                assert list_args[1:3] == ["source", "list"]
                assert "--json" in list_args
                assert "--" in list_args
                # "--" should be before the notebook_id
                dash_idx = list_args.index("--")
                id_idx = list_args.index(notebook_id)
                assert dash_idx < id_idx

                # 2. Check 'source add' call
                # Expected: [nlm, "source", "add", "--title", title, "--file", str(digest_path), "--wait", "--", notebook_id]
                add_args = mock_run.call_args_list[1][0][0]
                assert add_args[0] == mock_nlm_path
                assert add_args[1:3] == ["source", "add"]
                assert "--title" in add_args
                assert "--file" in add_args
                assert str(digest_path) in add_args
                assert "--text" not in add_args  # Vulnerable --text should be gone
                assert "--wait" in add_args
                assert "--" in add_args

                dash_idx = add_args.index("--")
                id_idx = add_args.index(notebook_id)
                assert dash_idx < id_idx

def test_security_delete_injection(mock_nlm_path):
    """Test that source_id in delete is also handled safely with --."""
    notebook_id = "normal-id"
    source_id = "--delete-everything"

    with patch.dict(os.environ, {"NOTEBOOKLM_ID": notebook_id}):
        with patch("shutil.which", return_value=mock_nlm_path):
            with patch("subprocess.run") as mock_run:
                # Mock 'source list' finding the malicious source_id
                list_result = MagicMock()
                list_result.returncode = 0
                list_result.stdout = json.dumps([{"id": source_id, "title": "Daily Trading Digest (2026-03-19)"}])

                # Mock 'source delete'
                delete_result = MagicMock()
                delete_result.returncode = 0

                # Mock 'source add'
                add_result = MagicMock()
                add_result.returncode = 0

                mock_run.side_effect = [list_result, delete_result, add_result]

                sync_to_notebooklm(Path("test.md"), "2026-03-19")

                # Check 'source delete' call
                # Expected: [nlm, "source", "delete", "-y", "--", notebook_id, source_id]
                delete_args = mock_run.call_args_list[1][0][0]
                assert delete_args[1:3] == ["source", "delete"]
                assert "-y" in delete_args
                assert "--" in delete_args

                dash_idx = delete_args.index("--")
                id_idx = delete_args.index(notebook_id)
                sid_idx = delete_args.index(source_id)
                assert dash_idx < id_idx
                assert dash_idx < sid_idx
