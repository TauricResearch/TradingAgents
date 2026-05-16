# Flight Tracker Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Daily automated flight price tracker — searches JFK↔JNB via SerpAPI, emails fewest-stops and cheapest picks for each leg, commits results to history.csv.

**Architecture:** Standalone `flight_tracker/` module triggered by GitHub Actions cron at 07:17 UTC. `tracker.py` orchestrates search → select → email → history. Always exits 0; errors go to alert email + empty history row. Workflow commits `history.csv` back to repo after each run.

**Tech Stack:** Python 3.12, SerpAPI (`google-search-results`), `smtplib` + `ssl` (stdlib), GitHub Actions, Gmail SMTP port 587 STARTTLS.

---

## File Map

| File | Purpose |
|---|---|
| `flight_tracker/__init__.py` | Package marker (empty) |
| `flight_tracker/requirements.txt` | `google-search-results>=2.4.2` |
| `flight_tracker/config.py` | Reads all 8 env vars; raises `KeyError` on missing |
| `flight_tracker/search.py` | SerpAPI call + normalize response → `list[Flight]` |
| `flight_tracker/select.py` | Picks fewest-stops + cheapest from `list[Flight]` |
| `flight_tracker/email_report.py` | Builds HTML report + sends via SMTP |
| `flight_tracker/tracker.py` | Entrypoint — orchestrates all modules; exits 0 always |
| `flight_tracker/history.csv` | Initial file with header row only |
| `.github/workflows/flight_tracker.yml` | Cron workflow with commit step |
| `tests/test_flight_search.py` | Unit tests for normalization logic |
| `tests/test_flight_select.py` | Unit tests for selection logic |
| `tests/test_flight_email.py` | Unit tests for HTML formatting |
| `tests/test_flight_history.py` | Unit tests for CSV read/write/dedup logic |
| `tests/test_flight_tracker_errors.py` | Unit tests for quota detection + error propagation |

---

## Chunk 1: Data Pipeline (search + select)

### Task 1: Scaffold

**Files:**
- Create: `flight_tracker/__init__.py`
- Create: `flight_tracker/requirements.txt`
- Create: `flight_tracker/config.py`

- [ ] **Step 1: Create package files**

`flight_tracker/__init__.py` — empty file.

`flight_tracker/requirements.txt`:
```
google-search-results>=2.4.2
```

`flight_tracker/config.py`:
```python
import os


def get_config() -> dict:
    return {
        "serpapi_key": os.environ["SERPAPI_KEY"],
        "gmail_user": os.environ["GMAIL_USER"],
        "gmail_app_password": os.environ["GMAIL_APP_PASSWORD"],
        "alert_email": os.environ["ALERT_EMAIL"],
        "origin": os.environ["ORIGIN"],
        "destination": os.environ["DESTINATION"],
        "outbound_date": os.environ["OUTBOUND_DATE"],
        "return_date": os.environ["RETURN_DATE"],
    }
```

- [ ] **Step 2: Commit scaffold**

```bash
git add flight_tracker/
git commit -m "feat(flight-tracker): scaffold package, config, requirements"
```

---

### Task 2: Search normalization (TDD)

**Files:**
- Create: `flight_tracker/search.py`
- Create: `tests/test_flight_search.py`

- [ ] **Step 1: Write failing tests**

