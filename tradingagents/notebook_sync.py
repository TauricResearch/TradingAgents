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


def _find_nlm() -> str | None:
    """Resolve the path to the nlm CLI."""
    if nlm_path := shutil.which("nlm"):
        return nlm_path
    return None


def sync_to_notebooklm(digest_path: Path, date: str, notebook_id: str | None = None) -> None:
    """Upload *digest_path* content to Google NotebookLM as a source.

    If a source with the title for the given day already exists, it is deleted
    and re-uploaded to ensure the latest content is indexed.

    Parameters
    ----------
    digest_path:
        Path to the digest markdown file to upload.
    date:
        The date string (e.g., "YYYY-MM-DD") used for the source title.
    notebook_id:
        NotebookLM notebook ID. Falls back to the ``NOTEBOOKLM_ID``
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

    title = f"Daily Trading Digest ({date})"

    # Find and delete existing source with the same title
    existing_source_id = _find_source(nlm, notebook_id, title)
    if existing_source_id:
        _delete_source(nlm, notebook_id, existing_source_id)

    # Add as a new source
    _add_source(nlm, notebook_id, digest_path, title)


def _find_source(nlm: str, notebook_id: str, title: str) -> str | None:
    """Return the source ID for the daily digest, or None if not found."""
    try:
        # Use -- to separate options from positional arguments
        result = subprocess.run(
            [nlm, "source", "list", "--json", "--", notebook_id],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        sources = json.loads(result.stdout)
        for source in sources:
            if isinstance(source, dict) and source.get("title") == title:
                return source.get("id")
    except (ValueError, KeyError, OSError):
        pass
    return None


def _delete_source(nlm: str, notebook_id: str, source_id: str) -> None:
    """Delete an existing source."""
    try:
        # Use -- to separate options from positional arguments
        subprocess.run(
            [nlm, "source", "delete", "-y", "--", notebook_id, source_id],
            capture_output=True,
            text=True,
            check=False,  # Ignore non-zero exit since nlm sometimes fails even on success
        )
    except OSError:
        pass


def _add_source(nlm: str, notebook_id: str, digest_path: Path, title: str) -> None:
    """Add content as a new source."""
    try:
        # Use --file instead of --text to avoid ARG_MAX issues and shell injection.
        # Use -- to separate options from positional arguments.
        result = subprocess.run(
            [nlm, "source", "add", "--title", title, "--file", str(digest_path), "--wait", "--", notebook_id],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            console.print(f"[green]✓ Synced NotebookLM source: {title}[/green]")
        else:
            console.print(f"[yellow]Warning: nlm source add failed: {result.stderr.strip()}[/yellow]")
    except OSError as exc:
        console.print(f"[yellow]Warning: could not add NotebookLM source: {exc}[/yellow]")
