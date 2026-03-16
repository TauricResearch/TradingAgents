"use client";

import { motion } from "framer-motion";
import { ReactNode } from "react";

interface PanelProps {
  title: string;
  badge?: string;
  badgeVariant?: "live" | "amber";
  children: ReactNode;
  className?: string;
  delay?: number;
}

export default function Panel({
  title,
  badge,
  badgeVariant = "amber",
  children,
  className = "",
  delay = 0,
}: PanelProps) {
  const badgeColors = {
    live: "bg-green-dim text-green",
    amber: "bg-amber-dim text-amber",
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay, ease: [0.22, 1, 0.36, 1] }}
      className={`bg-bg-surface border border-border-subtle rounded-xl overflow-hidden
        transition-colors duration-300 hover:border-border-medium ${className}`}
    >
      <div className="flex items-center justify-between px-4 pt-3.5 pb-2.5 border-b border-border-subtle">
        <span className="font-display font-semibold text-[11px] tracking-[2px] uppercase text-text-secondary">
          {title}
        </span>
        {badge && (
          <span
            className={`text-[9px] px-2 py-0.5 rounded-full tracking-[1px] uppercase ${badgeColors[badgeVariant]}`}
          >
            {badge}
          </span>
        )}
      </div>
      <div className="p-4">{children}</div>
    </motion.div>
  );
}
