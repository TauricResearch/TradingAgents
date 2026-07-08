import type { Meta, StoryObj } from "@storybook/react-vite";

import { ConsensusBar } from "./ConsensusBar";

const meta: Meta<typeof ConsensusBar> = {
  title: "Trading/ConsensusBar",
  component: ConsensusBar,
};
export default meta;
type Story = StoryObj<typeof ConsensusBar>;

const vote = (agent_id: string, v: string, confidence: number) => ({
  agent_id,
  vote: v,
  confidence,
});

export const BullishConsensus: Story = {
  args: {
    votes: [
      vote("rsi", "BUY", 70),
      vote("macd", "BUY", 65),
      vote("dxy", "SELL", 40),
      vote("sentiment", "HOLD", 50),
    ],
    judgeAction: "BUY",
  },
};

export const JudgeOverride: Story = {
  args: {
    votes: [
      vote("rsi", "SELL", 70),
      vote("macd", "SELL", 66),
      vote("flow", "BUY", 30),
    ],
    judgeAction: "BUY",
  },
};
