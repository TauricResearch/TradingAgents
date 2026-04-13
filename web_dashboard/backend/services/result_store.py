from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


class ResultStore:
    """Storage boundary for persisted task state and portfolio results."""

    def __init__(self, task_status_dir: Path, portfolio_gateway):
        self.task_status_dir = task_status_dir
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
