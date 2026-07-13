import type { Preview } from "@storybook/react-vite";

import "../src/styles/globals.css";

const preview: Preview = {
  globalTypes: {
    theme: {
      description: "Color theme",
      toolbar: { title: "Theme", items: ["dark", "light"] },
    },
  },
  initialGlobals: { theme: "light" },
  decorators: [
    (Story, context) => {
      document.documentElement.dataset.theme = String(context.globals.theme);
      document.body.style.background = "var(--bg)";
      return Story();
    },
  ],
  parameters: {
    backgrounds: { disable: true },
  },
};

export default preview;
