import type { StorybookConfig } from "@storybook/react-vite";

const config: StorybookConfig = {
  stories: ["../src/components/**/*.stories.tsx"],
  addons: ["@storybook/addon-a11y"],
  framework: { name: "@storybook/react-vite", options: {} },
  viteFinal: (viteConfig) => ({
    ...viteConfig,
    // the app's PWA plugin must not wrap Storybook's own build (its
    // manager runtime exceeds the precache size limit, and a service
    // worker inside the component workshop is meaningless anyway)
    plugins: (viteConfig.plugins ?? [])
      .flat()
      .filter((plugin) =>
        !(plugin && typeof plugin === "object" && "name" in plugin &&
          String(plugin.name).includes("pwa")),
      ),
  }),
};

export default config;
