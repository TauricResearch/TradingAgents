import json
import os
from datetime import datetime

class ReportWriter:
    def __init__(self, config=None):
        self.config = config or {}
        self.reports_dir = self.config.get("results_dir", ".")

    def log_event(self, event_type, data):
        os.makedirs(self.reports_dir, exist_ok=True)
        event_logs_path = os.path.join(self.reports_dir, "event_logs.jsonl")
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "data": data
        }
        
        with open(event_logs_path, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

    def generate_daily_summary(self):
        return "Daily summary stub"
