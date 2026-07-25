"""Repository APIs returning domain records instead of SQLite rows."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from tradingagents.domain import (
    AdviceVersion,
    AnalysisJob,
    Conversation,
    ConversationMessage,
    JobEvent,
    ProviderCacheEntry,
    Report,
    SourceObservation,
    TrustAssessment,
    UsageRecord,
)

from .database import Database


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def run_signature(request: dict[str, Any]) -> str:
    return hashlib.sha256(json_text(request).encode()).hexdigest()


def _loads(value: str | None, default: Any = None) -> Any:
    return json.loads(value) if value is not None else default


class Repository:
    def __init__(self, database: Database):
        self.database = database
        self.database.migrate()

    def create_job(
        self,
        request: dict[str, Any],
        *,
        job_id: str | None = None,
        retry_of_job_id: str | None = None,
        retry_attempt: int = 0,
    ) -> AnalysisJob:
        now = utc_now()
        job_id = job_id or str(uuid.uuid4())
        signature = run_signature(request)
        with self.database.connect() as conn:
            conn.execute(
                "INSERT INTO analysis_jobs(id,request_json,status,run_signature,created_at,updated_at,retry_of_job_id,retry_attempt) VALUES (?,?,?,?,?,?,?,?)",
                (job_id, json_text(request), "queued", signature, now, now, retry_of_job_id, retry_attempt),
            )
        return self.get_job(job_id)  # type: ignore[return-value]

    def get_job(self, job_id: str) -> AnalysisJob | None:
        with self.database.connect() as conn:
            row = conn.execute("SELECT * FROM analysis_jobs WHERE id=?", (job_id,)).fetchone()
        return self._job(row) if row else None

    def list_jobs(self, *, limit: int = 100) -> list[AnalysisJob]:
        with self.database.connect() as conn:
            rows = conn.execute("SELECT * FROM analysis_jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [self._job(row) for row in rows]

    def active_count(self) -> int:
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM analysis_jobs WHERE status IN ('queued','running','cancelling')"
            ).fetchone()
        return int(row[0])

    def update_job(self, job_id: str, status: str, **values: Any) -> AnalysisJob:
        allowed = {"started_at", "finished_at", "error", "result", "report_id", "advice_id", "cancel_requested", "resumable"}
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"Unsupported job fields: {sorted(unknown)}")
        assignments = ["status=?", "updated_at=?"]
        params: list[Any] = [status, utc_now()]
        for name, value in values.items():
            column = f"{name}_json" if name in {"error", "result"} else name
            assignments.append(f"{column}=?")
            if name in {"error", "result"}:
                value = json_text(value) if value is not None else None
            elif name in {"cancel_requested", "resumable"}:
                value = int(bool(value))
            params.append(value)
        params.append(job_id)
        with self.database.connect() as conn:
            conn.execute(f"UPDATE analysis_jobs SET {','.join(assignments)} WHERE id=?", params)
        job = self.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def interrupt_active_jobs(self) -> int:
        now = utc_now()
        with self.database.connect() as conn:
            cursor = conn.execute(
                "UPDATE analysis_jobs SET status='interrupted',updated_at=?,finished_at=?,cancel_requested=0 "
                "WHERE status IN ('queued','running','cancelling')",
                (now, now),
            )
            return cursor.rowcount

    def append_event(self, job_id: str, event_type: str, data: dict[str, Any]) -> JobEvent:
        now = utc_now()
        with self.database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            event_id = int(conn.execute("SELECT COALESCE(MAX(event_id),0)+1 FROM job_events WHERE job_id=?", (job_id,)).fetchone()[0])
            conn.execute(
                "INSERT INTO job_events(job_id,event_id,event_type,timestamp,data_json) VALUES (?,?,?,?,?)",
                (job_id, event_id, event_type, now, json_text(data)),
            )
            conn.execute("COMMIT")
        return JobEvent(job_id, event_id, event_type, now, data)

    def list_events(self, job_id: str, *, after: int = 0) -> list[JobEvent]:
        with self.database.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM job_events WHERE job_id=? AND event_id>? ORDER BY event_id", (job_id, after)
            ).fetchall()
        return [JobEvent(row["job_id"], row["event_id"], row["event_type"], row["timestamp"], _loads(row["data_json"], {})) for row in rows]

    def trim_events(self, job_id: str, *, keep: int = 512) -> None:
        terminal = ("analysis.completed", "analysis.failed", "analysis.cancelled", "analysis.interrupted", "analysis.budget_exhausted", "analysis.provider_rate_limited")
        with self.database.connect() as conn:
            conn.execute(
                f"DELETE FROM job_events WHERE job_id=? AND event_type NOT IN ({','.join('?' for _ in terminal)}) "
                "AND event_id <= COALESCE((SELECT MAX(event_id)-? FROM job_events WHERE job_id=?),0)",
                (job_id, *terminal, keep, job_id),
            )

    def create_report(self, job_id: str, result: dict[str, Any], markdown: str) -> Report:
        report_id, now = str(uuid.uuid4()), utc_now()
        with self.database.connect() as conn:
            conn.execute(
                "INSERT INTO reports(id,job_id,created_at,result_json,markdown) VALUES (?,?,?,?,?)",
                (report_id, job_id, now, json_text(result), markdown),
            )
        return Report(report_id, job_id, now, result, markdown)

    def get_report(self, report_id: str) -> Report | None:
        with self.database.connect() as conn:
            row = conn.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
        return self._report(row) if row else None

    def get_report_for_job(self, job_id: str) -> Report | None:
        with self.database.connect() as conn:
            row = conn.execute("SELECT * FROM reports WHERE job_id=?", (job_id,)).fetchone()
        return self._report(row) if row else None

    def create_advice(self, report_id: str, *, action: str, confidence: str, reason: str, eligibility: str, parent_id: str | None = None, trust_assessment_id: str | None = None, trigger_message_ids: list[str] | None = None, data_snapshot: dict[str, Any] | None = None, model_config: dict[str, Any] | None = None, usage: dict[str, Any] | None = None) -> AdviceVersion:
        advice_id, now = str(uuid.uuid4()), utc_now()
        with self.database.connect() as conn:
            version = int(conn.execute("SELECT COALESCE(MAX(version),0)+1 FROM advice_versions WHERE report_id=?", (report_id,)).fetchone()[0])
            conn.execute(
                "INSERT INTO advice_versions(id,report_id,parent_id,version,created_at,action,confidence,reason,eligibility,trust_assessment_id,trigger_message_ids_json,data_snapshot_json,model_config_json,usage_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (advice_id, report_id, parent_id, version, now, action, confidence, reason, eligibility, trust_assessment_id, json_text(trigger_message_ids or []), json_text(data_snapshot or {}), json_text(model_config or {}), json_text(usage or {})),
            )
        return self.get_advice(advice_id)  # type: ignore[return-value]

    def get_advice(self, advice_id: str) -> AdviceVersion | None:
        with self.database.connect() as conn:
            row = conn.execute("SELECT * FROM advice_versions WHERE id=?", (advice_id,)).fetchone()
        return self._advice(row) if row else None

    def list_advice(self, report_id: str) -> list[AdviceVersion]:
        with self.database.connect() as conn:
            rows = conn.execute("SELECT * FROM advice_versions WHERE report_id=? ORDER BY version", (report_id,)).fetchall()
        return [self._advice(row) for row in rows]

    def create_conversation(self, report_id: str) -> Conversation:
        conversation_id, now = str(uuid.uuid4()), utc_now()
        with self.database.connect() as conn:
            conn.execute("INSERT INTO conversations(id,report_id,created_at,updated_at) VALUES (?,?,?,?)", (conversation_id, report_id, now, now))
        return Conversation(conversation_id, report_id, now, now)

    def get_conversation(self, conversation_id: str) -> tuple[Conversation, list[ConversationMessage]] | None:
        with self.database.connect() as conn:
            row = conn.execute("SELECT * FROM conversations WHERE id=?", (conversation_id,)).fetchone()
            if not row:
                return None
            messages = conn.execute("SELECT * FROM conversation_messages WHERE conversation_id=? ORDER BY created_at,id", (conversation_id,)).fetchall()
        conversation = Conversation(row["id"], row["report_id"], row["created_at"], row["updated_at"])
        return conversation, [self._message(item) for item in messages]

    def add_message(self, conversation_id: str, role: str, content: str, *, source_references: list[str] | None = None, refreshed_data: bool = False, candidate_adjustment: bool = False, usage_record_id: str | None = None) -> ConversationMessage:
        message_id, now = str(uuid.uuid4()), utc_now()
        with self.database.connect() as conn:
            conn.execute(
                "INSERT INTO conversation_messages(id,conversation_id,role,content,created_at,source_references_json,refreshed_data,candidate_adjustment,usage_record_id) VALUES (?,?,?,?,?,?,?,?,?)",
                (message_id, conversation_id, role, content, now, json_text(source_references or []), int(refreshed_data), int(candidate_adjustment), usage_record_id),
            )
            conn.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now, conversation_id))
        return ConversationMessage(message_id, conversation_id, role, content, now, tuple(source_references or []), refreshed_data, candidate_adjustment, usage_record_id)

    def add_usage(self, record: UsageRecord) -> None:
        with self.database.connect() as conn:
            conn.execute(
                "INSERT INTO usage_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (record.id, record.job_id, record.conversation_id, record.provider, record.model, record.requests, record.input_tokens, record.output_tokens, record.retries, record.latency_ms, record.status, record.warning, record.created_at),
            )

    def list_usage(self, *, job_id: str | None = None, conversation_id: str | None = None, since: str | None = None) -> list[UsageRecord]:
        clauses, params = [], []
        if job_id is not None:
            clauses.append("job_id=?")
            params.append(job_id)
        if conversation_id is not None:
            clauses.append("conversation_id=?")
            params.append(conversation_id)
        if since is not None:
            clauses.append("created_at>=?")
            params.append(since)
        query = "SELECT id,job_id,conversation_id,provider,model,requests,input_tokens,output_tokens,retries,latency_ms,status,warning,created_at FROM usage_records"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at"
        with self.database.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [UsageRecord(*tuple(row)) for row in rows]

    def get_provider_cache(
        self,
        provider: str,
        symbol: str,
        capability: str,
        request_params: dict[str, Any] | None = None,
    ) -> ProviderCacheEntry | None:
        params_hash = hashlib.sha256(json_text(request_params or {}).encode()).hexdigest()
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT * FROM provider_cache WHERE provider=? AND symbol=? AND capability=? AND request_params_hash=?",
                (provider, symbol, capability, params_hash),
            ).fetchone()
        return self._provider_cache(row) if row else None

    def put_provider_cache(
        self,
        *,
        provider: str,
        symbol: str,
        capability: str,
        request_params: dict[str, Any] | None,
        normalized_payload: dict[str, Any],
        source_reference: str,
        retrieved_at: str,
        effective_at: str | None,
        expires_at: str,
    ) -> ProviderCacheEntry:
        params_hash = hashlib.sha256(json_text(request_params or {}).encode()).hexdigest()
        payload_hash = hashlib.sha256(json_text(normalized_payload).encode()).hexdigest()
        with self.database.connect() as conn:
            conn.execute(
                "INSERT INTO provider_cache(provider,symbol,capability,request_params_hash,normalized_json,source_reference,retrieved_at,effective_at,expires_at,payload_hash) VALUES (?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(provider,symbol,capability,request_params_hash) DO UPDATE SET normalized_json=excluded.normalized_json,source_reference=excluded.source_reference,retrieved_at=excluded.retrieved_at,effective_at=excluded.effective_at,expires_at=excluded.expires_at,payload_hash=excluded.payload_hash",
                (provider, symbol, capability, params_hash, json_text(normalized_payload), source_reference, retrieved_at, effective_at, expires_at, payload_hash),
            )
        return self.get_provider_cache(provider, symbol, capability, request_params)  # type: ignore[return-value]

    def add_observation(self, value: SourceObservation) -> None:
        with self.database.connect() as conn:
            conn.execute("INSERT INTO source_observations VALUES (?,?,?,?,?,?,?,?,?,?,?)", tuple(asdict(value).values()))

    def list_observations(self, *, job_id: str | None = None, conversation_id: str | None = None) -> list[SourceObservation]:
        field, value = ("job_id", job_id) if job_id is not None else ("conversation_id", conversation_id)
        if value is None:
            return []
        with self.database.connect() as conn:
            rows = conn.execute(f"SELECT * FROM source_observations WHERE {field}=? ORDER BY retrieved_at", (value,)).fetchall()
        return [SourceObservation(*tuple(row)) for row in rows]

    def add_trust(self, value: TrustAssessment) -> None:
        evidence = [asdict(item) for item in value.evidence]
        with self.database.connect() as conn:
            conn.execute(
                "INSERT INTO trust_assessments VALUES (?,?,?,?,?,?,?,?,?)",
                (value.id, value.job_id, value.conversation_id, value.level, int(value.executable), json_text(value.reason_codes), json_text(value.warnings), json_text(evidence), value.assessed_at),
            )

    def latest_trust(self, *, job_id: str | None = None, conversation_id: str | None = None) -> TrustAssessment | None:
        field, value = ("job_id", job_id) if job_id is not None else ("conversation_id", conversation_id)
        if value is None:
            return None
        with self.database.connect() as conn:
            row = conn.execute(f"SELECT * FROM trust_assessments WHERE {field}=? ORDER BY assessed_at DESC LIMIT 1", (value,)).fetchone()
        if not row:
            return None
        from tradingagents.domain import EvidenceField
        evidence = []
        for item in _loads(row["evidence_json"], []):
            item["normalization_warnings"] = tuple(item.get("normalization_warnings", ()))
            evidence.append(EvidenceField(**item))
        return TrustAssessment(row["id"], row["job_id"], row["conversation_id"], row["level"], bool(row["executable"]), tuple(_loads(row["reason_codes_json"], [])), tuple(_loads(row["warnings_json"], [])), row["assessed_at"], tuple(evidence))

    @staticmethod
    def _job(row: Any) -> AnalysisJob:
        return AnalysisJob(row["id"], _loads(row["request_json"], {}), row["status"], row["run_signature"], row["created_at"], row["updated_at"], row["started_at"], row["finished_at"], _loads(row["error_json"]), _loads(row["result_json"]), row["report_id"], row["advice_id"], bool(row["cancel_requested"]), bool(row["resumable"]), row["retry_of_job_id"], int(row["retry_attempt"]))

    @staticmethod
    def _provider_cache(row: Any) -> ProviderCacheEntry:
        return ProviderCacheEntry(
            row["provider"], row["symbol"], row["capability"], row["request_params_hash"],
            _loads(row["normalized_json"], {}), row["source_reference"], row["retrieved_at"],
            row["effective_at"], row["expires_at"], row["payload_hash"],
        )

    @staticmethod
    def _report(row: Any) -> Report:
        return Report(row["id"], row["job_id"], row["created_at"], _loads(row["result_json"], {}), row["markdown"], row["schema_version"])

    @staticmethod
    def _advice(row: Any) -> AdviceVersion:
        return AdviceVersion(row["id"], row["report_id"], row["version"], row["created_at"], row["action"], row["confidence"], row["reason"], row["eligibility"], row["parent_id"], row["trust_assessment_id"], tuple(_loads(row["trigger_message_ids_json"], [])), _loads(row["data_snapshot_json"], {}), _loads(row["model_config_json"], {}), _loads(row["usage_json"], {}))

    @staticmethod
    def _message(row: Any) -> ConversationMessage:
        return ConversationMessage(row["id"], row["conversation_id"], row["role"], row["content"], row["created_at"], tuple(_loads(row["source_references_json"], [])), bool(row["refreshed_data"]), bool(row["candidate_adjustment"]), row["usage_record_id"])
