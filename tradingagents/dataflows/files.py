"""Cache files written whole, safe under concurrent writers."""

import logging
import os
import uuid
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)


def replace_file(path, write: Callable[[str], None]) -> None:
    """Write ``path`` through a uniquely named temp file beside it, then move it into place.

    A reader sees the old file or the new one, never a partial write, and two
    writers of the same path (tool calls run concurrently) never share a temp file.
    ``write`` receives the temp path and creates the file, so it gets the usual
    permissions. The file is a cache: where another reader holds it open (Windows),
    the old one stays and the write is skipped.
    """
    path = Path(path)
    temp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        write(str(temp))
        os.replace(temp, path)
    except PermissionError as exc:
        temp.unlink(missing_ok=True)
        logger.warning("Kept the cached %s; it is in use (%s)", path.name, exc)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
