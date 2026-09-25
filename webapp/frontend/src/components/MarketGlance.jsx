import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApp } from "../context/AppContext";
import { formatMoney } from "../utils/currency";

const MAX_TICKERS = 4;

/** A live 5-day snapshot of the user's watchlist — sparkline + last price +
 * % change per ticker. Free (chart data), gives the Dashboard something to
 * look at beyond "type a ticker and wait". */
export function MarketGlance() {
  const { api } = useApp();
  const navigate = useNavigate();
  const [tickers, setTickers] = useState(null); // null = loading watchlist itself
  const [quotes, setQuotes] = useState({}); // ticker -> { points, status }

  useEffect(() => {
    let cancelled = false;
    api
      .fetchWatchlist()
      .then((rows) => {
        if (cancelled) return;
        setTickers(rows.slice(0, MAX_TICKERS).map((r) => r.ticker));
      })
      .catch(() => {
        if (!cancelled) setTickers([]);
      });
    return () => {
      cancelled = true;
    };
  }, [api]);

  useEffect(() => {
    if (!tickers || tickers.length === 0) return undefined;
    let cancelled = false;
    setQuotes({});
    tickers.forEach((ticker) => {
      api
        .fetchChart(ticker, "5d")
        .then((data) => {
          if (cancelled) return;
          setQuotes((prev) => ({ ...prev, [ticker]: { status: "done", points: data.points } }));
        })
        .catch((err) => {
          if (cancelled) return;
          setQuotes((prev) => ({ ...prev, [ticker]: { status: "error", message: err.message } }));
        });
    });
    return () => {
      cancelled = true;
    };
  }, [api, tickers]);

  if (tickers === null) return null;

  return (
    <section className="card market-glance" aria-labelledby="glance-heading">
      <div className="tape-heading">
        <h2 id="glance-heading">
          market glance
          {tickers.length > 0 && <span className="live-dot" aria-hidden="true" />}
        </h2>
        <button type="button" className="btn btn--ghost" onClick={() => navigate("/watchlist")}>
          Manage watchlist
        </button>
      </div>

      {tickers.length === 0 ? (
        <p className="tape-empty">
          Your watchlist is empty — add a ticker to see a live 5-day snapshot here.
        </p>
      ) : (
        <ul className="market-glance__list">
          {tickers.map((ticker) => (
            <MarketGlanceRow key={ticker} ticker={ticker} quote={quotes[ticker]} onAnalyze={() => navigate("/", { state: { ticker } })} />
          ))}
        </ul>
      )}
    </section>
  );
}

function MarketGlanceRow({ ticker, quote, onAnalyze }) {
  if (!quote || quote.status !== "done") {
    return (
      <li className="market-glance__row">
        <span className="ticker">{ticker}</span>
        <span className="market-glance__loading">
          {quote?.status === "error" ? "unavailable" : "loading…"}
        </span>
      </li>
    );
  }

  const closes = quote.points.map((p) => p.close);
  if (closes.length === 0) {
    return (
      <li className="market-glance__row">
        <span className="ticker">{ticker}</span>
        <span className="market-glance__loading">no data</span>
      </li>
    );
  }

  const first = closes[0];
  const last = closes[closes.length - 1];
  const changePct = first ? ((last - first) / first) * 100 : 0;
  const tone = changePct > 0 ? "buy" : changePct < 0 ? "sell" : "hold";

  return (
    <li className="market-glance__row">
      <button type="button" className="market-glance__ticker-btn" onClick={onAnalyze} title={`Analyze ${ticker}`}>
        <span className="ticker">{ticker}</span>
      </button>
      <Sparkline points={closes} tone={tone} />
      <span className="market-glance__price">{formatMoney(last, "USD")}</span>
      <span className="market-glance__change" data-tone={tone}>
        {changePct >= 0 ? "+" : ""}
        {changePct.toFixed(2)}%
      </span>
    </li>
  );
}

function Sparkline({ points, tone }) {
  const width = 100;
  const height = 28;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const stepX = points.length > 1 ? width / (points.length - 1) : 0;
  const path = points
    .map((p, i) => {
      const x = i * stepX;
      const y = height - ((p - min) / span) * height;
      return `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  return (
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" className="market-glance__spark" data-tone={tone} aria-hidden="true">
      <path d={path} fill="none" />
    </svg>
  );
}
