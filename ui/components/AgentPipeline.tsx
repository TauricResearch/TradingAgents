"use client";

import { motion } from "framer-motion";

type NodeState = "complete" | "active" | "pending";

interface PipelineNode {
  icon: string;
  label: string;
  state: NodeState;
}

interface PipelineStage {
  group: string;
  nodes: PipelineNode[];
}

const stages: PipelineStage[] = [
  {
    group: "Analysts",
    nodes: [
      { icon: "\u{1F4CA}", label: "Market", state: "complete" },
      { icon: "\u{1F4CB}", label: "Fundamentals", state: "complete" },
      { icon: "\u{1F4F0}", label: "News", state: "complete" },
      { icon: "\u{1F4AC}", label: "Social", state: "complete" },
    ],
  },
  {
    group: "Debate",
    nodes: [
      { icon: "\u{1F402}", label: "Bull", state: "active" },
      { icon: "\u{1F43B}", label: "Bear", state: "active" },
      { icon: "\u2696\uFE0F", label: "Judge", state: "pending" },
    ],
  },
  {
    group: "Execution",
    nodes: [{ icon: "\u{1F4B9}", label: "Trader", state: "pending" }],
  },
  {
    group: "Risk",
    nodes: [
      { icon: "\u{1F525}", label: "Aggressive", state: "pending" },
      { icon: "\u{1F6E1}\uFE0F", label: "Conservative", state: "pending" },
      { icon: "\u2696\uFE0F", label: "Neutral", state: "pending" },
      { icon: "\u{1F3DB}\uFE0F", label: "Risk Judge", state: "pending" },
    ],
  },
];

function NodeIcon({ node }: { node: PipelineNode }) {
  const stateClasses: Record<NodeState, string> = {
    complete: "bg-green-dim border-green",
    active: "bg-amber-dim border-amber",
    pending: "bg-bg-elevated border-border-medium",
  };

  return (
    <div className="flex flex-col items-center gap-1.5 px-2 py-1 group cursor-default">
      <div
        className={`w-10 h-10 rounded-[10px] grid place-items-center text-base
          border transition-all duration-400 ${stateClasses[node.state]}
          group-hover:-translate-y-0.5 group-hover:border-amber group-hover:shadow-[0_4px_20px_var(--amber-dim)]`}
        style={
          node.state === "active"
            ? { animation: "node-glow 2s ease-in-out infinite" }
            : undefined
        }
      >
        {node.icon}
      </div>
      <span
        className={`text-[9px] uppercase tracking-[1.5px] whitespace-nowrap
          ${node.state === "active" ? "text-amber" : node.state === "complete" ? "text-green" : "text-text-tertiary"}`}
      >
        {node.label}
      </span>
    </div>
  );
}

function Connector({ active }: { active: boolean }) {
  return (
    <div className="relative">
      <div
        className={`h-px transition-all duration-500 ${
          active
            ? "bg-gradient-to-r from-amber to-amber-dim h-0.5 shadow-[0_0_8px_var(--amber-dim)]"
            : "bg-border-medium"
        }`}
        style={{ width: 20 }}
      />
      {active && (
        <div
          className="absolute right-[-2px] top-1/2 w-1 h-1 bg-amber rounded-full"
          style={{
            transform: "translateY(-50%)",
            animation: "data-pulse 1.5s ease-in-out infinite",
          }}
        />
      )}
    </div>
  );
}

export default function AgentPipeline() {
  return (
    <motion.section
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.8, delay: 0.1, ease: [0.22, 1, 0.36, 1] }}
      className="flex items-center justify-center gap-0 py-7 overflow-x-auto"
    >
      {stages.map((stage, si) => (
        <div key={stage.group} className="flex items-center">
          {si > 0 && (
            <div className="mx-1">
              <div
                className={`h-px ${
                  stages[si - 1].nodes.every((n) => n.state === "complete")
                    ? "bg-gradient-to-r from-amber to-amber-dim h-0.5 shadow-[0_0_8px_var(--amber-dim)]"
                    : "bg-border-medium"
                }`}
                style={{ width: 40 }}
              />
            </div>
          )}
          <div className="relative flex items-center px-2.5 py-1.5 border border-border-subtle rounded-xl bg-bg-surface gap-1">
            <span className="absolute -top-2 left-3 text-[8px] text-text-tertiary uppercase tracking-[2px] bg-bg-surface px-1.5">
              {stage.group}
            </span>
            {stage.nodes.map((node, ni) => (
              <div key={node.label} className="flex items-center">
                {ni > 0 && (
                  <Connector
                    active={
                      stage.nodes[ni - 1].state === "complete" ||
                      stage.nodes[ni - 1].state === "active"
                    }
                  />
                )}
                <NodeIcon node={node} />
              </div>
            ))}
          </div>
        </div>
      ))}
    </motion.section>
  );
}