`tests/test_flight_search.py`:
```python
import unittest
import pytest
from flight_tracker.search import Flight, _normalize_response


@pytest.mark.unit
class TestNormalizeResponse(unittest.TestCase):
    def _make_item(self, price=980, layovers=None, duration=900, airline="Delta", departs="18:30"):
        return {
            "price": price,
            "layovers": layovers or [],
            "total_duration": duration,
            "flights": [
                {"airline": airline, "departure_airport": {"time": departs}}
            ],
        }

    def test_extracts_flight_fields(self):
        item = self._make_item(price=980, layovers=[{}], duration=900, airline="Delta", departs="18:30")
        flights = _normalize_response({"best_flights": [item]})
        self.assertEqual(len(flights), 1)
        f = flights[0]
        self.assertEqual(f.price, 980)
        self.assertEqual(f.stops, 1)
        self.assertEqual(f.duration_min, 900)
        self.assertEqual(f.airline, "Delta")
        self.assertEqual(f.departs, "18:30")

    def test_combines_best_and_other_flights(self):
        item1 = self._make_item(price=800)
        item2 = self._make_item(price=1200)
        flights = _normalize_response({"best_flights": [item1], "other_flights": [item2]})
        self.assertEqual(len(flights), 2)

    def test_missing_best_flights_key(self):
        item = self._make_item(price=700)
        flights = _normalize_response({"other_flights": [item]})
        self.assertEqual(len(flights), 1)

    def test_missing_other_flights_key(self):
        item = self._make_item(price=700)
        flights = _normalize_response({"best_flights": [item]})
        self.assertEqual(len(flights), 1)

    def test_empty_response_returns_empty_list(self):
        self.assertEqual(_normalize_response({}), [])

    def test_skips_items_with_no_price(self):
        item = self._make_item(price=None)
        flights = _normalize_response({"best_flights": [item]})
        self.assertEqual(flights, [])

    def test_nonstop_has_zero_stops_empty_list(self):
        item = self._make_item(layovers=[])
        flights = _normalize_response({"best_flights": [item]})
        self.assertEqual(flights[0].stops, 0)

    def test_nonstop_has_zero_stops_absent_key(self):
        item = self._make_item(layovers=[])
        del item["layovers"]  # key absent entirely — SerpAPI may omit it for nonstops
        flights = _normalize_response({"best_flights": [item]})
        self.assertEqual(flights[0].stops, 0)

    def test_two_stops(self):
        item = self._make_item(layovers=[{}, {}])
        flights = _normalize_response({"best_flights": [item]})
        self.assertEqual(flights[0].stops, 2)

    def test_skips_malformed_item_missing_flights_key(self):
        good = self._make_item(price=800)
        bad = {"price": 500, "layovers": [], "total_duration": 600}  # no "flights" key
        flights = _normalize_response({"best_flights": [bad, good]})
        self.assertEqual(len(flights), 1)
        self.assertEqual(flights[0].price, 800)

    def test_skips_malformed_item_empty_flights_list(self):
        good = self._make_item(price=800)
        bad = {"price": 500, "layovers": [], "total_duration": 600, "flights": []}
        flights = _normalize_response({"best_flights": [bad, good]})
        self.assertEqual(len(flights), 1)
        self.assertEqual(flights[0].price, 800)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run — verify FAIL**

```bash
cd C:\Users\geoff\GitHub\TradingAgents\.claude\worktrees\silly-sammet-af6e7a
pytest tests/test_flight_search.py -v -m unit
```

Expected: `ImportError: No module named 'flight_tracker.search'`

- [ ] **Step 3: Implement `search.py`**

`flight_tracker/search.py`:
```python
from collections import namedtuple
from serpapi import GoogleSearch

Flight = namedtuple("Flight", ["price", "stops", "duration_min", "airline", "departs"])


def _normalize_response(response: dict) -> list:
    items = response.get("best_flights", []) + response.get("other_flights", [])
    flights = []
    for item in items:
        price = item.get("price")
        if price is None:
            continue
        try:
            flights.append(Flight(
                price=price,
                stops=len(item.get("layovers", [])),
                duration_min=item.get("total_duration") or 0,  # None → 0 (key present with null value)
                airline=item["flights"][0]["airline"],
                departs=item["flights"][0]["departure_airport"]["time"],
            ))
        except (IndexError, KeyError):
            continue  # skip items where SerpAPI omits expected sub-fields
    return flights


def search_flights(origin: str, destination: str, date: str, api_key: str) -> list:
    params = {
        "engine": "google_flights",
        "departure_id": origin,
        "arrival_id": destination,
        "outbound_date": date,
        "type": "2",       # one-way — required for per-leg pricing (default is round-trip bundled)
        "currency": "USD",
        "hl": "en",
        "api_key": api_key,
    }
    search = GoogleSearch(params)
    return _normalize_response(search.get_dict())
```

- [ ] **Step 4: Install package**

```bash
pip install -r flight_tracker/requirements.txt
```

(Never use `pip install google-search-results>=2.4.2` unquoted — `>` is a shell redirect operator and will truncate a file named `2.4.2` instead of installing.)

- [ ] **Step 5: Run — verify PASS**

```bash
pytest tests/test_flight_search.py -v -m unit
```

Expected: All 11 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add flight_tracker/search.py tests/test_flight_search.py
git commit -m "feat(flight-tracker): search normalization with unit tests"
```

---

### Task 3: Selection logic (TDD)

**Files:**
- Create: `flight_tracker/select.py`
- Create: `tests/test_flight_select.py`

- [ ] **Step 1: Write failing tests**

