"use client";

import { motion } from "framer-motion";
import Panel from "./ui/Panel";

interface AnalystCard {
  name: string;
  role: string;
  avatarType: string;
  icon: string;
  signal: "bullish" | "bearish" | "neutral";
  signalText: string;
  metrics: { label: string; value: string }[];
  excerpt: string;
}

const analysts: AnalystCard[] = [
  {
    name: "Market Analyst",
    role: "Technical Analysis",
    avatarType: "market",
    icon: "\u{1F4CA}",
    signal: "bullish",
    signalText: "Bullish \u2014 Uptrend Confirmed",
    metrics: [
      { label: "Trend", value: "Strong Uptrend" },
      { label: "Momentum", value: "Accelerating" },
      { label: "Support", value: "$842.10" },
    ],
    excerpt:
      "MACD crossed above signal line with increasing histogram bars. RSI at 67.4 shows room before overbought. Price above all major moving averages with expanding volume.",
  },
  {
    name: "Fundamentals",
    role: "Financial Analysis",
    avatarType: "fundamentals",
    icon: "\u{1F4CB}",
    signal: "bullish",
    signalText: "Bullish \u2014 Strong Financials",
    metrics: [
      { label: "Revenue Growth", value: "+122% YoY" },
      { label: "Gross Margin", value: "74.8%" },
      { label: "Free Cash Flow", value: "$27.1B" },
    ],
    excerpt:
      "Data center revenue surged 409% YoY driven by AI infrastructure demand. Operating margins expanding to 61.6%. Balance sheet shows $26B cash with manageable debt.",
  },
  {
    name: "News Analyst",
    role: "Macro & News",
    avatarType: "news",
    icon: "\u{1F4F0}",
    signal: "bullish",
    signalText: "Bullish \u2014 Favorable Headlines",
    metrics: [
      { label: "Sentiment", value: "Positive (82%)" },
      { label: "Key Events", value: "3 Catalysts" },
      { label: "Risk Flags", value: "1 Moderate" },
    ],
    excerpt:
      "New Blackwell GPU architecture receiving strong OEM adoption. Sovereign AI investments from multiple nations. Minor concern: potential China export restrictions.",
  },
  {
    name: "Social Media",
    role: "Sentiment Analysis",
    avatarType: "social",
    icon: "\u{1F4AC}",
    signal: "neutral",
    signalText: "Neutral \u2014 Mixed Signals",
    metrics: [
      { label: "Overall Score", value: "0.62 / 1.0" },
      { label: "Buzz Volume", value: "Very High" },
      { label: "Inst. Sentiment", value: "Positive" },
    ],
    excerpt:
      "Institutional sentiment strongly positive with multiple analyst upgrades. Retail shows FOMO \u2014 elevated put/call ratio suggests hedging. Insider selling noted.",
  },
];

const avatarBg: Record<string, string> = {
  market: "bg-cyan-dim border-cyan/20",
  fundamentals: "bg-amber-dim border-amber/20",
  news: "bg-blue-dim border-blue/20",
  social: "bg-purple-dim border-purple/20",
};

const signalStyle: Record<string, string> = {
  bullish: "bg-green-dim text-green",
  bearish: "bg-red-dim text-red",
  neutral: "bg-cyan-dim text-cyan",
};

export default function AnalystGrid() {
  return (
    <Panel
      title="Analyst Reports"
      badge="Updated"
      badgeVariant="live"
      className="col-span-2"
      delay={0.25}
    >
      <div className="grid grid-cols-4 gap-2.5">
        {analysts.map((a, i) => (
          <motion.div
            key={a.name}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{
              duration: 0.5,
              delay: 0.3 + i * 0.08,
              ease: [0.22, 1, 0.36, 1],
            }}
            className="bg-bg-elevated border border-border-subtle rounded-lg p-3.5
              transition-all duration-300 cursor-default
              hover:border-border-medium hover:-translate-y-0.5 hover:shadow-[0_8px_30px_rgba(0,0,0,0.3)]"
          >
            <div className="flex items-center gap-2.5 mb-3">
              <div
                className={`w-8 h-8 rounded-lg grid place-items-center text-sm shrink-0 border ${avatarBg[a.avatarType]}`}
              >
                {a.icon}
              </div>
              <div>
                <div className="font-display font-semibold text-xs text-text-primary">
                  {a.name}
                </div>
                <div className="text-[9px] text-text-tertiary uppercase tracking-[1px]">
                  {a.role}
                </div>
              </div>
            </div>

            <div
              className={`flex items-center gap-1.5 mb-2.5 px-2.5 py-1.5 rounded text-[11px] font-medium ${signalStyle[a.signal]}`}
            >
              {a.signalText}
            </div>

            <div className="flex flex-col gap-1.5">
              {a.metrics.map((m) => (
                <div key={m.label} className="flex justify-between items-center">
                  <span className="text-[10px] text-text-tertiary">{m.label}</span>
                  <span className="text-[11px] font-medium text-text-secondary">
                    {m.value}
                  </span>
                </div>
              ))}
            </div>

            <div className="mt-2.5 pt-2.5 border-t border-border-subtle text-[11px] text-text-secondary leading-relaxed line-clamp-3">
              {a.excerpt}
            </div>
          </motion.div>
        ))}
      </div>
    </Panel>
  );
}
