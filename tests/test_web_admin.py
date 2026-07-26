from __future__ import annotations

import json
import sys

from tradingagents.web.admin import main


def run(monkeypatch, capsys, *args):
    monkeypatch.setattr(sys, "argv", ["tradingagents-web-admin", *args])
    main()
    return json.loads(capsys.readouterr().out)


def test_admin_backup_preview_and_restore_use_ids(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TRADINGAGENTS_WEB_DB_PATH", str(tmp_path / "workspace.sqlite3"))
    created = run(monkeypatch, capsys, "backup")
    assert created["valid"] and "path" not in created
    listed = run(monkeypatch, capsys, "list")
    assert listed["items"][0]["backup_id"] == created["backup_id"]
    preview = run(monkeypatch, capsys, "preview", created["backup_id"])
    assert preview["compatible"] and preview["schema_version"] == 5
    restored = run(monkeypatch, capsys, "restore", created["backup_id"])
    assert restored["restored"] is True
