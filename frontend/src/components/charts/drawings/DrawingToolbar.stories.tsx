import type { Meta, StoryObj } from "@storybook/react-vite";
import { useState } from "react";

import { TooltipProvider } from "@/components/ui/tooltip";
import { DrawingToolbar } from "./DrawingToolbar";
import type { ToolMode } from "./types";

const meta: Meta<typeof DrawingToolbar> = {
  title: "Charts/DrawingToolbar",
  component: DrawingToolbar,
  decorators: [(Story) => <TooltipProvider>{Story()}</TooltipProvider>],
};
export default meta;
type Story = StoryObj<typeof DrawingToolbar>;

function Interactive({ count }: { count: number }) {
  const [mode, setMode] = useState<ToolMode>("select");
  return (
    <DrawingToolbar
      mode={mode}
      onModeChange={setMode}
      count={count}
      onClearAll={() => {}}
    />
  );
}

export const Empty: Story = { render: () => <Interactive count={0} /> };
export const WithDrawings: Story = { render: () => <Interactive count={3} /> };