`tests/test_flight_select.py`:
```python
import unittest
import pytest
from flight_tracker.search import Flight
from flight_tracker.select import select_picks


def make_flight(price, stops, duration_min=600, airline="AA", departs="08:00"):
    return Flight(price=price, stops=stops, duration_min=duration_min, airline=airline, departs=departs)


@pytest.mark.unit
class TestSelectPicks(unittest.TestCase):
    def test_empty_list_returns_none_none(self):
        fewest, cheapest = select_picks([])
        self.assertIsNone(fewest)
        self.assertIsNone(cheapest)

    def test_single_flight_is_both_picks(self):
        f = make_flight(price=980, stops=1)
        fewest, cheapest = select_picks([f])
        self.assertEqual(fewest, f)
        self.assertEqual(cheapest, f)

    def test_fewest_stops_wins_over_price(self):
        nonstop = make_flight(price=1500, stops=0)
        one_stop_cheap = make_flight(price=800, stops=1)
        fewest, cheapest = select_picks([nonstop, one_stop_cheap])
        self.assertEqual(fewest, nonstop)
        self.assertEqual(cheapest, one_stop_cheap)

    def test_cheapest_is_lowest_price_regardless_of_stops(self):
        a = make_flight(price=1200, stops=0)
        b = make_flight(price=700, stops=3)
        _, cheapest = select_picks([a, b])
        self.assertEqual(cheapest, b)

    def test_fewest_stops_uses_price_as_tiebreaker(self):
        f1 = make_flight(price=900, stops=0)
        f2 = make_flight(price=800, stops=0)
        fewest, _ = select_picks([f1, f2])
        self.assertEqual(fewest, f2)  # same stops, lower price wins

    def test_fewest_stops_falls_back_when_no_nonstop(self):
        f1 = make_flight(price=900, stops=2)
        f2 = make_flight(price=1100, stops=1)
        fewest, _ = select_picks([f1, f2])
        self.assertEqual(fewest, f2)  # 1 stop < 2 stops

    def test_multiple_flights_same_cheapest(self):
        a = make_flight(price=500, stops=2)
        b = make_flight(price=500, stops=1)
        c = make_flight(price=900, stops=0)
        _, cheapest = select_picks([a, b, c])
        self.assertEqual(cheapest.price, 500)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run — verify FAIL**

```bash
pytest tests/test_flight_select.py -v -m unit
```

Expected: `ImportError: No module named 'flight_tracker.select'`

- [ ] **Step 3: Implement `select.py`**

`flight_tracker/select.py`:
```python
def select_picks(flights: list) -> tuple:
    """Returns (fewest_stops_flight, cheapest_flight). Both None if flights is empty."""
    if not flights:
        return None, None
    fewest_stops = min(flights, key=lambda f: (f.stops, f.price))
    cheapest = min(flights, key=lambda f: f.price)
    return fewest_stops, cheapest
```

- [ ] **Step 4: Run — verify PASS**

```bash
pytest tests/test_flight_select.py -v -m unit
```

Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add flight_tracker/select.py tests/test_flight_select.py
git commit -m "feat(flight-tracker): pick fewest-stops and cheapest per leg"
```

---

## Chunk 2: Email + Tracker

### Task 4: Email HTML formatting (TDD)

**Files:**
- Create: `flight_tracker/email_report.py`
- Create: `tests/test_flight_email.py`

Testing strategy: test `build_html()` — pure function, no network. Don't unit-test `send_email()` (SMTP) — it's a stdlib integration point tested only in production.

- [ ] **Step 1: Write failing tests**

`tests/test_flight_email.py`:
```python
import unittest
import pytest
from flight_tracker.search import Flight
from flight_tracker.email_report import build_html, build_subject


def make_flight(price=980, stops=1, duration_min=980, airline="SAA", departs="18:30"):
    return Flight(price=price, stops=stops, duration_min=duration_min, airline=airline, departs=departs)


@pytest.mark.unit
class TestBuildSubject(unittest.TestCase):
    def test_subject_includes_prices_and_date(self):
        outbound = (make_flight(price=1240, stops=1), make_flight(price=980, stops=2))
        ret = (make_flight(price=900, stops=0), make_flight(price=850, stops=1))
        subject = build_subject(outbound, ret, "2026-05-16", "JFK", "JNB")
        self.assertIn("JFK", subject)
        self.assertIn("JNB", subject)
        self.assertIn("$1,240", subject)
        self.assertIn("$980", subject)
        self.assertIn("2026-05-16", subject)

    def test_subject_na_when_no_outbound_picks(self):
        subject = build_subject((None, None), (None, None), "2026-05-16", "JFK", "JNB")
        self.assertIn("N/A", subject)


@pytest.mark.unit
class TestBuildHtml(unittest.TestCase):
    def test_html_contains_flight_data(self):
        fewest = make_flight(price=1240, stops=1, duration_min=980, airline="SAA", departs="18:30")
        cheapest = make_flight(price=980, stops=2, duration_min=1365, airline="Ethiopian", departs="21:00")
        html = build_html((fewest, cheapest), (None, None), "2026-05-16")
        self.assertIn("SAA", html)
        self.assertIn("Ethiopian", html)
        self.assertIn("$1,240", html)
        self.assertIn("$980", html)
        self.assertIn("16h 20m", html)  # 980 min

    def test_html_shows_na_for_missing_leg(self):
        html = build_html((None, None), (None, None), "2026-05-16")
        self.assertIn("N/A", html)

    def test_html_contains_footer(self):
        html = build_html((None, None), (None, None), "2026-05-16")
        self.assertIn("SerpAPI", html)
        self.assertIn("history.csv", html)

    def test_duration_format_zero_minutes(self):
        f = make_flight(duration_min=0)
        html = build_html((f, f), (f, f), "2026-05-16")
        self.assertIn("0h 0m", html)

    def test_duration_format_exact_hour(self):
        f = make_flight(duration_min=120)
        html = build_html((f, f), (f, f), "2026-05-16")
        self.assertIn("2h 0m", html)

    def test_html_escapes_airline_name(self):
        f = make_flight(airline='<script>alert("xss")</script>')
        html = build_html((f, f), (f, f), "2026-05-16")
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run — verify FAIL**

```bash
pytest tests/test_flight_email.py -v -m unit
```

Expected: `ImportError: No module named 'flight_tracker.email_report'`

- [ ] **Step 3: Implement `email_report.py`**

`flight_tracker/email_report.py`:
```python
import html as html_module
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def _fmt_price(price) -> str:
    if price is None:
        return "N/A"
    return f"${price:,}"


