"""Flight selection — picks fewest-stops and cheapest flight from a normalized list."""


def select_picks(flights: list) -> tuple:
    """Returns (fewest_stops_flight, cheapest_flight). Both None if flights is empty."""
    if not flights:
        return None, None
    fewest_stops = min(flights, key=lambda f: (f.stops, f.price))
    cheapest = min(flights, key=lambda f: f.price)
    return fewest_stops, cheapest
