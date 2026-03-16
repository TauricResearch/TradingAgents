"use client";

import { motion } from "framer-motion";

const messages = [
  {
    side: "bull" as const,
    author: "Bull Researcher",
    text: "NVDA demonstrates exceptional fundamentals with 122% revenue growth and industry-defining margins. The AI infrastructure buildout is in early innings \u2014 data center revenue alone grew 409% YoY. The MACD bullish crossover confirms technical strength.",
  },
  {
    side: "bear" as const,
    author: "Bear Researcher",
    text: "Valuation is stretched at 65x forward earnings with RSI approaching overbought territory. Insider selling has accelerated and China export restrictions pose material revenue risk. Social sentiment shows FOMO-driven buying \u2014 a contrarian red flag.",
  },
  {
    side: "bull" as const,
    author: "Bull Researcher",
    text: "The premium valuation is justified by a near-monopoly in AI accelerators. Blackwell architecture orders extend visibility through 2026. The addressable market is expanding \u2014 sovereign AI alone represents a $100B+ opportunity.",
  },
  {
    side: "bear" as const,
    author: "Bear Researcher",
    text: "Competition is intensifying from AMD MI300, Intel Gaudi, and custom silicon from Google, Amazon, and Microsoft. Customer concentration risk is real \u2014 top 4 hyperscalers represent 45% of data center revenue.",
  },
  {
    side: "judge" as const,
    author: "Research Manager",
    text: "RECOMMENDATION: BUY with conviction. Bull arguments regarding early-cycle AI infrastructure and expanding TAM outweigh near-term valuation concerns. Position sizing should reflect elevated volatility. Entry at current levels with 3-month horizon.",
  },
];

const sideStyles = {
  bull: {
    border: "border-l-2 border-l-green",
    bg: "bg-gradient-to-r from-green-dim to-transparent",
    author: "text-green",
  },
  bear: {
    border: "border-l-2 border-l-red",
    bg: "bg-gradient-to-r from-red-dim to-transparent",
    author: "text-red",
  },
  judge: {
    border: "border-l-2 border-l-amber",
    bg: "bg-gradient-to-r from-amber-glow to-transparent",
    author: "text-amber",
  },
};

export default function DebatePanel() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.3, ease: [0.22, 1, 0.36, 1] }}
      className="bg-bg-surface border border-border-subtle rounded-xl overflow-hidden
        transition-colors duration-300 hover:border-border-medium col-span-1 row-span-2 flex flex-col"
    >
      <div className="flex items-center justify-between px-4 pt-3.5 pb-2.5 border-b border-border-subtle">
        <span className="font-display font-semibold text-[11px] tracking-[2px] uppercase text-text-secondary">
          Investment Debate
        </span>
        <span className="text-[9px] px-2 py-0.5 rounded-full tracking-[1px] uppercase bg-amber-dim text-amber">
          Round 1
        </span>
      </div>

      <div className="flex items-center justify-center gap-4 px-4 py-3 border-b border-border-subtle">
        <span className="flex items-center gap-1.5 text-[11px] font-medium text-green">
          &#9650; Bull
        </span>
        <span className="font-serif italic text-sm text-text-tertiary">vs</span>
        <span className="flex items-center gap-1.5 text-[11px] font-medium text-red">
          &#9660; Bear
        </span>
      </div>

      <div className="flex-1 overflow-y-auto max-h-[500px]">
        {messages.map((m, i) => {
          const style = sideStyles[m.side];
          return (
            <motion.div
              key={i}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.4, delay: 0.4 + i * 0.1 }}
              className={`px-4 py-3 border-b border-border-subtle ${style.border} ${style.bg}`}
            >
              <div className={`text-[10px] font-medium uppercase tracking-[1px] mb-1 ${style.author}`}>
                {m.author}
              </div>
              <div className="text-[11px] leading-relaxed text-text-secondary">
                {m.text}
              </div>
            </motion.div>
          );
        })}
      </div>
    </motion.div>
  );
}
