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
        o, h, l, c = row["Open"], row["High"], row["Low"], row["Close"]
        date_label = row.get("Date", idx)
        # A row with no close is an unsettled session, not corruption: the
        # loader already handles trailing unsettled bars (#1201/#1289).
        if pd.isna(o) and pd.isna(h) and pd.isna(l) and pd.isna(c):
            continue
        if pd.isna(h) or pd.isna(l):
            result.add("OHLCV_MISSING_HL", ERROR,
                       f"{date_label}: high/low missing on a priced row",
                       field="High/Low")
            continue
        if h < l:
            result.add("OHLCV_INVERTED_RANGE", ERROR,
                       f"{date_label}: high {h} < low {l}",
                       field="High", expected=">= low", actual=h)
        if not pd.isna(o) and not pd.isna(c):
            lo, hi = min(o, c), max(o, c)
            if l > lo or (not pd.isna(h) and h < hi):
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
# Share-class conversion (contract: never mix BRK-A book value with BRK-B price)
# ---------------------------------------------------------------------------


def convert_share_class(value: float, ratio: float, from_class: str, to_class: str) -> float:
    """Convert a per-share value between share classes by a fixed ratio.

    ``ratio`` is how many ``to_class`` shares one ``from_class`` share equals
    (BRK: 1 A = 1500 B). A per-A book value becomes per-B by dividing; per-B
    to per-A multiplies.
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

# Tickers that share a root but are different instruments. A validator that
# only string-matches the root would serve one class's data for the other.
_SHARE_CLASS_SIBLINGS = {
    "BRK": ("BRK-A", "BRK-B"),
}


def check_ticker_identity(requested: str, served: str) -> ValidationResult:
    """Verify the served symbol is the requested instrument, not a sibling class.

    ``requested`` is what the user asked for; ``served`` is the canonical
    symbol the vendor actually served (after normalization). A mismatch is
    an error when the two are known share-class siblings, a warning when
    they merely differ (normalization may legitimately rewrite the symbol).
    """
    result = ValidationResult()
    req, srv = requested.strip().upper(), served.strip().upper()
    if req == srv:
        return result
    root_req = req.split("-")[0].split(".")[0]
    for sibling_pair in _SHARE_CLASS_SIBLINGS.values():
        if req in sibling_pair and srv in sibling_pair and req != srv:
            result.add(
                "TICKER_SIBLING_CLASS", ERROR,
                f"requested {req} but vendor served {srv}: different share class, "
                f"not interchangeable",
                field="symbol", expected=req, actual=srv,
            )
            return result
    result.add("TICKER_REWRITTEN", WARNING,
               f"requested {req} was served as {srv} (normalization)")
    return result
