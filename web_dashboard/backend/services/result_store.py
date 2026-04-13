from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


CONTRACT_VERSION = "v1alpha1"


class ResultStore:
    """Storage boundary for persisted task state and portfolio results."""

    def __init__(self, task_status_dir: Path, portfolio_gateway):
        self.task_status_dir = task_status_dir
        self.result_contract_dir = self.task_status_dir / "results"
        self.legacy_result_contract_dir = self.task_status_dir / "result_contracts"
        self.portfolio_gateway = portfolio_gateway

    def restore_task_results(self) -> dict[str, dict]:
        restored: dict[str, dict] = {}
        self.task_status_dir.mkdir(parents=True, exist_ok=True)
        for file_path in self.task_status_dir.glob("*.json"):
            try:
                data = json.loads(file_path.read_text())
            except Exception:
                continue
            task_id = data.get("task_id")
            if task_id:
                restored[task_id] = data
        return restored

    def save_task_status(self, task_id: str, data: dict) -> None:
        self.task_status_dir.mkdir(parents=True, exist_ok=True)
        (self.task_status_dir / f"{task_id}.json").write_text(json.dumps(data, ensure_ascii=False))

    def save_result_contract(self, task_id: str, contract: dict) -> str:
        target_dir = self.result_contract_dir / task_id
        target_dir.mkdir(parents=True, exist_ok=True)
        payload = dict(contract)
        payload.setdefault("task_id", task_id)
        payload.setdefault("contract_version", CONTRACT_VERSION)
        file_path = target_dir / "result.v1alpha1.json"
        file_path.write_text(json.dumps(payload, ensure_ascii=False))
        return file_path.relative_to(self.task_status_dir).as_posix()

    def load_result_contract(
        self,
        *,
        result_ref: str | None = None,
        task_id: str | None = None,
    ) -> dict | None:
        candidates: list[Path] = []
        if result_ref:
            candidates.append(self.task_status_dir / result_ref)
        if task_id:
            candidates.append(self.result_contract_dir / task_id / "result.v1alpha1.json")
            candidates.append(self.legacy_result_contract_dir / f"{task_id}.json")
        for path in candidates:
            if not path.exists():
                continue
            try:
                return json.loads(path.read_text())
            except Exception:
                continue
        return None

    def delete_task_status(self, task_id: str) -> None:
        (self.task_status_dir / f"{task_id}.json").unlink(missing_ok=True)

    def get_watchlist(self) -> list:
        return self.portfolio_gateway.get_watchlist()

    def get_accounts(self) -> dict:
        return self.portfolio_gateway.get_accounts()

    async def get_positions(self, account: Optional[str] = None) -> list:
        return await self.portfolio_gateway.get_positions(account)

    def get_recommendations(self, date: Optional[str] = None, limit: int = 50, offset: int = 0) -> dict:
        return self.portfolio_gateway.get_recommendations(date, limit, offset)

    def get_recommendation(self, date: str, ticker: str) -> Optional[dict]:
        return self.portfolio_gateway.get_recommendation(date, ticker)

    def save_recommendation(self, date: str, ticker: str, data: dict) -> None:
        self.portfolio_gateway.save_recommendation(date, ticker, data)
