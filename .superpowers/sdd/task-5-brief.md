# Task 5: Add Detailed Notification Messages

**Files:**
- Modify: `web/server/notifier.py:218-258`

**Interfaces:**
- Consumes: Indicator check results with `ticker_price` kind
- Produces: `build_ticker_price_message()` function

- [ ] **Step 1: Add `build_ticker_price_message()` function**

```python
# web/server/notifier.py - add after build_change_message()
def build_ticker_price_message(check: dict) -> str:
    """Build a detailed HTML Telegram message for a ticker price alert.
    
    ``check`` is a single check dict from ``run_checks()`` with indicator kind ``ticker_price``.
    """
    now = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
    ind = check.get("indicator", {})
    result = check.get("result") or {}
    
    ticker = ind.get("ticker", "???")
    threshold = ind.get("threshold", 0)
    comparator = ind.get("comparator", "above")
    message = result.get("message", "")
    value = result.get("value", {})
    
    # Parse price data from value
    if isinstance(value, dict):
        price = value.get("price", 0)
        change_pct = value.get("change_pct", 0)
        day_high = value.get("day_high", price)
        day_low = value.get("day_low", price)
    else:
        price = float(value) if value else 0
        change_pct = 0
        day_high = price
        day_low = price
    
    # Build comparator text
    comparator_text = {
        "above": "above",
        "below": "below",
        "at_least": "at least",
        "within": "within",
    }.get(comparator, comparator)
    
    lines = [
        f"🚨 <b>Price Alert: {_e(ticker)}</b>",
        f"<i>{_e(now)}</i>",
        "",
        f"<b>Price:</b> ${price:.2f} ({comparator_text} your ${threshold:.2f} target)",
        f"<b>Change:</b> {change_pct:+.2f}% today",
        f"<b>Day Range:</b> ${day_low:.2f} - ${day_high:.2f}",
        "",
        "<i>Automated price alert. Not financial advice.</i>",
    ]
    return "\n".join(lines)
```

- [ ] **Step 2: Update `build_change_message()` to use detailed format for ticker_price alerts**

```python
# web/server/notifier.py line 227-258
def build_change_message(diff: dict) -> str:
    """Build an HTML Telegram message describing what changed.
    
    ``diff`` is the dict returned by ``storage.diff_indicator_states()``.
    """
    now = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"📊 <b>TradingAgents Indicators — Signal Update</b>\n<i>{_e(now)}</i>\n"]

    new_checks = diff.get("newly_triggered", [])
    resolved_checks = diff.get("resolved", [])
    still_checks = diff.get("still_active", [])

    if new_checks:
        lines.append("🚨 <b>New Signals</b>")
        for c in new_checks:
            ind = c.get("indicator", {})
            if ind.get("kind") == "ticker_price":
                # Use detailed message for ticker_price alerts
                lines.append(_ticker_price_inline(c))
            else:
                lines.append(f"• {_check_to_line(c)}")
        lines.append("")

    if resolved_checks:
        lines.append("✅ <b>Resolved</b>")
        for c in resolved_checks:
            lines.append(f"• {_check_to_line(c)}")
        lines.append("")

    if still_checks:
        lines.append("ℹ️ <b>Still Active</b>")
        for c in still_checks:
            lines.append(f"• {_check_to_line(c)}")
        lines.append("")

    lines.append("<i>Automated indicator alert. Not financial advice.</i>")
    return "\n".join(lines)


def _ticker_price_inline(check: dict) -> str:
    """Format a ticker_price alert as an inline HTML line."""
    ind = check.get("indicator", {})
    result = check.get("result") or {}
    ticker = ind.get("ticker", "???")
    threshold = ind.get("threshold", 0)
    comparator = ind.get("comparator", "above")
    value = result.get("value", {})
    
    if isinstance(value, dict):
        price = value.get("price", 0)
        change_pct = value.get("change_pct", 0)
    else:
        price = float(value) if value else 0
        change_pct = 0
    
    comparator_symbol = {"above": ">", "below": "<", "at_least": ">=", "within": "~"}.get(comparator, "?")
    return f"• <b>{_e(ticker)}</b> ${price:.2f} ({comparator_symbol} ${threshold:.2f}) {change_pct:+.2f}%"
```

- [ ] **Step 3: Commit**

```bash
git add web/server/notifier.py
git commit -m "feat: add detailed ticker price notification messages"
```
