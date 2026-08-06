"""Pre-registered, dependence-aware diagnostics for formal portfolio returns."""

from __future__ import annotations

import math
import random
import statistics
from itertools import combinations

from tradingagents.research_protocol import (
    GLOBAL_EVENT_V2_PROTOCOL,
    GLOBAL_EVENT_V2_PROTOCOL_ID,
    content_id,
)


def newey_west_mean_test(returns: list[float], lags: int | None = None) -> dict:
    """HAC standard error and t-statistic for a daily mean return."""
    values = [float(value) for value in returns]
    n = len(values)
    if n < 3:
        return {"observations": n, "lags": None, "mean": None, "standard_error": None,
                "t_statistic": None}
    lags = lags if lags is not None else max(1, int(4 * (n / 100) ** (2 / 9)))
    lags = min(max(0, lags), n - 1)
    mean = statistics.fmean(values)
    centered = [value - mean for value in values]
    long_run_variance = sum(value * value for value in centered) / n
    for lag in range(1, lags + 1):
        covariance = sum(centered[index] * centered[index - lag]
                         for index in range(lag, n)) / n
        long_run_variance += 2 * (1 - lag / (lags + 1)) * covariance
    standard_error = math.sqrt(max(0.0, long_run_variance) / n)
    return {
        "observations": n, "lags": lags, "mean": mean,
        "standard_error": standard_error,
        "t_statistic": mean / standard_error if standard_error > 0 else None,
    }


def moving_block_bootstrap_mean(
    returns: list[float], *, block_length: int | None = None,
    trials: int = 2000, seed: int = 1729,
) -> dict:
    """Deterministic moving-block bootstrap confidence interval for the mean."""
    values = [float(value) for value in returns]
    n = len(values)
    if n < 2 or trials < 1:
        return {"observations": n, "trials": trials, "confidence_interval_95": None}
    block_length = block_length or max(2, round(n ** (1 / 3)))
    block_length = min(max(1, block_length), n)
    blocks = [values[index:index + block_length] for index in range(n - block_length + 1)]
    rng = random.Random(seed)
    means = []
    for _ in range(trials):
        sample = []
        while len(sample) < n:
            sample.extend(rng.choice(blocks))
        means.append(statistics.fmean(sample[:n]))
    ordered = sorted(means)
    return {
        "observations": n, "trials": trials, "seed": seed,
        "block_length": block_length,
        "confidence_interval_95": [
            ordered[int(0.025 * (trials - 1))], ordered[int(0.975 * (trials - 1))]
        ],
    }


def _normal_cdf(value: float) -> float:
    return 0.5 * (1 + math.erf(value / math.sqrt(2)))


def probabilistic_sharpe_ratio(
    returns: list[float], *, benchmark_sharpe: float = 0.0,
    periods_per_year: int = 252,
) -> dict:
    """Probability the observed annualized Sharpe exceeds a benchmark Sharpe."""
    values = [float(value) for value in returns]
    n = len(values)
    if n < 3 or statistics.stdev(values) == 0:
        return {"observations": n, "sharpe": None, "probability": None}
    mean = statistics.fmean(values)
    std = statistics.stdev(values)
    daily_sharpe = mean / std
    centered = [(value - mean) / std for value in values]
    skew = sum(value ** 3 for value in centered) / n
    kurtosis = sum(value ** 4 for value in centered) / n
    benchmark_daily = benchmark_sharpe / math.sqrt(periods_per_year)
    denominator = math.sqrt(
        max(1e-12, (1 - skew * daily_sharpe + ((kurtosis - 1) / 4) * daily_sharpe ** 2)
                    / (n - 1))
    )
    probability = _normal_cdf((daily_sharpe - benchmark_daily) / denominator)
    return {
        "observations": n, "sharpe": daily_sharpe * math.sqrt(periods_per_year),
        "benchmark_sharpe": benchmark_sharpe, "probability": probability,
        "skew": skew, "kurtosis": kurtosis,
    }


