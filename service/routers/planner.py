"""Planner integration: status check + sync holdings into TA positions.

    GET  /planner/status                    — is it configured + reachable?
    POST /planner/sync?dry_run=true|false   — pull holdings, upsert into positions

Sync semantics:
- For every (planner_holding ticker, planner account_name) pair, look up an
  existing TA position with the same ticker + account that's still open.
- If found and quantity differs: update shares + cost_basis_per_share.
- If not found: insert a new open position.
- We don't auto-close TA positions that the planner no longer has — let
  the user do that explicitly. (Safer; planner deletions can be transient
  e.g. if a SimpleFIN sync hiccups.)

``dry_run=true`` (default) returns the diff without applying it, so the UI
can show "would create N, update M, leave K untouched" before the user
commits.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from gui import storage
from service import planner_client

router = APIRouter(prefix="/planner", tags=["planner"])


class PlannerStatus(BaseModel):
    configured: bool
    url: Optional[str] = None
    reachable: bool
    error: Optional[str] = None


class SyncDiffEntry(BaseModel):
    ticker: str
    account: str
    action: str  # create | update | unchanged
    planner_shares: float
    planner_cost_basis: Optional[float] = None
    existing_shares: Optional[float] = None
    existing_cost_basis: Optional[float] = None


class SyncResult(BaseModel):
    dry_run: bool
    fetched_holdings: int
    accounts: int
    diff: List[SyncDiffEntry]
    applied: int = 0
    skipped: int = 0
    errors: List[str] = []


@router.get("/status", response_model=PlannerStatus)
def status() -> PlannerStatus:
    if not planner_client.is_configured():
        return PlannerStatus(
            configured=False,
            url=planner_client.planner_url(),
            reachable=False,
            error="Set PLANNER_API_URL and PLANNER_API_KEY in the API container's .env",
        )
    health = planner_client.healthcheck()
    return PlannerStatus(
        configured=True,
        url=planner_client.planner_url(),
        reachable=bool(health.get("ok")),
        error=health.get("error") or (health.get("body") if not health.get("ok") else None),
    )


def _account_label(account: Dict[str, Any]) -> str:
    """Build a human-readable account label that doubles as our position
    ``account`` field. Matches by-name when re-syncing."""
    name = account.get("name") or account.get("nickname") or f"account_{account.get('id')}"
    typ = account.get("account_type")
    if typ:
        return f"{name} ({typ})"
    return name


@router.post("/sync", response_model=SyncResult)
def sync(dry_run: bool = Query(True)) -> SyncResult:
    """Pull holdings from the planner and reconcile against our positions table."""
    if not planner_client.is_configured():
        raise HTTPException(
            status_code=412,
            detail="Planner not configured. Set PLANNER_API_URL and PLANNER_API_KEY.",
        )

    try:
        accounts = planner_client.list_accounts()
        holdings_resp = planner_client.list_holdings()
    except planner_client.PlannerClientError as e:
        raise HTTPException(status_code=502, detail=str(e))

    accounts_by_id: Dict[int, Dict[str, Any]] = {}
    for a in accounts:
        try:
            accounts_by_id[int(a["id"])] = a
        except (KeyError, ValueError, TypeError):
            continue

    holdings = holdings_resp.get("holdings") or []

    # Index existing TA open positions by (ticker, account-string).
    existing = storage.list_positions(include_closed=False)
    existing_by_key: Dict[tuple, Dict[str, Any]] = {}
    for p in existing:
        key = ((p["ticker"] or "").upper(), p.get("account") or "")
        existing_by_key[key] = p

    diff: List[SyncDiffEntry] = []
    actions: List[Dict[str, Any]] = []  # what to do if not dry_run

    for h in holdings:
        ticker = (h.get("symbol") or "").upper()
        if not ticker:
            continue
        qty = float(h.get("quantity") or 0)
        cost = h.get("avg_cost_basis")
        cost_f = float(cost) if cost is not None else None
        if qty <= 0:
            continue
        account_id = h.get("account_id")
        account = accounts_by_id.get(int(account_id)) if account_id is not None else None
        account_label = _account_label(account or {"id": account_id})

        key = (ticker, account_label)
        existing_p = existing_by_key.get(key)

        # Cost basis fallback: if planner doesn't have one, use current price
        # so the position has *some* basis and unrealized P&L can be 0 at
        # snapshot time. We'd rather have an obvious "0% return" position
        # than fail the create entirely.
        effective_cost = cost_f if cost_f else float(h.get("current_price") or 0)

        if existing_p is None:
            diff.append(SyncDiffEntry(
                ticker=ticker, account=account_label, action="create",
                planner_shares=qty, planner_cost_basis=cost_f,
            ))
            actions.append({
                "kind": "create", "ticker": ticker, "account": account_label,
                "shares": qty, "cost_basis": effective_cost,
            })
        else:
            same_qty = abs(existing_p["shares"] - qty) < 1e-9
            same_cost = (
                cost_f is None
                or abs((existing_p.get("cost_basis_per_share") or 0) - cost_f) < 1e-6
            )
            if same_qty and same_cost:
                diff.append(SyncDiffEntry(
                    ticker=ticker, account=account_label, action="unchanged",
                    planner_shares=qty, planner_cost_basis=cost_f,
                    existing_shares=existing_p["shares"],
                    existing_cost_basis=existing_p.get("cost_basis_per_share"),
                ))
            else:
                diff.append(SyncDiffEntry(
                    ticker=ticker, account=account_label, action="update",
                    planner_shares=qty, planner_cost_basis=cost_f,
                    existing_shares=existing_p["shares"],
                    existing_cost_basis=existing_p.get("cost_basis_per_share"),
                ))
                actions.append({
                    "kind": "update", "id": existing_p["id"],
                    "shares": qty,
                    "cost_basis": cost_f if cost_f else existing_p.get("cost_basis_per_share"),
                })

    applied = 0
    errors: List[str] = []
    if not dry_run:
        for a in actions:
            try:
                if a["kind"] == "create":
                    storage.add_position(
                        ticker=a["ticker"], shares=a["shares"],
                        cost_basis_per_share=a["cost_basis"] or 1e-9,
                        account=a["account"],
                        notes="synced from planner",
                    )
                elif a["kind"] == "update":
                    storage.update_position(
                        a["id"],
                        shares=a["shares"],
                        cost_basis_per_share=a["cost_basis"],
                    )
                applied += 1
            except Exception as e:
                errors.append(f"{a}: {e}")

    return SyncResult(
        dry_run=dry_run,
        fetched_holdings=len(holdings),
        accounts=len(accounts_by_id),
        diff=diff,
        applied=applied,
        skipped=sum(1 for d in diff if d.action == "unchanged"),
        errors=errors,
    )
