# PR7: Watchlist And Run History

The cockpit now separates two local concerns:

- `watchlist.json` records the symbols the user explicitly follows;
- archived bundles under `runs/<SYMBOL>/` are selectable historical research
  runs, rather than only a latest-run summary.

The cockpit can add or remove a watchlist symbol through its local HTTP API.
The selector combines watchlist entries with symbols discovered in cached
artifacts and archived runs, so an empty or newly watched ticker remains
visible even before its first research run.

Selecting a historical run loads the archived decision, risk review, and
backtest captured at that time. Current cached facts remain visible as current
context; the selected run is always labelled as an archived snapshot.

All state stays under the chosen local data directory. No broker integration,
authentication, remote synchronization, or modification to the original
TradingAgents graph is introduced.
