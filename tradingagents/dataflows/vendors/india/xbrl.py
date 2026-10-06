"""Results and shareholding-pattern filings, read from their XBRL.

NSE and BSE share the taxonomies, so a file saved from either reads the same:

    results      in-bse-fin (filings to December 2024; INDAS_*, BANKING_*)
                 in-capmkt  (SEBI's Integrated Filing, March 2025 on;
                             INTEGRATED_FILING_INDAS/BANKING/NBFC_INDAS_*)
    shareholding in-bse-shp (2020, 2022 and 2025 versions; SHP_*)

A results filing reports its own quarter, its year to date and, with the second
and fourth quarters, its balance sheet; none carries comparative columns. Three
things in the files are not what they seem, and each is handled here rather
than trusted:

- The in-bse-fin year-to-date context (``FourD``) declares the quarter's dates
  but holds year-to-date values. Each context's period is read from its own
  ``DateOfStartOfReportingPeriod`` / ``DateOfEndOfReportingPeriod`` facts.
- Shareholding percentages are percents (66.07) up to the 2022 taxonomy and
  fractions (0.5048) from 2025. The scale is read off the total row.
- Money is in rupees with ``decimals`` saying how it was rounded (-7 = crores).
  A filing whose values contradict their own rounding, or that reports money in
  another currency, is refused rather than mis-scaled.

When a filing became public (``filed_at``) is the point-in-time key. NSE names
each file with its submission time, ``..._16012025082021_WEB.xml`` for
16 Jan 2025 08:20:21, on a 12-hour clock without AM or PM; the reading not
before the board meeting's end is taken, else the later one. A file without
that stamp falls back to the board meeting's end plus the 30 minutes SEBI allows
for disclosure, then to the end of the meeting's day. A filing that gives no
date at all is refused: a guessed date would leak or hide it in an as-of read.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import PurePath

from tradingagents.dataflows.field_aliases import (
    ALIASES,
    XBRL_UNUSED,
    XBRL_UNUSED_INFIXES,
    XBRL_UNUSED_PREFIXES,
)

NS_XBRLI = "http://www.xbrl.org/2003/instance"
NS_XBRLDI = "http://xbrl.org/2006/xbrldi"
NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"
_SKIP_NS = {NS_XBRLI, "http://www.xbrl.org/2003/linkbase"}
NSE_XBRL_URL = "https://nsearchives.nseindia.com/corporate/xbrl/{name}"

# Duration of a context, in days, by the period type it stores as.
_SPANS = (("Q", 80, 100), ("H", 170, 190), ("N", 260, 290), ("A", 350, 380))
# The contexts a filing's own figures sit in, best first, when two give the same period.
_CONTEXT_ORDER = ("OneD", "OneI", "MainD", "MainI", "FourD", "FourI")
_UNITS = {"INR": "INR", "INR/SHARES": "INR/share", "PURE": "pure", "SHARES": "shares"}
DISCLOSURE_WINDOW = timedelta(minutes=30)  # SEBI LODR Reg. 33: results out within 30 minutes


class FilingError(ValueError):
    """A file that cannot be imported as it stands; the message says why."""


# --- The instance -----------------------------------------------------------------

@dataclass
class Context:
    id: str
    start: str | None = None
    end: str | None = None
    instant: str | None = None
    members: dict[str, str] = field(default_factory=dict)  # dimension -> member local name
    dimensioned: bool = False


@dataclass
class Fact:
    name: str
    namespace: str
    context: str
    unit: str | None
    decimals: str | None
    text: str

    @property
    def number(self) -> float | None:
        try:
            return float(self.text)
        except (TypeError, ValueError):
            return None


@dataclass
class Instance:
    namespaces: set[str]
    contexts: dict[str, Context]
    units: dict[str, str]
    facts: list[Fact]
    comment: str = ""

    def first(self, name: str, context: str | None = None) -> str | None:
        for fact in self.facts:
            if fact.name == name and (context is None or fact.context == context) and fact.text.strip():
                return fact.text.strip()
        return None


def _local(tag: str) -> tuple[str, str]:
    if tag.startswith("{"):
        ns, _, name = tag[1:].partition("}")
        return ns, name
    return "", tag


def read_instance(data: bytes) -> Instance:
    """The contexts, units and facts of an XBRL instance document."""
    head = data[:400].decode("utf-8", errors="replace")
    comment = m.group(1).strip() if (m := re.search(r"<!--(.*?)-->", head)) else ""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise FilingError(f"not well-formed XML: {exc}") from None
    if _local(root.tag) != (NS_XBRLI, "xbrl"):
        raise FilingError("not an XBRL instance (no xbrli:xbrl root)")
    contexts, units, facts, namespaces = {}, {}, [], set()
    for el in root:
        ns, name = _local(el.tag)
        if ns == NS_XBRLI and name == "context":
            ctx = Context(el.get("id", ""))
            for node in el.iter():
                kind = _local(node.tag)[1]
                if kind == "startDate":
                    ctx.start = (node.text or "").strip()[:10]
                elif kind == "endDate":
                    ctx.end = (node.text or "").strip()[:10]
                elif kind == "instant":
                    ctx.instant = (node.text or "").strip()[:10]
                elif kind == "explicitMember":
                    dimension = (node.get("dimension") or "").rpartition(":")[2]
                    ctx.members[dimension] = (node.text or "").strip().rpartition(":")[2]
                    ctx.dimensioned = True
                elif kind == "typedMember" or (kind in ("segment", "scenario") and len(node)):
                    ctx.dimensioned = True
            contexts[ctx.id] = ctx
        elif ns == NS_XBRLI and name == "unit":
            measures = [m.text.strip().rpartition(":")[2] for m in el.iter()
                        if _local(m.tag)[1] == "measure" and m.text]
            units[el.get("id", "")] = "/".join(measures)  # INR, pure, shares; INR/shares for a divide
        elif ns not in _SKIP_NS and el.get("contextRef"):
            namespaces.add(ns)
            if el.get(f"{{{NS_XSI}}}nil") == "true":
                continue
            facts.append(Fact(name, ns, el.get("contextRef"), el.get("unitRef"), el.get("decimals"),
                              (el.text or "").strip()))
    return Instance(namespaces, contexts, units, facts, comment)


def detect_kind(instance: Instance) -> str | None:
    """'results', 'shareholding' or None for a filing this layer does not read."""
    if any("/xbrl/shp/" in ns for ns in instance.namespaces):
        return "shareholding"
    if any(("in-bse-fin" in ns or "in-capmkt" in ns) for ns in instance.namespaces):
        names = {f.name for f in instance.facts}
        if "NatureOfReportStandaloneConsolidated" in names or names & {"RevenueFromOperations", "InterestEarned"}:
            return "results"
    return None


# --- When it was filed --------------------------------------------------------------

_STAMP = re.compile(r"_(\d{2})(\d{2})(\d{4})(\d{2})(\d{2})(\d{2})(?:_WEB)?$", re.IGNORECASE)


def filename_stamp(filename: str) -> tuple[date, list[datetime]] | None:
    """The submission date in an NSE file name and the times it can stand for
    (two on a 12-hour clock, one past 12)."""
    match = _STAMP.search(PurePath(filename).stem)
    if not match:
        return None
    dd, mm, yyyy, hh, mi, ss = (int(g) for g in match.groups())
    try:
        day = date(yyyy, mm, dd)
        clock = [hh] if hh > 12 else sorted({hh % 12, hh % 12 + 12})
        return day, [datetime.combine(day, time(h, mi, ss)) for h in clock]
    except ValueError:
        return None


def _meeting_end(instance: Instance) -> datetime | None:
    day = instance.first("DateOfEndOfBoardMeeting") or instance.first("DateOfBoardMeetingWhenFinancialResultsWereApproved")
    clock = instance.first("EndTimeOfBoardMeeting")
    if not day:
        return None
    try:
        when = datetime.fromisoformat(day[:10])
        if clock:
            h, m, *s = (int(x) for x in clock.split(":"))
            when = when.replace(hour=h, minute=m, second=s[0] if s else 0)
        return when
    except ValueError:
        return None


def filed_at(filename: str, instance: Instance, override: str | None = None) -> tuple[str, str]:
    """(ISO timestamp, how it was worked out) for when the filing became public,
    in India time. Raises FilingError when the filing gives no date to go by."""
    if override:
        return _iso(override), "given on import"
    meeting = _meeting_end(instance)
    stamp = filename_stamp(filename)
    if stamp is not None:
        day, readings = stamp
        if len(readings) == 1:
            return readings[0].isoformat(), "file name (submission time)"
        if meeting is not None and meeting.date() == day:
            chosen = next((r for r in readings if r >= meeting), readings[-1])
            return chosen.isoformat(), "file name (submission time; AM/PM from the board meeting's end)"
        return readings[-1].isoformat(), "file name (submission time; the later of AM/PM)"
    if meeting is not None and instance.first("EndTimeOfBoardMeeting"):
        return (meeting + DISCLOSURE_WINDOW).isoformat(), "board meeting end + 30 minutes"
    if meeting is not None:
        return f"{meeting.date().isoformat()}T23:59:59", "board meeting date (end of day)"
    raise FilingError("no submission time in the file name and no board meeting date in the filing; "
                      "import it with --filed-at")


def _iso(value: str) -> str:
    text = value.strip().replace(" ", "T")
    when = datetime.fromisoformat(text) if "T" in text else datetime.combine(date.fromisoformat(text), time(23, 59, 59))
    return when.replace(tzinfo=None).isoformat(timespec="seconds")


# --- Results ------------------------------------------------------------------------

@dataclass
class ResultsFiling:
    filing_id: str
    isin: str | None
    symbol: str | None
    scrip_code: str | None
    name: str | None
    basis: str  # standalone | consolidated
    format: str  # indas | banking | nbfc
    period_end: str
    filed_at: str
    filed_at_basis: str
    taxonomy: str
    rows: list[tuple[str, str, str | None, str, float, str]]  # (end, type, start, field, value, unit)
    unknown: Counter = field(default_factory=Counter)
    url: str | None = None

    @property
    def financial(self) -> bool:
        return self.format in ("banking", "nbfc")


def _format(instance: Instance, filename: str) -> str:
    upper = filename.upper()
    names = {f.name for f in instance.facts}
    if "BANKING" in upper or "IFBANKING" in instance.comment.upper() or "InterestExpended" in names:
        return "banking"
    if "NBFC" in upper or "IFNBFC" in instance.comment.upper() or (
            "InterestEarned" in names and "FinanceCosts" in names):
        return "nbfc"
    return "indas"


def _taxonomy(instance: Instance) -> str:
    for ns in sorted(instance.namespaces):
        if "in-capmkt" in ns or "in-bse-fin" in ns or "in-bse-shp" in ns:
            return ns
    return ""


def _span_type(start: str, end: str) -> str | None:
    days = (date.fromisoformat(end) - date.fromisoformat(start)).days
    return next((kind for kind, low, high in _SPANS if low <= days <= high), None)


def pick(get, alternatives):
    """The first alternative ``get`` has a value for; a tuple sums those present."""
    for alternative in alternatives:
        if isinstance(alternative, tuple):
            parts = [v for v in map(get, alternative) if v is not None]
            if parts:
                return sum(parts)
        elif (value := get(alternative)) is not None:
            return value
    return None


def _tags(alternatives) -> set[str]:
    out = set()
    for alternative in alternatives:
        out |= set(alternative) if isinstance(alternative, tuple) else {alternative}
    return out


_RESULT_TAGS = set().union(*(_tags(alts) for section in ALIASES["xbrl"].values() for alts in section.values()))


def _is_known(name: str) -> bool:
    return (name in _RESULT_TAGS or name in XBRL_UNUSED or name.startswith(XBRL_UNUSED_PREFIXES)
            or any(infix in name for infix in XBRL_UNUSED_INFIXES))


def _unit_of(instance: Instance, fact: Fact) -> str:
    measure = instance.units.get(fact.unit or "", "")
    return _UNITS.get(measure.upper(), measure)


def _check_money(instance: Instance, facts: list[Fact]) -> None:
    """Refuse money in another currency, or values that contradict their own
    rounding (a filing in crores declared as rupees, say)."""
    for f in facts:
        currency = instance.units.get(f.unit or "", "").split("/")[0]
        if currency.upper() not in ("INR", "PURE", "SHARES", ""):
            raise FilingError(f"money reported in {currency}, not rupees")
    checked = bad = 0
    for f in facts:
        if instance.units.get(f.unit or "", "").upper() != "INR" or not f.decimals:
            continue
        try:
            decimals = int(f.decimals)
        except ValueError:
            continue  # INF: exact
        value = f.number
        if decimals >= 0 or value is None or value == 0:
            continue
        checked += 1
        step = 10 ** (-decimals)
        if abs(value) < step or abs(round(value / step) * step - value) > step * 1e-6:
            bad += 1
    if checked >= 5 and bad > checked * 0.2:
        raise FilingError(f"{bad} of {checked} rupee figures contradict their stated rounding; "
                          "the filing may be in lakhs or crores rather than rupees")


def _derive(fields: dict[str, float], raw: dict[str, float], fmt: str, kind: str) -> None:
    """The fields ``field_aliases.XBRL_DERIVED`` lists, in place."""
    if kind == "income":
        if fmt == "indas" and "Expenses" in raw and "FinanceCosts" in raw:
            fields["total_expenses"] = raw["Expenses"] - raw["FinanceCosts"]
        if fmt == "banking":
            if "InterestEarned" in raw and "InterestExpended" in raw:
                fields["net_interest_income"] = raw["InterestEarned"] - raw["InterestExpended"]
            if "Income" in raw and "InterestExpended" in raw:
                fields["sales"] = raw["Income"] - raw["InterestExpended"]
        if fmt == "nbfc":
            if "InterestEarned" in raw and "FinanceCosts" in raw:
                fields["net_interest_income"] = raw["InterestEarned"] - raw["FinanceCosts"]
            if "Income" in raw and "FinanceCosts" in raw:
                fields["sales"] = raw["Income"] - raw["FinanceCosts"]
            else:
                fields.pop("sales", None)
        if "net_income" not in fields and "net_profit" in fields:
            fields["net_income"] = fields["net_profit"]
    elif kind == "cashflow" and "operating" in fields and "capex" in fields:
        fields["free_cash_flow"] = fields["operating"] - fields["capex"]


_FIELD_UNITS = {"eps": "INR/share", "eps_basic": "INR/share", "face_value": "INR/share",
                "gross_npa_ratio": "pure", "net_npa_ratio": "pure", "cet1_ratio": "pure",
                "return_on_assets": "pure"}


def parse_results(data: bytes, filename: str, filed_at_override: str | None = None,
                  instance: Instance | None = None) -> ResultsFiling:
    instance = instance or read_instance(data)
    if detect_kind(instance) != "results":
        raise FilingError("not a financial results filing")
    fmt = _format(instance, filename)
    plain = {cid: c for cid, c in instance.contexts.items() if not c.dimensioned}
    by_context: dict[str, list[Fact]] = {}
    for fact in instance.facts:
        if fact.context in plain:
            by_context.setdefault(fact.context, []).append(fact)

    def own_period(cid: str) -> tuple[str | None, str | None]:
        ctx = plain[cid]
        start = instance.first("DateOfStartOfReportingPeriod", cid) or ctx.start
        end = instance.first("DateOfEndOfReportingPeriod", cid) or ctx.end
        return start, end

    lead = next((c for c in _CONTEXT_ORDER if c in plain and plain[c].instant is None), None) or next(
        (cid for cid, c in plain.items() if c.instant is None), None)
    if lead is None:
        raise FilingError("no reporting period in the filing")
    period_end = own_period(lead)[1]
    basis_text = (instance.first("NatureOfReportStandaloneConsolidated") or "").lower()
    basis = "consolidated" if basis_text.startswith("consolidated") else "standalone" \
        if basis_text.startswith(("standalone", "non")) else None
    if basis is None:
        raise FilingError("the filing does not say whether it is standalone or consolidated")
    currency = (instance.first("DescriptionOfPresentationCurrency") or "INR").upper()
    if currency not in ("INR", "RUPEES", "RS", "INDIAN RUPEE"):
        raise FilingError(f"presentation currency {currency}, not rupees")

    used_facts = []
    periods: dict[tuple[str, str], tuple[str | None, dict[str, Fact]]] = {}
    order = sorted(plain, key=lambda c: (_CONTEXT_ORDER.index(c) if c in _CONTEXT_ORDER else 99, c))
    for cid in order:
        ctx = plain[cid]
        facts = [f for f in by_context.get(cid, []) if f.unit]
        if not facts:
            continue
        if ctx.instant is not None:
            if ctx.instant != period_end:
                continue
            key, start = (period_end, "I"), None
        else:
            start, end = own_period(cid)
            if end != period_end or not start or (kind := _span_type(start, end)) is None:
                continue
            key = (end, kind)
        _, seen = periods.setdefault(key, (start, {}))
        for fact in facts:
            seen.setdefault(fact.name, fact)
            used_facts.append(fact)
    _check_money(instance, used_facts)

    rows, unknown = [], Counter()
    for (end, kind), (start, facts) in sorted(periods.items()):
        raw = {name: n for name, f in facts.items() if (n := f.number) is not None}
        units = {name: _unit_of(instance, f) for name, f in facts.items()}
        sections = ("balance",) if kind == "I" else ("income", "cashflow")
        for section in sections:
            fields = {name: v for name, alts in ALIASES["xbrl"][section].items()
                      if (v := pick(raw.get, alts)) is not None}
            _derive(fields, raw, fmt, section)
            for name, value in fields.items():
                alts = ALIASES["xbrl"][section].get(name, ())
                unit = _FIELD_UNITS.get(name) or next(
                    (units[t] for t in _tags(alts) if t in units), "INR")
                rows.append((end, kind, start, name, float(value), unit))
        unknown.update(name for name in raw if not _is_known(name))

    name = PurePath(filename).name
    stamp, how = filed_at(name, instance, filed_at_override)
    return ResultsFiling(
        filing_id=PurePath(filename).stem, isin=instance.first("ISIN"), symbol=instance.first("Symbol"),
        scrip_code=instance.first("ScripCode"),
        name=instance.first("NameOfTheCompany") or instance.first("NameOfBank"), basis=basis, format=fmt,
        period_end=period_end, filed_at=stamp, filed_at_basis=how, taxonomy=_taxonomy(instance),
        rows=rows, unknown=unknown,
        url=NSE_XBRL_URL.format(name=name) if filename_stamp(name) else None)


# --- Shareholding --------------------------------------------------------------------

@dataclass
class ShareholdingFiling:
    filing_id: str
    isin: str | None
    symbol: str | None
    scrip_code: str | None
    name: str | None
    quarter_end: str
    filed_at: str
    filed_at_basis: str
    taxonomy: str
    values: dict[str, float | None]
    url: str | None = None
    warnings: list[str] = field(default_factory=list)


_CATEGORY_AXIS = "CategoryOfShareholdersAxis"
_PLEDGED = ("EncumberedShareUnderPledgedAsPercentageOfTotalNumberOfShares",)
_ENCUMBERED = ("EncumberedSharesHeldAsPercentageOfTotalNumberOfShares",
               "PledgedOrEncumberedSharesHeldAsPercentageOfTotalNumberOfShares")
_NO_PLEDGE_FLAGS = ("WhetherAnySharesHeldByPromotersAreEncumberedUnderPledgedForPromoterAndPromoterGroup",
                    "WhetherAnySharesHeldByPromotersAreEncumberedUnderPledged",
                    "WhetherAnySharesHeldByPromotersArePledgeOrOtherwiseEncumberedForPromoterAndPromoterGroup",
                    "WhetherAnySharesHeldByPromotersArePledgeOrOtherwiseEncumbered")


def parse_shareholding(data: bytes, filename: str, filed_at_override: str | None = None,
                       instance: Instance | None = None) -> ShareholdingFiling:
    instance = instance or read_instance(data)
    if detect_kind(instance) != "shareholding":
        raise FilingError("not a shareholding pattern filing")
    category = {cid: c.members[_CATEGORY_AXIS] for cid, c in instance.contexts.items()
                if len(c.members) == 1 and _CATEGORY_AXIS in c.members}
    pct, holders, shares, by_member = {}, {}, {}, {}
    for fact in instance.facts:
        member = category.get(fact.context)
        if member is None or (value := fact.number) is None:
            continue
        by_member.setdefault(member, {}).setdefault(fact.name, value)
        if fact.name == "ShareholdingAsAPercentageOfTotalNumberOfShares":
            pct.setdefault(member, value)
        elif fact.name == "NumberOfShareholders":
            holders.setdefault(member, value)
        elif fact.name == "NumberOfShares":
            shares.setdefault(member, value)
    aliases = ALIASES["shareholding"]
    total = pick(pct.get, aliases["total"])
    promoter, public_total = pct.get("ShareholdingOfPromoterAndPromoterGroupMember"), pct.get("PublicShareholdingMember")
    reference = total if total is not None else (
        promoter + public_total if promoter is not None and public_total is not None else None)
    if reference is None:
        raise FilingError("no category totals in the shareholding pattern")
    scale = 100.0 if abs(reference - 1) < 0.05 else 1.0 if abs(reference - 100) < 5 else None
    if scale is None:
        raise FilingError(f"shareholding percentages total {reference}, neither 1 nor 100")

    def pct_of(name: str):
        value = pick(pct.get, aliases[name])
        return None if value is None else round(value * scale, 4)

    values = {name: pct_of(name) for name in ("promoter_pct", "fii_pct", "dii_pct", "govt_pct",
                                               "public_pct", "others_pct")}
    if values["dii_pct"] is None and (institutions := pct.get("InstitutionsMember")) is not None:
        foreign = pick(pct.get, aliases["fii_pct"]) or 0.0
        values["dii_pct"] = round((institutions - foreign) * scale, 4)
    promoter_facts = by_member.get("ShareholdingOfPromoterAndPromoterGroupMember", {})
    pledged = pick(promoter_facts.get, _PLEDGED)
    encumbered = pick(promoter_facts.get, _ENCUMBERED)
    no_pledge = any((instance.first(flag) or "").lower() in ("false", "no") for flag in _NO_PLEDGE_FLAGS)
    values["pledged_pct"] = round(pledged * scale, 4) if pledged is not None else (0.0 if no_pledge else None)
    values["encumbered_pct"] = (round(encumbered * scale, 4) if encumbered is not None
                                else (0.0 if no_pledge else None))
    values["num_shareholders"] = pick(holders.get, aliases["total"])
    values["total_shares"] = pick(shares.get, aliases["total"])

    parts = [values[k] for k in ("promoter_pct", "fii_pct", "dii_pct", "govt_pct", "public_pct")]
    warnings = []
    if all(v is not None for v in parts) and abs(sum(parts) + (values["others_pct"] or 0) - 100) > 1.0:
        warnings.append(f"categories add up to {sum(parts) + (values['others_pct'] or 0):.2f}%, not 100%")

    quarter_end = instance.first("DateOfReport")
    if not quarter_end:
        raise FilingError("the shareholding pattern has no report date")
    name = PurePath(filename).name
    stamp, how = filed_at(name, instance, filed_at_override)
    return ShareholdingFiling(
        filing_id=PurePath(filename).stem, isin=instance.first("ISIN"), symbol=instance.first("Symbol"),
        scrip_code=instance.first("ScripCode"), name=instance.first("NameOfTheCompany"),
        quarter_end=quarter_end[:10], filed_at=stamp, filed_at_basis=how, taxonomy=_taxonomy(instance),
        values=values, url=NSE_XBRL_URL.format(name=name) if filename_stamp(name) else None,
        warnings=warnings)


def parse_filing(data: bytes, filename: str, filed_at_override: str | None = None):
    """A results or shareholding filing, whichever the file is."""
    instance = read_instance(data)
    kind = detect_kind(instance)
    if kind == "results":
        return parse_results(data, filename, filed_at_override, instance)
    if kind == "shareholding":
        return parse_shareholding(data, filename, filed_at_override, instance)
    raise FilingError("neither a results nor a shareholding pattern filing")
