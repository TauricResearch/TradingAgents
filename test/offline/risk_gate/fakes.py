"""Test-only fakes and fixture builders for FR-04.

These are not the formal shared contracts. They mirror the field names and meanings
documented in ``execution_plan_261111.md`` §5.1 so the risk gate can be specified
before A/B/C freeze ``src/egta/contracts/``. No production module may import this
file.

The tests deliberately keep this file dependency-free (stdlib only) so the test
suite can be collected while the implementation is absent. Behavioural tests fail
red at fixture setup; the manifest and harness self-checks remain green.

Test fixture parameters are not product policy. ``price_freshness_seconds``,
``fee_bps`` and ``slippage_bps`` are injected by tests only; the product policy is
PENDING human approval and an unconfigured policy must fail closed. The FR-04
freshness boundary cases pass the parameter explicitly via ``freshness`` rather
than relying on a product default.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

NOW = datetime(2026, 1, 2, 15, 0, 0, tzinfo=UTC)
ZERO_HASH = "0" * 64
CANARY = "CANARY_SECRET_SHOULD_NOT_BE_PERSISTED_9f3a"

# Test-fixture parameters only. They do not approve any product threshold.
TEST_PRICE_FRESHNESS_SECONDS = 240
TEST_FEE_BPS = Decimal("10")
TEST_SLIPPAGE_BPS = Decimal("0")
TEST_FIXTURE_PARAMETERS = {
    "price_freshness_seconds": TEST_PRICE_FRESHNESS_SECONDS,
    "fee_bps": str(TEST_FEE_BPS),
    "slippage_bps": str(TEST_SLIPPAGE_BPS),
}


@dataclass(frozen=True)
class FixedClock:
    now: datetime

    def __call__(self) -> datetime:
        return self.now


def _dt(seconds: int = 0, tz_hours: int = 0, naive: bool = False) -> datetime:
    value = NOW + timedelta(seconds=seconds)
    if tz_hours:
        value = value.astimezone(timezone(timedelta(hours=tz_hours)))
    if naive:
        value = value.replace(tzinfo=None)
    return value


def _dec(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _normalize(value: Any) -> Any:
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            return value.isoformat()
        return value.astimezone(UTC).isoformat()
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_normalize(item) for item in value)
    if isinstance(value, dict):
        items = sorted(value.items(), key=lambda pair: str(pair[0]))
        return {str(key): _normalize(item) for key, item in items}
    if hasattr(value, "to_canonical_dict"):
        return _normalize(value.to_canonical_dict())
    raise TypeError(f"cannot canonicalize {type(value)!r}")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        _normalize(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


@dataclass(frozen=True)
class FakeClaim:
    claim_id: str
    text: str
    evidence_ids: tuple[str, ...]
    stance: str = "support"
    counterargument: str | None = None
    unresolved: bool = False

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "text": self.text,
            "evidence_ids": self.evidence_ids,
            "stance": self.stance,
            "counterargument": self.counterargument,
            "unresolved": self.unresolved,
        }


@dataclass(frozen=True)
class FakeEvidenceItem:
    evidence_id: str
    source_uri: str
    published_at: datetime
    fetched_at: datetime
    content_hash: str
    excerpt: str
    availability: str
    trust_label: str

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "source_uri": self.source_uri,
            "published_at": self.published_at,
            "fetched_at": self.fetched_at,
            "content_hash": self.content_hash,
            "excerpt": self.excerpt,
            "availability": self.availability,
            "trust_label": self.trust_label,
        }


@dataclass(frozen=True)
class FakeEvidencePack:
    run_id: str
    snapshot_id: str
    items: tuple[FakeEvidenceItem, ...]
    excluded_items: tuple[FakeEvidenceItem, ...]
    cutoff: datetime
    pack_hash: str

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "snapshot_id": self.snapshot_id,
            "items": self.items,
            "excluded_items": self.excluded_items,
            "cutoff": self.cutoff,
        }


@dataclass(frozen=True)
class FakeAdvisoryProposal:
    proposal_id: str
    run_id: str
    ticker: str
    action: Any
    quantity: Any
    currency: Any
    reference_price: Any
    price_time: Any
    claims: tuple[FakeClaim, ...]
    evidence_pack_hash: Any
    portfolio_version: Any
    policy_hash: Any
    expires_at: Any
    proposal_hash: Any
    policy_override: Any = None
    bypass: Any = None

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "run_id": self.run_id,
            "ticker": self.ticker,
            "action": self.action,
            "quantity": self.quantity,
            "currency": self.currency,
            "reference_price": self.reference_price,
            "price_time": self.price_time,
            "claims": self.claims,
            "evidence_pack_hash": self.evidence_pack_hash,
            "portfolio_version": self.portfolio_version,
            "policy_hash": self.policy_hash,
            "expires_at": self.expires_at,
        }


@dataclass(frozen=True)
class FakePosition:
    symbol: str
    quantity: int
    mark_price: Decimal


@dataclass(frozen=True)
class FakePortfolioSnapshot:
    portfolio_id: str
    version: int
    base_currency: str
    cash: Decimal
    positions: tuple[FakePosition, ...]
    as_of: datetime


@dataclass(frozen=True)
class FakeRiskPolicy:
    version: str
    policy_hash: str
    base_currency: str
    max_position_pct: Decimal | None
    max_order_pct: Decimal | None
    price_freshness_seconds: int | None
    fee_bps: Decimal | None
    slippage_bps: Decimal | None
    allowed_actions: frozenset[str]
    long_only: bool
    paper_only: bool
    effective_from: datetime | None
    expires_at: datetime | None
    quantization: Decimal | None

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "base_currency": self.base_currency,
            "max_position_pct": self.max_position_pct,
            "max_order_pct": self.max_order_pct,
            "price_freshness_seconds": self.price_freshness_seconds,
            "fee_bps": self.fee_bps,
            "slippage_bps": self.slippage_bps,
            "allowed_actions": self.allowed_actions,
            "long_only": self.long_only,
            "paper_only": self.paper_only,
            "effective_from": self.effective_from,
            "expires_at": self.expires_at,
            "quantization": self.quantization,
        }


def base_claim() -> FakeClaim:
    return FakeClaim(
        claim_id="claim-1",
        text="AAPL is trading below its recent fair-value estimate.",
        evidence_ids=("ev-1",),
    )


def base_evidence_item() -> FakeEvidenceItem:
    return FakeEvidenceItem(
        evidence_id="ev-1",
        source_uri="fixture://market/aapl",
        published_at=_dt(-3600),
        fetched_at=_dt(-1800),
        content_hash="b" * 64,
        excerpt="AAPL reference price 100.00 USD.",
        availability="available",
        trust_label="trusted",
    )


def base_evidence_pack() -> FakeEvidencePack:
    item = base_evidence_item()
    fields = {
        "run_id": "run-1",
        "snapshot_id": "snap-1",
        "items": (item,),
        "excluded_items": (),
        "cutoff": _dt(-600),
    }
    return FakeEvidencePack(**fields, pack_hash=sha256_hex(fields))


def base_policy() -> FakeRiskPolicy:
    return make_policy()


def base_portfolio() -> FakePortfolioSnapshot:
    return make_portfolio()


def base_proposal() -> FakeAdvisoryProposal:
    return make_proposal(
        policy=base_policy(),
        evidence=base_evidence_pack(),
        portfolio=base_portfolio(),
    )


def _coerce_claims(value: Any) -> tuple[FakeClaim, ...]:
    if value is None:
        return ()
    result = []
    for item in value:
        if isinstance(item, FakeClaim):
            result.append(item)
        elif isinstance(item, dict):
            result.append(FakeClaim(**item))
        else:
            raise TypeError(f"unsupported claim fixture {type(item)!r}")
    return tuple(result)


def _coerce_items(value: Any) -> tuple[FakeEvidenceItem, ...]:
    if value is None:
        return ()
    result = []
    for item in value:
        if isinstance(item, FakeEvidenceItem):
            result.append(item)
        elif isinstance(item, dict):
            result.append(FakeEvidenceItem(**item))
        else:
            raise TypeError(f"unsupported evidence fixture {type(item)!r}")
    return tuple(result)


def _coerce_positions(value: Any) -> tuple[FakePosition, ...]:
    if value is None:
        return ()
    result = []
    for item in value:
        if isinstance(item, FakePosition):
            result.append(item)
        elif isinstance(item, dict):
            result.append(
                FakePosition(
                    symbol=item["symbol"],
                    quantity=int(item["quantity"]),
                    mark_price=_dec(item["mark_price"]),
                )
            )
        else:
            symbol, quantity, mark_price = item
            result.append(
                FakePosition(
                    symbol=symbol,
                    quantity=int(quantity),
                    mark_price=_dec(mark_price),
                )
            )
    return tuple(result)


def make_policy(**overrides: Any) -> FakeRiskPolicy:
    effective_offset = overrides.pop("effective_from_offset", -86400)
    expires_offset = overrides.pop("expires_at_offset", 86400)
    policy_hash = overrides.pop("policy_hash", None)
    fields: dict[str, Any] = {
        "version": "test-policy-v1",
        "base_currency": "USD",
        "max_position_pct": Decimal("0.20"),
        "max_order_pct": Decimal("0.10"),
        "price_freshness_seconds": TEST_PRICE_FRESHNESS_SECONDS,
        "fee_bps": TEST_FEE_BPS,
        "slippage_bps": TEST_SLIPPAGE_BPS,
        "allowed_actions": frozenset({"BUY", "SELL", "HOLD"}),
        "long_only": True,
        "paper_only": True,
        "effective_from": _dt(effective_offset),
        "expires_at": _dt(expires_offset),
        "quantization": Decimal("0.01"),
    }
    fields.update(overrides)
    for key in ("max_position_pct", "max_order_pct", "fee_bps", "slippage_bps", "quantization"):
        fields[key] = _dec(fields[key])
    if fields["effective_from"] is None:
        fields["effective_from"] = _dt(effective_offset)
    if fields["expires_at"] is None:
        fields["expires_at"] = _dt(expires_offset)
    computed = sha256_hex(fields)
    return FakeRiskPolicy(policy_hash=policy_hash if policy_hash is not None else computed, **fields)


def make_portfolio(**overrides: Any) -> FakePortfolioSnapshot:
    as_of_offset = overrides.pop("as_of_offset", 0)
    values: dict[str, Any] = {
        "portfolio_id": "portfolio-1",
        "version": 1,
        "base_currency": "USD",
        "cash": Decimal("10000.00"),
        "positions": (),
        "as_of": _dt(as_of_offset),
    }
    values.update(overrides)
    values["cash"] = _dec(values["cash"])
    values["positions"] = _coerce_positions(values["positions"])
    return FakePortfolioSnapshot(**values)


def make_evidence(**overrides: Any) -> FakeEvidencePack:
    cutoff_offset = overrides.pop("cutoff_offset", -30)
    excluded_base = overrides.pop("excluded_base", False)
    pack_hash = overrides.pop("pack_hash", None)
    item_overrides = overrides.pop("item_overrides", None)
    item = base_evidence_item()
    if item_overrides:
        item = replace(item, **item_overrides)
    fields: dict[str, Any] = {
        "run_id": "run-1",
        "snapshot_id": "snap-1",
        "items": (item,),
        "excluded_items": (),
        "cutoff": _dt(cutoff_offset),
    }
    fields.update(overrides)
    fields["items"] = _coerce_items(fields["items"])
    fields["excluded_items"] = (
        (item,) if excluded_base else _coerce_items(fields["excluded_items"])
    )
    computed = sha256_hex(fields)
    return FakeEvidencePack(pack_hash=pack_hash if pack_hash is not None else computed, **fields)


def make_proposal(
    *,
    policy: FakeRiskPolicy | None = None,
    evidence: FakeEvidencePack | None = None,
    portfolio: FakePortfolioSnapshot | None = None,
    **overrides: Any,
) -> FakeAdvisoryProposal:
    portfolio = portfolio if portfolio is not None else make_portfolio()
    price_offset = overrides.pop("price_time_offset", -60)
    price_tz = overrides.pop("price_time_tz", 0)
    price_naive = overrides.pop("price_time_naive", False)
    expires_offset = overrides.pop("expires_at_offset", 3600)
    hash_mode = overrides.pop("proposal_hash_mode", None)
    policy_hash = overrides.pop("policy_hash", ZERO_HASH if policy is None else policy.policy_hash)
    evidence_hash = overrides.pop(
        "evidence_pack_hash", ZERO_HASH if evidence is None else evidence.pack_hash
    )
    fields: dict[str, Any] = {
        "proposal_id": "proposal-1",
        "run_id": "run-1",
        "ticker": "AAPL",
        "action": "BUY",
        "quantity": 1,
        "currency": "USD",
        "reference_price": "100.00",
        "price_time": _dt(price_offset, price_tz, price_naive),
        "claims": (base_claim(),),
        "evidence_pack_hash": evidence_hash,
        "portfolio_version": portfolio.version,
        "policy_hash": policy_hash,
        "expires_at": _dt(expires_offset),
        "policy_override": None,
        "bypass": None,
    }
    fields.update(overrides)
    fields["claims"] = _coerce_claims(fields["claims"])
    formal = {
        key: value
        for key, value in fields.items()
        if key not in {"proposal_hash", "policy_override", "bypass"}
    }
    computed = sha256_hex(formal)
    if hash_mode == "uppercase":
        digest = computed.upper()
    elif hash_mode == "short":
        digest = computed[:32]
    elif hash_mode == "zeros":
        digest = ZERO_HASH
    else:
        digest = fields.get("proposal_hash") or computed
        if not digest:
            digest = computed
    fields["proposal_hash"] = digest
    return FakeAdvisoryProposal(**fields)


def build_case(case: Any) -> CaseInput:
    params = case.params
    policy_params = params.get("policy", {})
    proposal_params = dict(params.get("proposal", {}))
    freshness = params.get("freshness")
    if freshness:
        policy_params = dict(policy_params or {})
        policy_params["price_freshness_seconds"] = freshness["seconds"]
        proposal_params["price_time_offset"] = -(
            int(freshness["seconds"]) + int(freshness.get("delta", 0))
        )
    policy = None if policy_params is None else make_policy(**policy_params)
    portfolio_params = params.get("portfolio", {})
    portfolio = make_portfolio(**portfolio_params)
    evidence_params = params.get("evidence", {})
    evidence = None if evidence_params is None else make_evidence(**evidence_params)
    forge_field = params.get("forge_field")
    if forge_field:
        base = make_proposal(policy=policy, evidence=evidence, portfolio=portfolio)
        forged = replace(base, **{forge_field: params.get("forge_value")})
        proposal = replace(forged, proposal_hash=base.proposal_hash)
    else:
        proposal = make_proposal(
            policy=policy, evidence=evidence, portfolio=portfolio, **proposal_params
        )
    return CaseInput(
        policy=policy,
        portfolio=portfolio,
        evidence=evidence,
        proposal=proposal,
    )


@dataclass(frozen=True)
class CaseInput:
    policy: FakeRiskPolicy | None
    portfolio: FakePortfolioSnapshot
    evidence: FakeEvidencePack | None
    proposal: FakeAdvisoryProposal


@dataclass(frozen=True)
class LedgerSnapshot:
    version: int
    cash: Decimal
    positions: dict[str, int]
    ledger_count: int
    verdict_count: int
    outbox_count: int
    outbox_rows: tuple[tuple[Any, ...], ...]


def ledger_snapshot(db_path: str | Path, portfolio_id: str = "portfolio-1") -> LedgerSnapshot:
    path = Path(db_path)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        portfolio = connection.execute(
            "SELECT version, cash FROM portfolios WHERE portfolio_id = ?",
            (portfolio_id,),
        ).fetchone()
        if portfolio is None:
            raise AssertionError(f"portfolio {portfolio_id!r} is missing from {path}")
        positions = {
            row["symbol"]: int(row["quantity"])
            for row in connection.execute(
                "SELECT symbol, quantity FROM positions "
                "WHERE portfolio_id = ? AND quantity > 0 ORDER BY symbol",
                (portfolio_id,),
            )
        }
        return LedgerSnapshot(
            version=int(portfolio["version"]),
            cash=Decimal(str(portfolio["cash"])),
            positions=positions,
            ledger_count=int(connection.execute("SELECT COUNT(*) FROM ledger_entries").fetchone()[0]),
            verdict_count=int(
                connection.execute("SELECT COUNT(*) FROM risk_verdicts").fetchone()[0]
            ),
            outbox_count=int(connection.execute("SELECT COUNT(*) FROM outbox_events").fetchone()[0]),
            outbox_rows=tuple(
                tuple(row)
                for row in connection.execute(
                    "SELECT event_id, run_id, sequence, payload_hash, prev_event_hash "
                    "FROM outbox_events ORDER BY run_id, sequence"
                )
            ),
        )
    finally:
        connection.close()


def raw_positions(db_path: str | Path, portfolio_id: str = "portfolio-1") -> dict[str, int]:
    connection = sqlite3.connect(Path(db_path))
    try:
        return {
            row[0]: int(row[1])
            for row in connection.execute(
                "SELECT symbol, quantity FROM positions WHERE portfolio_id = ? ORDER BY symbol",
                (portfolio_id,),
            )
        }
    finally:
        connection.close()


def table_exists(db_path: str | Path, table: str) -> bool:
    connection = sqlite3.connect(Path(db_path))
    try:
        row = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone()
    finally:
        connection.close()
    return row is not None


def dump_text_columns(db_path: str | Path) -> str:
    connection = sqlite3.connect(Path(db_path))
    chunks: list[str] = []
    try:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        for table in tables:
            for row in connection.execute(f"SELECT * FROM {table}"):
                chunks.append(" | ".join("" if value is None else str(value) for value in row))
    finally:
        connection.close()
    return "\n".join(chunks)


def reason_codes(verdict: Any) -> set[str]:
    result: set[str] = set()
    for reason in getattr(verdict, "reasons", ()):
        value = getattr(reason, "code", reason)
        result.add(str(getattr(value, "value", value)))
    return result


def status_of(verdict: Any) -> str:
    status = verdict.status
    return str(getattr(status, "value", status))


def assert_case(case: Any, harness: Any, case_input: CaseInput) -> Any:
    before = ledger_snapshot(harness.db_path, case_input.portfolio.portfolio_id)
    verdict = harness.gate.evaluate_and_commit(
        case_input.proposal, case_input.evidence, case_input.portfolio
    )
    after = ledger_snapshot(harness.db_path, case_input.portfolio.portfolio_id)
    codes = reason_codes(verdict)
    assert status_of(verdict) == case.expected_status, (
        f"{case.test_id}: expected status {case.expected_status!r}, "
        f"got {status_of(verdict)!r}; reasons={sorted(codes)}"
    )
    if case.expected_reason is not None:
        assert case.expected_reason in codes, (
            f"{case.test_id}: expected reason {case.expected_reason!r}, "
            f"got {sorted(codes)}"
        )
    assert after.ledger_count - before.ledger_count == case.ledger_delta, (
        f"{case.test_id}: ledger delta {after.ledger_count - before.ledger_count}, "
        f"expected {case.ledger_delta}"
    )
    assert after.version - before.version == case.version_delta, (
        f"{case.test_id}: version delta {after.version - before.version}, "
        f"expected {case.version_delta}"
    )
    if case.expected_cash is not None:
        assert after.cash == Decimal(case.expected_cash), (
            f"{case.test_id}: cash {after.cash}, expected {case.expected_cash}"
        )
    if case.expected_positions is not None:
        assert after.positions == case.expected_positions, (
            f"{case.test_id}: positions {after.positions}, "
            f"expected {case.expected_positions}"
        )
    if case.expected_raw_positions is not None:
        actual_raw = raw_positions(harness.db_path, case_input.portfolio.portfolio_id)
        assert actual_raw == case.expected_raw_positions, (
            f"{case.test_id}: raw positions {actual_raw}, "
            f"expected {case.expected_raw_positions}"
        )
    return verdict
