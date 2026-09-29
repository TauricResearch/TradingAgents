import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApp } from "../context/AppContext";

export function WatchlistPage() {
  const { api } = useApp();
  const navigate = useNavigate();
  const [tickers, setTickers] = useState([]);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState("idle"); // idle | loading | error
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    setStatus("loading");
    try {
      const data = await api.fetchWatchlist();
      setTickers(data);
      setStatus("idle");
      setMessage("");
    } catch (err) {
      setStatus("error");
      setMessage(err.message);
    }
  }, [api]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleAdd(event) {
    event.preventDefault();
    const ticker = input.trim().toUpperCase();
    if (!ticker) return;
    try {
      const data = await api.addWatchlistTicker(ticker);
      setTickers(data);
      setInput("");
    } catch (err) {
      setStatus("error");
      setMessage(err.message);
    }
  }

  async function handleRemove(ticker) {
    try {
      const data = await api.removeWatchlistTicker(ticker);
      setTickers(data);
    } catch (err) {
      setStatus("error");
      setMessage(err.message);
    }
  }

  return (
    <main className="app-main app-main--single">
      <div>
        <section className="desk-section" aria-labelledby="watchlist-heading">
          <h2 className="panel-heading" id="watchlist-heading">
            watchlist
          </h2>
          <p className="step-help">Save tickers you check often — Analyze runs them straight from here.</p>
          <form onSubmit={handleAdd} className="field-row field-row--with-button">
            <div className="field">
              <label htmlFor="watchlist-ticker">add a ticker</label>
              <input
                id="watchlist-ticker"
                type="text"
                placeholder="NVDA"
                value={input}
                onChange={(e) => setInput(e.target.value)}
              />
            </div>
            <button type="submit" className="btn btn--primary">
              Add
            </button>
          </form>
          <p className="status-line" role="status" aria-live="polite" data-tone={status === "error" ? "error" : undefined}>
            {message}
          </p>
        </section>

        <section className="card">
          {tickers.length === 0 && status !== "loading" ? (
            <p className="tape-empty">No tickers yet — add one above to build your watchlist.</p>
          ) : (
            <ul className="watchlist-list">
              {tickers.map((row) => (
                <li key={row.ticker} className="watchlist-list__row">
                  <span className="ticker">{row.ticker}</span>
                  <div>
                    <button
                      type="button"
                      className="btn btn--primary"
                      onClick={() => navigate("/", { state: { ticker: row.ticker } })}
                    >
                      Analyze
                    </button>
                    <button type="button" className="btn btn--ghost" onClick={() => handleRemove(row.ticker)}>
                      Remove
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </main>
  );
}
