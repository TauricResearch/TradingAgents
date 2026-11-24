// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Long-only portfolio weights from historical daily returns, for analysis: minimum variance, maximum
 * Sharpe ratio, risk parity, and points on the efficient frontier. Weights sum to 1, none is negative,
 * and none exceeds the cap given (risk parity's are set by the risk contributions alone). The covariance
 * is Ledoit-Wolf shrunk; expected returns are mean daily returns, so only maximum Sharpe and the frontier
 * depend on them. Figures are annualized by the sessions in a year: means times them, covariance too.
 */
import { setImmediate } from "node:timers/promises";
import { OPTIMIZER } from "../contracts/limits.js";
import { covariance, sharedReturns, times, varianceShares } from "./portfolio.js";
import type { PriceSeries } from "./risk.js";
import { round } from "./series.js";

type Method = "min_variance" | "max_sharpe" | "risk_parity";

/** A portfolio the optimizer found: its weights and what they give under the estimates. */
type Allocation = {
  weights: number[];
  /** Annualized, in-sample. */
  return: number;
  volatility: number;
  sharpe: number | null;
  /** Each weight's share of the variance under the shrunk covariance. */
  riskShares: number[];
};

/**
 * The Ledoit-Wolf shrinkage of the sample covariance toward a multiple of the identity (Ledoit and Wolf,
 * "A well-conditioned estimator for large-dimensional covariance matrices", J. Multivariate Analysis
 * 2004), in closed form as the paper states it: with S the covariance of the centred observations x_k
 * divided by n, m = tr(S) / p, d^2 = |S - mI|^2 / p and b^2 = min(d^2, sum_k |x_k x_k' - S|^2 / (n^2 p))
 * (Frobenius norms), the estimate is (b^2 / d^2) mI + (1 - b^2 / d^2) S. This is
 * scikit-learn's ledoit_wolf.
 */
export function ledoitWolf(columns: readonly (readonly number[])[]): {
  sigma: number[][];
  shrinkage: number;
} {
  const p = columns.length;
  const n = columns[0]?.length ?? 0;
  const centred = columns.map((column) => {
    const mean = column.reduce((a, b) => a + b, 0) / n;
    return column.map((x) => x - mean);
  });
  const s = covariance(centred).map((row) => row.map((value) => (value * (n - 1)) / n));
  const m = s.reduce((sum, row, i) => sum + (row[i] as number), 0) / p;
  let d2 = 0;
  s.forEach((row, i) => {
    row.forEach((value, j) => {
      d2 += (value - (i === j ? m : 0)) ** 2;
    });
  });
  d2 /= p;
  let b2 = 0;
  for (let k = 0; k < n; k++) {
    for (let i = 0; i < p; i++) {
      for (let j = 0; j < p; j++) {
        const outer = (centred[i]?.[k] as number) * (centred[j]?.[k] as number);
        b2 += (outer - (s[i]?.[j] as number)) ** 2;
      }
    }
  }
  b2 = Math.min(d2, b2 / (n * n * p));
  const shrinkage = d2 === 0 ? 0 : b2 / d2;
  return {
    sigma: s.map((row, i) => row.map((value, j) => (1 - shrinkage) * value + (i === j ? shrinkage * m : 0))),
    shrinkage,
  };
}

/**
 * The Euclidean projection of v onto the capped simplex {w : sum w = 1, 0 <= w_i <= cap} (Wang and Lu,
 * "Projection onto the capped simplex", 2015): w_i = min(cap, max(0, v_i - tau)) for the tau at which
 * the weights sum to 1. The sum falls piecewise linearly in tau with breaks at v_i and v_i - cap, so
 * tau is found exactly between the two breaks that bracket 1.
 */
export function projectCapped(v: readonly number[], cap: number): number[] {
  const at = (tau: number) => v.map((x) => Math.min(cap, Math.max(0, x - tau)));
  const total = (tau: number) => at(tau).reduce((a, b) => a + b, 0);
  const breaks = [...new Set(v.flatMap((x) => [x, x - cap]))].sort((a, b) => a - b);
  for (let k = 1; k < breaks.length; k++) {
    const low = breaks[k - 1] as number;
    const high = breaks[k] as number;
    const above = total(low);
    const below = total(high);
    if (above >= 1 && below <= 1) {
      return at(above === below ? low : low + ((above - 1) / (above - below)) * (high - low));
    }
  }
  // Only a cap of exactly 1 / n leaves a single point, where every break gives the same sum.
  return v.map(() => cap);
}

/**
 * The weights minimizing w' Sigma w / 2 - lambda mu' w over the capped simplex, exactly, by the primal
 * active-set method (Nocedal and Wright, Numerical Optimization, 2nd ed. 2006, algorithm 16.3). Each
 * weight is free or held at 0 or at the cap; the free weights' minimizer with the rest held solves a
 * linear system, and a step toward it stops at the first bound it meets. At that minimizer a held
 * weight whose multiplier has the wrong sign is freed; when none has, the weights are optimal. At least
 * one weight stays free, the one the sum of weights sets, so the held bounds and the sum stay
 * independent. `start` (feasible weights, such as a solution at a nearby lambda) sets which weights are
 * held first. lambda = 0 is the minimum-variance portfolio.
 */
export function meanVariance(
  sigma: readonly (readonly number[])[],
  mu: readonly number[],
  lambda: number,
  cap: number,
  start?: readonly number[],
): number[] {
  const w = [
    ...(start ??
      projectCapped(
        sigma.map(() => 1 / sigma.length),
        cap,
      )),
  ];
  const held: Held[] = w.map((value) => (value <= 0 ? "low" : value >= cap ? "high" : "free"));
  if (!held.includes("free")) held[w.indexOf(Math.max(...w))] = "free";
  held.forEach((state, i) => {
    if (state !== "free") w[i] = state === "low" ? 0 : cap;
  });
  const scale = Math.max(...sigma.map((row, i) => row[i] as number), lambda * Math.max(...mu.map(Math.abs)));
  for (let iteration = 0; iteration < OPTIMIZER.activeSetIterations; iteration++) {
    const free = held.flatMap((state, i) => (state === "free" ? [i] : []));
    // The free weights' minimizer: Sigma_FF x = b + nu 1, with b what lambda mu and the held weights
    // give, and nu set so the free weights sum to what the held ones leave.
    const left = 1 - w.reduce((sum, value, i) => (held[i] === "free" ? sum : sum + value), 0);
    const b = free.map(
      (i) =>
        lambda * (mu[i] as number) -
        (sigma[i] as number[]).reduce(
          (sum, value, j) => (held[j] === "free" ? sum : sum + value * (w[j] as number)),
          0,
        ),
    );
    const [ones, base] = solveSymmetric(
      free.map((i) => free.map((j) => (sigma[i] as number[])[j] as number)),
      [free.map(() => 1), b],
    ) as [number[], number[]];
    const nu = (left - base.reduce((a, c) => a + c, 0)) / ones.reduce((a, c) => a + c, 0);
    const target = base.map((value, k) => value + nu * (ones[k] as number));
    let step = 1;
    let blocking = -1;
    let rising = false;
    // A single free weight is set by the sum and cannot block.
    if (free.length > 1) {
      free.forEach((i, k) => {
        const move = (target[k] as number) - (w[i] as number);
        const room =
          move < 0 ? (w[i] as number) / -move : move > 0 ? (cap - (w[i] as number)) / move : Infinity;
        if (room < step) {
          step = room;
          blocking = i;
          rising = move > 0;
        }
      });
    }
    free.forEach((i, k) => {
      w[i] = (w[i] as number) + step * ((target[k] as number) - (w[i] as number));
    });
    if (blocking >= 0) {
      held[blocking] = rising ? "high" : "low";
      w[blocking] = rising ? cap : 0;
      continue;
    }
    // At the minimizer, a held weight's gradient against nu, the free weights' common one: a weight at 0
    // that lowers the objective by rising, or one at the cap by falling, is freed.
    const gradient = times(sigma, w).map((g, i) => g - lambda * (mu[i] as number));
    let worst = -1;
    let most = OPTIMIZER.tolerance * scale;
    held.forEach((state, i) => {
      const pull =
        state === "low" ? nu - (gradient[i] as number) : state === "high" ? (gradient[i] as number) - nu : 0;
      if (pull > most) {
        most = pull;
        worst = i;
      }
    });
    if (worst < 0) return w;
    held[worst] = "free";
  }
  return w;
}

/** Whether a weight is free or held at a bound in the active-set method. */
type Held = "free" | "low" | "high";

/**
 * The solutions x of A x = b for each right-hand side, A symmetric positive semidefinite, by Cholesky
 * factorization. A pivot at or near 0 (a mix of holdings with no variance) is lifted to a tiny multiple
 * of the largest diagonal, which picks one of the equally good solutions.
 */
function solveSymmetric(a: readonly (readonly number[])[], rhs: readonly (readonly number[])[]): number[][] {
  const n = a.length;
  const floor = OPTIMIZER.tolerance * Math.max(...a.map((row, i) => row[i] as number));
  const l = a.map(() => new Array<number>(n).fill(0));
  for (let j = 0; j < n; j++) {
    const lj = l[j] as number[];
    let pivot = (a[j] as number[])[j] as number;
    for (let k = 0; k < j; k++) pivot -= (lj[k] as number) ** 2;
    lj[j] = Math.sqrt(Math.max(pivot, floor));
    for (let i = j + 1; i < n; i++) {
      const li = l[i] as number[];
      let value = (a[i] as number[])[j] as number;
      for (let k = 0; k < j; k++) value -= (li[k] as number) * (lj[k] as number);
      li[j] = value / (lj[j] as number);
    }
  }
  return rhs.map((b) => {
    const y = new Array<number>(n).fill(0);
    for (let i = 0; i < n; i++) {
      let value = b[i] as number;
      for (let k = 0; k < i; k++) value -= ((l[i] as number[])[k] as number) * (y[k] as number);
      y[i] = value / ((l[i] as number[])[i] as number);
    }
    for (let i = n - 1; i >= 0; i--) {
      let value = y[i] as number;
      for (let k = i + 1; k < n; k++) value -= ((l[k] as number[])[i] as number) * (y[k] as number);
      y[i] = value / ((l[i] as number[])[i] as number);
    }
    return y;
  });
}

/** Whether two solutions hold the same weights at the same bounds, so the solutions between them are on one line. */
function sameHolding(a: readonly number[], b: readonly number[], cap: number): boolean {
  const state = (value: number) => (value <= 0 ? 0 : value >= cap ? 2 : 1);
  return a.every((value, i) => state(value) === state(b[i] as number));
}

/** The highest return under the cap: the largest means filled to the cap in turn. */
function maxReturn(mu: readonly number[], cap: number): number {
  let left = 1;
  let total = 0;
  for (const value of [...mu].sort((a, b) => b - a)) {
    const take = Math.min(cap, left);
    total += take * value;
    left -= take;
  }
  return total;
}

/** A solution of the mean-variance problem: its lambda, weights and return. */
type Solved = { lambda: number; weights: number[]; return: number };

/**
 * The efficient frontier under the cap, from the minimum-variance portfolio (`first`, lambda 0) to the
 * least-variance one at the highest return the cap allows (`last`). The solutions are piecewise linear
 * in lambda, and their return rises with it, so lambda's end is found by doubling.
 */
type Frontier = { first: Solved; last: Solved; solve(lambda: number, near: Solved): Solved };

async function frontierOf(
  sigma: readonly (readonly number[])[],
  mu: readonly number[],
  cap: number,
  signal?: AbortSignal,
): Promise<Frontier> {
  const solve = (lambda: number, near?: Solved): Solved => {
    const weights = meanVariance(sigma, mu, lambda, cap, near?.weights);
    return { lambda, weights, return: dot(weights, mu) };
  };
  const first = solve(0);
  const top = maxReturn(mu, cap);
  const spread = Math.max(...mu) - Math.min(...mu);
  let last = solve(spread > 0 ? 1 / spread : 1, first);
  for (let k = 0; k < OPTIMIZER.searchSteps && last.return < top - OPTIMIZER.endTolerance * spread; k++) {
    await pause(signal);
    last = solve(last.lambda * 2, last);
  }
  return { first, last, solve };
}

/** Whether the return rises from one solution to the next by more than rounding. */
function rises(a: Solved, b: Solved): boolean {
  return b.return - a.return > OPTIMIZER.endTolerance * (Math.abs(a.return) + Math.abs(b.return));
}

/** The point between two solutions on one line: weights and return at the fraction `t` from `a` to `b`. */
function between(a: Solved, b: Solved, t: number): Solved {
  return {
    lambda: a.lambda + t * (b.lambda - a.lambda),
    weights: a.weights.map((value, i) => value + t * ((b.weights[i] as number) - value)),
    return: a.return + t * (b.return - a.return),
  };
}

/**
 * The least-variance weights at a target return between the frontier's ends: lambda is bisected until
 * the two solutions bracketing the target hold the same weights at their bounds, and the solutions
 * between them are on the line joining them, so the target's weights are found on it exactly.
 */
async function atReturn(
  line: Frontier,
  target: number,
  cap: number,
  signal?: AbortSignal,
): Promise<number[]> {
  let low = line.first;
  let high = line.last;
  for (let k = 0; k < OPTIMIZER.searchSteps && !sameHolding(low.weights, high.weights, cap); k++) {
    await pause(signal);
    const mid = line.solve((low.lambda + high.lambda) / 2, low);
    if (mid.return < target) low = mid;
    else high = mid;
  }
  return high.return > low.return
    ? between(low, high, (target - low.return) / (high.return - low.return)).weights
    : high.weights;
}

/**
 * The maximum-Sharpe weights under the cap: the tangency portfolio, the point on the efficient frontier
 * where (mu' w - rf) / sqrt(w' Sigma w) is highest, for a frontier that reaches above the risk-free
 * rate. Along the frontier the ratio rises to a single peak, so lambda is narrowed by golden-section
 * search (Kiefer, Proc. AMS 1953). Once the two inner points hold the same weights at their bounds the
 * ratio on the line through them peaks where its derivative is 0, in closed form; that point is kept
 * when the solution there is on the same line. Null when no weights earn more than the risk-free rate:
 * below it the ratio is negative, and a higher ratio goes with more volatility rather than a better trade-off.
 */
export async function maxSharpe(
  sigma: readonly (readonly number[])[],
  mu: readonly number[],
  riskFree: number,
  cap: number,
  signal?: AbortSignal,
): Promise<number[] | null> {
  const line = await frontierOf(sigma, mu, cap, signal);
  if (line.last.return <= riskFree) return null;
  const sharpe = (point: Solved) => (point.return - riskFree) / Math.sqrt(quadratic(sigma, point.weights));
  const ratio = (Math.sqrt(5) - 1) / 2;
  let low = 0;
  let high = line.last.lambda;
  let left = line.solve(high - ratio * (high - low), line.first);
  let right = line.solve(low + ratio * (high - low), left);
  const candidates = [line.first, line.last];
  for (let k = 0; k < OPTIMIZER.searchSteps && high - low > OPTIMIZER.tolerance * line.last.lambda; k++) {
    await pause(signal);
    if (right.lambda > left.lambda && sameHolding(left.weights, right.weights, cap)) {
      const peak = linePeak(sigma, left, right, riskFree);
      if (peak !== null && peak.lambda > low && peak.lambda < high) {
        const solved = line.solve(peak.lambda, left);
        if (
          sameHolding(solved.weights, left.weights, cap) &&
          sharpe(solved) >= Math.max(sharpe(left), sharpe(right))
        ) {
          candidates.push(solved);
          break;
        }
      }
    }
    // Past the frontier's high end the weights stay put, so a tie there narrows toward the peak.
    if (rises(left, right) && sharpe(left) < sharpe(right)) {
      low = left.lambda;
      left = right;
      right = line.solve(low + ratio * (high - low), left);
    } else {
      high = right.lambda;
      right = left;
      left = line.solve(high - ratio * (high - low), right);
    }
  }
  candidates.push(left, right);
  return candidates.reduce((best, one) => (sharpe(one) > sharpe(best) ? one : best)).weights;
}

/**
 * Where the Sharpe ratio peaks on the line through two solutions: with w(t) = a + t (b - a), the ratio
 * (c0 + c1 t) / sqrt(q0 + 2 q1 t + q2 t^2) has its derivative 0 at t = (c0 q1 - c1 q0) / (c1 q1 - c0 q2).
 * Null when the return does not rise along the line.
 */
function linePeak(
  sigma: readonly (readonly number[])[],
  a: Solved,
  b: Solved,
  riskFree: number,
): Solved | null {
  const d = b.weights.map((value, i) => value - (a.weights[i] as number));
  const c0 = a.return - riskFree;
  const c1 = b.return - a.return;
  const q0 = quadratic(sigma, a.weights);
  const q1 = dot(a.weights, times(sigma, d));
  const q2 = quadratic(sigma, d);
  // Where the return stays put (the frontier's high end) every point is stationary, and none is a peak.
  if (!rises(a, b)) return null;
  const denominator = c1 * q1 - c0 * q2;
  return denominator === 0 ? null : between(a, b, (c0 * q1 - c1 * q0) / denominator);
}

/**
 * Least-variance weights at target returns evenly spaced along the frontier, its two ends included; one
 * point, or a frontier whose ends have the same return, is the minimum-variance portfolio alone.
 */
export async function frontier(
  sigma: readonly (readonly number[])[],
  mu: readonly number[],
  cap: number,
  points: number,
  signal?: AbortSignal,
): Promise<number[][]> {
  const line = await frontierOf(sigma, mu, cap, signal);
  const { first, last } = line;
  if (points < 2 || last.return - first.return <= OPTIMIZER.tolerance) return [first.weights];
  const inner: number[][] = [];
  for (let k = 1; k < points - 1; k++) {
    inner.push(
      await atReturn(line, first.return + (k / (points - 1)) * (last.return - first.return), cap, signal),
    );
  }
  return [first.weights, ...inner, last.weights];
}

/** Lets the event loop run between bounded steps of a solve, and stops the solve once `signal` aborts. */
function pause(signal?: AbortSignal): Promise<void> {
  return setImmediate(undefined, signal ? { signal } : {});
}

/**
 * Equal risk contributions, w_i (Sigma w)_i the same for every holding, long-only (Maillard, Roncalli and
 * Teiletche, J. Portfolio Management 2010), by cyclical coordinate descent on y' Sigma y / 2 - sum ln(y_i) / n
 * (Griveau-Billion, Richard and Roncalli, "A fast algorithm for computing high-dimensional risk parity
 * portfolios", 2013): each y_i in turn solves Sigma_ii y_i^2 + c_i y_i - 1 / n = 0, with c_i the rest of
 * row i of Sigma times y; the weights are y scaled to sum to 1. Null when the weights it settles on do
 * not give every holding the same share of a variance above 0, as when a mix of the holdings has little
 * or no variance and the descent does not settle.
 */
export function riskParity(sigma: readonly (readonly number[])[]): number[] | null {
  const n = sigma.length;
  const y = sigma.map((row, i) => 1 / Math.sqrt(row[i] as number));
  for (let sweep = 0; sweep < OPTIMIZER.riskParitySweeps; sweep++) {
    let moved = 0;
    for (let i = 0; i < n; i++) {
      const row = sigma[i] as number[];
      const own = row[i] as number;
      const c = row.reduce((sum, value, j) => (j === i ? sum : sum + value * (y[j] as number)), 0);
      const next = (-c + Math.sqrt(c * c + (4 * own) / n)) / (2 * own);
      moved = Math.max(moved, Math.abs(next - (y[i] as number)) / next);
      y[i] = next;
    }
    if (moved <= OPTIMIZER.tolerance) break;
  }
  const total = y.reduce((a, b) => a + b, 0);
  const weights = y.map((value) => value / total);
  const shares = varianceShares(sigma, weights);
  const equal =
    shares.length > 0 && shares.every((share) => Math.abs(share - 1 / n) <= OPTIMIZER.shareTolerance);
  return equal ? weights : null;
}

/** What the weights give under the estimates, annualized by `perYear`. */
function allocation(
  weights: readonly number[],
  sigma: readonly (readonly number[])[],
  mu: readonly number[],
  riskFree: number,
  perYear: number,
): Allocation {
  const annualReturn = dot(weights, mu) * perYear;
  const volatility = Math.sqrt(quadratic(sigma, weights) * perYear);
  return {
    weights: [...weights],
    return: annualReturn,
    volatility,
    sharpe: volatility > 0 ? (annualReturn - riskFree * perYear) / volatility : null,
    riskShares: varianceShares(sigma, weights),
  };
}

/** A portfolio as a result states it: weights by holding, and annualized figures in percent. */
export type Point = {
  /** Weights as solved, unrounded; a share of risk is null when the portfolio has no variance. */
  weights: { label: string; weight: number; risk_share_pct: number | null }[];
  return_pct: number;
  volatility_pct: number;
  sharpe: number | null;
};

export type Optimization = {
  method: Method;
  from: string;
  to: string;
  /** Daily returns the estimates come from. */
  returns: number;
  sessions_per_year: number;
  /** The Ledoit-Wolf shrinkage intensity, from 0 (the sample covariance) to 1 (a multiple of the identity). */
  shrinkage: number;
  max_weight: number | null;
  portfolio: Point;
  /**
   * From the minimum-variance portfolio to the highest return the cap allows (one point: the minimum-variance
   * portfolio alone); mean-variance methods only.
   */
  frontier: Point[];
  notes: string[];
};

/**
 * Weights for the series by `method`, with the frontier's points, on the dates they all share. The solve
 * yields to the event loop between its steps and stops when `signal` aborts.
 */
export async function optimizeOf(
  series: readonly PriceSeries[],
  options: {
    method: Method;
    maxWeight?: number;
    riskFreePct?: number;
    frontierPoints?: number;
    signal?: AbortSignal;
  },
): Promise<Optimization | { error: string }> {
  const n = series.length;
  const cap = options.maxWeight ?? 1;
  if (options.method !== "risk_parity" && cap * n < 1 - OPTIMIZER.tolerance) {
    return {
      error: `a max_weight of ${cap} across ${n} holdings cannot reach a total of 1; the smallest cap for ${n} holdings is ${round(1 / n, 4)}`,
    };
  }
  const returns = sharedReturns(series);
  if ("error" in returns) return returns;
  const { columns, dates, perYear, labels } = returns;
  const still = columns.findIndex((column) => column.every((r) => r === column[0]));
  if (still >= 0)
    return { error: `${labels[still]} does not move over these dates, so its risk is not defined` };
  const { sigma, shrinkage } = ledoitWolf(columns);
  const mu = columns.map((column) => column.reduce((a, b) => a + b, 0) / column.length);
  const riskFree = (options.riskFreePct ?? 0) / 100 / perYear;
  const notes: string[] = [];
  if (options.maxWeight !== undefined && options.method === "risk_parity") {
    notes.push(
      "risk parity's weights follow from the risk contributions alone; max_weight does not apply to them",
    );
  }

  let weights: number[];
  if (options.method === "min_variance") weights = meanVariance(sigma, mu, 0, cap);
  else if (options.method === "risk_parity") {
    const parity = riskParity(sigma);
    if (!parity) {
      return {
        error:
          "risk parity did not reach equal shares of risk over these dates: a mix of the holdings has little or no variance; min_variance gives that mix",
      };
    }
    weights = parity;
  } else {
    const best = await maxSharpe(sigma, mu, riskFree, cap, options.signal);
    if (!best) {
      return {
        error:
          "no long-only weights earn more than the risk-free rate over these dates; max_sharpe ranks only weights that do (below it, a higher Sharpe ratio favours more volatility). min_variance and risk_parity need no return estimate",
      };
    }
    weights = best;
  }
  const point = (w: readonly number[]): Point => {
    const figures = allocation(w, sigma, mu, riskFree, perYear);
    return {
      weights: labels.map((label, i) => ({
        label,
        weight: w[i] as number,
        risk_share_pct: figures.riskShares.length ? round((figures.riskShares[i] as number) * 100) : null,
      })),
      return_pct: round(figures.return * 100),
      volatility_pct: round(figures.volatility * 100),
      sharpe: figures.sharpe === null ? null : round(figures.sharpe, 3),
    };
  };
  const points = options.method === "risk_parity" ? 0 : (options.frontierPoints ?? 0);
  if (options.method !== "risk_parity") {
    notes.push(
      "expected returns are the mean daily returns of this window, which are noisy estimates: max_sharpe and the frontier move with them, while min_variance and risk_parity use no return estimate",
    );
  }
  return {
    method: options.method,
    from: dates[0] as string,
    to: dates.at(-1) as string,
    returns: dates.length - 1,
    sessions_per_year: perYear,
    shrinkage: round(shrinkage, 4),
    max_weight: options.maxWeight ?? null,
    portfolio: point(weights),
    frontier: points >= 1 ? (await frontier(sigma, mu, cap, points, options.signal)).map(point) : [],
    notes,
  };
}

function dot(a: readonly number[], b: readonly number[]): number {
  return a.reduce((sum, value, i) => sum + value * (b[i] as number), 0);
}

function quadratic(sigma: readonly (readonly number[])[], w: readonly number[]): number {
  return dot(w, times(sigma, w));
}