def _fmt_duration(minutes: int) -> str:
    return f"{minutes // 60}h {minutes % 60}m"


def _flight_row(flight) -> dict:
    if flight is None:
        return {"price": "N/A", "airline": "N/A", "stops": "N/A", "duration": "N/A", "departs": "N/A"}
    return {
        "price": _fmt_price(flight.price),
        "airline": html_module.escape(flight.airline),
        "stops": str(flight.stops),
        "duration": _fmt_duration(flight.duration_min),
        "departs": html_module.escape(flight.departs),
    }


def _leg_table(title: str, picks: tuple) -> str:
    fewest, cheapest = picks
    f = _flight_row(fewest)
    c = _flight_row(cheapest)
    return f"""
<h2>{title}</h2>
<table border="1" cellpadding="6" cellspacing="0">
  <tr><th></th><th>Fewest Stops</th><th>Overall Cheapest</th></tr>
  <tr><td>Price</td><td>{f['price']}</td><td>{c['price']}</td></tr>
  <tr><td>Airline</td><td>{f['airline']}</td><td>{c['airline']}</td></tr>
  <tr><td>Stops</td><td>{f['stops']}</td><td>{c['stops']}</td></tr>
  <tr><td>Duration</td><td>{f['duration']}</td><td>{c['duration']}</td></tr>
  <tr><td>Departs</td><td>{f['departs']}</td><td>{c['departs']}</td></tr>
</table>
"""


def build_subject(outbound_picks: tuple, return_picks: tuple, today: str, origin: str, destination: str) -> str:
    fewest, cheapest = outbound_picks
    fewest_price = _fmt_price(fewest.price if fewest else None)
    cheapest_price = _fmt_price(cheapest.price if cheapest else None)
    return f"✈ {origin}→{destination} | Fewest Stops: {fewest_price} | Cheapest: {cheapest_price} | {today}"


def build_html(outbound_picks: tuple, return_picks: tuple, today: str) -> str:
    outbound_table = _leg_table("Outbound", outbound_picks)
    return_table = _leg_table("Return", return_picks)
    return f"""<html><body>
{outbound_table}
{return_table}
<p><small>Searched via SerpAPI Google Flights &middot; History tracked in history.csv</small></p>
</body></html>"""


def send_email(html: str, subject: str, config: dict) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config["gmail_user"]
    msg["To"] = config["alert_email"]
    msg.attach(MIMEText(html, "html"))

    ctx = ssl.create_default_context()
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.ehlo()
        server.starttls(context=ctx)
        server.login(config["gmail_user"], config["gmail_app_password"])
        server.sendmail(config["gmail_user"], config["alert_email"], msg.as_string())
```

- [ ] **Step 4: Run — verify PASS**

```bash
pytest tests/test_flight_email.py -v -m unit
```

Expected: All 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add flight_tracker/email_report.py tests/test_flight_email.py
git commit -m "feat(flight-tracker): HTML email builder and SMTP sender"
```

---

### Task 5: History CSV + tracker entrypoint (TDD)

**Files:**
- Create: `flight_tracker/history.csv`
- Create: `tests/test_flight_history.py`
- Create: `flight_tracker/tracker.py`

CSV header (18 columns):
```
schema_version,date,outbound_fewest_stops_price,outbound_fewest_stops_airline,outbound_fewest_stops_stops,outbound_fewest_stops_duration,outbound_cheapest_price,outbound_cheapest_airline,outbound_cheapest_stops,outbound_cheapest_duration,return_fewest_stops_price,return_fewest_stops_airline,return_fewest_stops_stops,return_fewest_stops_duration,return_cheapest_price,return_cheapest_airline,return_cheapest_stops,return_cheapest_duration
```

- [ ] **Step 0: Correct spec error table for SMTP failure**

