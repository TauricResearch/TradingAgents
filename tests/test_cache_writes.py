"""Cache files are replaced whole: a reader never sees a half-written file, and
concurrent writers (tool calls run in parallel) never share a temp file."""

import os
from pathlib import Path

import pandas as pd
import pytest

from tradingagents.dataflows import files
from tradingagents.dataflows.vendors import sec_edgar
from tradingagents.dataflows.vendors.yahoo import ohlcv


def _recording_replace(monkeypatch):
    moves = []
    real = os.replace

    def replace(src, dst):
        moves.append((Path(src), Path(dst)))
        real(src, dst)

    monkeypatch.setattr(os, "replace", replace)
    return moves


@pytest.mark.unit
def test_sec_edgar_writers_never_share_a_temp_file(monkeypatch, tmp_path):
    monkeypatch.setattr(sec_edgar, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
    monkeypatch.setattr(sec_edgar, "_fetch_json", lambda url: {"url": url})
    moves = _recording_replace(monkeypatch)

    sec_edgar._cached_json("https://example/a", "facts.json")
    (tmp_path / "sec_edgar" / "facts.json").unlink()
    sec_edgar._cached_json("https://example/a", "facts.json")

    temps = [src for src, _ in moves]
    assert len(set(temps)) == 2
    assert all(src.parent == dst.parent for src, dst in moves)


@pytest.mark.unit
def test_the_price_cache_is_replaced_whole(monkeypatch, tmp_path):
    frame = pd.DataFrame({"Date": pd.bdate_range("2026-01-02", periods=3), "Open": 1.0, "High": 1.0,
                          "Low": 1.0, "Close": 1.0, "Volume": 1})
    monkeypatch.setattr(ohlcv, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
    monkeypatch.setattr(ohlcv.yf, "Ticker", lambda s: type("T", (), {"history": lambda self, **k: frame.set_index("Date")})())
    moves = _recording_replace(monkeypatch)

    ohlcv.load_ohlcv("AAPL", "2026-01-06")

    assert [dst.name for _, dst in moves] == ["AAPL-YFin-data.csv"]
    assert moves[0][0].parent == tmp_path and moves[0][0] != moves[0][1]
    assert not list(tmp_path.glob("*.tmp*"))


@pytest.mark.unit
def test_a_replaced_file_keeps_the_usual_permissions(tmp_path):
    from tradingagents.dataflows.files import replace_file

    plain = tmp_path / "plain.txt"
    plain.write_text("x")
    replaced = tmp_path / "replaced.txt"
    replace_file(replaced, lambda temp: Path(temp).write_text("x"))

    assert replaced.stat().st_mode & 0o777 == plain.stat().st_mode & 0o777


@pytest.mark.unit
def test_a_file_held_open_elsewhere_keeps_its_old_content(monkeypatch, tmp_path):
    """On Windows a file another reader has open cannot be replaced; the cache
    write is skipped rather than failing the call that produced the data."""
    from tradingagents.dataflows import files

    target = tmp_path / "cache.csv"
    target.write_text("old")

    def locked(src, dst):
        raise PermissionError("in use")

    monkeypatch.setattr(files.os, "replace", locked)
    files.replace_file(target, lambda temp: Path(temp).write_text("new"))

    assert target.read_text() == "old"
    assert list(tmp_path.iterdir()) == [target]


def _fake_msvcrt(results):
    """msvcrt whose locking() raises the next error in ``results``, or succeeds on None."""
    import types

    calls = []

    def locking(fd, mode, nbytes):
        calls.append(mode)
        if mode == 2 and results:   # LK_LOCK; unlocking always succeeds
            error = results.pop(0)
            if error is not None:
                raise error

    return types.SimpleNamespace(LK_LOCK=2, LK_UNLCK=0, locking=locking), calls


@pytest.mark.unit
def test_on_windows_the_lock_is_waited_for_while_another_writer_holds_it(tmp_path, monkeypatch):
    import errno
    import sys

    fake, calls = _fake_msvcrt([OSError(errno.EDEADLOCK, "held"), None])
    monkeypatch.setitem(sys.modules, "msvcrt", fake)

    with open(tmp_path / "log.md.lock", "a+b") as handle, files._hold_windows(handle):
        pass

    assert calls == [2, 2, 0]


@pytest.mark.unit
def test_on_windows_a_lock_that_cannot_be_taken_is_reported_not_retried_forever(tmp_path, monkeypatch):
    import errno
    import sys

    fake, _ = _fake_msvcrt([OSError(errno.EINVAL, "bad handle")] * 3)
    monkeypatch.setitem(sys.modules, "msvcrt", fake)

    with pytest.raises(OSError, match="bad handle"), open(tmp_path / "log.md.lock", "a+b") as handle, \
            files._hold_windows(handle):
        pass
