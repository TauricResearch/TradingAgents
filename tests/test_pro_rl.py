"""RL layer: features, offline env, tabular policy, trainer, advisor."""

import pytest

from tests.pro_fakes import make_bars
from tradingagents.pro.rl import (
    ACTIONS,
    MIN_BARS,
    QTablePolicy,
    RLAdvisor,
    build_transitions,
    evaluate_policy,
    state_from_bars,
    train_q_policy,
)


class TestFeatures:
    def test_state_is_deterministic(self):
        bars = make_bars(n=120)
        assert state_from_bars(bars) == state_from_bars(bars)

    def test_rising_series_maps_to_up_trend_bucket(self):
        state = state_from_bars(make_bars(n=120))
        assert state.trend_bucket >= 3  # up or strong-up
        assert 0 <= state.vol_bucket <= 2
        assert "|t" in state.key() and "|z" in state.key()

    def test_minimum_history_enforced(self):
        with pytest.raises(ValueError, match=str(MIN_BARS)):
            state_from_bars(make_bars(n=30))


class TestOfflineEnv:
    def test_full_feedback_rewards_are_consistent(self):
        bars = make_bars(n=200)
        transitions = build_transitions(bars, horizon=5, window=120, cost_bps=0)
        t = transitions[0]
        assert set(t.rewards) == set(ACTIONS)
        # rising market: BUY reward positive, SELL is its negation, HOLD zero
        assert t.rewards["BUY"] > 0
        assert t.rewards["SELL"] == pytest.approx(-t.rewards["BUY"])
        assert t.rewards["HOLD"] == 0.0

    def test_costs_penalize_directional_actions_only(self):
        bars = make_bars(n=200)
        free = build_transitions(bars, horizon=5, window=120, cost_bps=0)
        costed = build_transitions(bars, horizon=5, window=120, cost_bps=10)
        assert costed[0].rewards["BUY"] < free[0].rewards["BUY"]
        assert costed[0].rewards["HOLD"] == 0.0

    def test_transition_count_and_validation(self):
        bars = make_bars(n=200)
        transitions = build_transitions(bars, horizon=5, window=120)
        assert len(transitions) == 200 - 120 + 1 - 5
        with pytest.raises(ValueError, match="too short"):
            build_transitions(make_bars(n=100), horizon=5, window=120)


class TestPolicy:
    def test_update_moves_toward_reward(self):
        policy = QTablePolicy(alpha=0.5)
        state = state_from_bars(make_bars(n=120))
        policy.update(state, "BUY", 1.0)
        assert policy.q_values(state)["BUY"] == pytest.approx(0.5)
        policy.update(state, "BUY", 1.0)
        assert policy.q_values(state)["BUY"] == pytest.approx(0.75)
        assert policy.visits(state) == 2

    def test_best_returns_action_and_edge(self):
        policy = QTablePolicy(alpha=1.0)
        state = state_from_bars(make_bars(n=120))
        policy.update(state, "BUY", 0.9)
        policy.update(state, "SELL", -0.9)
        action, edge = policy.best(state)
        assert action == "BUY"
        assert edge == pytest.approx(0.9)  # over HOLD at 0.0

    def test_persistence_round_trip(self, tmp_path):
        policy, _ = train_q_policy(make_bars(n=250), eval_fraction=0)
        path = tmp_path / "policy.json"
        policy.save(path)
        loaded = QTablePolicy.load(path)
        state = state_from_bars(make_bars(n=250)[-120:])
        assert loaded.q_values(state) == policy.q_values(state)
        assert loaded.visits(state) == policy.visits(state)

    def test_hyperparameter_validation(self):
        with pytest.raises(ValueError):
            QTablePolicy(alpha=0)
        with pytest.raises(ValueError):
            QTablePolicy(gamma=1.0)


class TestTrainer:
    def test_learns_buy_in_rising_market(self):
        policy, report = train_q_policy(make_bars(n=300), eval_fraction=0.25, seed=3)
        assert report.transitions > 0 and report.states_seen >= 1
        state = state_from_bars(make_bars(n=300)[:220][-120:])
        action, edge = policy.best(state)
        assert action == "BUY" and edge > 0

    def test_training_is_deterministic_under_seed(self):
        a, _ = train_q_policy(make_bars(n=300), seed=11)
        b, _ = train_q_policy(make_bars(n=300), seed=11)
        state = state_from_bars(make_bars(n=300)[-120:])
        assert a.q_values(state) == b.q_values(state)

    def test_eval_uses_phase7_objectives(self):
        _, report = train_q_policy(make_bars(n=400), eval_fraction=0.4, seed=3)
        assert report.eval_report is not None
        # rising market + learned BUY => positive out-of-sample return
        assert report.eval_report.total_return > 0
        assert report.eval_report.max_drawdown >= 0
        assert report.baseline_hold_return is not None

    def test_evaluate_policy_standalone(self):
        policy, _ = train_q_policy(make_bars(n=300), eval_fraction=0, seed=3)
        report = evaluate_policy(policy, make_bars(n=200))
        assert report.total_return != 0 or report.n_trades == 0


class TestAdvisor:
    def test_trained_state_yields_advice(self):
        policy, _ = train_q_policy(make_bars(n=300), eval_fraction=0, seed=3)
        advisor = RLAdvisor(policy, min_visits=1)
        readings = advisor.advise(make_bars(n=300)[-120:])
        assert {"RL_Q_BUY", "RL_Q_SELL", "RL_Q_HOLD",
                "RL_POLICY_EDGE", "RL_STATE_VISITS"} <= set(readings)
        assert readings["RL_Q_BUY"].source == "rl_advisor"
        assert readings["RL_Q_BUY"].value > readings["RL_Q_SELL"].value

    def test_undertrained_state_yields_nothing(self):
        advisor = RLAdvisor(QTablePolicy(), min_visits=10)
        assert advisor.advise(make_bars(n=120)) == {}

    def test_short_history_yields_nothing(self):
        policy, _ = train_q_policy(make_bars(n=300), eval_fraction=0)
        assert RLAdvisor(policy, min_visits=1).advise(make_bars(n=30)) == {}
