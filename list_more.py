"""List the next tranche of screened candidates without trend kline fetches."""

from __future__ import annotations

import math
import sys

from pick_five_sina import fetch_quotes


ANALYZED = {
    "601665", "601083", "000902", "603529", "600583",
    "601058", "600901", "605599", "603939", "000923",
    "603565", "600801", "601918", "600177", "600531",
    "603198", "600795", "601077", "601838", "601825",
}


def score(per: float, pb: float, cap_yi: float, amount: float, turnover: float) -> float:
    s = 0.0
    if 0 < per <= 30:
        s += (30 - per) / 30 * 3
    if 0 < pb <= 5:
        s += (5 - pb) / 5 * 1.5
    if 80 <= cap_yi <= 600:
        s += 1.0
    elif 40 <= cap_yi < 80 or 600 < cap_yi <= 1000:
        s += 0.5
    if amount:
        s += min(math.log10(max(amount, 1)), 9.5) / 9.5 * 0.8
    if turnover:
        s += min(turnover, 10) / 10 * 0.5
    return round(s, 3)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    quotes = fetch_quotes()
    rows = []
    for row in quotes:
        code = str(row.get("code", ""))
        name = str(row.get("name", ""))
        if not code.startswith(("60", "000")):
            continue
        if code in ANALYZED or "ST" in name.upper() or "退" in name:
            continue
        try:
            price = float(row.get("trade") or 0)
            amount = float(row.get("amount") or 0)
            per = float(row.get("per") or 0)
            pb = float(row.get("pb") or 0)
            cap_yi = float(row.get("mktcap") or 0) / 10000
            turnover = float(row.get("turnoverratio") or 0)
        except (TypeError, ValueError):
            continue
        if price <= 0 or amount < 2e8:
            continue
        if not (50 <= cap_yi <= 1000) or not (0 < per <= 30) or not (0 < pb <= 5):
            continue
        if turnover <= 0.3:
            continue
        rows.append(
            {
                "code": code,
                "symbol": row["symbol"],
                "name": name,
                "price": price,
                "per": per,
                "pb": pb,
                "cap_yi": cap_yi,
                "amount_yi": amount / 1e8,
                "turnover": turnover,
                "score": score(per, pb, cap_yi, amount, turnover),
            }
        )

    rows.sort(key=lambda r: r["score"], reverse=True)
    for i, r in enumerate(rows[:60], 1):
        print(
            f"{i:02d}. {r['code']} {r['name']} price={r['price']:.2f} "
            f"pe={r['per']:.2f} pb={r['pb']:.2f} cap={r['cap_yi']:.0f} "
            f"amount={r['amount_yi']:.2f} turnover={r['turnover']:.2f} "
            f"score={r['score']}"
        )


if __name__ == "__main__":
    main()
