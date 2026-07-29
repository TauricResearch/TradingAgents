#!/usr/bin/env python3
"""Fit a Gaussian Hidden Markov Model to market returns and emit JSON results.

Bridge contract (JSON lines, same as analyze_stream.py):
  Receives JSON on stdin: {"ticker": "AAPL", "returns": [...], "n_states": 3, "n_iter": 1000}
  Emits JSON result on stdout: {"ticker", "transition_matrix", "state_means",
    "state_vols", "labeled_states", "log_likelihood", "converged"}

Multi-start fitting: runs from multiple random seeds, keeps the model with
the highest log likelihood. Baum-Welch converges to local maxima — single
initialization frequently produces suboptimal regime assignments.

After fitting, states are sorted by mean return:
  0 = bull (highest mean), 1 = sideways, 2 = bear (lowest)

Edge cases:
  - <2 distinct return values → error (not enough variation for HMM)
  - All identical returns → error
  - Fewer data points than n_states → error
"""
import json
import sys
import traceback
from typing import Any

import numpy as np
from hmmlearn import hmm


def fit_market_hmm(
    returns: list[float],
    n_states: int = 3,
    n_iter: int = 1000,
    n_starts: int = 5,
) -> dict[str, Any]:
    """Fit a Gaussian HMM to market returns with multi-start optimization.

    Args:
        returns: List of daily log returns (as decimals, e.g. 0.01 = 1%).
        n_states: Number of hidden states (default: 3 = bull/sideways/bear).
        n_iter: Maximum Baum-Welch iterations per start.
        n_starts: Number of random initializations (best kept).

    Returns:
        Dictionary with transition_matrix, state_means, state_vols,
        labeled_states, log_likelihood, converged.

    Raises:
        ValueError: If returns array is invalid for HMM fitting.
    """
    arr = np.array(returns, dtype=np.float64)

    if len(arr) < n_states + 1:
        raise ValueError(
            f"Need at least {n_states + 1} data points, got {len(arr)}"
        )

    unique_vals = np.unique(arr)
    if len(unique_vals) < 2:
        raise ValueError(
            "Returns have zero variation — cannot fit HMM"
        )

    X = arr.reshape(-1, 1)

    best_model: hmm.GaussianHMM | None = None
    best_score = -np.inf

    for start_idx in range(n_starts):
        model = hmm.GaussianHMM(
            n_components=n_states,
            covariance_type="full",
            n_iter=n_iter,
            random_state=42 + start_idx,
            init_params="stmc",  # skip initial state distribution
        )

        try:
            model.fit(X)
            score = float(model.score(X))
            if score > best_score:
                best_score = score
                best_model = model
        except Exception:
            # Individual start failure — skip and try next
            continue

    if best_model is None:
        raise RuntimeError(
            f"All {n_starts} starts failed to converge"
        )

    # Predict hidden states for each day
    hidden_states = best_model.predict(X)

    # Sort states by mean return: 0=bull (highest), 2=bear (lowest)
    state_means: dict[int, float] = {}
    for s in range(n_states):
        mask = hidden_states == s
        if mask.any():
            state_means[s] = float(np.mean(arr[mask]))
        else:
            state_means[s] = 0.0

    sorted_states = sorted(state_means, key=state_means.get, reverse=True)
    state_map = {old: new for new, old in enumerate(sorted_states)}
    labeled = np.array([state_map[s] for s in hidden_states])

    # Compute per-state statistics after labeling
    means_out = []
    vols_out = []
    for i in range(n_states):
        mask = labeled == i
        if mask.any():
            means_out.append(float(np.mean(arr[mask])))
            vols_out.append(float(np.std(arr[mask], ddof=1) if mask.sum() > 1 else 0.0))
        else:
            means_out.append(0.0)
            vols_out.append(0.0)

    # Permute the transition matrix into the relabelled (bull/side/bear)
    # ordering. sorted_states[new_idx] = old_idx, so indexing both axes by
    # it reorders rows and columns together.
    perm = sorted_states
    transmat = best_model.transmat_[np.ix_(perm, perm)].tolist()

    return {
        "transition_matrix": transmat,
        "state_means": means_out,
        "state_vols": vols_out,
        "labeled_states": labeled.tolist(),
        "log_likelihood": best_score,
        "converged": bool(best_model.monitor_.converged),
    }


def main() -> None:
    """Read JSON from stdin, fit HMM, emit JSON to stdout."""
    raw = sys.stdin.read()
    if not raw.strip():
        print(json.dumps({"error": "No input received"}))
        sys.exit(1)

    try:
        req = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON: {e}"}))
        sys.exit(1)

    ticker = req.get("ticker", "UNKNOWN")
    returns = req.get("returns", [])
    n_states = req.get("n_states", 3)
    n_iter = req.get("n_iter", 1000)
    n_starts = req.get("n_starts", 5)

    try:
        result = fit_market_hmm(returns, n_states, n_iter, n_starts)
        result["ticker"] = ticker
        print(json.dumps(result))
    except Exception as e:
        print(json.dumps({
            "ticker": ticker,
            "error": str(e),
        }))
        sys.exit(1)


if __name__ == "__main__":
    main()