The spec's Error Handling table says "Gmail SMTP failure | Log to Actions stdout; **Actions marks run failed**." This contradicts the Exit Policy ("tracker.py always exits 0") whose stated reason is to ensure the GitHub Actions commit step always runs. Update the spec at `docs/superpowers/specs/2026-05-16-flight-tracker-design.md`:

Change the Gmail SMTP failure row from:
```
| Gmail SMTP failure | Log to Actions stdout; Actions marks run failed — no email possible; **Actions run status is the authoritative signal** |
```
To:
```
| Gmail SMTP failure | Log to Actions stdout; tracker exits 0 (commit step must still run); **Actions run shows green but no email arrived — check Actions log for SMTP failure message** |
```

Also fix the stale cron comment in the spec's architecture tree (line ~30): change `# cron: daily 07:00 UTC` to `# cron: daily 07:17 UTC` to match the workflow section.

Commit: `git add docs/superpowers/specs/2026-05-16-flight-tracker-design.md && git commit -m "docs(flight-tracker): correct SMTP exit behavior and stale cron comment in spec"`

- [ ] **Step 1: Create initial `history.csv`**

Create `flight_tracker/history.csv` with the header row and nothing else:
```
schema_version,date,outbound_fewest_stops_price,outbound_fewest_stops_airline,outbound_fewest_stops_stops,outbound_fewest_stops_duration,outbound_cheapest_price,outbound_cheapest_airline,outbound_cheapest_stops,outbound_cheapest_duration,return_fewest_stops_price,return_fewest_stops_airline,return_fewest_stops_stops,return_fewest_stops_duration,return_cheapest_price,return_cheapest_airline,return_cheapest_stops,return_cheapest_duration
```

- [ ] **Step 2: Write failing tests**

`tests/test_flight_history.py`:
```python
import csv
import io
import unittest
import pytest
from flight_tracker.search import Flight
from flight_tracker.tracker import _build_row, _update_history


def make_flight(price=980, stops=1, duration_min=980, airline="SAA", departs="18:30"):
    return Flight(price=price, stops=stops, duration_min=duration_min, airline=airline, departs=departs)


@pytest.mark.unit
class TestBuildRow(unittest.TestCase):
    def test_row_has_schema_version_1(self):
        row = _build_row("2026-05-16", (None, None), (None, None))
        self.assertEqual(row["schema_version"], "1")

    def test_row_has_correct_date(self):
        row = _build_row("2026-05-16", (None, None), (None, None))
        self.assertEqual(row["date"], "2026-05-16")

    def test_row_empty_when_no_picks(self):
        row = _build_row("2026-05-16", (None, None), (None, None))
        self.assertEqual(row["outbound_fewest_stops_price"], "")
        self.assertEqual(row["return_cheapest_airline"], "")

    def test_row_populated_with_picks(self):
        f = make_flight(price=980, stops=1, duration_min=900, airline="SAA")
        row = _build_row("2026-05-16", (f, f), (f, f))
        self.assertEqual(row["outbound_fewest_stops_price"], "980")
        self.assertEqual(row["outbound_fewest_stops_airline"], "SAA")
        self.assertEqual(row["outbound_fewest_stops_stops"], "1")
        self.assertEqual(row["outbound_fewest_stops_duration"], "900")


@pytest.mark.unit
class TestUpdateHistory(unittest.TestCase):
    HEADER = [
        "schema_version", "date",
        "outbound_fewest_stops_price", "outbound_fewest_stops_airline",
        "outbound_fewest_stops_stops", "outbound_fewest_stops_duration",
        "outbound_cheapest_price", "outbound_cheapest_airline",
        "outbound_cheapest_stops", "outbound_cheapest_duration",
        "return_fewest_stops_price", "return_fewest_stops_airline",
        "return_fewest_stops_stops", "return_fewest_stops_duration",
        "return_cheapest_price", "return_cheapest_airline",
        "return_cheapest_stops", "return_cheapest_duration",
    ]

    def _make_csv(self, rows):
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=self.HEADER)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        buf.seek(0)
        return buf

    def _read_csv(self, path):
        with open(path, newline="") as f:
            return list(csv.DictReader(f))

    def test_appends_new_date(self, tmp_path=None):
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
            csv_path = f.name
            writer = csv.DictWriter(f, fieldnames=self.HEADER)
            writer.writeheader()
        try:
            _update_history("2026-05-16", (None, None), (None, None), csv_path)
            rows = self._read_csv(csv_path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["date"], "2026-05-16")
        finally:
            os.unlink(csv_path)

    def test_overwrites_existing_date(self):
        import tempfile, os
        f_pick = make_flight(price=999)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
            csv_path = f.name
            writer = csv.DictWriter(f, fieldnames=self.HEADER)
            writer.writeheader()
            writer.writerow({"schema_version": "1", "date": "2026-05-16",
                             **{k: "" for k in self.HEADER if k not in ("schema_version", "date")}})
        try:
            _update_history("2026-05-16", (f_pick, f_pick), (f_pick, f_pick), csv_path)
            rows = self._read_csv(csv_path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["outbound_fewest_stops_price"], "999")
        finally:
            os.unlink(csv_path)

    def test_preserves_other_dates(self):
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
            csv_path = f.name
            writer = csv.DictWriter(f, fieldnames=self.HEADER)
            writer.writeheader()
            writer.writerow({"schema_version": "1", "date": "2026-05-15",
                             **{k: "" for k in self.HEADER if k not in ("schema_version", "date")}})
        try:
            _update_history("2026-05-16", (None, None), (None, None), csv_path)
            rows = self._read_csv(csv_path)
            self.assertEqual(len(rows), 2)
            dates = {r["date"] for r in rows}
            self.assertEqual(dates, {"2026-05-15", "2026-05-16"})
        finally:
            os.unlink(csv_path)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2b: Write error injection tests**

`tests/test_flight_tracker_errors.py`:
```python
import unittest
from unittest.mock import patch
import pytest
from flight_tracker.tracker import _safe_search


