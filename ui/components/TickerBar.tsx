"use client";

import { motion } from "framer-motion";

const tickerData = [
  { symbol: "NVDA", price: 892.45, change: 3.21 },
  { symbol: "AAPL", price: 213.07, change: -0.45 },
  { symbol: "MSFT", price: 441.2, change: 1.87 },
  { symbol: "GOOGL", price: 178.92, change: 0.63 },
  { symbol: "TSLA", price: 248.5, change: -2.14 },
  { symbol: "META", price: 612.3, change: 4.5 },
  { symbol: "AMZN", price: 225.88, change: 1.02 },
  { symbol: "AMD", price: 178.34, change: 2.76 },
  { symbol: "INTC", price: 31.22, change: -1.55 },
  { symbol: "NFLX", price: 895.6, change: 5.12 },
];

function TickerItem({ symbol, price, change }: (typeof tickerData)[0]) {
  const isUp = change >= 0;
  return (
    <div className="flex items-center gap-2 whitespace-nowrap text-[11px]">
      <span className="font-display font-semibold text-text-primary">
        {symbol}
      </span>
      <span className="text-text-secondary tabular-nums">
        ${price.toFixed(2)}
      </span>
      <span className={isUp ? "text-green" : "text-red"}>
        {isUp ? "+" : ""}
        {change.toFixed(2)}%
      </span>
    </div>
  );
}

export default function TickerBar() {
  const doubled = [...tickerData, ...tickerData];

  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="overflow-hidden border-b border-border-subtle py-1.5"
    >
      <div
        className="flex gap-10 w-max"
        style={{ animation: "ticker-scroll 30s linear infinite" }}
      >
        {doubled.map((t, i) => (
          <TickerItem key={`${t.symbol}-${i}`} {...t} />
        ))}
      </div>
    </motion.div>
  );
}
