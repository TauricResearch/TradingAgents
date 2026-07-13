/** Boot auth: exchange stored key for the session cookie; on 401 show a
 * proper token dialog (no window.prompt). Open backends skip straight
 * through. */
import { Lock } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  clearToken,
  establishSession,
  getToken,
  registerUnauthorizedHandler,
  setToken,
} from "@/lib/api/client";

type Phase = "checking" | "need-token" | "ready";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const [phase, setPhase] = useState<Phase>("checking");
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);

  const attempt = useCallback(async () => {
    try {
      await establishSession();
      setPhase("ready");
      setError(null);
    } catch {
      clearToken();
      setPhase("need-token");
    }
  }, []);

  useEffect(() => {
    registerUnauthorizedHandler(() => setPhase("need-token"));
    void attempt();
  }, [attempt]);

  if (phase === "checking") {
    return (
      <div className="flex h-screen items-center justify-center text-fg-muted">
        Connecting…
      </div>
    );
  }

  if (phase === "need-token") {
    return (
      <div className="flex h-screen items-center justify-center">
        <form
          className="w-full max-w-sm space-y-3 rounded-[20px] border border-border bg-surface p-7 shadow-(--shadow-1) backdrop-blur-[16px]"
          onSubmit={(event) => {
            event.preventDefault();
            if (!draft.trim()) return;
            setToken(draft.trim());
            setDraft("");
            void attempt().then(() => {
              if (getToken() === null) setError("Invalid token.");
            });
          }}
        >
          <h1 className="text-lg font-bold">TradingAgents Pro</h1>
          <p className="text-sm text-fg-muted">
            This dashboard is token-protected. Paste the API token
            (PRO_DASHBOARD_TOKEN) to continue.
          </p>
          <label className="block text-sm">
            <span className="sr-only">API token</span>
            <Input
              type="password"
              autoFocus
              placeholder="API token"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              data-testid="token-input"
            />
          </label>
          {error && <p className="text-sm text-bear">{error}</p>}
          <Button type="submit" className="w-full" data-testid="token-submit">
            Unlock
          </Button>
          <p className="flex items-center justify-center gap-1.5 pt-1 text-[11px] text-fg-subtle">
            <Lock size={11} aria-hidden="true" /> Your security is our priority
          </p>
        </form>
      </div>
    );
  }

  return <>{children}</>;
}