def deflated_sharpe_ratio(
    returns: list[float], *, trial_sharpes: list[float], periods_per_year: int = 252,
) -> dict:
    """Deflate significance using the observed distribution of tried strategies."""
    if not trial_sharpes:
        raise ValueError("trial_sharpes must record every tried strategy")
    if len(trial_sharpes) == 1:
        benchmark = trial_sharpes[0]
    else:
        from statistics import NormalDist
        mean = statistics.fmean(trial_sharpes)
        std = statistics.stdev(trial_sharpes)
        trials = len(trial_sharpes)
        euler_gamma = 0.5772156649015329
        normal = NormalDist()
        expected_max_z = (
            (1 - euler_gamma) * normal.inv_cdf(1 - 1 / trials)
            + euler_gamma * normal.inv_cdf(1 - 1 / (trials * math.e))
        )
        benchmark = mean + std * expected_max_z
    result = probabilistic_sharpe_ratio(
        returns, benchmark_sharpe=benchmark, periods_per_year=periods_per_year
    )
    return {**result, "trials": len(trial_sharpes), "deflated_benchmark_sharpe": benchmark}


def probability_of_backtest_overfitting(
    strategy_returns: dict[str, list[float]], *, partitions: int = 10,
) -> dict:
    """CSCV estimate of how often the in-sample winner is below median out of sample."""
    if len(strategy_returns) < 2:
        raise ValueError("PBO requires at least two registered strategies")
    names = sorted(strategy_returns)
    lengths = {len(strategy_returns[name]) for name in names}
    if len(lengths) != 1:
        raise ValueError("all strategy return series must be synchronized")
    n = lengths.pop()
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        for name in names
        for value in strategy_returns[name]
    ):
        raise ValueError("PBO returns must be finite numeric values")
    partitions = min(partitions, n)
    if partitions < 4:
        return {"observations": n, "partitions": partitions, "combinations": 0,
                "probability_overfit": None}
    if partitions % 2:
        partitions -= 1
    boundaries = [round(index * n / partitions) for index in range(partitions + 1)]
    blocks = [list(range(boundaries[index], boundaries[index + 1]))
              for index in range(partitions)]

    def sharpe(name: str, indices: list[int]) -> float:
        values = [float(strategy_returns[name][index]) for index in indices]
        std = statistics.stdev(values) if len(values) >= 2 else 0.0
        mean = statistics.fmean(values)
        if std > 0:
            return mean / std
        return math.inf if mean > 0 else -math.inf if mean < 0 else 0.0

    logits = []
    tied_train_combinations = 0
    half = partitions // 2
    # Complement pairs are symmetric; keep only combinations containing block 0.
    for train_blocks in combinations(range(partitions), half):
        if 0 not in train_blocks:
            continue
        train_set = set(train_blocks)
        train = [index for block in train_blocks for index in blocks[block]]
        test = [index for block in range(partitions) if block not in train_set
                for index in blocks[block]]
        train_scores = {name: sharpe(name, train) for name in names}
        best = max(train_scores.values())
        winners = [name for name in names if train_scores[name] == best]
        # An arbitrary lexicographic tie-break can make an indistinguishable
        # family look perfectly stable. Formal use therefore treats an
        # in-sample tie as an unresolved CSCV combination, not evidence against
        # overfitting.
        if len(winners) != 1:
            tied_train_combinations += 1
            continue
        winner = winners[0]
        test_scores = {name: sharpe(name, test) for name in names}
        winner_score = test_scores[winner]
        lower = sum(score < winner_score for score in test_scores.values())
        equal = sum(score == winner_score for score in test_scores.values())
        percentile = (lower + equal / 2.0) / len(names)
        logits.append(math.log(percentile / (1 - percentile)))
    return {
        "observations": n, "partitions": partitions, "combinations": len(logits),
        "tied_train_combinations": tied_train_combinations,
        "probability_overfit": (
            sum(value <= 0 for value in logits) / len(logits) if logits else None
        ),
        "logit_rank_values": logits,
    }


