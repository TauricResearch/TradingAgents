import type { Meta, StoryObj } from "@storybook/react-vite";

import { GateWaterfall } from "./GateWaterfall";

const meta: Meta<typeof GateWaterfall> = {
  title: "Trading/GateWaterfall",
  component: GateWaterfall,
};
export default meta;
type Story = StoryObj<typeof GateWaterfall>;

const SEQUENCE = [
  "prepare",
  "technical",
  "macro",
  "sentiment",
  "risk_team",
  "debate",
  "risk_gate",
  "critic",
  "reflection",
  "judge",
  "portfolio_manager",
  "execution",
];

export const AllPassed: Story = {
  args: { nodeSequence: SEQUENCE, rejection: null },
};

export const RejectedAtRiskGate: Story = {
  args: {
    nodeSequence: SEQUENCE.slice(0, 7),
    rejection: {
      stage: "risk_gate",
      reasons: ["VaR95 0.0388 exceeds max daily loss 0.0300"],
    },
  },
};
