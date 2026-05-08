"""Per-format export download endpoints.

Layout matches the existing on-disk structure:
    GET /runs/{run_id}/exports             -> list of (format, path, size_bytes, modified_at)
    GET /runs/{run_id}/exports/{ext}       -> stream the file (md/html/pdf/json)
    POST /runs/{run_id}/exports/regenerate -> re-render and save fresh files
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from gui import export as export_mod
from gui import storage
from gui.log_browser import load_log

router = APIRouter(prefix="/runs", tags=["exports"])


def _meta_for_run(run_id: str) -> tuple[Dict, str]:
    row = storage.get_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="run not found")
    log_path = row.get("log_path") or ""
    if not log_path or not Path(log_path).exists():
        raise HTTPException(
            status_code=409,
            detail="run has no on-disk transcript yet — wait for it to finish",
        )
    meta = {
        "ticker": row["ticker"],
        "trade_date": row["trade_date"],
        "decision": row.get("decision"),
        "provider": row.get("provider"),
        "deep_model": row.get("deep_model"),
        "quick_model": row.get("quick_model"),
        "started_at": row.get("started_at"),
        "completed_at": row.get("completed_at"),
        "tokens_in": row.get("tokens_in", 0),
        "tokens_out": row.get("tokens_out", 0),
        "run_id": run_id,
        "log_path": log_path,
    }
    return meta, log_path


@router.get("/{run_id}/exports")
def list_run_exports(run_id: str) -> List[dict]:
    meta, log_path = _meta_for_run(run_id)
    out: List[dict] = []

    # JSON archive — already on disk, point to the source file.
    archive_path = Path(log_path)
    if archive_path.exists():
        out.append({
            "ext": "json",
            "path": str(archive_path),
            "size_bytes": archive_path.stat().st_size,
            "filename": archive_path.name,
        })

    # Auto-generate the other three if they don't already exist.
    state = load_log(log_path)
    if state is not None:
        existing = export_mod.list_exports_for_run(meta)
        if "md" not in existing:
            export_mod.write_export(export_mod.render_markdown(state, meta), meta, "md")
        if "html" not in existing:
            export_mod.write_export(export_mod.render_html(state, meta), meta, "html")
        if "pdf" not in existing and export_mod.has_pdf_support():
            pdf = export_mod.render_pdf(state, meta)
            if pdf:
                export_mod.write_export(pdf, meta, "pdf")
        existing = export_mod.list_exports_for_run(meta)
        for export_ext in ("md", "html", "pdf"):
            export_path = existing.get(export_ext)
            if export_path and export_path.exists():
                out.append({
                    "ext": export_ext,
                    "path": str(export_path),
                    "size_bytes": export_path.stat().st_size,
                    "filename": export_path.name,
                })
    return out


@router.get("/{run_id}/exports/{ext}")
def download_export(run_id: str, ext: str) -> FileResponse:
    if ext not in {"json", "md", "html", "pdf"}:
        raise HTTPException(status_code=400, detail="unsupported format")
    meta, log_path = _meta_for_run(run_id)
    path: Path | None
    if ext == "json":
        path = Path(log_path)
    else:
        existing = export_mod.list_exports_for_run(meta)
        path = existing.get(ext)
        if not path:
            # Generate on demand.
            state = load_log(log_path)
            if state is None:
                raise HTTPException(status_code=500, detail="could not parse state log")
            if ext == "md":
                path = export_mod.write_export(
                    export_mod.render_markdown(state, meta), meta, "md")
            elif ext == "html":
                path = export_mod.write_export(
                    export_mod.render_html(state, meta), meta, "html")
            elif ext == "pdf":
                if not export_mod.has_pdf_support():
                    raise HTTPException(status_code=501, detail="pdf support not installed")
                pdf = export_mod.render_pdf(state, meta)
                if not pdf:
                    raise HTTPException(status_code=500, detail="pdf rendering failed")
                path = export_mod.write_export(pdf, meta, "pdf")
    if not path or not Path(path).exists():
        raise HTTPException(status_code=404, detail=f"{ext} not available")
    media_types = {
        "json": "application/json",
        "md": "text/markdown",
        "html": "text/html",
        "pdf": "application/pdf",
    }
    return FileResponse(path, media_type=media_types[ext], filename=Path(path).name)


@router.post("/{run_id}/exports/regenerate")
def regenerate_exports(run_id: str) -> List[dict]:
    """Force fresh md/html/pdf renders. Old files stay on disk (timestamped)."""
    meta, log_path = _meta_for_run(run_id)
    state = load_log(log_path)
    if state is None:
        raise HTTPException(status_code=500, detail="could not parse state log")
    out = []
    p = export_mod.write_export(export_mod.render_markdown(state, meta), meta, "md")
    out.append({"ext": "md", "path": str(p)})
    p = export_mod.write_export(export_mod.render_html(state, meta), meta, "html")
    out.append({"ext": "html", "path": str(p)})
    if export_mod.has_pdf_support():
        pdf = export_mod.render_pdf(state, meta)
        if pdf:
            p = export_mod.write_export(pdf, meta, "pdf")
            out.append({"ext": "pdf", "path": str(p)})
    return out