def factor_attribution(
    portfolio_returns: list[float], factors: dict[str, list[float]],
    *, periods_per_year: int = 252,
) -> dict:
    """OLS attribution prepared for market, QQQ, sector, and academic factors."""
    if not factors:
        raise ValueError("at least one factor series is required")
    try:
        import numpy as np
    except ImportError as exc:  # pandas normally supplies numpy
        raise RuntimeError("factor attribution requires numpy") from exc
    names = sorted(factors)
    n = len(portfolio_returns)
    if n < len(names) + 2 or any(len(factors[name]) != n for name in names):
        return {"observations": n, "alpha_annualized": None, "betas": {}}
    y = np.asarray(portfolio_returns, dtype=float)
    columns = [np.ones(n), *(np.asarray(factors[name], dtype=float) for name in names)]
    x = np.column_stack(columns)
    coefficients, _, _, _ = np.linalg.lstsq(x, y, rcond=None)
    residuals = y - x @ coefficients
    return {
        "observations": n,
        "alpha_annualized": float(coefficients[0] * periods_per_year),
        "betas": {name: float(coefficients[index + 1]) for index, name in enumerate(names)},
        "residual_volatility_annualized": float(
            np.std(residuals, ddof=len(names) + 1) * math.sqrt(periods_per_year)
        ),
    }


def formal_return_diagnostics(
    returns: list[float], *, tested_variations: int,
    bootstrap_trials: int = 2000, trial_sharpes: list[float] | None = None,
) -> dict:
    """Legacy exploratory diagnostics that can never support formal promotion.

    This API intentionally remains available for notebooks and historical
    reports.  Its caller-selected window, bootstrap count, and variation count
    are incompatible with the locked V2 confirmatory analysis; production
    promotion code must use :func:`formal_primary_readout` and
    :func:`formal_secondary_readout` instead.
    """
    if tested_variations < 1:
        raise ValueError("tested_variations must be >= 1")
    # Bonferroni-adjusted confidence threshold is intentionally explicit. More
    # sophisticated deflated-Sharpe/PBO outputs can be added only by a protocol revision.
    return {
        "status": "exploratory-legacy-not-for-promotion",
        "newey_west": newey_west_mean_test(returns),
        "moving_block_bootstrap": moving_block_bootstrap_mean(
            returns, trials=bootstrap_trials
        ),
        "probabilistic_sharpe": probabilistic_sharpe_ratio(returns),
        "deflated_sharpe": (
            deflated_sharpe_ratio(returns, trial_sharpes=trial_sharpes)
            if trial_sharpes else None
        ),
        "tested_variations": tested_variations,
        "familywise_alpha_bonferroni": 0.05 / tested_variations,
    }


def _one_sided_positive_mean_p_value(hac: dict) -> float:
    """Return a coherent one-sided p-value, including degenerate samples."""
    mean = float(hac["mean"])
    standard_error = float(hac["standard_error"])
    if standard_error > 0:
        return 1.0 - _normal_cdf(float(hac["t_statistic"]))
    if mean > 0:
        return 0.0
    if mean < 0:
        return 1.0
    return 0.5


def holm_bonferroni(p_values: dict[str, float], *, alpha: float = 0.05) -> dict:
    """Return deterministic Holm-adjusted p-values and step-down decisions."""
    if not p_values:
        raise ValueError("Holm correction requires at least one hypothesis")
    if not 0 < alpha < 1:
        raise ValueError("Holm alpha must be between zero and one")
    ordered = sorted((float(value), name) for name, value in p_values.items())
    if any(not math.isfinite(value) or not 0 <= value <= 1 for value, _ in ordered):
        raise ValueError("Holm p-values must be finite and between zero and one")
    total = len(ordered)
    adjusted = {}
    running = 0.0
    rejection_open = True
    rejected = {}
    for index, (p_value, name) in enumerate(ordered):
        multiplier = total - index
        running = max(running, min(1.0, multiplier * p_value))
        adjusted[name] = running
        threshold = alpha / multiplier
        rejected[name] = rejection_open and p_value <= threshold
        if p_value > threshold:
            rejection_open = False
    return {
        "method": "Holm",
        "familywise_alpha": alpha,
        "adjusted_p_values": adjusted,
        "rejected": rejected,
    }


