import builtins

import pytest


def test_state_root_is_created_and_probe_removed(tmp_path):
    from tradingagents.plugin.server import prepare_state_root

    root = prepare_state_root(tmp_path / "new")

    assert root == (tmp_path / "new").resolve()
    assert list(root.iterdir()) == []


def test_state_root_rejects_file(tmp_path):
    from tradingagents.plugin.server import prepare_state_root

    root = tmp_path / "file"
    root.write_text("keep", encoding="utf-8")

    with pytest.raises(OSError):
        prepare_state_root(root)

    assert root.read_text(encoding="utf-8") == "keep"


def test_write_probe_is_required(tmp_path, monkeypatch):
    from tradingagents.plugin import server

    def denied(*args, **kwargs):
        raise PermissionError("probe denied")

    monkeypatch.setattr(server.tempfile, "TemporaryFile", denied)

    with pytest.raises(PermissionError, match="probe denied"):
        server.prepare_state_root(tmp_path)


def test_main_rejects_file_state_dir(tmp_path, capsys):
    from tradingagents.plugin.server import main

    root = tmp_path / "file"
    root.write_text("keep", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        main(["--state-dir", str(root)])

    captured = capsys.readouterr()
    assert exc_info.value.code == 1
    assert captured.out == ""
    assert "Cannot use plugin state directory" in captured.err
    assert "Set --state-dir to a writable directory." in captured.err


def test_main_hints_install_when_mcp_is_missing(tmp_path, monkeypatch, capsys):
    from tradingagents.plugin import server

    original_import = builtins.__import__

    def missing_mcp(name, *args, **kwargs):
        if name == "mcp.server.fastmcp":
            raise ModuleNotFoundError("No module named 'mcp'", name="mcp")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing_mcp)

    with pytest.raises(SystemExit) as exc_info:
        server.main(["--state-dir", str(tmp_path)])

    captured = capsys.readouterr()
    assert exc_info.value.code == 1
    assert captured.out == ""
    assert "Install the plugin runtime with: python -m pip install 'tradingagents[plugin]'" in captured.err
