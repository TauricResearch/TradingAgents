"""Publish chart PNG + JSON metadata to Notion page.

This module provides the publish_chart_to_notion() function that uploads
a rendered chart image and its metadata to an existing Notion page.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

_NOTION_API_VERSION = "2026-03-11"
_NOTION_BASE = "https://api.notion.com/v1"
_MAX_BLOCK_TEXT = 1900  # Notion rich_text limit is 2000; stay under it


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": _NOTION_API_VERSION,
        "Content-Type": "application/json",
    }


def _paragraph(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": text[:_MAX_BLOCK_TEXT]}}]
        },
    }


def _heading2(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": [{"type": "text", "text": {"content": text[:_MAX_BLOCK_TEXT]}}]
        },
    }


def _heading3(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "heading_3",
        "heading_3": {
            "rich_text": [{"type": "text", "text": {"content": text[:_MAX_BLOCK_TEXT]}}]
        },
    }


def _divider() -> dict[str, Any]:
    return {"object": "block", "type": "divider", "divider": {}}


def _callout(text: str, emoji: str = "📊") -> dict[str, Any]:
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": [{"type": "text", "text": {"content": text[:_MAX_BLOCK_TEXT]}}],
            "icon": {"type": "emoji", "emoji": emoji},
        },
    }


def _table_row(cells: list[str]) -> dict[str, Any]:
    """Create a table row with text cells."""
    return {
        "object": "block",
        "type": "table_row",
        "table_row": {
            "cells": [
                [{"type": "text", "text": {"content": cell[:_MAX_BLOCK_TEXT]}}]
                for cell in cells
            ]
        },
    }


def _table(headers: list[str], rows: list[list[str]]) -> dict[str, Any]:
    """Create a table block with headers and rows."""
    children = [_table_row(headers)]
    children.extend(_table_row(row) for row in rows)
    return {
        "object": "block",
        "type": "table",
        "table": {
            "table_width": len(headers),
            "has_column_header": True,
            "has_row_header": False,
            "children": children,
        },
    }



# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------


def publish_chart_to_notion(
    chart_png_path: Path,
    chart_json: dict,
    page_id: str,
    api_key: str | None = None,
) -> None:
    """Upload chart PNG + JSON summary to an existing Notion page.

    Steps:
    1. Upload chart PNG as Notion image block (external URL or file upload)
    2. Append reference_lines as a formatted table block
    3. Append chart_info as a callout block with key metrics

    Handles:
    - Image upload via Notion file block or external hosting
    - Graceful fallback: logs warning on failure, never raises

    Args:
        chart_png_path: Path to the rendered chart PNG from draw_chart().
        chart_json: Raw dict from transform_to_json() for metadata table.
        page_id: Notion page ID to append blocks to.
        api_key: Notion API key (default: NOTION_API_KEY env).
    """
    effective_api_key = api_key or os.environ.get("NOTION_API_KEY")
    if not effective_api_key:
        logger.warning("NOTION_API_KEY not set, skipping chart publish")
        return

    chart_png_path = Path(chart_png_path)
    if not chart_png_path.exists():
        logger.warning("Chart PNG not found at %s, skipping publish", chart_png_path)
        return

    try:
        # Build blocks to append
        blocks: list[dict[str, Any]] = []

        # 1. Section header
        blocks.append(_heading2("📈 Trading Plan Chart"))
        blocks.append(_divider())

        # 2. Chart info callout
        chart_info = chart_json.get("chart_info", {})
        title = chart_info.get("title", "Trading Plan")
        current_price = chart_info.get("current_price")
        y_range = chart_info.get("y_axis_range")

        # Guard against missing/non-numeric values before applying float format specs
        price_str = f"{current_price:,.2f}" if isinstance(current_price, (int, float)) else "N/A"
        if (
            isinstance(y_range, (list, tuple))
            and len(y_range) == 2
            and all(isinstance(v, (int, float)) for v in y_range)
        ):
            range_str = f"{y_range[0]:,.0f} - {y_range[1]:,.0f}"
        else:
            range_str = "N/A"

        callout_text = f"{title}\nCurrent Price: {price_str}\nY-Axis Range: {range_str}"
        blocks.append(_callout(callout_text, "📊"))

        # 3. Reference lines table
        reference_lines = chart_json.get("reference_lines", [])
        if reference_lines:
            blocks.append(_heading3("Reference Lines"))

            table_headers = ["Label", "Price", "Color", "Style"]
            table_rows = []
            for ref in reference_lines:
                table_rows.append([
                    ref.get("label", "N/A"),
                    f"{ref.get('price', 0):,.2f}",
                    ref.get("color", "gray"),
                    ref.get("linestyle", "solid"),
                ])

            blocks.append(_table(table_headers, table_rows))

        # 4. Upload chart image via Notion file upload API and attach as image block
        blocks.append(_heading3("Chart Image"))
        upload_id = upload_image_to_notion(chart_png_path, api_key=effective_api_key)
        if upload_id is not None:
            blocks.append({
                "object": "block",
                "type": "image",
                "image": {
                    "type": "file_upload",
                    "file_upload": {"id": upload_id},
                },
            })
        else:
            # Fallback: show local path if upload failed
            blocks.append(
                _callout(
                    f"Chart saved locally (upload failed):\n{chart_png_path.resolve()}",
                    "📁",
                )
            )

        # 5. Append blocks to page
        url = f"{_NOTION_BASE}/blocks/{page_id}/children"
        response = requests.patch(
            url,
            headers=_headers(effective_api_key),
            json={"children": blocks},
            timeout=30,
        )

        if response.status_code != 200:
            logger.warning(
                "Failed to append chart blocks to Notion: %s - %s",
                response.status_code,
                response.text,
            )
            return

        logger.info("Successfully published chart to Notion page %s", page_id)

    except requests.RequestException as e:
        logger.warning("Network error publishing chart to Notion: %s", e)
    except Exception as e:
        logger.warning("Failed to publish chart to Notion: %s", e)


def upload_image_to_notion(
    image_path: Path,
    api_key: str | None = None,
) -> str | None:
    """Upload an image to Notion and return the file upload ID.

    Uses Notion's file upload API with correct endpoints:
    1. POST /v1/file_uploads (create upload object)
    2. POST /v1/file_uploads/{id}/send (send file content)
    
    Note: The uploaded file must be attached within 1 hour or Notion archives it.

    Args:
        image_path: Path to the image file.
        api_key: Notion API key (default: NOTION_API_KEY env).

    Returns:
        File upload ID, or None on failure.
    """
    effective_api_key = api_key or os.environ.get("NOTION_API_KEY")
    if not effective_api_key:
        logger.warning("NOTION_API_KEY not set, cannot upload image")
        return None

    image_path = Path(image_path)
    if not image_path.exists():
        logger.warning("Image not found at %s", image_path)
        return None

    # Determine content type
    content_type = _guess_content_type(image_path)

    # Headers for JSON endpoints
    json_headers = {
        "Authorization": f"Bearer {effective_api_key}",
        "Notion-Version": _NOTION_API_VERSION,
        "Content-Type": "application/json",
    }

    # Headers for multipart upload (NO Content-Type - requests sets it with boundary)
    upload_headers = {
        "Authorization": f"Bearer {effective_api_key}",
        "Notion-Version": _NOTION_API_VERSION,
    }

    try:
        # Step 1: Create file upload object
        create_resp = requests.post(
            f"{_NOTION_BASE}/file_uploads",
            headers=json_headers,
            json={
                "mode": "single_part",
                "filename": image_path.name,
                "content_type": content_type,
            },
            timeout=30,
        )
        
        if create_resp.status_code != 200:
            logger.warning(
                "Failed to create file upload: %s - %s",
                create_resp.status_code,
                create_resp.text,
            )
            return None
        
        upload_id = create_resp.json()["id"]
        logger.info("Created file upload: %s", upload_id)

        # Step 2: Send file content (multipart/form-data)
        with open(image_path, "rb") as f:
            send_resp = requests.post(
                f"{_NOTION_BASE}/file_uploads/{upload_id}/send",
                headers=upload_headers,  # NO Content-Type here
                files={"file": (image_path.name, f, content_type)},
                timeout=120,
            )
        
        if send_resp.status_code != 200:
            logger.warning(
                "Failed to send file: %s - %s",
                send_resp.status_code,
                send_resp.text,
            )
            return None
        
        logger.info("File sent successfully for upload: %s", upload_id)
        return upload_id

    except requests.RequestException as e:
        logger.warning("Network error uploading image to Notion: %s", e)
        return None
    except Exception as e:
        logger.warning("Failed to upload image to Notion: %s", e)
        return None


def _guess_content_type(file_path: Path) -> str:
    """Map file extension to MIME type."""
    _MIME_MAP = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    return _MIME_MAP.get(file_path.suffix.lower(), "application/octet-stream")
