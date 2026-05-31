from dataclasses import dataclass, field
from threading import Lock
from uuid import uuid4


@dataclass
class RunState:
    active_run_id: str | None = None
    lock: Lock = field(default_factory=Lock)

    def start(self) -> str:
        with self.lock:
            if self.active_run_id is not None:
                raise RuntimeError("Another analysis run is already active.")
            self.active_run_id = str(uuid4())
            return self.active_run_id

    def finish(self, run_id: str) -> None:
        with self.lock:
            if self.active_run_id == run_id:
                self.active_run_id = None


run_state = RunState()
