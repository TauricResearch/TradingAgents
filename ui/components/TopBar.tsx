"use client";

import { motion } from "framer-motion";
import { useState } from "react";

export default function TopBar() {
  const [ticker, setTicker] = useState("NVDA");
  const [running, setRunning] = useState(false);

  const handleRun = () => {
    setRunning(true);
    setTimeout(() => setRunning(false), 2000);
  };

  return (
    <motion.header
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
      className="flex items-center justify-between py-4 border-b border-border-subtle"
    >
      <div className="flex items-center gap-3.5">
        <div
          className="w-9 h-9 rounded-md grid place-items-center font-display font-extrabold text-base
          text-bg-void tracking-tighter"
          style={{
            background: "linear-gradient(135deg, #d4af37, #b8941f)",
            boxShadow: "0 0 20px rgba(212, 175, 55, 0.15)",
          }}
        >
          TA
        </div>
        <div>
          <div className="font-display font-bold text-lg tracking-tight text-text-primary">
            TradingAgents
          </div>
          <div className="text-[11px] text-text-tertiary tracking-[2px] uppercase">
            Multi-Agent Intelligence
          </div>
        </div>
      </div>

      <div className="flex items-center gap-6">
        <div className="flex items-center gap-2 text-[11px] text-text-secondary">
          <div
            className="w-1.5 h-1.5 rounded-full bg-green"
            style={{ animation: "pulse-dot 2s ease-in-out infinite" }}
          />
          <span>System Online</span>
        </div>

        <div className="flex items-center gap-2 bg-bg-elevated border border-border-medium rounded-lg px-3 py-1.5">
          <label className="text-[10px] text-text-tertiary uppercase tracking-[1px]">
            Ticker
          </label>
          <input
            type="text"
            value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
            onKeyDown={(e) => e.key === "Enter" && handleRun()}
            maxLength={5}
            spellCheck={false}
            className="bg-transparent border-none outline-none text-amber font-display font-bold text-base w-20 tracking-wide"
          />
        </div>

        <button
          onClick={handleRun}
          className="border-none px-5 py-2 rounded-lg font-display font-bold text-xs tracking-[1px]
            uppercase cursor-pointer transition-all duration-300 text-bg-void
            hover:-translate-y-0.5"
          style={{
            background: running
              ? "linear-gradient(135deg, #4ecdc4, #3ab5ad)"
              : "linear-gradient(135deg, #d4af37, #c9a020)",
            boxShadow: running
              ? "0 0 20px rgba(78, 205, 196, 0.15)"
              : "0 0 20px rgba(212, 175, 55, 0.15)",
          }}
        >
          {running ? "Analyzing..." : "Run Analysis"}
        </button>
      </div>
    </motion.header>
  );
}
