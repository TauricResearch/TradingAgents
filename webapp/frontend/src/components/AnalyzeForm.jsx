import { useState } from "react";

export function AnalyzeForm({ api, onSubmitted }) {
  const [ticker, setTicker] = useState("");
  const [tradeDate, setTradeDate] = useState("");
  const [status, setStatus] = useState("idle"); // idle | loading | error
  const [message, setMessage] = useState("");

  async function handleSubmit(event) {
    event.preventDefault();
    if (!api.apiKey) {
      setStatus("error");
      setMessage("Load your account first — an API key is required.");
      return;
    }
    setStatus("loading");
    setMessage("Submitting…");
    try {
      const data = await api.analyze(ticker.trim().toUpperCase(), tradeDate.trim());
      setStatus("idle");
      setMessage(
        data.cached
          ? "Resolved from the tape — instant, no quota used."
          : "Agents are debating this one — can take a few minutes."
      );
      onSubmitted(data.job_id);
    } catch (err) {
      setStatus("error");
      setMessage(err.message);
    }
  }

  return (
    <section className="desk-section" aria-labelledby="analyze-heading">
      <h2 className="panel-heading" id="analyze-heading">
        run analysis
      </h2>
      <form onSubmit={handleSubmit}>
        <div className="field-row">
          <div className="field">
            <label htmlFor="ticker-input">ticker</label>
            <input
              id="ticker-input"
              type="text"
              required
              autoComplete="off"
              placeholder="NVDA"
              value={ticker}
              onChange={(e) => setTicker(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="trade-date-input">date (optional)</label>
            <input
              id="trade-date-input"
              type="text"
              autoComplete="off"
              placeholder="YYYY-MM-DD"
              value={tradeDate}
              onChange={(e) => setTradeDate(e.target.value)}
            />
          </div>
        </div>
        <button type="submit" className="btn" disabled={status === "loading"}>
          {status === "loading" ? "Submitting…" : "Analyze"}
        </button>
      </form>
      <p className="status-line" role="status" aria-live="polite" data-tone={status === "error" ? "error" : undefined}>
        {message}
      </p>
    </section>
  );
}
