import { useEffect, useState } from "react";
import { useApp } from "../context/AppContext";
import { formatMoney } from "../utils/currency";

const RANGES = ["1mo", "3mo", "6mo", "1y"];
const DEBOUNCE_MS = 450;

/**
 * A free live price preview — no LLM cost, no quota impact. Debounces on
 * the ticker prop itself (rather than requiring the caller to debounce)
 * so any consumer can just pass whatever the user is typing.
 */
export function PriceChart({ ticker }) {
  const { api, account } = useApp();
  const [range, setRange] = useState("3mo");
  const [points, setPoints] = useState(null);
  const [status, setStatus] = useState("idle"); // idle | loading | error | empty
  const [message, setMessage] = useState("");
  const [fxRate, setFxRate] = useState(null);

  // Prices are USD-denominated (yfinance). Convert to the profile's
  // preferred currency (set on the Profile page) — one fetch per currency,
  // not per ticker/range change.
  const currency = account?.currency || "USD";
  useEffect(() => {
    if (currency === "USD") {
      setFxRate(null);
      return undefined;
    }
    let cancelled = false;
    api
      .fetchRates("USD")
      .then((data) => {
        if (!cancelled) setFxRate(data.rates[currency] ?? null);
      })
      .catch(() => {
        if (!cancelled) setFxRate(null);
      });
    return () => {
      cancelled = true;
    };
  }, [api, currency]);

  useEffect(() => {
    if (!ticker) {
      setPoints(null);
      setStatus("idle");
      return undefined;
    }

    let cancelled = false;
    const timer = setTimeout(async () => {
      setStatus("loading");
      try {
        const data = await api.fetchChart(ticker, range);
        if (cancelled) return;
        setPoints(data.points);
        setStatus(data.points.length ? "idle" : "empty");
      } catch (err) {
        if (!cancelled) {
          setStatus("error");
          setMessage(err.message);
        }
      }
    }, DEBOUNCE_MS);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [ticker, range, api]);

  if (!ticker) return null;

  return (
    <div className="price-chart">
      <div className="price-chart__head">
        <span className="price-chart__ticker">{ticker}</span>
        <div className="price-chart__ranges" role="group" aria-label="Chart range">
          {RANGES.map((r) => (
            <button
              key={r}
              type="button"
              className={"price-chart__range" + (r === range ? " price-chart__range--active" : "")}
              onClick={() => setRange(r)}
              aria-pressed={r === range}
            >
              {r}
            </button>
          ))}
        </div>
      </div>

      <p className="status-line" role="status" aria-live="polite" data-tone={status === "error" ? "error" : undefined}>
        {status === "loading" && "Loading chart…"}
        {status === "error" && message}
        {status === "empty" && `No price data for ${ticker}.`}
      </p>

      {points && points.length > 0 && (
        <PriceChartSvg points={points} currency={currency} fxRate={fxRate} />
      )}
    </div>
  );
}

function PriceChartSvg({ points, currency, fxRate }) {
  const width = 100;
  const height = 36;
  const closes = points.map((p) => p.close);
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const span = max - min || 1;
  const stepX = points.length > 1 ? width / (points.length - 1) : 0;

  const coords = points.map((p, i) => [i * stepX, height - ((p.close - min) / span) * height]);
  const linePath = coords.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
  const areaPath = `${linePath} L${width},${height} L0,${height} Z`;

  const first = closes[0];
  const last = closes[closes.length - 1];
  const changePct = first ? ((last - first) / first) * 100 : 0;
  const tone = changePct > 0 ? "buy" : changePct < 0 ? "sell" : "hold";

  return (
    <div className="price-chart__body">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        className="price-chart__svg"
        data-tone={tone}
        role="img"
        aria-label={`Price chart, ${changePct >= 0 ? "up" : "down"} ${Math.abs(changePct).toFixed(2)}% over the period`}
      >
        <path d={areaPath} className="price-chart__area" />
        <path d={linePath} className="price-chart__line" />
      </svg>
      <div className="price-chart__stats">
        <span className="price-chart__last">{formatMoney(last, "USD")}</span>
        {fxRate && (
          <span className="price-chart__converted">≈ {formatMoney(last * fxRate, currency)}</span>
        )}
        <span className="price-chart__change" data-tone={tone}>
          {changePct >= 0 ? "+" : ""}
          {changePct.toFixed(2)}%
        </span>
      </div>
    </div>
  );
}
