import json
import os

class PortfolioMemory:
    def __init__(self, config=None):
        self.config = config or {}
        self.balance = 10000.0
        self.past_decisions = []
        self.results_dir = self.config.get("results_dir", ".")
        self.memory_file = os.path.join(self.results_dir, "portfolio_memory.json")
        self.load_memory()

    def load_memory(self):
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, "r") as f:
                    data = json.load(f)
                    self.balance = data.get("balance", 10000.0)
                    self.past_decisions = data.get("past_decisions", [])
            except Exception:
                pass
        return {
            "balance": self.balance,
            "past_decisions": self.past_decisions
        }

    def save_snapshot(self, snapshot):
        pass

    def update_portfolio(self, decision):
        if isinstance(decision, dict):
            self.past_decisions.append(decision)
        else:
            self.past_decisions.append({"decision": str(decision)})
            
        os.makedirs(self.results_dir, exist_ok=True)
        try:
            with open(self.memory_file, "w") as f:
                json.dump({
                    "balance": self.balance,
                    "past_decisions": self.past_decisions
                }, f, indent=2)
        except Exception:
            pass

    def review_performance(self):
        return {}

class RiskGuard:
    def __init__(self, config=None):
        self.config = config or {}

    def assess_risk(self, ticker, portfolio):
        return {"risk_score": 0.1, "status": "APPROVED", "safe": True}
