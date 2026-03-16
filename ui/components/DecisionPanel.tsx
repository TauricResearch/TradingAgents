"use client";

import { motion } from "framer-motion";
import Panel from "./ui/Panel";

function RiskGauge({
  label,
  level,
  color,
}: {
  label: string;
  level: number;
  color: string;
}) {
  return (
    <div className="flex-1 flex flex-col items-center gap-1">
      <div className="w-full h-1 bg-bg-panel rounded-sm overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${level}%` }}
          transition={{ duration: 1, delay: 0.5, ease: [0.22, 1, 0.36, 1] }}
          className="h-full rounded-sm"
          style={{ background: color }}
        />
      </div>
      <span className="text-[9px] text-text-tertiary uppercase tracking-[1px]">
        {label}
      </span>
    </div>
  );
}

export default function DecisionPanel() {
  return (
    <Panel
      title="Final Decision"
      badge="Risk-Adjusted"
      badgeVariant="amber"
      className="col-span-2"
      delay={0.35}
    >
      <div className="grid grid-cols-[200px_1fr_1fr_1fr] gap-4 items-center">
        {/* Verdict */}
        <div className="flex flex-col items-center gap-2 p-4 bg-bg-elevated rounded-lg border border-border-accent">
          <div className="text-[9px] text-text-tertiary uppercase tracking-[2px]">
            Final Verdict
          </div>
          <motion.div
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{
              duration: 0.6,
              delay: 0.5,
              ease: [0.34, 1.56, 0.64, 1],
            }}
            className="font-display font-extrabold text-[32px] tracking-[2px] text-green"
            style={{ textShadow: "0 0 30px rgba(46, 204, 113, 0.15)" }}
          >
            BUY
          </motion.div>
          <div className="text-[11px] text-text-secondary">Confidence: 78%</div>
          <div className="flex gap-3 w-full mt-1">
            <RiskGauge label="Risk" level={60} color="var(--amber)" />
            <RiskGauge label="Reward" level={85} color="var(--green)" />
          </div>
        </div>

        {/* Position Size */}
        <div className="p-3.5 bg-bg-elevated rounded-lg">
          <div className="text-[9px] text-text-tertiary uppercase tracking-[1.5px] mb-2">
            Position Size
          </div>
          <div className="font-display font-semibold text-lg text-text-primary mb-1">
            12.5%
          </div>
          <div className="text-[10px] text-text-tertiary">of portfolio allocation</div>
          <div className="mt-2 text-[10px] text-text-tertiary leading-relaxed">
            Risk-adjusted by conservative analyst. Reduced from trader&apos;s initial 18%.
          </div>
        </div>

        {/* Entry Target */}
        <div className="p-3.5 bg-bg-elevated rounded-lg">
          <div className="text-[9px] text-text-tertiary uppercase tracking-[1.5px] mb-2">
            Entry Target
          </div>
          <div className="font-display font-semibold text-lg text-cyan mb-1">
            $885 &ndash; $895
          </div>
          <div className="text-[10px] text-text-tertiary">current: $892.45</div>
          <div className="mt-2 text-[10px] text-text-tertiary leading-relaxed">
            Scale in on pullbacks to 50 SMA support zone at $842.
          </div>
        </div>

        {/* Stop / Target */}
        <div className="p-3.5 bg-bg-elevated rounded-lg">
          <div className="text-[9px] text-text-tertiary uppercase tracking-[1.5px] mb-2">
            Stop / Target
          </div>
          <div className="font-display font-semibold text-lg mb-1">
            <span className="text-red">$820</span>
            <span className="text-text-tertiary text-sm"> / </span>
            <span className="text-green">$980</span>
          </div>
          <div className="text-[10px] text-text-tertiary">R:R ratio 1 : 2.4</div>
          <div className="mt-2 text-[10px] text-text-tertiary leading-relaxed">
            3-month horizon. Re-evaluate on earnings date.
          </div>
        </div>
      </div>
    </Panel>
  );
}
