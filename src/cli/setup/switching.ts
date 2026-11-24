// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The setup's actions in the chat, where what they save applies to the open session too: a model chosen
 * (or a server saved) runs from the next question, and a key for what the session uses (its model's
 * provider, Tauric's data) is used from then on.
 */

import { ENV } from "../../config/index.js";
import { type ModelRoute, message, type RouteName } from "../../contracts/index.js";
import { routeOf } from "../../engine/index.js";
import type { SetupActions } from "./setup-flows.js";

/** The open session, as the setup moves it. */
type Switching<Next> = {
  /** What the session would run on with `route`; refused (thrown) when it cannot be used now. */
  choose(route: RouteName): Promise<Next>;
  /** Run the session on it from its next question. */
  apply(next: Next): Promise<void>;
  /** The model the session runs on now. */
  current(): ModelRoute;
  /** The address a server model `next` would be reached at. */
  endpointOf(next: Next): string | undefined;
};

export function switchingActions<Next>(saved: SetupActions, session: Switching<Next>): SetupActions {
  /** Applied again on its own route, so what was saved for it is read. */
  const reconnect = async () => session.apply(await session.choose(routeOf(session.current())));
  return {
    ...saved,
    // Resolved before it is saved: a model that cannot be used now is refused, and nothing changes.
    async saveModel(choice) {
      // A choice of the provider's default level names it, so the level set before is not carried over.
      const next = await session.choose(
        choice.reasoning || choice.provider === "openai-compatible"
          ? choice
          : { ...choice, reasoning: "provider-default" },
      );
      await saved.saveModel(choice);
      await session.apply(next);
    },
    async saveKey(name, key) {
      await saved.saveKey(name, key);
      const { provider } = session.current();
      if (name === "tauric" || name === provider || (name === "model" && provider === "openai-compatible"))
        await reconnect();
    },
    // A server saved is the model from here on, as a model chosen is.
    // The conversation goes only to the address given: one the environment names in its place is not used.
    async saveServer(server, key) {
      await saved.saveServer(server, key);
      const next = await session.choose({ provider: "openai-compatible", model: server.model });
      const bare = (address: string | undefined) => address?.replace(/\/+$/, "");
      if (bare(session.endpointOf(next)) !== bare(server.baseURL))
        throw new Error(message("setup.serverNamedElsewhere", { variable: ENV.baseURL }));
      await session.apply(next);
    },
  };
}
