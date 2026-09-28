"""The CLI's stream loop must bind run_config so a graph built later in the
same process cannot flip the running graph's vendors (#1369 — the isolation
96daaf1 added for propagate, missing on the programmatic streaming path).

Behavioural: the probe graph's stream() executes inside the with-block, so it
records the config the loop actually reads at stream time.
"""

from tests.test_cli_decision_log import _run_cli
from tradingagents.dataflows.config import get_config, set_config


class _ProbeGraph:
    """Fake graph that records the config its stream() reads.

    Carries the same surface run_analysis touches as the decision-log fakes
    (create_run_state / process_signal / no checkpointing).
    """

    def __init__(self):
        self.config = {"data_vendors": {"stock": "eodhd"}}
        self.seen = None
        self.graph = self
        self.propagator = self

    def get_graph_args(self, **kwargs):
        return {}

    def begin_checkpoint(self, *a, **k):
        return None

    def checkpoint_input(self, state):
        return state

    def clear_checkpoint_on_success(self, *a, **k):
        pass

    def record_decision(self, ticker, trade_date, final_state):
        pass

    def end_checkpoint(self):
        pass

    def create_run_state(self, ticker, trade_date, asset_type="stock", portfolio=None):
        return {"messages": [], "company_of_interest": ticker}

    def process_signal(self, text):
        return None

    def stream(self, *args, **kwargs):
        self.seen = dict(get_config())
        yield {"messages": []}


def test_the_cli_stream_reads_the_graphs_own_config(monkeypatch, tmp_path):
    probe = _ProbeGraph()

    # A second graph built after this one rewrites the process-wide config —
    # its __init__ calls set_config on the global dict (#1369's scenario).
    set_config({"data_vendors": {"stock": "yahoo"}})

    _run_cli(monkeypatch, tmp_path, probe)

    assert probe.seen["data_vendors"]["stock"] == "eodhd"


def test_a_bare_stream_outside_the_cli_reads_the_global_config():
    """Counterfactual: with no run_config bound, a bare stream would read the
    process-wide dict — this is the hazard the CLI binding protects against."""
    set_config({"data_vendors": {"stock": "yahoo"}})
    assert get_config()["data_vendors"]["stock"] == "yahoo"
