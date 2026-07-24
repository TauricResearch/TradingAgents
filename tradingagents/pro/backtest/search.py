"""Iterative parameter search: genetic + Bayesian (TPE), pure-Python & seeded.

Both expose the same ``ask``/``tell`` interface the optimizer's
``_run_iterative`` drives, so they inherit the existing parallel evaluation and
the overfitting guards (validation.py) unchanged — a genetic/Bayesian search's
"best" ships with the same deflated Sharpe + PBO as a grid search, and the
guards see EVERY evaluated trial (so the expected-max-Sharpe bar rises with the
true amount of searching, never under-reported).

Determinism (the load-bearing property, since the byte-identical equivalence
suite depends on it): a single ``random.Random(seed)`` drives all stochastic
choices, and each generation/batch is evaluated and reassembled in submission
order before ``tell`` consumes it — so the RNG advances identically regardless
of worker completion order. No new dependency: the TPE density is a small 1-D
Parzen estimator over stdlib math.
"""

from __future__ import annotations

import math
import random

from tradingagents.pro.backtest.strategy import ParamSpace

_SQRT_2PI = math.sqrt(2.0 * math.pi)


class GeneticSampler:
    """Tournament-selection genetic algorithm over a ``ParamSpace``. Generation
    0 is random; each later generation is bred from the previous (elitism +
    tournament parents + uniform crossover + per-gene mutation). Evaluates
    ``population × generations`` trials total."""

    def __init__(
        self,
        space: ParamSpace,
        *,
        population: int = 12,
        generations: int = 5,
        seed: int = 0,
        tournament: int = 3,
        mutation_rate: float = 0.2,
    ):
        self.space = space
        self.population = max(2, population)
        self.generations = max(1, generations)
        self.tournament = max(2, min(tournament, self.population))
        self.mutation_rate = mutation_rate
        self.rng = random.Random(seed)
        self._gen = 0
        self._scored: list[tuple[dict, float]] = []

    def ask(self) -> list[dict]:
        if self._gen >= self.generations:
            return []
        if self._gen == 0:
            return [self.space.sample(self.rng) for _ in range(self.population)]
        return self._breed()

    def tell(self, params: list[dict], objectives: list[float]) -> None:
        self._scored = list(zip(params, objectives, strict=False))
        self._gen += 1

    def _breed(self) -> list[dict]:
        ranked = sorted(self._scored, key=lambda po: po[1], reverse=True)
        children: list[dict] = [dict(ranked[0][0])]  # elitism: keep the best
        while len(children) < self.population:
            child = self._crossover(self._tournament(), self._tournament())
            self._mutate(child)
            children.append(child)
        return children

    def _tournament(self) -> dict:
        contenders = [self.rng.choice(self._scored) for _ in range(self.tournament)]
        return dict(max(contenders, key=lambda po: po[1])[0])

    def _crossover(self, a: dict, b: dict) -> dict:
        return {p.name: (a[p.name] if self.rng.random() < 0.5 else b[p.name])
                for p in self.space}

    def _mutate(self, individual: dict) -> None:
        for p in self.space:
            if self.rng.random() < self.mutation_rate:
                individual[p.name] = p.sample(self.rng)


