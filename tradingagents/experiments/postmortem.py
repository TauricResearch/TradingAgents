from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class StrategyRuleStore:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()

    def load(self) -> list[str]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8")).get("rules", [])

    def write(self, rules: list[str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"rules": rules}, indent=2) + "\n", encoding="utf-8"
        )

    def as_prompt(self) -> str:
        rules = self.load()
        if not rules:
            return ""
        return "Strategy rules from prior outcomes:\n" + "\n".join(f"- {rule}" for rule in rules)


class PostMortemRunner:
    def __init__(self, llm: Any, memory, rule_store: StrategyRuleStore):
        self.llm = llm
        self.memory = memory
        self.rule_store = rule_store

    def run(self) -> list[str]:
        entries = self.memory.resolved_entries()
        if not entries:
            return []
        prompt = (
            "Review these resolved trading situations. Return at most five concise "
            "rules of thumb, one per line, without bullets or numbering.\n\n"
            + "\n".join(
                f"{item['trade_date']} {item['ticker']} {item['rating']} "
                f"return={item['raw_return']:+.1%}: {item['reflection']}"
                for item in entries
            )
        )
        response = self.llm.invoke(prompt)
        rules = [line.strip(" -\t") for line in response.content.splitlines() if line.strip()]
        self.rule_store.write(rules[:5])
        return rules[:5]
