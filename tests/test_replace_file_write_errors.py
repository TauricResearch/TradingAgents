"""Write-callback failures in replace_file must not be mistaken for a locked cache.

replace_file's PermissionError handler exists for one case only: on Windows a
reader holding the destination open makes os.replace fail, and the cache write
is skipped. A PermissionError raised while writing the temp file (a read-only
cache dir, an ACL-denied temp path, a failing writer) is a different failure:
it must propagate so the caller knows the data was not persisted, instead of
being swallowed and mislabeled "it is in use".
"""
from pathlib import Path

import pytest

from tradingagents.dataflows.files import replace_file


@pytest.mark.unit
def test_write_callback_permission_error_is_not_swallowed(tmp_path):
    target = tmp_path / "cache.json"
    target.write_text("old", encoding="utf-8")

    def denied_write(temp):
        raise PermissionError("[Errno 13] Permission denied: '%s'" % temp)

    with pytest.raises(PermissionError):
        replace_file(target, denied_write)

    # A failed write cleans up its temp file and leaves the old cache intact.
    assert not list(tmp_path.glob("*.tmp"))
    assert target.read_text(encoding="utf-8") == "old"


@pytest.mark.unit
def test_write_callback_error_leaves_no_temp_file(tmp_path):
    target = tmp_path / "cache.csv"

    def failing_write(temp):
        Path(temp).write_bytes(b"partial")
        raise OSError("disk full")

    with pytest.raises(OSError, match="disk full"):
        replace_file(target, failing_write)

    assert list(tmp_path.iterdir()) == []
