from __future__ import annotations

import hashlib
from pathlib import Path

from .types import ArtifactManifestEntry


class LocalArtifactBackend:
    def manifest_entry_for_file(
        self,
        *,
        kind: str,
        path: Path,
        content_type: str,
    ) -> ArtifactManifestEntry:
        resolved_path = path.resolve()
        payload = resolved_path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        return ArtifactManifestEntry(
            kind=kind,
            uri=resolved_path.as_uri(),
            sha256=digest,
            bytes=len(payload),
            content_type=content_type,
        )