def formal_primary_readout(
    champion_returns: list[float],
    market_only_returns: list[float],
    *,
    successful_decision_sets: int,
    synchronized_marks: int,
) -> dict:
    """Execute the immutable V2 confirmatory readout with no caller-tuned knobs."""
    analysis = GLOBAL_EVENT_V2_PROTOCOL["analysis"]
    required = int(analysis["trial_clock"]["holding_intervals"])
    if len(champion_returns) != required or len(market_only_returns) != required:
        raise ValueError(f"formal readout requires exactly {required} paired intervals")
    if type(successful_decision_sets) is not int or type(synchronized_marks) is not int:
        raise ValueError("formal completeness counts must be integers")
    if not 0 <= successful_decision_sets <= required \
            or not 0 <= synchronized_marks <= required:
        raise ValueError("formal completeness counts must be within the trial horizon")
    values = [*champion_returns, *market_only_returns]
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        for value in values
    ):
        raise ValueError("formal returns must be finite numeric values")
    differences = [
        float(champion) - float(comparator)
        for champion, comparator in zip(
            champion_returns, market_only_returns, strict=True
        )
    ]
    test_policy = analysis["primary_test"]
    hac = newey_west_mean_test(differences, lags=int(test_policy["lags"]))
    mean = float(hac["mean"])
    standard_error = float(hac["standard_error"])
    alpha = float(test_policy["one_sided_alpha"])
    # The protocol freezes alpha=.025, whose standard-normal critical value is
    # 1.959963984540054. Reject protocol drift rather than silently generalize.
    if alpha != 0.025:
        raise ValueError("unsupported formal primary alpha")
    critical_value = 1.959963984540054
    lower_bound = mean - critical_value * standard_error
    p_value = _one_sided_positive_mean_p_value(hac)
    bootstrap_policy = analysis["bootstrap_robustness"]
    if float(bootstrap_policy["lower_quantile"]) != 0.025:
        raise ValueError("unsupported formal bootstrap quantile")
    bootstrap = moving_block_bootstrap_mean(
        differences,
        block_length=int(bootstrap_policy["block_length"]),
        trials=int(bootstrap_policy["trials"]),
        seed=int(bootstrap_policy["seed"]),
    )
    bootstrap_lower = bootstrap["confidence_interval_95"][0]
    missingness = analysis["missingness"]
    completeness_passed = (
        successful_decision_sets >= int(missingness["minimum_successful_decision_sets"])
        and synchronized_marks == int(missingness["required_synchronized_marks"])
    )
    economic_floor = float(
        analysis["primary_estimand"]["minimum_effect_bps_per_session"]
    )
    gates = {
        "hac_lower_bound_positive": lower_bound > 0,
        "economic_effect": mean * 10_000 >= economic_floor,
        "bootstrap_lower_bound_positive": bootstrap_lower > 0,
        "completeness": completeness_passed,
    }
    return {
        "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
        "paired_intervals": required,
        "successful_decision_sets": successful_decision_sets,
        "synchronized_marks": synchronized_marks,
        "mean_difference": mean,
        "mean_difference_bps_per_session": mean * 10_000,
        "one_sided_p_value": p_value,
        "one_sided_lower_bound": lower_bound,
        "newey_west": hac,
        "moving_block_bootstrap": bootstrap,
        "gates": gates,
        "passed": all(gates.values()),
    }


