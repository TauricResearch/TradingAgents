from pathlib import Path

import pytest

from tradingagents.runapi.persist import PersistenceError, publish_run


class _Events:
    def emit(self, *args):
        pass

    def write_to(self, path):
        path.write_text("{}\n", encoding="utf-8")
        return True


class _Redactor:
    def scrub(self, value):
        return value


def _publish(root: Path, run_id: str, redactor=None):
    return publish_run(
        root, "AAPL", run_id, "report", None, {}, _Events(),
        redactor or _Redactor(),
    )


@pytest.mark.parametrize("run_id", ["../escape", "../../outside", "/tmp/escape", "a/b", "a\\b", ".", ".."])
def test_unsafe_run_id_is_rejected_before_filesystem_changes(tmp_path, run_id):
    outside = tmp_path.parent / "outside"
    with pytest.raises(ValueError, match="safe single path component"):
        _publish(tmp_path / "results", run_id)
    assert not outside.exists()
    assert not (tmp_path / "results" / "_staging").exists()


def test_existing_staging_directory_is_preserved_on_collision(tmp_path):
    staging = tmp_path / "_staging" / "same-run"
    staging.mkdir(parents=True)
    sentinel = staging / "owned-by-another-run.txt"
    sentinel.write_text("keep", encoding="utf-8")

    with pytest.raises(PersistenceError):
        _publish(tmp_path, "same-run")

    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_only_staging_directory_created_by_this_call_is_cleaned(tmp_path):
    class _FailingRedactor:
        def scrub(self, value):
            raise RuntimeError("synthetic render failure")

    with pytest.raises(PersistenceError):
        _publish(tmp_path, "owned-run", _FailingRedactor())

    assert not (tmp_path / "_staging" / "owned-run").exists()
