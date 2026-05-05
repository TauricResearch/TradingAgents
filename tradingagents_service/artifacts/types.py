from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ArtifactManifestEntry:
    kind: str
    uri: str
    sha256: str
    bytes: int
    content_type: str


class ArtifactStore(Protocol):
    def manifest_entry_for_file(
        self,
        *,
        kind: str,
        path: Path,
        content_type: str,
    ) -> ArtifactManifestEntry:
        ...