@pytest.mark.unit
class TestSafeSearch(unittest.TestCase):
    def test_returns_empty_and_error_on_failure(self):
        with patch("flight_tracker.tracker.search_flights", side_effect=Exception("connection error")):
            flights, err = _safe_search("JFK", "JNB", "2026-08-20", "key")
        self.assertEqual(flights, [])
        self.assertIn("connection error", err)

    def test_quota_429_prefixed(self):
        with patch("flight_tracker.tracker.search_flights", side_effect=Exception("HTTP 429 Too Many Requests")):
            flights, err = _safe_search("JFK", "JNB", "2026-08-20", "key")
        self.assertEqual(flights, [])
        self.assertTrue(err.startswith("[QUOTA EXCEEDED]"))

    def test_quota_keyword_prefixed(self):
        with patch("flight_tracker.tracker.search_flights", side_effect=Exception("out of credits")):
            flights, err = _safe_search("JFK", "JNB", "2026-08-20", "key")
        self.assertTrue(err.startswith("[QUOTA EXCEEDED]"))

    def test_non_quota_error_not_prefixed(self):
        with patch("flight_tracker.tracker.search_flights", side_effect=Exception("network timeout")):
            flights, err = _safe_search("JFK", "JNB", "2026-08-20", "key")
        self.assertFalse(err.startswith("[QUOTA EXCEEDED]"))
        self.assertIn("network timeout", err)

    def test_success_returns_flights_and_none_error(self):
        from flight_tracker.search import Flight
        mock_flight = Flight(price=980, stops=1, duration_min=900, airline="SAA", departs="18:30")
        with patch("flight_tracker.tracker.search_flights", return_value=[mock_flight]):
            flights, err = _safe_search("JFK", "JNB", "2026-08-20", "key")
        self.assertEqual(flights, [mock_flight])
        self.assertIsNone(err)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run — verify FAIL**

```bash
pytest tests/test_flight_history.py tests/test_flight_tracker_errors.py -v -m unit
```

Expected: `ImportError: No module named 'flight_tracker.tracker'`

- [ ] **Step 4: Implement `tracker.py`**

