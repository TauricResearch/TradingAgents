"""Google NotebookLM sync via the ``nlm`` CLI tool (jacob-bd/notebooklm-mcp-cli).

Uploads the daily digest as a note to a NotebookLM notebook, updating the
existing note if one with the same title already exists. Entirely opt-in:
if no ``NOTEBOOK_ID`` is configured the function is a silent no-op.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from rich.console import Console

console = Console()

_NOTE_TITLE = "Daily Trading Digest"

# Common install locations outside of PATH (e.g. pip install --user)
_FALLBACK_PATHS = [
    Path.home() / ".local" / "bin" / "nlm",
    Path("/usr/local/bin/nlm"),
]


def _find_nlm() -> str | None:
    """Return the path to the nlm binary, or None if not found."""
    found = shutil.which("nlm")
    if found:
        return found
    for p in _FALLBACK_PATHS:
        if p.exists():
            return str(p)
    return None


def sync_to_notebooklm(digest_path: Path, notebook_id: str | None = None) -> None:
    """Upload *digest_path* content to Google NotebookLM as a note.

    If a note titled ``Daily Trading Digest`` already exists it is updated
    in-place; otherwise a new note is created.

    Parameters
    ----------
    digest_path:
        Path to the digest markdown file to upload.
    notebook_id:
        NotebookLM notebook ID.  Falls back to the ``NOTEBOOK_ID``
        environment variable when *None*.
    """
    if notebook_id is None:
        notebook_id = os.environ.get("NOTEBOOKLM_ID")
    if not notebook_id:
        return  # opt-in — silently skip when not configured

    nlm = _find_nlm()
    if not nlm:
        console.print("[yellow]Warning: nlm CLI not found — skipping NotebookLM sync[/yellow]")
        return

    content = digest_path.read_text()

    # Check for an existing note with the same title
    existing_note_id = _find_note(nlm, notebook_id)

    if existing_note_id:
        _update_note(nlm, notebook_id, existing_note_id, content)
    else:
        _create_note(nlm, notebook_id, content)


def _find_note(nlm: str, notebook_id: str) -> str | None:
    """Return the note ID for the daily digest note, or None if not found."""
    try:
        result = subprocess.run(
            [nlm, "note", "list", notebook_id, "--json"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        notes = data.get("notes", data) if isinstance(data, dict) else data
        for note in notes:
            if isinstance(note, dict) and note.get("title") == _NOTE_TITLE:
                return note.get("id") or note.get("noteId")
    except (ValueError, KeyError, OSError):
        pass
    return None


def _create_note(nlm: str, notebook_id: str, content: str) -> None:
    """Create a new note in the notebook."""
    try:
        result = subprocess.run(
            [nlm, "note", "create", notebook_id, "--title", _NOTE_TITLE, "--content", content],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            console.print(f"[green]✓ Created NotebookLM note: {_NOTE_TITLE}[/green]")
        else:
            console.print(f"[yellow]Warning: nlm note create failed: {result.stderr.strip()}[/yellow]")
    except OSError as exc:
        console.print(f"[yellow]Warning: could not create NotebookLM note: {exc}[/yellow]")


def _update_note(nlm: str, notebook_id: str, note_id: str, content: str) -> None:
    """Update an existing note's content."""
    try:
        result = subprocess.run(
            [nlm, "note", "update", notebook_id, note_id, "--content", content],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            console.print(f"[green]✓ Updated NotebookLM note: {_NOTE_TITLE}[/green]")
        else:
            console.print(f"[yellow]Warning: nlm note update failed: {result.stderr.strip()}[/yellow]")
    except OSError as exc:
        console.print(f"[yellow]Warning: could not update NotebookLM note: {exc}[/yellow]")