class TPESampler:
    """Tree-structured Parzen Estimator (a light Bayesian search). Warms up with
    ``n_startup`` random trials, then models the "good" (top ``gamma``) and
    "bad" observed configurations with per-parameter 1-D densities and proposes
    the candidate maximizing the good/bad density ratio. Batched (``batch``
    candidates per round from the same model) so rounds parallelize and stay
    deterministic; evaluates ``n_trials`` total."""

    def __init__(
        self,
        space: ParamSpace,
        *,
        n_trials: int = 40,
        n_startup: int = 8,
        batch: int = 4,
        gamma: float = 0.25,
        candidates: int = 24,
        seed: int = 0,
    ):
        self.space = space
        self.n_trials = max(2, n_trials)
        self.n_startup = max(1, min(n_startup, self.n_trials))
        self.batch = max(1, batch)
        self.gamma = gamma
        self.candidates = max(1, candidates)
        self.rng = random.Random(seed)
        self._history: list[tuple[dict, float]] = []
        self._asked = 0

    def ask(self) -> list[dict]:
        remaining = self.n_trials - self._asked
        if remaining <= 0:
            return []
        if self._asked < self.n_startup:
            k = min(self.batch, self.n_startup - self._asked, remaining)
            batch = [self.space.sample(self.rng) for _ in range(k)]
        else:
            k = min(self.batch, remaining)
            batch = [self._suggest() for _ in range(k)]
        self._asked += len(batch)
        return batch

    def tell(self, params: list[dict], objectives: list[float]) -> None:
        self._history.extend(zip(params, objectives, strict=False))

    def _suggest(self) -> dict:
        ranked = sorted(self._history, key=lambda po: po[1], reverse=True)
        n_good = max(1, math.ceil(self.gamma * len(ranked)))
        good = [p for p, _ in ranked[:n_good]]
        bad = [p for p, _ in ranked[n_good:]] or good
        best_cand: dict | None = None
        best_score = -math.inf
        for _ in range(self.candidates):
            cand = self._sample_from(good)
            score = self._density(cand, good) / (self._density(cand, bad) + 1e-12)
            if score > best_score:
                best_cand, best_score = cand, score
        return best_cand if best_cand is not None else self.space.sample(self.rng)

    def _bandwidth(self, p, pool: list[dict]) -> float:
        span = (p.high - p.low) if p.high is not None and p.low is not None else 0.0
        if span <= 0:
            return 0.0
        return max(span / math.sqrt(max(len(pool), 1)), span * 0.05)

    def _sample_from(self, pool: list[dict]) -> dict:
        cand: dict = {}
        for p in self.space:
            vals = [ind[p.name] for ind in pool]
            if p.kind == "categorical":
                cand[p.name] = self.rng.choice(vals)
                continue
            center = self.rng.choice(vals)
            bw = self._bandwidth(p, pool)
            v = self.rng.gauss(center, bw) if bw > 0 else center
            v = min(max(v, p.low), p.high)
            cand[p.name] = int(round(v)) if p.kind == "int" else v
        return cand

    def _density(self, cand: dict, pool: list[dict]) -> float:
        log_d = 0.0
        for p in self.space:
            vals = [ind[p.name] for ind in pool]
            x = cand[p.name]
            if p.kind == "categorical":
                count = sum(1 for v in vals if v == x)
                d = (count + 1) / (len(vals) + len(p.choices))
            else:
                bw = self._bandwidth(p, pool) or 1.0
                kernels = sum(math.exp(-0.5 * ((x - v) / bw) ** 2) for v in vals)
                d = kernels / (len(vals) * bw * _SQRT_2PI) + 1e-12
            log_d += math.log(d)
        return math.exp(log_d)


def build_sampler(space: ParamSpace, search: str, seed: int, config: dict):
    """Construct the sampler for ``search`` and return ``(sampler, total_hint)``
    where total_hint is the expected trial count (for progress reporting)."""
    if search == "genetic":
        s = GeneticSampler(
            space, seed=seed,
            population=int(config.get("population", 12)),
            generations=int(config.get("generations", 5)),
            tournament=int(config.get("tournament", 3)),
            mutation_rate=float(config.get("mutation_rate", 0.2)))
        return s, s.population * s.generations
    if search == "bayesian":
        s = TPESampler(
            space, seed=seed,
            n_trials=int(config.get("n_trials", 40)),
            n_startup=int(config.get("n_startup", 8)),
            batch=int(config.get("batch", 4)),
            gamma=float(config.get("gamma", 0.25)))
        return s, s.n_trials
    raise ValueError(f"unknown iterative search {search!r} (genetic | bayesian)")


__all__ = ["GeneticSampler", "TPESampler", "build_sampler"]
