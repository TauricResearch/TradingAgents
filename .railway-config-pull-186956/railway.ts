import { defineRailway, project, service } from "railway/iac";

export default defineRailway(() => {
  const web = service("web", {
    // Add build/start commands when Railway cannot infer them.
    // build: "pnpm install --frozen-lockfile && pnpm build",
    // start: "pnpm start",
    env: {
      NODE_ENV: "production",
    },
  });

  return project("import-placeholder", {
    resources: [web],
  });
});
