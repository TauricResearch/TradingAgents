"""SerpAPI Google Flights search — normalize raw API responses into Flight namedtuples."""
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