`flight_tracker/tracker.py`:
```python
import csv
import os
import sys
from datetime import date

from flight_tracker.config import get_config
from flight_tracker.email_report import build_html, build_subject, send_email
from flight_tracker.search import search_flights
from flight_tracker.select import select_picks

_HISTORY_PATH = os.path.join(os.path.dirname(__file__), "history.csv")

_CSV_FIELDS = [
    "schema_version", "date",
    "outbound_fewest_stops_price", "outbound_fewest_stops_airline",
    "outbound_fewest_stops_stops", "outbound_fewest_stops_duration",
    "outbound_cheapest_price", "outbound_cheapest_airline",
    "outbound_cheapest_stops", "outbound_cheapest_duration",
    "return_fewest_stops_price", "return_fewest_stops_airline",
    "return_fewest_stops_stops", "return_fewest_stops_duration",
    "return_cheapest_price", "return_cheapest_airline",
    "return_cheapest_stops", "return_cheapest_duration",
]


def _pick_val(flight, field):
    if flight is None:
        return ""
    return str(getattr(flight, field))


def _build_row(today: str, outbound_picks: tuple, return_picks: tuple) -> dict:
    ob_fewest, ob_cheapest = outbound_picks
    ret_fewest, ret_cheapest = return_picks
    return {
        "schema_version": "1",
        "date": today,
        "outbound_fewest_stops_price": _pick_val(ob_fewest, "price"),
        "outbound_fewest_stops_airline": _pick_val(ob_fewest, "airline"),
        "outbound_fewest_stops_stops": _pick_val(ob_fewest, "stops"),
        "outbound_fewest_stops_duration": _pick_val(ob_fewest, "duration_min"),
        "outbound_cheapest_price": _pick_val(ob_cheapest, "price"),
        "outbound_cheapest_airline": _pick_val(ob_cheapest, "airline"),
        "outbound_cheapest_stops": _pick_val(ob_cheapest, "stops"),
        "outbound_cheapest_duration": _pick_val(ob_cheapest, "duration_min"),
        "return_fewest_stops_price": _pick_val(ret_fewest, "price"),
        "return_fewest_stops_airline": _pick_val(ret_fewest, "airline"),
        "return_fewest_stops_stops": _pick_val(ret_fewest, "stops"),
        "return_fewest_stops_duration": _pick_val(ret_fewest, "duration_min"),
        "return_cheapest_price": _pick_val(ret_cheapest, "price"),
        "return_cheapest_airline": _pick_val(ret_cheapest, "airline"),
        "return_cheapest_stops": _pick_val(ret_cheapest, "stops"),
        "return_cheapest_duration": _pick_val(ret_cheapest, "duration_min"),
    }


def _update_history(today: str, outbound_picks: tuple, return_picks: tuple, path: str) -> None:
    existing = []
    if os.path.exists(path):
        with open(path, newline="") as f:
            existing = [r for r in csv.DictReader(f) if r["date"] != today]
    new_row = _build_row(today, outbound_picks, return_picks)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        writer.writerows(existing)
        writer.writerow(new_row)


def _safe_search(origin, destination, flight_date, api_key):
    try:
        flights = search_flights(origin, destination, flight_date, api_key)
        return flights, None
    except Exception as exc:
        err_str = str(exc)
        if "429" in err_str or "quota" in err_str.lower() or "credit" in err_str.lower():
            return [], f"[QUOTA EXCEEDED] {err_str}"
        return [], err_str


def main():
    today = date.today().isoformat()
    try:
        cfg = get_config()
    except KeyError as exc:
        missing_key = str(exc).strip("'")
        print(f"Missing required environment variable: {missing_key}")
        _update_history(today, (None, None), (None, None), _HISTORY_PATH)
        # Attempt alert email if SMTP credentials are available (the missing key may not be an SMTP key).
        gmail_user = os.environ.get("GMAIL_USER")
        gmail_pass = os.environ.get("GMAIL_APP_PASSWORD")
        alert_email = os.environ.get("ALERT_EMAIL")
        if gmail_user and gmail_pass and alert_email:
            try:
                smtp_cfg = {
                    "gmail_user": gmail_user,
                    "gmail_app_password": gmail_pass,
                    "alert_email": alert_email,
                }
                send_email(
                    f"<p>Missing required environment variable: <b>{missing_key}</b></p>",
                    f"[CONFIG ERROR] Flight Tracker: missing {missing_key}",
                    smtp_cfg,
                )
            except Exception:
                pass
        sys.exit(0)

    outbound_flights, outbound_err = _safe_search(
        cfg["origin"], cfg["destination"], cfg["outbound_date"], cfg["serpapi_key"]
    )
    return_flights, return_err = _safe_search(
        cfg["destination"], cfg["origin"], cfg["return_date"], cfg["serpapi_key"]
    )

    outbound_picks = select_picks(outbound_flights)
    return_picks = select_picks(return_flights)

    _update_history(today, outbound_picks, return_picks, _HISTORY_PATH)

    errors = [e for e in (outbound_err, return_err) if e]
    subject = build_subject(outbound_picks, return_picks, today, cfg["origin"], cfg["destination"])
    if errors:
        subject = f"[ERROR] {subject}"
    html = build_html(outbound_picks, return_picks, today)
    if errors:
        error_block = "<br>".join(f"<b>Error:</b> {e}" for e in errors)
        html = f"<p style='color:red'>{error_block}</p>" + html

    try:
        send_email(html, subject, cfg)
    except Exception as exc:
        print(f"SMTP failure: {exc}")  # stdout; exit 0 so commit step still runs


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run — verify PASS**

```bash
pytest tests/test_flight_history.py -v -m unit
```

Expected: All 6 history tests + 5 error injection tests PASS.

- [ ] **Step 6: Run full unit suite — no regressions**

```bash
pytest tests/ -v -m unit
```

Expected: All tests PASS.

- [ ] **Step 7: Verify history-write invariant**

Every `sys.exit(0)` path in `main()` must have called `_update_history` before exiting. Verify by inspection:
- Normal path: `_update_history` called after both searches ✓
- KeyError (missing config): `_update_history` called in except handler ✓
- Unhandled exception: exits non-zero (red Actions run) — spec-correct, no history write needed ✓

- [ ] **Step 8: Commit**

```bash
git add flight_tracker/tracker.py flight_tracker/history.csv tests/test_flight_history.py tests/test_flight_tracker_errors.py
git commit -m "feat(flight-tracker): tracker entrypoint, history CSV, quota detection, error handling"
```

---

## Chunk 3: GitHub Actions Workflow

### Task 6: Workflow + final wiring

**Files:**
- Create: `.github/workflows/flight_tracker.yml`

No unit test — verify YAML structure by inspection against spec.

- [ ] **Step 1: Create workflow**

`.github/workflows/flight_tracker.yml`:
```yaml
name: Flight Tracker