def formal_secondary_readout(
    paired_differences: dict[str, list[float]],
) -> dict:
    """Execute the complete locked seven-hypothesis secondary family.

    Values are champion-minus-comparator period returns.  This readout is
    descriptive unless the sole primary hypothesis also passes; secondaries
    can never rescue a failed primary result.
    """
    analysis = GLOBAL_EVENT_V2_PROTOCOL["analysis"]
    family = list(analysis["multiplicity"]["secondary_family"])
    if set(paired_differences) != set(family) \
            or len(paired_differences) != len(family):
        raise ValueError(
            "formal secondary readout requires exactly the seven "
            "pre-registered hypotheses"
        )
    required = int(analysis["trial_clock"]["holding_intervals"])
    lags = int(analysis["primary_test"]["lags"])
    results = {}
    p_values = {}
    for name in family:
        values = paired_differences[name]
        if len(values) != required:
            raise ValueError(
                f"formal secondary readout requires exactly {required} "
                f"intervals for {name}"
            )
        if any(
            isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            for value in values
        ):
            raise ValueError("formal secondary differences must be finite numbers")
        hac = newey_west_mean_test([float(value) for value in values], lags=lags)
        p_value = _one_sided_positive_mean_p_value(hac)
        p_values[name] = p_value
        results[name] = {
            "mean_difference": float(hac["mean"]),
            "mean_difference_bps_per_session": float(hac["mean"]) * 10_000,
            "one_sided_p_value": p_value,
            "newey_west": hac,
        }

    alpha = float(analysis["multiplicity"]["secondary_familywise_alpha"])
    holm = holm_bonferroni(p_values, alpha=alpha)
    for name in family:
        results[name]["holm_adjusted_p_value"] = holm["adjusted_p_values"][name]
        results[name]["holm_rejected"] = holm["rejected"][name]

    no_reaction = "champion_vs_without_public_reaction"
    required_significant = {
        "champion_vs_equal_weight",
        "champion_vs_momentum",
        "champion_vs_stale_events_negative_control",
        "champion_vs_shuffled_events_negative_control",
    }
    point_estimate_only = {
        "champion_vs_public_reaction_only",
        "champion_vs_spy",
    }
    no_reaction_floor = float(
        GLOBAL_EVENT_V2_PROTOCOL["promotion"]["requires"]
        ["without_public_reaction"]["minimum_effect_bps_per_session"]
    )
    gates = {
        "without_public_reaction": (
            results[no_reaction]["holm_rejected"]
            and results[no_reaction]["mean_difference_bps_per_session"]
            >= no_reaction_floor
        ),
        "holm_significant_positive_controls": all(
            results[name]["holm_rejected"]
            and results[name]["mean_difference"] > 0
            for name in required_significant
        ),
        "positive_point_estimates": all(
            results[name]["mean_difference"] > 0 for name in point_estimate_only
        ),
    }
    return {
        "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
        "paired_intervals": required,
        "family": family,
        "holm": holm,
        "hypotheses": results,
        "promotion_gates": gates,
        "passed_secondary_gates": all(gates.values()),
        "can_rescue_failed_primary": False,
    }


def _annualized_sharpe(values: list[float], periods_per_year: int = 252) -> float:
    standard_deviation = statistics.stdev(values)
    if standard_deviation == 0:
        mean = statistics.fmean(values)
        return math.inf if mean > 0 else -math.inf if mean < 0 else 0.0
    return statistics.fmean(values) / standard_deviation * math.sqrt(periods_per_year)


def _max_drawdown_from_returns(values: list[float]) -> float:
    nav = peak = 1.0
    maximum = 0.0
    for value in values:
        nav *= 1.0 + float(value)
        if nav <= 0:
            return -1.0
        peak = max(peak, nav)
        maximum = min(maximum, nav / peak - 1.0)
    return maximum


def _not_identified_selection_bias(reason_code: str) -> dict:
    common = {
        "status": "not_identified",
        "reason_code": reason_code,
        "registered_forward_arms_used_as_development_trials": False,
    }
    return {
        "status": "not_identified",
        "development_selection_audit_id": None,
        "registered_forward_arms": len(GLOBAL_EVENT_V2_PROTOCOL["strategies"]),
        "registered_forward_arms_used_as_development_trials": False,
        "deflated_sharpe": dict(common),
        "probability_of_backtest_overfitting": dict(common),
    }


