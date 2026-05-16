# Flight Tracker — Design Spec

**Date:** 2026-05-16  
**Status:** Approved  
**Route:** JFK ↔ JNB  
**Dates:** Outbound 2026-08-20 · Return 2026-09-06

---

## Goal

Daily automated flight price tracker that searches JFK→JNB and JNB→JFK, selects the fewest-stops and overall cheapest option for each leg, and emails a report every morning. Results accumulate in a CSV for trend visibility.

---

## Architecture

Standalone `flight_tracker/` module in this repo. GitHub Actions cron triggers daily at 07:17 UTC (off `:00` to avoid GitHub's documented top-of-hour scheduling delays). No external hosting required.

```
flight_tracker/
├── search.py        # SerpAPI calls, normalizes response to internal Flight objects
├── select.py        # picks fewest-stops + overall cheapest from normalized results
├── email_report.py  # formats HTML email, sends via Gmail SMTP (port 587, STARTTLS)
├── tracker.py       # entrypoint: orchestrates search → select → email → log
├── history.csv      # one row per day, committed back to repo after each run
└── config.py        # reads all config from environment variables

.github/workflows/
└── flight_tracker.yml   # cron: daily 07:17 UTC
```

---

## Configuration

Config split into **Secrets** (sensitive, write-only in GitHub UI) and **Variables** (non-sensitive, readable/editable in GitHub UI):

**Secrets** (Settings → Secrets and variables → Actions → **Secrets** tab):

| Variable | Example Value | Description |
|---|---|---|
| `SERPAPI_KEY` | `abc123...` | SerpAPI API key |
| `GMAIL_USER` | `you@gmail.com` | Sender Gmail address |
| `GMAIL_APP_PASSWORD` | `xxxx xxxx xxxx` | Gmail app password — requires Google 2FA enabled |
| `ALERT_EMAIL` | `you@gmail.com` | Recipient email |

**Variables** (Settings → Secrets and variables → Actions → **Variables** tab — values are visible and editable):

| Variable | Example Value | Description |
|---|---|---|
| `ORIGIN` | `JFK` | Departure airport IATA code |
| `DESTINATION` | `JNB` | Arrival airport IATA code |
| `OUTBOUND_DATE` | `2026-08-20` | Outbound flight date (YYYY-MM-DD) |
| `RETURN_DATE` | `2026-09-06` | Return flight date (YYYY-MM-DD) |

**Reuse model:** Clone repo, update 4 secrets + 4 variables → tracker works for any route/dates. No code changes needed. Use Variables for dates/routes so values can be read back and confirmed before re-runs.

**Note:** Gmail app passwords are silently revoked if Google 2FA is ever disabled. If email alerts stop arriving, check Actions run status directly — it is the authoritative signal when SMTP is unavailable.

---

## Data Flow

1. `tracker.py` calls `search.py` for outbound leg, then return leg
2. `search.py` calls SerpAPI `google_flights` with `type=2` (one-way), normalizes raw response into a list of `Flight` objects
3. `select.py` processes each leg:
   - **Fewest stops**: minimum stops available (nonstop preferred; falls back to minimum available if no nonstops exist). Lowest price as tiebreaker. If no results, field is marked "N/A".
   - **Overall cheapest**: lowest price regardless of stops. If no results, marked "N/A".
4. `email_report.py` sends HTML email combining both legs
5. `history.csv` updated (today's date overwritten if exists, else appended); GitHub Actions commits the file back

### SerpAPI call structure

`type=2` is required for one-way pricing. Without it, SerpAPI returns round-trip bundled fares.

```python
params = {
    "engine": "google_flights",
    "departure_id": "JFK",
    "arrival_id": "JNB",
    "outbound_date": "2026-08-20",
    "type": "2",          # one-way — required for independent per-leg pricing
    "currency": "USD",
    "hl": "en",
    "api_key": SERPAPI_KEY
}
```

### SerpAPI response contract

The actual SerpAPI `google_flights` response structure (relevant fields):

```python
response = {
    "best_flights": [          # top-ranked options
        {
            "flights": [...],  # list of flight legs (each leg = one plane segment)
            "layovers": [...], # list of layover objects (len = stops count)
            "total_duration": 1220,   # minutes
            "price": 980,             # USD integer
            # airline is inside flights[0]["airline"], not top-level
        }
    ],
    "other_flights": [...]     # additional options, same structure
}
```

**Normalization mapping** (`search.py` converts to internal `Flight` namedtuple):

| Internal field | Source in API response |
|---|---|
| `price` | `item["price"]` — skip if missing/None |
| `stops` | `len(item["layovers"])` |
| `duration_min` | `item["total_duration"]` |
| `airline` | `item["flights"][0]["airline"]` |
| `departs` | `item["flights"][0]["departure_airport"]["time"]` |

`search.py` combines `response.get("best_flights", []) + response.get("other_flights", [])` before returning — both keys must be treated as optional since SerpAPI may return results in only one of them. Items missing `price` are excluded from results.

---

## Email Format

**Subject:**
```
✈ JFK→JNB | Fewest Stops: $1,240 | Cheapest: $980 | 2026-05-16
```

**Body:** Two HTML tables (outbound + return), each with columns:

| | Fewest Stops | Overall Cheapest |
|---|---|---|
| Price | $1,240 | $980 |
| Airline | South African Airways | Ethiopian Airlines |
| Stops | 1 | 2 |
| Duration | 16h 20m | 22h 45m |
| Departs | 18:30 JFK | 21:00 JFK |

Footer: "Searched via SerpAPI Google Flights · History tracked in history.csv"

**Partial results:** If one leg fails but the other succeeds, email what was found and note the failure inline. Do not suppress the entire email.

---

## History Tracking

`history.csv` — one row per calendar date. If today's date already exists, overwrite it (handles manual re-runs without duplicates).

Columns:
```
schema_version,date,
outbound_fewest_stops_price,outbound_fewest_stops_airline,outbound_fewest_stops_stops,outbound_fewest_stops_duration,
outbound_cheapest_price,outbound_cheapest_airline,outbound_cheapest_stops,outbound_cheapest_duration,
return_fewest_stops_price,return_fewest_stops_airline,return_fewest_stops_stops,return_fewest_stops_duration,
return_cheapest_price,return_cheapest_airline,return_cheapest_stops,return_cheapest_duration
```

`schema_version=1` on every row. Future schema changes increment the version; old rows retain their version number.

GitHub Actions commits `history.csv` after each run using `GITHUB_TOKEN` with `contents: write` permission (explicitly granted in workflow).

---

## Error Handling

| Failure | Behaviour |
|---|---|
| SerpAPI HTTP error (non-429) | Send alert email with error details; append empty row to history.csv |
| SerpAPI HTTP 429 quota exceeded | Attempt alert email; if SMTP also unavailable, Actions run marked failed — check Actions UI directly |
| One leg returns no results | Email partial results for the leg that succeeded; note missing leg |
| `price` missing on all flights | Treat as no results for that leg |
| Gmail SMTP failure | Log to Actions stdout; tracker exits 0 (commit step must still run); **Actions run shows green but no email arrived — check Actions log for SMTP failure message** |
| Git push conflict | `git pull --rebase` after commit, before push (see workflow below) |

**Exit policy:** `tracker.py` always exits 0. Errors are recorded in `history.csv` (empty fields) and trigger an alert email. This ensures the commit step is always reached and history rows are never silently skipped. Only unhandled exceptions cause a non-zero exit and a red Actions run.

No automatic retries — Actions UI shows failure clearly; manual re-run via `workflow_dispatch`.

**Quota note:** 2 SerpAPI calls/day = ~60/month. Free tier is 250/month. Manual re-runs or adding a second route will approach the limit. If quota is exhausted and SMTP is also unavailable in the same run, the Actions run failure is the only notification — monitor Actions run status independently.

---

## GitHub Actions Workflow

Scheduled workflows only run from the **default branch**. Branch-based testing requires `workflow_dispatch` triggers.

```yaml
name: Flight Tracker
on:
  schedule:
    - cron: '17 7 * * *'  # daily 07:17 UTC (off :00 to avoid GitHub top-of-hour delays)
  workflow_dispatch:        # allow manual trigger

permissions:
  contents: write           # required for git push of history.csv

concurrency:
  group: flight-tracker
  cancel-in-progress: false  # queue; never cancel a run mid-write

jobs:
  track:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r flight_tracker/requirements.txt
      - run: python flight_tracker/tracker.py  # always exits 0; errors written to history.csv + alert email
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

---

## Dependencies

`flight_tracker/requirements.txt`:
```
google-search-results>=2.4.2   # SerpAPI Python client
```

Standard library only for email (`smtplib` + `email.mime`, port 587 STARTTLS). TLS must use `ssl.create_default_context()` passed to `starttls(context=...)` — fail closed on any TLS error.

---

## Success Criteria

- Daily email arrives with two picks (fewest-stops + cheapest) for each leg
- `history.csv` grows by one row per day, committed to repo, no duplicate dates
- Partial results emailed when one leg fails — no silent failures
- Quota exhaustion surfaces as a named error in the alert email
- Config change (new route/dates) requires only updating 4 secrets + 4 variables in GitHub, no code edit
