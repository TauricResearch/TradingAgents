"""RiskGate orchestration: validate, decide, and commit atomically."""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from . import ledger
from .canonical import hash_is_valid, recompute_proposal_hash
from .models import ReasonCode, RiskVerdict, VerdictStatus
from .policy import check_policy
from .rules import Decision, decide


class RiskGate:
    def __init__(
        self,
        db_path: str | Path,
        policy: Any,
        clock: Callable[[], datetime] | None = None,
        busy_timeout_seconds: float = 5.0,
        _fault_hook: Callable[[str], None] | None = None,
    ) -> None:
        self._db_path = Path(db_path)
        self._policy = policy
        self._clock = clock
        self._busy_timeout = float(busy_timeout_seconds)
        self._fault_hook = _fault_hook
        self._portfolio_id = "portfolio-1"

    def ensure_initialized(self, portfolio: Any) -> None:
        ledger.initialize(self._db_path, portfolio)
        self._portfolio_id = getattr(portfolio, "portfolio_id", self._portfolio_id)

    def snapshot(self) -> Any:
        return ledger.snapshot(self._db_path, self._portfolio_id)

    def evaluate_and_commit(
        self,
        proposal: Any,
        evidence_pack: Any,
        current_portfolio: Any,
    ) -> RiskVerdict:
        now = self._now()
        connection = None
        try:
            connection = ledger.connect(self._db_path, self._busy_timeout)
            connection.execute("BEGIN IMMEDIATE")
            portfolio_id = getattr(
                current_portfolio, "portfolio_id", self._portfolio_id
            )
            db_portfolio = ledger.read_portfolio(connection, portfolio_id)

            supplied_hash = getattr(proposal, "proposal_hash", None)
            if not hash_is_valid(supplied_hash):
                return self._finish(
                    connection,
                    proposal,
                    db_portfolio,
                    Decision(
                        status=VerdictStatus.REJECTED,
                        reasons=(ReasonCode.INVALID_OUTPUT,),
                        checked_rules=("proposal_hash",),
                    ),
                    now,
                )
            try:
                computed_hash = recompute_proposal_hash(proposal)
            except Exception:
                return self._finish(
                    connection,
                    proposal,
                    db_portfolio,
                    Decision(
                        status=VerdictStatus.REJECTED,
                        reasons=(ReasonCode.INVALID_OUTPUT,),
                        checked_rules=("proposal_hash",),
                    ),
                    now,
                )
            if computed_hash != supplied_hash:
                return self._finish(
                    connection,
                    proposal,
                    db_portfolio,
                    Decision(
                        status=VerdictStatus.REJECTED,
                        reasons=(ReasonCode.INTEGRITY_VIOLATION,),
                        checked_rules=("proposal_hash",),
                    ),
                    now,
                )

            existing = ledger.read_verdict(connection, supplied_hash)
            if existing is not None:
                connection.rollback()
                connection.close()
                return existing

            policy_issue = check_policy(self._policy, now)
            if policy_issue is not None:
                return self._finish(
                    connection,
                    proposal,
                    db_portfolio,
                    Decision(
                        status=policy_issue.status,
                        reasons=(policy_issue.reason,),
                        checked_rules=("policy",),
                    ),
                    now,
                )
            if getattr(proposal, "policy_hash", None) != getattr(
                self._policy, "policy_hash", None
            ):
                return self._finish(
                    connection,
                    proposal,
                    db_portfolio,
                    Decision(
                        status=VerdictStatus.REJECTED,
                        reasons=(ReasonCode.INTEGRITY_VIOLATION,),
                        checked_rules=("policy_hash",),
                    ),
                    now,
                )

            decision = decide(
                proposal,
                evidence_pack,
                db_portfolio,
                current_portfolio,
                self._policy,
                now,
            )
            return self._finish(
                connection, proposal, db_portfolio, decision, now
            )
        except Exception:
            if connection is not None:
                with contextlib.suppress(Exception):
                    connection.rollback()
                with contextlib.suppress(Exception):
                    connection.close()
            return self._blocked_verdict(proposal, current_portfolio)

    def _finish(
        self,
        connection: Any,
        proposal: Any,
        db_portfolio: Any,
        decision: Decision,
        now: datetime,
    ) -> RiskVerdict:
        expires_at = getattr(proposal, "expires_at", None)
        verdict = RiskVerdict(
            proposal_hash=getattr(proposal, "proposal_hash", ""),
            status=decision.status,
            reasons=decision.reasons,
            checked_rules=decision.checked_rules,
            portfolio_version=db_portfolio.version,
            expires_at=expires_at if isinstance(expires_at, datetime) else None,
            verdict_id=uuid4().hex,
        )
        ledger.store_verdict(connection, verdict, now)

        if decision.executes:
            assert decision.side is not None
            assert decision.quantity is not None
            assert decision.exec_price is not None
            assert decision.fee is not None
            assert decision.cash_after is not None
            assert decision.position_after is not None
            ledger.store_ledger_entry(
                connection,
                proposal_hash=verdict.proposal_hash,
                verdict_id=verdict.verdict_id,
                side=decision.side,
                quantity=decision.quantity,
                exec_price=decision.exec_price,
                fee=decision.fee,
                cash_after=decision.cash_after,
                position_after=decision.position_after,
                created_at=now,
            )
            self._call_hook("after_ledger_insert")
            ledger.update_portfolio(
                connection,
                portfolio_id=db_portfolio.portfolio_id,
                old_version=db_portfolio.version,
                new_version=db_portfolio.version + 1,
                cash_after=decision.cash_after,
                position_symbol=getattr(proposal, "ticker", ""),
                position_after=decision.position_after,
                mark_price=decision.exec_price,
                as_of=now,
            )

        ledger.store_outbox_event(
            connection,
            run_id=getattr(proposal, "run_id", None) or "run-1",
            status=self._event_status(decision.status),
            reason_code=self._event_reason(decision),
            metrics=self._metrics(verdict, decision),
            timestamp=now,
        )
        self._call_hook("after_outbox_insert")
        self._call_hook("before_commit")
        connection.commit()
        connection.close()
        return verdict

    def _blocked_verdict(self, proposal: Any, current_portfolio: Any) -> RiskVerdict:
        expires_at = getattr(proposal, "expires_at", None)
        return RiskVerdict(
            proposal_hash=getattr(proposal, "proposal_hash", ""),
            status=VerdictStatus.BLOCKED,
            reasons=(ReasonCode.AUDIT_UNAVAILABLE,),
            checked_rules=("audit",),
            portfolio_version=getattr(current_portfolio, "version", 0),
            expires_at=expires_at if isinstance(expires_at, datetime) else None,
            verdict_id=uuid4().hex,
        )

    def _now(self) -> datetime:
        value = self._clock() if self._clock is not None else datetime.now(UTC)
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _call_hook(self, stage: str) -> None:
        if self._fault_hook is not None:
            self._fault_hook(stage)

    @staticmethod
    def _event_status(status: VerdictStatus) -> str:
        if status is VerdictStatus.APPROVED:
            return "ok"
        if status is VerdictStatus.REVIEW:
            return "review"
        return "blocked"

    @staticmethod
    def _event_reason(decision: Decision) -> str | None:
        if not decision.reasons:
            return None
        return decision.reasons[0].value

    @staticmethod
    def _metrics(verdict: RiskVerdict, decision: Decision) -> dict[str, Any]:
        metrics: dict[str, Any] = {
            "verdict_id": verdict.verdict_id,
            "proposal_hash": verdict.proposal_hash,
            "ledger_committed": decision.executes,
        }
        if decision.executes:
            metrics.update(
                {
                    "side": decision.side,
                    "cash_after": str(decision.cash_after),
                    "position_after": decision.position_after,
                    "nav_after": str(decision.nav_after),
                }
            )
        return metrics
