"""Deterministic data validator (Phase 1, contract section 3.3).

Pure, typed checks over data the vendors serve. Every rule is a function
returning a :class:`ValidationIssue` — never an exception for a data-quality
problem, because the caller must be able to collect *all* issues and decide
(quarantine, degrade, block) rather than fail on the first one.

Rules here are generic: ticker identity, OHLC consistency, unit/scale
reconciliation, share-class conversion. Nothing is hardcoded for BRK-B; the
BRK-B numbers appear only in the regression tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

# Issue severities. ``error`` means the datum must not feed a decision;
# ``warning`` means it may, with the caveat surfaced.
ERROR = "error"
WARNING = "warning"

# Statuses a validated datum can carry (contract section 3.3).
OK = "OK"
QUARANTINED = "QUARANTINED"
UNVERIFIED = "UNVERIFIED"

# Berkshire share-class conversion: 1 class A = 1500 class B. Recorded as a
# named constant because the *rule* (convert before per-share math across
# classes) is general even though this pair is the known hazard.
BRK_A_TO_B_RATIO = 1500


@dataclass(frozen=True)
class ValidationIssue:
    """One data-quality finding, machine-readable for the audit trail."""

    code: str
    severity: str
    message: str
    field: str | None = None
    expected: object = None
    actual: object = None

    @property
    def is_error(self) -> bool:
        return self.severity == ERROR


@dataclass
class ValidationResult:
    """Collected issues for one datum or frame, with the derived status."""

    issues: list[ValidationIssue] = field(default_factory=list)

    def add(self, code: str, severity: str, message: str, **kwargs) -> ValidationIssue:
        issue = ValidationIssue(code=code, severity=severity, message=message, **kwargs)
        self.issues.append(issue)
        return issue

    @property
    def has_errors(self) -> bool:
        return any(i.is_error for i in self.issues)

    @property
    def status(self) -> str:
        """QUARANTINED on any error, UNVERIFIED on warnings, else OK."""
        if self.has_errors:
            return QUARANTINED
        return UNVERIFIED if self.issues else OK

    def error_messages(self) -> list[str]:
        return [i.message for i in self.issues if i.is_error]


# ---------------------------------------------------------------------------
# OHLC consistency (contract: low <= min(open,close) <= max(open,close) <= high)
# ---------------------------------------------------------------------------


def validate_ohlcv_frame(df: pd.DataFrame) -> ValidationResult:
    """Check an OHLCV frame's internal consistency, row by row.

    Flags inverted ranges (high < low), closes outside the bar's range,
    negative volumes and non-positive prices. Rows after the first error are
    still checked: the caller wants the full picture, not the first failure.
    """
    result = ValidationResult()
    required = {"Open", "High", "Low", "Close"}
    missing = required - set(df.columns)
    if missing:
        result.add("OHLCV_MISSING_COLUMNS", ERROR,
                   f"frame is missing columns: {sorted(missing)}")
        return result

    for idx, row in df.iterrows():
        o, h, low, c = row["Open"], row["High"], row["Low"], row["Close"]
        date_label = row.get("Date", idx)
        # A row with no close is an unsettled session, not corruption: the
        # loader already handles trailing unsettled bars (#1201/#1289).
        if pd.isna(o) and pd.isna(h) and pd.isna(low) and pd.isna(c):
            continue
        if pd.isna(h) or pd.isna(low):
            result.add("OHLCV_MISSING_HL", ERROR,
                       f"{date_label}: high/low missing on a priced row",
                       field="High/Low")
            continue
        if h < low:
            result.add("OHLCV_INVERTED_RANGE", ERROR,
                       f"{date_label}: high {h} < low {low}",
                       field="High", expected=">= low", actual=h)
        if not pd.isna(o) and not pd.isna(c):
            lo, hi = min(o, c), max(o, c)
            if low > lo or (not pd.isna(h) and h < hi):
                result.add("OHLCV_RANGE_VIOLATION", ERROR,
                           f"{date_label}: open/close outside the bar's low-high range",
                           field="OHLC")
        if not pd.isna(c) and c <= 0:
            result.add("OHLCV_NONPOSITIVE_PRICE", ERROR,
                       f"{date_label}: close {c} is not positive",
                       field="Close", actual=c)
        vol = row.get("Volume")
        if vol is not None and not pd.isna(vol) and vol < 0:
            result.add("OHLCV_NEGATIVE_VOLUME", ERROR,
                       f"{date_label}: volume {vol} is negative",
                       field="Volume", actual=vol)
    return result


# ---------------------------------------------------------------------------
# Unit / scale reconciliation (contract: USD vs millions/billions, vendor drift)
# ---------------------------------------------------------------------------

_SCALES = {"unit": 1, "thousand": 1e3, "million": 1e6, "billion": 1e9}


def reconcile_metric(
    reported_value: float,
    derived_value: float,
    *,
    reported_unit: str,
    derived_unit: str,
    materiality_pct: float = 1.0,
) -> tuple[ValidationResult, float | None]:
    """Reconcile a vendor-reported metric against an independently derived one.

    Returns ``(result, reconciliation_delta_pct)``. The delta is the signed
    percentage difference after normalizing both sides to their base units;
    ``None`` when either side is unusable. A delta beyond ``materiality_pct``
    percent is an error (the datum is quarantined until reconciled); within
    it, a warning (usable, caveat surfaced).
    """
    result = ValidationResult()
    rep_scale = _SCALES.get(reported_unit.strip().lower())
    der_scale = _SCALES.get(derived_unit.strip().lower())
    if rep_scale is None or der_scale is None:
        result.add("UNIT_UNKNOWN", ERROR,
                   f"unknown unit {reported_unit!r}/{derived_unit!r}; cannot reconcile")
        return result, None
    if reported_value is None or derived_value is None:
        result.add("VALUE_MISSING", ERROR, "one side of the reconciliation is missing")
        return result, None

    rep_base = reported_value * rep_scale
    der_base = derived_value * der_scale
    if der_base == 0:
        result.add("RECONCILIATION_UNDEFINED", ERROR,
                   "derived value is zero; relative delta undefined")
        return result, None

    delta_pct = (rep_base - der_base) / abs(der_base) * 100
    if abs(delta_pct) > materiality_pct:
        result.add(
            "RECONCILIATION_MISMATCH", ERROR,
            f"reported {rep_base:,.0f} vs derived {der_base:,.0f} "
            f"({delta_pct:+.2f}%, materiality {materiality_pct}%)",
            expected=der_base, actual=rep_base,
        )
    elif delta_pct != 0:
        result.add(
            "RECONCILIATION_MINOR_DRIFT", WARNING,
            f"reported vs derived differ by {delta_pct:+.4f}% (within materiality)",
        )
    return result, delta_pct


# ---------------------------------------------------------------------------
# Currency consistency (contract: verify currency before dividing metrics)
# ---------------------------------------------------------------------------


def validate_currency_consistency(
    price_currency: str | None,
    metric_currency: str | None,
    *,
    profile=None,
) -> ValidationResult:
    """Check that a price and a per-share metric are in comparable currency units.

    A Milan-listed utility quotes in EUR and reports in EUR: consistent. A
    London listing quotes in GBp (pence) while per-share financials are in
    GBP: a direct ratio is wrong by 100x. When an :class:`InstrumentProfile`
    is supplied, the profiler's conversion factor resolves a minor-unit
    mismatch into a pass-with-conversion; without it, any mismatch is an
    error. Unknown currencies on either side are UNVERIFIED, not errors —
    the caller's fail-closed rule decides whether to proceed.
    """
    result = ValidationResult()
    if not price_currency or not metric_currency:
        result.add(
            "CURRENCY_UNKNOWN", WARNING,
            f"currency not reported (price: {price_currency!r}, metric: "
            f"{metric_currency!r}); ratios are unverified until known",
        )
        return result
    price_c, metric_c = price_currency.strip(), metric_currency.strip()
    if price_c == metric_c:
        return result
    # A minor-unit quote (GBp) against main-unit financials (GBP) is fine
    # with the profiler's conversion factor; without it, it is an error.
    if profile is not None and profile.currency_conversion is not None \
            and profile.per_share_currency() == metric_c:
        result.add(
            "CURRENCY_MINOR_UNIT", WARNING,
            f"price quoted in {price_c} (minor unit); metrics in {metric_c}: "
            f"apply the {profile.currency_conversion} factor before ratios",
        )
        return result
    result.add(
        "CURRENCY_MISMATCH", ERROR,
        f"price is in {price_c} but the metric is in {metric_c}: not "
        f"comparable without conversion",
        field="currency", expected=price_c, actual=metric_c,
    )
    return result


# ---------------------------------------------------------------------------
# Share-class conversion (contract: never mix class-A book value with class-B price)
# ---------------------------------------------------------------------------

# Class suffixes the identity checks recognize, shared with the profiler.
_CLASS_SUFFIXES = ("-A", "-B", "-C", ".A", ".B", ".C")


def convert_share_class(value: float, ratio: float, from_class: str, to_class: str) -> float:
    """Convert a per-share value between share classes by a fixed ratio.

    ``ratio`` is how many ``to_class`` shares one ``from_class`` share equals
    (BRK: 1 A = 1500 B). A per-A book value becomes per-B by dividing; per-B
    to per-A multiplies. The ratio comes from the vendor (the profiler reads
    it) or from a verified source — never derived from prices here.
    """
    if ratio <= 0:
        raise ValueError(f"conversion ratio must be positive, got {ratio}")
    pair = {from_class.upper(), to_class.upper()}
    if len(pair) != 2:
        raise ValueError("share classes must differ")
    return value / ratio if to_class.upper() == "B" else value * ratio


def validate_share_class_comparison(
    price: float, book_value_per_share: float, price_class: str, bvps_class: str
) -> ValidationResult:
    """Check a direct price-to-BVPS comparison across share classes.

    Comparing a class-B price to a class-A book value without conversion is
    the DEF-006 hazard: the ratio is 1500, so the resulting P/B is wrong by
    three orders of magnitude. Any cross-class comparison is an error unless
    the classes match.
    """
    result = ValidationResult()
    if price_class.upper() != bvps_class.upper():
        result.add(
            "SHARE_CLASS_MISMATCH", ERROR,
            f"price is per {price_class} share but book value is per {bvps_class} "
            f"share; convert before dividing (e.g. 1 A = {BRK_A_TO_B_RATIO} B)",
            field="share_class", expected=price_class, actual=bvps_class,
        )
    return result


# ---------------------------------------------------------------------------
# Ticker identity (contract: verify identity before dividing metrics)
# ---------------------------------------------------------------------------


def check_ticker_identity(requested: str, served: str, *, profile=None) -> ValidationResult:
    """Verify the served symbol is the requested instrument, not a sibling class.

    ``requested`` is what the user asked for; ``served`` is the canonical
    symbol the vendor actually served (after normalization). When an
    :class:`InstrumentProfile` is supplied, sibling-class detection comes
    from the profiler (structural, any ticker with a class suffix); without
    one, only an exact match passes and any other difference is a warning —
    normalization may legitimately rewrite a symbol (``700.HK`` ->
    ``0700.HK``), so a bare string mismatch is never an error on its own.
    """
    result = ValidationResult()
    req, srv = requested.strip().upper(), served.strip().upper()
    if req == srv:
        return result
    if profile is not None:
        root = profile.share_class_root
        own = profile.share_class
        if root and own:
            def _class_of(symbol: str) -> str | None:
                for suffix in _CLASS_SUFFIXES:
                    if symbol.endswith(suffix):
                        return suffix.lstrip("-.")
                    if symbol == f"{root}{suffix}":
                        return suffix
                return None
            served_class = _class_of(srv)
            if served_class is not None and served_class != own:
                result.add(
                    "TICKER_SIBLING_CLASS", ERROR,
                    f"requested {req} but vendor served {srv}: different share "
                    f"class of {root}, not interchangeable",
                    field="symbol", expected=req, actual=srv,
                )
                return result
    result.add("TICKER_REWRITTEN", WARNING,
               f"requested {req} was served as {srv} (normalization)")
    return result
