"""Atomic, immutable, content-addressed filesystem artifacts."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tradingagents.domain.contracts import canonical_json, content_id


class ArtifactIntegrityError(RuntimeError):
    """Raised when an artifact is absent, incomplete, or no longer authentic."""


@dataclass(frozen=True)
class ArtifactRef:
    kind: str
    artifact_id: str
    payload_sha256: str


_KIND = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
_ARTIFACT_ID = re.compile(r"^[a-z][a-z0-9_-]{0,31}_[0-9a-f]{24}$")


def _validate_kind(kind: str) -> str:
    if not isinstance(kind, str) or _KIND.fullmatch(kind) is None:
        raise ValueError("artifact kind must be a safe lowercase identifier")
    return kind


def _validate_artifact_id(artifact_id: str) -> str:
    if not isinstance(artifact_id, str) or _ARTIFACT_ID.fullmatch(artifact_id) is None:
        raise ValueError("artifact ID is malformed")
    return artifact_id


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def reference_for_payload(kind: str, payload: dict[str, Any]) -> ArtifactRef:
    """Return the only valid reference for a canonical artifact payload."""
    kind = _validate_kind(kind)
    if not isinstance(payload, dict):
        raise TypeError("artifact payload must be a mapping")
    encoded = canonical_json(payload).encode("utf-8")
    return ArtifactRef(
        kind=kind,
        artifact_id=content_id(kind, {"kind": kind, "payload": payload}),
        payload_sha256=hashlib.sha256(encoded).hexdigest(),
    )


def require_payload_reference(
    reference: ArtifactRef, *, kind: str, payload: dict[str, Any]
) -> None:
    """Reject a caller that pairs an object with a different artifact ref."""
    if not isinstance(reference, ArtifactRef):
        raise TypeError("artifact reference has an invalid type")
    expected = reference_for_payload(kind, payload)
    if reference != expected:
        raise ArtifactIntegrityError(
            f"{kind} object does not match its supplied artifact reference"
        )


class FilesystemArtifactStore:
    """One immutable directory per payload, finalized by an atomic rename."""

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, kind: str, artifact_id: str) -> Path:
        return self.root / _validate_kind(kind) / _validate_artifact_id(artifact_id)

    def commit(self, kind: str, payload: dict[str, Any]) -> ArtifactRef:
        reference = reference_for_payload(kind, payload)
        kind = reference.kind
        encoded = canonical_json(payload).encode("utf-8")
        digest = reference.payload_sha256
        artifact_id = reference.artifact_id
        parent = self.root / kind
        try:
            parent.mkdir(mode=0o700)
        except FileExistsError:
            if not parent.is_dir():
                raise
        else:
            _fsync_directory(self.root)
        final = self._path(kind, artifact_id)
        if final.exists():
            if self.load_ref(kind, artifact_id) != reference:
                raise ArtifactIntegrityError("existing artifact differs from its content ID")
            return reference

        staging = parent / f".staging-{artifact_id}-{uuid.uuid4().hex}"
        staging.mkdir(mode=0o700)
        try:
            payload_path = staging / "payload.json"
            with payload_path.open("xb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            marker = {
                "schema_version": 1,
                "kind": kind,
                "artifact_id": artifact_id,
                "payload_sha256": digest,
            }
            marker_path = staging / "COMMITTED.json"
            with marker_path.open("x", encoding="utf-8") as handle:
                handle.write(canonical_json(marker))
                handle.flush()
                os.fsync(handle.fileno())
            _fsync_directory(staging)
            try:
                staging.rename(final)
            except OSError as exc:
                if exc.errno not in {errno.EEXIST, errno.ENOTEMPTY}:
                    raise
                if self.load_ref(kind, artifact_id) != reference:
                    raise ArtifactIntegrityError(
                        "concurrent artifact commit disagreed"
                    ) from None
            _fsync_directory(parent)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        return reference

    def load_with_ref(
        self, kind: str, artifact_id: str
    ) -> tuple[ArtifactRef, dict[str, Any]]:
        """Read once, validate once, and return the exact validated payload."""
        path = self._path(kind, artifact_id)
        marker_path = path / "COMMITTED.json"
        payload_path = path / "payload.json"
        if not path.is_dir() or not marker_path.is_file() or not payload_path.is_file():
            raise ArtifactIntegrityError("artifact is missing its atomic commit marker")
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            payload_bytes = payload_path.read_bytes()
        except (OSError, json.JSONDecodeError) as exc:
            raise ArtifactIntegrityError("artifact cannot be read") from exc
        expected_keys = {"schema_version", "kind", "artifact_id", "payload_sha256"}
        if not isinstance(marker, dict) or set(marker) != expected_keys:
            raise ArtifactIntegrityError("artifact commit marker has an invalid shape")
        digest = hashlib.sha256(payload_bytes).hexdigest()
        if marker != {
            "schema_version": 1,
            "kind": kind,
            "artifact_id": artifact_id,
            "payload_sha256": digest,
        }:
            raise ArtifactIntegrityError("artifact payload or commit marker was modified")
        try:
            payload = json.loads(payload_bytes)
        except json.JSONDecodeError as exc:
            raise ArtifactIntegrityError("artifact payload is not JSON") from exc
        if not isinstance(payload, dict) or canonical_json(payload).encode("utf-8") != payload_bytes:
            raise ArtifactIntegrityError("artifact payload is not canonical JSON")
        expected_id = content_id(kind, {"kind": kind, "payload": payload})
        if expected_id != artifact_id:
            raise ArtifactIntegrityError("artifact content ID does not match its payload")
        return ArtifactRef(kind, artifact_id, digest), payload

    def load_ref(self, kind: str, artifact_id: str) -> ArtifactRef:
        reference, _ = self.load_with_ref(kind, artifact_id)
        return reference

    def load(self, kind: str, artifact_id: str) -> dict[str, Any]:
        _, payload = self.load_with_ref(kind, artifact_id)
        return payload