on:
  schedule:
    - cron: '17 7 * * *'   # 07:17 UTC daily — off :00 to avoid GitHub top-of-hour delays
  workflow_dispatch:          # allow manual trigger for testing

permissions:
  contents: write             # required for git push of history.csv

concurrency:
  group: flight-tracker
  cancel-in-progress: false   # queue runs; never cancel mid-write

jobs:
  track:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: pip install -r flight_tracker/requirements.txt

      - name: Run flight tracker
        run: python flight_tracker/tracker.py
        env:
          SERPAPI_KEY: ${{ secrets.SERPAPI_KEY }}
          GMAIL_USER: ${{ secrets.GMAIL_USER }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
          ALERT_EMAIL: ${{ secrets.ALERT_EMAIL }}
          ORIGIN: ${{ vars.ORIGIN }}
          DESTINATION: ${{ vars.DESTINATION }}
          OUTBOUND_DATE: ${{ vars.OUTBOUND_DATE }}
          RETURN_DATE: ${{ vars.RETURN_DATE }}

      - name: Commit history
        run: |
          git config user.name "flight-tracker[bot]"
          git config user.email "actions@github.com"
          git add flight_tracker/history.csv
          git diff --staged --quiet && exit 0
          git commit -m "chore: flight tracker history $(date +%Y-%m-%d)"
          git pull --rebase origin ${{ github.ref_name }}
          git push
```

- [ ] **Step 2: Verify checklist (by reading, not running)**

Confirm these properties in the YAML:
- `cron: '17 7 * * *'` — not top-of-hour
- `cancel-in-progress: false` — queues, never cancels
- `permissions: contents: write` — at workflow or job level (YAML has it at workflow level; either is valid)
- `type: "2"` in `tracker.py` search params — already in code
- `git pull --rebase` before `git push` — conflict-safe
- `workflow_dispatch` present — allows manual test trigger

- [ ] **Step 3: Configure GitHub repository**

In the repo Settings → Secrets and variables → Actions:

**Secrets tab:**
- `SERPAPI_KEY` — your SerpAPI key
- `GMAIL_USER` — sender Gmail address
- `GMAIL_APP_PASSWORD` — Gmail app password (requires 2FA on Google account)
- `ALERT_EMAIL` — recipient email address

**Variables tab:**
- `ORIGIN` → `JFK`
- `DESTINATION` → `JNB`
- `OUTBOUND_DATE` → `2026-08-20`
- `RETURN_DATE` → `2026-09-06`

**Branch protection check (required):** The workflow pushes `history.csv` directly to the branch it ran on. If the default branch (`main`) has push protection enabled, the `git push` step will fail on every scheduled run. Before merging to main: Settings → Branches → verify that `main` either has no push protection rule, or that `github-actions[bot]` is listed in the bypass list.

**Note:** Scheduled workflows only run from the **default branch** (main). The workflow must be merged to main before the cron fires. Test via `workflow_dispatch` from the branch while in development.

- [ ] **Step 4: Commit workflow**

```bash
git add .github/workflows/flight_tracker.yml
git commit -m "feat(flight-tracker): GitHub Actions cron workflow with history commit"
```

---

## Final Verification

- [ ] **Run full unit suite one last time**

```bash
pytest tests/ -v -m unit
```

Expected: All tests pass, no failures.

- [ ] **Smoke test locally (optional — requires real secrets)**

```bash
export SERPAPI_KEY=... GMAIL_USER=... GMAIL_APP_PASSWORD=... ALERT_EMAIL=...
export ORIGIN=JFK DESTINATION=JNB OUTBOUND_DATE=2026-08-20 RETURN_DATE=2026-09-06
python flight_tracker/tracker.py
```

Check: email arrives, `flight_tracker/history.csv` has a new row with today's date.

- [ ] **Trigger manual run via GitHub Actions UI**

Navigate: Actions → Flight Tracker → Run workflow. Confirm:
- Run completes green
- Email arrives
- A new commit appears on the branch with updated `history.csv`

---

## Success Criteria (from spec)

- Daily email arrives with two picks (fewest-stops + cheapest) for each leg
- `history.csv` grows by one row per day, committed to repo, no duplicate dates
- Partial results emailed when one leg fails — no silent failures
- Quota exhaustion surfaces as a named error in the alert email
- Config change requires only updating 4 secrets + 4 variables — no code edit
