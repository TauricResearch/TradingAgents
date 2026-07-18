"""Append-only filesystem source of truth for localhost analysis history."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

from tradingagents.observability.canonical import canonical_business_value
from tradingagents.observability.events import ArtifactRef, PersistedEvent, RunEventDraft
from tradingagents.observability.redaction import redact_recursive

from .run_models import RunSnapshot, RunSummary, utc_timestamp, validate_run_id


ARTIFACT_KIND_DIRECTORIES = {
    "data": "data",
    "prompt": "prompts",
    "tool-result": "tool-results",
    "report-revision": "report-revisions",
}
ARTIFACT_KIND_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class RunStoreError(RuntimeError):
    pass


class RunNotFound(RunStoreError):
    pass


class RunAlreadyExists(RunStoreError):
    pass


class RunStoreCorruption(RunStoreError):
    pass


class InvalidStorePath(RunStoreError):
    pass


def _extension_for_media_type(media_type: str) -> str:
    return {
        "application/json": ".json",
        "text/markdown": ".md",
        "text/plain": ".txt",
    }.get(media_type, ".bin")


class RunStore:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or Path.home() / ".tradingagents" / "web" / "runs")
        self.root.mkdir(parents=True, exist_ok=True)
        self._global_lock = threading.RLock()
        self._locks_guard = threading.Lock()
        self._run_locks: dict[str, threading.RLock] = {}

    def lock_for(self, run_id: str) -> threading.RLock:
        validate_run_id(run_id)
        with self._locks_guard:
            return self._run_locks.setdefault(run_id, threading.RLock())

    def _run_dir(self, run_id: str, *, must_exist: bool = True) -> Path:
        try:
            validate_run_id(run_id)
        except ValueError as exc:
            raise InvalidStorePath("invalid run_id") from exc
        path = self.root / run_id
        if path.parent.resolve() != self.root.resolve():
            raise InvalidStorePath("run path escapes store root")
        if must_exist and not path.is_dir():
            raise RunNotFound(run_id)
        return path

    def create_run(self, snapshot: RunSnapshot) -> RunSnapshot:
        run_dir = self._run_dir(snapshot.run_id, must_exist=False)
        with self._global_lock, self.lock_for(snapshot.run_id):
            try:
                run_dir.mkdir(parents=False, exist_ok=False)
            except FileExistsError as exc:
                raise RunAlreadyExists(snapshot.run_id) from exc
            try:
                self._write_snapshot_file(run_dir, snapshot)
                self._fsync_directory(run_dir)
                self._fsync_directory(self.root)
            except Exception:
                # Leave a visible directory rather than deleting possible evidence.
                raise
        return snapshot

    def read_snapshot(self, run_id: str) -> RunSnapshot:
        run_dir = self._run_dir(run_id)
        with self.lock_for(run_id):
            try:
                payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, TypeError) as exc:
                raise RunStoreCorruption(f"invalid run snapshot for {run_id}") from exc
            snapshot = RunSnapshot.from_dict(payload)
            latest_event = self._last_event_sequence(run_dir)
            if latest_event > snapshot.latest_sequence:
                snapshot = replace(
                    snapshot,
                    latest_sequence=latest_event,
                    updated_at=utc_timestamp(),
                )
                self._write_snapshot_file(run_dir, snapshot)
            elif latest_event < snapshot.latest_sequence:
                raise RunStoreCorruption(
                    f"snapshot sequence {snapshot.latest_sequence} is ahead of events {latest_event}"
                )
            return snapshot

    def write_snapshot_atomic(self, snapshot: RunSnapshot) -> RunSnapshot:
        run_dir = self._run_dir(snapshot.run_id)
        with self.lock_for(snapshot.run_id):
            current = self.read_snapshot(snapshot.run_id)
            if snapshot.latest_sequence < current.latest_sequence:
                raise RunStoreError("snapshot latest_sequence cannot decrease")
            self._write_snapshot_file(run_dir, snapshot)
        return snapshot

    def append_event(self, draft: RunEventDraft) -> PersistedEvent:
        run_dir = self._run_dir(draft.run_id)
        with self.lock_for(draft.run_id):
            if draft.type == "run.completed" and not (
                run_dir / "reports" / "complete_report.md"
            ).is_file():
                raise RunStoreError(
                    "run.completed requires an atomically published canonical report tree"
                )
            snapshot = self.read_snapshot(draft.run_id)
            sequence = max(snapshot.latest_sequence, self._last_event_sequence(run_dir)) + 1
            redacted_payload = redact_recursive(draft.payload)
            payload = dict(redacted_payload.value)
            if redacted_payload.manifest:
                payload["redaction_manifest"] = [
                    record.path for record in redacted_payload.manifest
                ]
            safe_draft = replace(draft, payload=payload)
            event = PersistedEvent.from_draft(safe_draft, sequence)
            serialized = canonical_business_value(event.as_dict()).bytes + b"\n"
            event_file = run_dir / "events.jsonl"
            with event_file.open("ab", buffering=0) as handle:
                handle.write(serialized)
                os.fsync(handle.fileno())
            self._fsync_directory(run_dir)

            status = snapshot.status
            if event.type.startswith("run.") and isinstance(payload.get("run_status"), str):
                status = payload["run_status"]
            updated = replace(
                snapshot,
                status=status,
                latest_sequence=sequence,
                updated_at=event.timestamp,
            )
            self._write_snapshot_file(run_dir, updated)
            return event

    def read_events(
        self,
        run_id: str,
        *,
        after: int = 0,
        through: int | None = None,
    ) -> list[PersistedEvent]:
        if after < 0 or (through is not None and through < after):
            raise ValueError("invalid event sequence range")
        run_dir = self._run_dir(run_id)
        event_file = run_dir / "events.jsonl"
        if not event_file.exists():
            return []
        events: list[PersistedEvent] = []
        expected = 1
        try:
            with event_file.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if not line.endswith("\n"):
                        raise RunStoreCorruption(
                            f"unterminated event at line {line_number} for {run_id}"
                        )
                    payload = json.loads(line)
                    event = PersistedEvent(**payload)
                    if event.run_id != run_id or event.sequence != expected:
                        raise RunStoreCorruption(
                            f"non-contiguous event sequence at line {line_number} for {run_id}"
                        )
                    expected += 1
                    if event.sequence > after and (
                        through is None or event.sequence <= through
                    ):
                        events.append(event)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            if isinstance(exc, RunStoreCorruption):
                raise
            raise RunStoreCorruption(f"invalid event log for {run_id}") from exc
        return events

    def list_runs(self) -> list[RunSummary]:
        summaries = []
        with self._global_lock:
            for path in self.root.iterdir():
                if not path.is_dir():
                    continue
                try:
                    validate_run_id(path.name)
                    summaries.append(RunSummary.from_snapshot(self.read_snapshot(path.name)))
                except (ValueError, RunStoreError):
                    continue
        return sorted(summaries, key=lambda summary: summary.created_at, reverse=True)

    def store_artifact(
        self,
        run_id: str,
        *,
        kind: str,
        value: Any,
        media_type: str = "application/json",
    ) -> ArtifactRef:
        run_dir = self._run_dir(run_id)
        if not ARTIFACT_KIND_PATTERN.fullmatch(kind):
            raise InvalidStorePath("invalid artifact kind")
        directory_name = ARTIFACT_KIND_DIRECTORIES.get(kind, kind)
        artifact_dir = run_dir / directory_name
        if artifact_dir.parent.resolve() != run_dir.resolve():
            raise InvalidStorePath("artifact path escapes run directory")

        if isinstance(value, bytes):
            content = value
        elif isinstance(value, str):
            redacted = redact_recursive({"content": value}).value["content"]
            content = redacted.encode("utf-8")
        else:
            content = canonical_business_value(value).bytes
        digest = hashlib.sha256(content).hexdigest()
        extension = _extension_for_media_type(media_type)
        locator = f"{directory_name}/{digest}{extension}"
        destination = run_dir / locator

        with self.lock_for(run_id):
            artifact_dir.mkdir(parents=True, exist_ok=True)
            if not destination.exists():
                self._write_bytes_atomic(destination, content)
                self._fsync_directory(artifact_dir)
        return ArtifactRef(
            artifact_id=f"{kind}:{digest}",
            kind=kind,
            media_type=media_type,
            content_sha256=digest,
            byte_size=len(content),
            locator=locator,
        )

    def read_artifact(self, run_id: str, artifact_id: str) -> bytes:
        run_dir = self._run_dir(run_id)
        try:
            kind, digest = artifact_id.split(":", 1)
        except ValueError as exc:
            raise InvalidStorePath("invalid artifact_id") from exc
        if not ARTIFACT_KIND_PATTERN.fullmatch(kind) or not SHA256_PATTERN.fullmatch(digest):
            raise InvalidStorePath("invalid artifact_id")
        directory_name = ARTIFACT_KIND_DIRECTORIES.get(kind, kind)
        artifact_dir = run_dir / directory_name
        if artifact_dir.parent.resolve() != run_dir.resolve():
            raise InvalidStorePath("artifact path escapes run directory")
        matches = list(artifact_dir.glob(f"{digest}.*")) if artifact_dir.is_dir() else []
        if len(matches) != 1 or not matches[0].is_file():
            raise RunNotFound(f"artifact {artifact_id}")
        return matches[0].read_bytes()

    def _write_snapshot_file(self, run_dir: Path, snapshot: RunSnapshot) -> None:
        raw = snapshot.as_dict()
        redacted = redact_recursive(raw)
        payload = dict(redacted.value)
        existing_manifest = set(payload.get("redaction_manifest") or [])
        existing_manifest.update(record.path for record in redacted.manifest)
        payload["redaction_manifest"] = sorted(existing_manifest)
        content = canonical_business_value(payload).bytes + b"\n"
        self._write_bytes_atomic(run_dir / "run.json", content)
        self._fsync_directory(run_dir)

    @staticmethod
    def _write_bytes_atomic(destination: Path, content: bytes) -> None:
        temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("xb", buffering=0) as handle:
                handle.write(content)
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _last_event_sequence(run_dir: Path) -> int:
        event_file = run_dir / "events.jsonl"
        if not event_file.exists() or event_file.stat().st_size == 0:
            return 0
        last_sequence = 0
        try:
            with event_file.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.endswith("\n"):
                        raise RunStoreCorruption("unterminated final event")
                    payload = json.loads(line)
                    last_sequence = int(payload["sequence"])
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, RunStoreCorruption):
                raise
            raise RunStoreCorruption("unable to read latest event sequence") from exc
        return last_sequence
