from langchain_core.tools import tool
from typing import Annotated
from datetime import datetime, timedelta
import logging

import numpy as np
import pandas as pd
import yfinance as yf
from scipy import stats
from statsmodels.stats.stattools import jarque_bera
from statsmodels.regression.linear_model import OLS
from statsmodels.tools import add_constant

logger = logging.getLogger(__name__)


def _fetch_close_prices(ticker: str, end_date: str, days: int = 400) -> pd.Series:
    """Fetch closing prices for a ticker ending on end_date (exclusive)."""
    end = datetime.strptime(end_date, "%Y-%m-%d")
    start = end - timedelta(days=days)
    data = yf.download(
        ticker,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        progress=False,
        auto_adjust=True,
    )
    if data.empty:
        return pd.Series(dtype=float)
    close = data["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return close.dropna()


def _breusch_pagan(residuals: np.ndarray, X: np.ndarray):
    """
    Manual Breusch-Pagan test for heteroskedasticity.
    H0: residuals have constant variance.
    Returns (LM statistic, p-value).
    """
    n = len(residuals)
    sq_resid = residuals ** 2
    aux = OLS(sq_resid, X).fit()
    lm = n * aux.rsquared
    p = float(stats.chi2.sf(lm, df=X.shape[1] - 1))
    return float(lm), p


def _ljung_box(series: np.ndarray, lags: int = 10):
    """
    Manual Ljung-Box test for autocorrelation in residuals.
    H0: no autocorrelation up to `lags`.
    Returns (Q statistic, p-value) for the given lag count.
    """
    n = len(series)
    acf_vals = [np.corrcoef(series[k:], series[:-k])[0, 1] for k in range(1, lags + 1)]
    q = n * (n + 2) * sum(r ** 2 / (n - k) for k, r in enumerate(acf_vals, start=1))
    p = float(stats.chi2.sf(q, df=lags))
    return float(q), p


@tool
def get_quant_analysis(
    ticker: Annotated[str, "Ticker symbol of the stock to analyse, e.g. AAPL"],
    analysis_date: Annotated[str, "End date for the analysis window in yyyy-mm-dd format"],
) -> str:
    """
    Compute a comprehensive quantitative finance analysis for a stock including:
    dispersion/risk metrics, Sharpe ratio, statistical moments, correlation with SPY,
    OLS market beta regression, regression diagnostics (Breusch-Pagan heteroskedasticity,
    Ljung-Box autocorrelation, Newey-West robust errors, structural break detection),
    and multi-factor adjusted R². Returns a formatted Markdown report.
    """
    close = _fetch_close_prices(ticker, analysis_date)
    if len(close) < 30:
        return f"Insufficient price data for {ticker} (only {len(close)} trading days available before {analysis_date})."

    log_returns = np.log(close / close.shift(1)).dropna().values
    n = len(log_returns)
    mean_ret = float(np.mean(log_returns))

    # ── 1. Dispersion & Risk ─────────────────────────────────────────────────
    ann_vol = float(np.std(log_returns, ddof=1) * np.sqrt(252))

    # Semideviation: divide by total N (Sortino convention)
    downside = log_returns[log_returns < mean_ret]
    semivar = float(np.sum((downside - mean_ret) ** 2) / n) if len(downside) > 0 else float("nan")
    ann_semidev = float(np.sqrt(semivar) * np.sqrt(252)) if not np.isnan(semivar) else float("nan")

    # Target semideviation (target = 0%, i.e. capital preservation)
    target = 0.0
    below_target = log_returns[log_returns < target]
    target_semivar = float(np.sum((below_target - target) ** 2) / n) if len(below_target) > 0 else float("nan")
    ann_target_semidev = float(np.sqrt(target_semivar) * np.sqrt(252)) if not np.isnan(target_semivar) else float("nan")

    ann_mad = float(np.mean(np.abs(log_returns - mean_ret)) * np.sqrt(252))
    ret_range = float(np.ptp(log_returns))  # peak-to-peak

    # Sharpe Ratio (rf = 0, annualised)
    sharpe = float((mean_ret / np.std(log_returns, ddof=1)) * np.sqrt(252))

    # Rolling 30-day Sharpe (last value); guard against zero-std window producing inf
    ret_series = pd.Series(log_returns)
    roll_std = ret_series.rolling(30).std().replace(0, float("nan"))
    roll_sharpe = (ret_series.rolling(30).mean() / roll_std) * np.sqrt(252)
    last_roll_sharpe_raw = roll_sharpe.iloc[-1] if not roll_sharpe.empty else float("nan")
    last_roll_sharpe = float(last_roll_sharpe_raw) if np.isfinite(last_roll_sharpe_raw) else float("nan")

    # ── 2. Statistical Moments ───────────────────────────────────────────────
    skewness = float(stats.skew(log_returns))
    excess_kurtosis = float(stats.kurtosis(log_returns))
    jb_stat, jb_pvalue, _, _ = jarque_bera(log_returns)
    jb_pvalue = float(jb_pvalue)
    normal_dist = "YES" if jb_pvalue > 0.05 else "NO"

    # ── 3. Market Relationship (SPY) ─────────────────────────────────────────
    mkt_section = ""
    diag_section = ""
    break_section = ""

    # Fetch SPY — network/data errors are expected and handled gracefully
    try:
        spy_close = _fetch_close_prices("SPY", analysis_date)
    except Exception:
        logger.exception("Failed to fetch SPY data for %s", ticker)
        spy_close = pd.Series(dtype=float)

    common_idx = close.index.intersection(spy_close.index)

    if len(common_idx) >= 30:
        stock_ret = np.log(close.loc[common_idx] / close.loc[common_idx].shift(1)).dropna()
        spy_ret   = np.log(spy_close.loc[common_idx] / spy_close.loc[common_idx].shift(1)).dropna()
        cidx = stock_ret.index.intersection(spy_ret.index)
        sr = stock_ret.loc[cidx].values
        mr = spy_ret.loc[cidx].values

        # Correlation
        pearson_r, pearson_p = stats.pearsonr(sr, mr)
        s_s = pd.Series(sr, index=cidx)
        m_s = pd.Series(mr, index=cidx)
        last_roll_corr = float(s_s.rolling(30).corr(m_s).iloc[-1])

        # OLS beta (standard)
        X = add_constant(mr)
        ols = OLS(sr, X).fit()
        alpha      = float(ols.params[0])
        beta       = float(ols.params[1])
        r2         = float(ols.rsquared)
        adj_r2     = float(ols.rsquared_adj)
        beta_p     = float(ols.pvalues[1])
        ci         = ols.conf_int()   # ndarray shape (n_params, 2): rows=params, cols=[lower, upper]
        beta_ci_lo = float(ci[1][0])  # row 1 = beta, col 0 = lower bound
        beta_ci_hi = float(ci[1][1])  # row 1 = beta, col 1 = upper bound

        # Newey-West HAC robust beta
        hac = ols.get_robustcov_results(cov_type="HAC", maxlags=5)
        beta_hac_se = float(hac.bse[1])
        beta_hac_p  = float(hac.pvalues[1])

        mkt_section = (
            f"\n| Pearson r vs SPY | {pearson_r:.4f} |"
            f"\n| Pearson p-value | {pearson_p:.4f} |"
            f"\n| 30-day Rolling Corr (last) | {last_roll_corr:.4f} |"
            f"\n| Market Beta (β) | {beta:.4f} |"
            f"\n| Beta 95% CI | [{beta_ci_lo:.4f}, {beta_ci_hi:.4f}] |"
            f"\n| Alpha (α, daily) | {alpha:.6f} |"
            f"\n| R² | {r2:.4f} |"
            f"\n| Adjusted R² | {adj_r2:.4f} |"
            f"\n| β p-value (OLS) | {beta_p:.4f} |"
            f"\n| β Newey-West SE | {beta_hac_se:.4f} |"
            f"\n| β p-value (HAC) | {beta_hac_p:.4f} |"
        )

        # ── 4. Regression Diagnostics ────────────────────────────────────
        residuals = ols.resid

        # Breusch-Pagan heteroskedasticity test
        bp_lm, bp_p = _breusch_pagan(residuals, X)
        bp_result = "Heteroskedastic" if bp_p < 0.05 else "Homoskedastic"

        # Ljung-Box autocorrelation test (10 lags)
        lb_q, lb_p = _ljung_box(residuals, lags=10)
        lb_result = "Autocorrelated" if lb_p < 0.05 else "No autocorrelation"

        diag_section = (
            f"\n\n### Regression Diagnostics"
            f"\n\n| Test | Statistic | p-value | Result |"
            f"\n|------|-----------|---------|--------|"
            f"\n| Breusch-Pagan (heteroskedasticity) | {bp_lm:.4f} | {bp_p:.4f} | {bp_result} |"
            f"\n| Ljung-Box Q(10) (autocorrelation) | {lb_q:.4f} | {lb_p:.4f} | {lb_result} |"
        )

        # ── 5. Structural Break ──────────────────────────────────────────
        if len(sr) >= 60:
            mid = len(sr) // 2
            sr1, mr1 = sr[:mid], mr[:mid]
            sr2, mr2 = sr[mid:], mr[mid:]

            res1 = OLS(sr1, add_constant(mr1)).fit()
            res2 = OLS(sr2, add_constant(mr2)).fit()
            beta1, beta2 = float(res1.params[1]), float(res2.params[1])
            alpha1, alpha2 = float(res1.params[0]), float(res2.params[0])
            r2_1, r2_2 = float(res1.rsquared), float(res2.rsquared)
            beta_shift = beta2 - beta1
            stability = "STABLE" if abs(beta_shift) < 0.3 else "UNSTABLE"

            break_section = (
                f"\n\n### Structural Break Analysis (first half vs second half)"
                f"\n\n| Period | Beta | Alpha (daily) | R² |"
                f"\n|--------|------|---------------|----|"
                f"\n| First half ({mid} days) | {beta1:.4f} | {alpha1:.6f} | {r2_1:.4f} |"
                f"\n| Second half ({len(sr)-mid} days) | {beta2:.4f} | {alpha2:.6f} | {r2_2:.4f} |"
                f"\n| β shift | {beta_shift:+.4f} | — | — |"
                f"\n\n**Beta stability**: {stability} (|Δβ| {'< 0.30' if stability == 'STABLE' else '≥ 0.30'})"
            )
    else:
        mkt_section = "\n| SPY Market Data | Insufficient overlapping data |"

    # ── Build report ──────────────────────────────────────────────────────────
    report = f"""## Quantitative Analysis: {ticker} (as of {analysis_date})

**Data window**: {n} trading days of log returns

### 1. Dispersion & Risk

| Metric | Value |
|--------|-------|
| Annualised Volatility | {ann_vol:.4f} ({ann_vol*100:.2f}%) |
| Annualised Semideviation (vs mean) | {ann_semidev:.4f} ({ann_semidev*100:.2f}%) |
| Annualised Semideviation (vs 0%) | {ann_target_semidev:.4f} ({ann_target_semidev*100:.2f}%) |
| Annualised MAD | {ann_mad:.4f} ({ann_mad*100:.2f}%) |
| Return Range (peak-to-peak) | {ret_range:.4f} ({ret_range*100:.2f}%) |
| Sharpe Ratio (annualised, rf=0) | {sharpe:.4f} |
| Rolling 30-day Sharpe (last) | {last_roll_sharpe:.4f} |

### 2. Statistical Moments

| Metric | Value |
|--------|-------|
| Skewness | {skewness:.4f} |
| Excess Kurtosis | {excess_kurtosis:.4f} |
| Jarque-Bera p-value | {jb_pvalue:.4f} |
| Normally Distributed (JB test) | {normal_dist} |

### 3. Market Relationship (vs SPY)

| Metric | Value |
|--------|-------|{mkt_section}
{diag_section}
{break_section}

### Interpretation Guide
- **Semideviation vs mean**: downside risk relative to average return (Sortino denominator).
- **Semideviation vs 0%**: downside risk relative to capital preservation threshold.
- **Sharpe > 1**: good risk-adjusted return; **< 0**: negative excess return.
- **Skewness < 0**: left tail (larger losses than gains); **> 0**: right tail.
- **Kurtosis > 0**: fat tails — more extreme moves than a normal distribution.
- **JB p < 0.05**: returns NOT normally distributed.
- **β > 1**: amplifies market; **β < 1**: defensive.
- **Beta CI**: narrow CI = precisely estimated; wide CI = unreliable beta.
- **HAC p-value**: robust to het + autocorrelation — prefer over OLS p-value if BP/LB flagged.
- **Breusch-Pagan p < 0.05**: heteroskedastic residuals — OLS standard errors unreliable.
- **Ljung-Box p < 0.05**: autocorrelated residuals — model missing serial structure.
- **β shift > 0.30**: regime change detected — beta from full period may be misleading.
"""
    return report
