# Flight Tracker — Design Spec

**Date:** 2026-05-16  
**Status:** Approved  
**Route:** JFK ↔ JNB  
**Dates:** Outbound 2026-08-20 · Return 2026-09-06

---

## Goal

Daily automated flight price tracker that searches JFK→JNB and JNB→JFK, selects the best-direct and overall cheapest option for each leg, and emails a report every morning. Results accumulate in a CSV for trend visibility.

---

## Architecture

Standalone `flight_tracker/` module in this repo. GitHub Actions cron triggers daily at 07:00 UTC. No external hosting required.

```
flight_tracker/
├── search.py        # SerpAPI calls, returns raw flight results per leg
├── select.py        # picks best-direct + overall cheapest from results
├── email_report.py  # formats HTML email, sends via Gmail SMTP
├── tracker.py       # entrypoint: orchestrates search → select → email
├── history.csv      # appended each run, committed back to repo
└── config.py        # reads all config from environment variables

.github/workflows/
└── flight_tracker.yml   # cron: daily 07:00 UTC
```

---

## Configuration

All config via environment variables (stored as GitHub Actions secrets):

| Variable | Example Value | Description |
|---|---|---|
| `SERPAPI_KEY` | `abc123...` | SerpAPI API key |
| `GMAIL_USER` | `you@gmail.com` | Sender Gmail address |
| `GMAIL_APP_PASSWORD` | `xxxx xxxx xxxx` | Gmail app password (not account password) |
| `ALERT_EMAIL` | `you@gmail.com` | Recipient email |
| `ORIGIN` | `JFK` | Departure airport IATA code |
| `DESTINATION` | `JNB` | Arrival airport IATA code |
| `OUTBOUND_DATE` | `2026-08-20` | Outbound flight date (YYYY-MM-DD) |
| `RETURN_DATE` | `2026-09-06` | Return flight date (YYYY-MM-DD) |

**Reuse model:** Clone repo, update these 8 secrets → tracker works for any route/dates. No code changes needed.

---

## Data Flow

1. `tracker.py` calls `search.py` for outbound leg, then return leg
2. `search.py` hits SerpAPI `google_flights` engine, returns list of flights with: price, stops, duration, airline, departure/arrival times
3. `select.py` processes each leg:
   - **Best direct**: fewest stops first, lowest price as tiebreaker
   - **Overall cheapest**: lowest price regardless of stops
4. `email_report.py` sends HTML email combining both legs
5. `history.csv` appended with today's results; GitHub Actions commits the file back

### SerpAPI call structure

```python
params = {
    "engine": "google_flights",
    "departure_id": "JFK",
    "arrival_id": "JNB",
    "outbound_date": "2026-08-20",
    "currency": "USD",
    "hl": "en",
    "api_key": SERPAPI_KEY
}
```

---

## Email Format

**Subject:**
```
✈ JFK→JNB | Best Direct: $1,240 | Cheapest: $980 | 2026-05-16
```

**Body:** Two HTML tables (outbound + return), each with columns:

| | Best Direct | Overall Cheapest |
|---|---|---|
| Price | $1,240 | $980 |
| Airline | South African Airways | Ethiopian Airlines |
| Stops | 1 | 2 |
| Duration | 16h 20m | 22h 45m |
| Departs | 18:30 JFK | 21:00 JFK |

Footer: "Searched via SerpAPI Google Flights · History tracked in history.csv"

---

## History Tracking

`history.csv` columns:
```
date,
outbound_best_direct_price, outbound_best_direct_airline, outbound_best_direct_stops, outbound_best_direct_duration,
outbound_cheapest_price, outbound_cheapest_airline, outbound_cheapest_stops, outbound_cheapest_duration,
return_best_direct_price, return_best_direct_airline, return_best_direct_stops, return_best_direct_duration,
return_cheapest_price, return_cheapest_airline, return_cheapest_stops, return_cheapest_duration
```

GitHub Actions commits `history.csv` after each successful run using the repo's `GITHUB_TOKEN` (no extra secret needed).

---

## Error Handling

- SerpAPI failure or empty results → send alert email: "Flight search failed on YYYY-MM-DD: {error}" — do not silently fail
- Gmail SMTP failure → log to Actions stdout, let Actions mark run as failed
- No fallback retries — Actions will show failure clearly; manual re-run via GitHub UI

---

## GitHub Actions Workflow

```yaml
name: Flight Tracker
on:
  schedule:
    - cron: '0 7 * * *'   # daily 07:00 UTC
  workflow_dispatch:        # allow manual trigger

jobs:
  track:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r flight_tracker/requirements.txt
      - run: python flight_tracker/tracker.py
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
          git diff --staged --quiet || git commit -m "chore: flight tracker history $(date +%Y-%m-%d)"
          git push
```

---

## Dependencies

`flight_tracker/requirements.txt`:
```
google-search-results>=2.4.2   # SerpAPI Python client
```

Standard library only for email (smtplib + email.mime).

---

## Success Criteria

- Daily email arrives with two picks (best-direct + cheapest) for each leg
- `history.csv` grows by one row per day, committed to repo
- Error email sent on any failure — no silent failures
- Config change (new route/dates) requires only updating GitHub secrets/vars, no code edit
