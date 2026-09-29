import { useCallback, useEffect, useRef, useState } from "react";
import { useApp } from "../context/AppContext";
import { SUPPORTED_CURRENCIES } from "../utils/currency";

const AUTO_REFRESH_MS = 30000;

/** A live exchange-rate board (base currency + a table of rates), in the
 * spirit of a simple Xe-style converter. Free — no LLM cost, no quota. */
export function ExchangeRatesPage() {
  const { api, account } = useApp();
  const [base, setBase] = useState(account?.currency || "USD");
  const [board, setBoard] = useState(null);
  const [status, setStatus] = useState("idle"); // idle | loading | error
  const [message, setMessage] = useState("");
  const loadedOnce = useRef(false);

  useEffect(() => {
    if (account?.currency) setBase(account.currency);
  }, [account?.currency]);

  const load = useCallback(async () => {
    if (!loadedOnce.current) setStatus("loading");
    try {
      const data = await api.fetchRates(base);
      setBoard(data);
      setStatus("idle");
      setMessage("");
      loadedOnce.current = true;
    } catch (err) {
      setStatus("error");
      setMessage(err.message);
    }
  }, [api, base]);

  useEffect(() => {
    loadedOnce.current = false;
    load();
    const interval = setInterval(load, AUTO_REFRESH_MS);
    return () => clearInterval(interval);
  }, [load]);

  const others = board ? Object.entries(board.rates).filter(([code]) => code !== board.base) : [];

  return (
    <main className="app-main app-main--single">
      <div className="card">
        <div className="tape-heading">
          <h2 id="rates-heading">
            exchange rates
            <span className="live-dot" aria-hidden="true" />
            <span className="visually-hidden">Live, updates automatically</span>
          </h2>
        </div>
        <p className="card__hint">
          A free live board — not a quote for executing a trade, and unrelated to your analysis
          quota.
        </p>

        <div className="field field--narrow">
          <label htmlFor="rates-base">base currency</label>
          <select id="rates-base" value={base} onChange={(e) => setBase(e.target.value)}>
            {SUPPORTED_CURRENCIES.map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
        </div>

        {status === "error" && (
          <p className="status-line" data-tone="error" role="alert">
            {message}
          </p>
        )}

        {board && (
          <table className="rates-table">
            <thead>
              <tr>
                <th scope="col">currency</th>
                <th scope="col">rate</th>
                <th scope="col">1 {board.base} =</th>
              </tr>
            </thead>
            <tbody>
              {others.map(([code, rate]) => (
                <tr key={code}>
                  <td className="ticker">{code}</td>
                  <td>{rate}</td>
                  <td>
                    1 {board.base} = {rate} {code}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </main>
  );
}
