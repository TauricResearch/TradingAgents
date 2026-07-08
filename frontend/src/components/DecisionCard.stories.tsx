import type { Meta, StoryObj } from "@storybook/react-vite";
import { MemoryRouter } from "react-router-dom";

import { DecisionCard } from "./DecisionCard";

const meta: Meta<typeof DecisionCard> = {
  title: "Trading/DecisionCard",
  component: DecisionCard,
  decorators: [(Story) => <MemoryRouter>{Story()}</MemoryRouter>],
};
export default meta;
type Story = StoryObj<typeof DecisionCard>;

export const Buy: Story = {
  args: {
    runId: "abc",
    rec: {
      action: "BUY",
      confidence: 72,
      market_regime: "trending_up",
      entry_price: 130,
      stop_loss: 125,
      take_profits: [
        { price: 135, size_fraction: 0.5 },
        { price: 140, size_fraction: 0.5 },
      ],
      position_size: { quantity: 76.9231, pct_of_equity: 10 },
      risk_reward: 1.5,
      vote_tally: { BUY: 46, HOLD: 0, SELL: 0 },
      n_evidence: 45,
      n_counterarguments: 2,
      invalidation: "A close below the shown stop level.",
      counterarguments: [
        {
          agent_id: "macro_bear",
          direction: "bearish",
          confidence: 55,
          claim: "Real yields rising; historically caps gold rallies.",
        },
      ],
      historical_analogs: [
        {
          description: "2024-03 breakout in similar low-vol regime",
          similarity: 0.82,
          outcome: "ran +6% before mean reversion",
        },
      ],
    },
  },
};

export const Rejected: Story = {
  args: {
    rec: {
      status: "rejected",
      rejection: {
        stage: "risk_gate",
        reasons: ["VaR95 0.0388 exceeds max daily loss 0.0300"],
      },
    },
  },
};

export const NoRuns: Story = {
  args: { rec: { status: "no recommendation" } },
};