def _validated_development_selection_audit(envelope: dict) -> dict:
    """Validate an optional pre-activity, content-addressed audit envelope.

    The caller that eventually loads this envelope from the ledger must derive
    ``first_formal_activity_utc`` from immutable trial activity. It is not an
    analysis parameter and must never be supplied from a report consumer.
    """
    envelope_keys = {
        "artifact_id", "artifact_type", "created_utc",
        "first_formal_activity_utc", "content",
    }
    if not isinstance(envelope, dict) or set(envelope) != envelope_keys \
            or envelope.get("artifact_type") != "formal_development_selection_audit":
        raise ValueError("development selection audit envelope is malformed")
    created = envelope.get("created_utc")
    first_activity = envelope.get("first_formal_activity_utc")
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        for value in (created, first_activity)
    ) or float(created) >= float(first_activity):
        raise ValueError("development selection audit was not frozen before activity")
    content = envelope.get("content")
    content_keys = {
        "schema_version", "audit_type", "protocol_id", "development_sample_id",
        "selected_candidate_id", "candidate_ids", "candidate_sharpes",
        "candidate_return_paths", "observation_count", "periods_per_year",
        "completeness_attested", "audit_id",
    }
    if not isinstance(content, dict) or set(content) != content_keys \
            or content.get("schema_version") != 1 \
            or content.get("audit_type") != "complete-development-selection-universe" \
            or content.get("protocol_id") != GLOBAL_EVENT_V2_PROTOCOL_ID \
            or not isinstance(content.get("development_sample_id"), str) \
            or not content["development_sample_id"] \
            or content.get("periods_per_year") != 252 \
            or content.get("completeness_attested") is not True:
        raise ValueError("development selection audit content is incomplete")
    candidate_ids = content.get("candidate_ids")
    if not isinstance(candidate_ids, list) or len(candidate_ids) < 2 \
            or candidate_ids != sorted(candidate_ids) \
            or len(candidate_ids) != len(set(candidate_ids)) \
            or any(not isinstance(value, str) or not value for value in candidate_ids) \
            or content.get("selected_candidate_id") not in candidate_ids:
        raise ValueError("development selection candidate identities are incomplete")
    sharpes = content.get("candidate_sharpes")
    paths = content.get("candidate_return_paths")
    observations = content.get("observation_count")
    if type(observations) is not int or observations < 4 \
            or not isinstance(sharpes, dict) or set(sharpes) != set(candidate_ids) \
            or not isinstance(paths, dict) or set(paths) != set(candidate_ids):
        raise ValueError("development selection audit path coverage is incomplete")
    for candidate_id in candidate_ids:
        path = paths[candidate_id]
        reported_sharpe = sharpes[candidate_id]
        if not isinstance(path, list) or len(path) != observations \
                or any(
                    isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(float(value)) or float(value) <= -1.0
                    for value in path
                ) or isinstance(reported_sharpe, bool) \
                or not isinstance(reported_sharpe, (int, float)) \
                or not math.isfinite(float(reported_sharpe)):
            raise ValueError("development selection audit returns are incomplete")
        recomputed = _annualized_sharpe([float(value) for value in path])
        if not math.isfinite(recomputed) or not math.isclose(
            recomputed, float(reported_sharpe), rel_tol=1e-12, abs_tol=1e-12
        ):
            raise ValueError("development selection audit Sharpe is inconsistent")
    base = {key: value for key, value in content.items() if key != "audit_id"}
    if content.get("audit_id") != content_id(
        base, prefix="selection_audit_"
    ) or envelope.get("artifact_id") != content_id(
        {
            "artifact_type": "formal_development_selection_audit",
            "content": content,
        },
        prefix="artifact_",
    ):
        raise ValueError("development selection audit content identity is invalid")
    return content


def _selection_bias_diagnostics(
    development_selection_audit: dict | None,
) -> dict:
    if development_selection_audit is None:
        return _not_identified_selection_bias(
            "missing_pre_activity_development_selection_audit"
        )
    try:
        audit = _validated_development_selection_audit(
            development_selection_audit
        )
    except ValueError:
        return _not_identified_selection_bias(
            "invalid_or_incomplete_pre_activity_development_selection_audit"
        )
    candidate_ids = audit["candidate_ids"]
    selected = audit["selected_candidate_id"]
    paths = {
        candidate_id: [float(value) for value in audit["candidate_return_paths"][candidate_id]]
        for candidate_id in candidate_ids
    }
    dsr = deflated_sharpe_ratio(
        paths[selected],
        trial_sharpes=[float(audit["candidate_sharpes"][name]) for name in candidate_ids],
    )
    pbo = probability_of_backtest_overfitting(paths, partitions=10)
    return {
        "status": "identified",
        "development_selection_audit_id": audit["audit_id"],
        "development_candidates": len(candidate_ids),
        "development_observations": audit["observation_count"],
        "registered_forward_arms": len(GLOBAL_EVENT_V2_PROTOCOL["strategies"]),
        "registered_forward_arms_used_as_development_trials": False,
        "deflated_sharpe": {**dsr, "status": "identified"},
        "probability_of_backtest_overfitting": {**pbo, "status": "identified"},
    }


def formal_complete_readout(
    strategy_returns: dict[str, list[float]],
    benchmark_returns: list[float],
    *,
    successful_decision_sets: int,
    synchronized_marks: int,
    development_selection_audit: dict | None = None,
) -> dict:
    """Run every machine-checkable V2 statistical gate without tunable knobs."""
    expected = list(GLOBAL_EVENT_V2_PROTOCOL["strategies"])
    if set(strategy_returns) != set(expected) or len(strategy_returns) != len(expected):
        raise ValueError("formal complete readout requires exactly all registered strategies")
    required = int(
        GLOBAL_EVENT_V2_PROTOCOL["analysis"]["trial_clock"]["holding_intervals"]
    )
    if len(benchmark_returns) != required or any(
        len(strategy_returns[name]) != required for name in expected
    ):
        raise ValueError(f"formal complete readout requires exactly {required} intervals")
    all_values = [
        value
        for series in [benchmark_returns, *(strategy_returns[name] for name in expected)]
        for value in series
    ]
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float))
        or not math.isfinite(float(value)) or float(value) <= -1.0
        for value in all_values
    ):
        raise ValueError("formal complete returns must be finite and greater than -100%")

    champion = [float(value) for value in strategy_returns["global_events_champion"]]
    market = [float(value) for value in strategy_returns["market_only"]]
    benchmark = [float(value) for value in benchmark_returns]
    primary = formal_primary_readout(
        champion,
        market,
        successful_decision_sets=successful_decision_sets,
        synchronized_marks=synchronized_marks,
    )
    comparator_by_hypothesis = {
        "champion_vs_without_public_reaction": (
            strategy_returns["global_events_without_public_reaction"]
        ),
        "champion_vs_public_reaction_only": strategy_returns["public_reaction_only"],
        "champion_vs_equal_weight": strategy_returns["equal_weight"],
        "champion_vs_momentum": strategy_returns["momentum"],
        "champion_vs_stale_events_negative_control": (
            strategy_returns["stale_events_negative_control"]
        ),
        "champion_vs_shuffled_events_negative_control": (
            strategy_returns["shuffled_events_negative_control"]
        ),
        "champion_vs_spy": benchmark,
    }
    secondary = formal_secondary_readout({
        name: [
            champion_value - float(comparator_value)
            for champion_value, comparator_value in zip(
                champion, comparator, strict=True
            )
        ]
        for name, comparator in comparator_by_hypothesis.items()
    })

    selection_bias = _selection_bias_diagnostics(development_selection_audit)
    champion_drawdown = _max_drawdown_from_returns(champion)
    market_drawdown = _max_drawdown_from_returns(market)
    drawdown_disadvantage = max(0.0, market_drawdown - champion_drawdown)
    requirements = GLOBAL_EVENT_V2_PROTOCOL["promotion"]["requires"]
    machine_gates = {
        "primary": primary["passed"],
        "secondary": secondary["passed_secondary_gates"],
        "drawdown_disadvantage": (
            drawdown_disadvantage * 100
            <= float(
                requirements[
                    "max_drawdown_disadvantage_vs_market_only_percentage_points_at_most"
                ]
            )
        ),
    }
    return {
        "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
        "paired_intervals": required,
        "primary": primary,
        "secondary": secondary,
        "selection_bias_diagnostics": selection_bias,
        "deflated_sharpe": selection_bias["deflated_sharpe"],
        "probability_of_backtest_overfitting": selection_bias[
            "probability_of_backtest_overfitting"
        ],
        "drawdowns": {
            "champion": champion_drawdown,
            "market_only": market_drawdown,
            "disadvantage_percentage_points": drawdown_disadvantage * 100,
        },
        "machine_gates": machine_gates,
        "machine_statistical_candidate": all(machine_gates.values()),
        "live_capital_approved": False,
        "remaining_nonstatistical_gates": [
            "operations_integrity_restore_alert_replay",
            "verifier_and_mark_vector_completeness",
            "attribution_concentration_review",
            "selection_bias_diagnostics_applicability_review",
            "explicit_human_approval",
            "separate_live_protocol",
        ],
    }
