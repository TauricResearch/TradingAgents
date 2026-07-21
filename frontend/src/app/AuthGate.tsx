/** Boot auth: exchange stored key for the session cookie; on 401 show a
 * proper login screen (no window.prompt). Open backends skip straight
 * through.
 *
 * Which login UI renders is the SERVER's call (/api/auth/config): when
 * Google sign-in is configured (deployed site) the card is Google-only;
 * otherwise it's the API-token form (localhost/demo/e2e — the whole
 * Playwright suite unlocks via token-input/token-submit). */
import { Lock } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  type AuthConfig,
  clearToken,
  establishGoogleSession,
  establishSession,
  fetchAuthConfig,
  getToken,
  registerUnauthorizedHandler,
  setToken,
} from "@/lib/api/client";

type Phase = "checking" | "need-login" | "ready";

function GoogleMark() {
  // official "G" in currentColor-free brand colors, inline (no asset fetch)
  return (
    <svg width="16" height="16" viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
      <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
    </svg>
  );
}

export function AuthGate({ children }: { children: React.ReactNode }) {
  const [phase, setPhase] = useState<Phase>("checking");
  const [config, setConfig] = useState<AuthConfig | null>(null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const attempt = useCallback(async () => {
    try {
      await establishSession();
      setPhase("ready");
      setError(null);
    } catch {
      clearToken();
      try {
        setConfig(await fetchAuthConfig());
      } catch {
        setConfig(null); // older backend: fall back to the token form
      }
      setPhase("need-login");
    }
  }, []);

  useEffect(() => {
    registerUnauthorizedHandler(() => setPhase("need-login"));
    void attempt();
  }, [attempt]);

  const googleSignIn = useCallback(async () => {
    if (!config?.firebase) return;
    setBusy(true);
    setError(null);
    try {
      const { signInWithGoogle } = await import("@/lib/googleSignIn");
      const idToken = await signInWithGoogle(config.firebase);
      await establishGoogleSession(idToken);
      setPhase("ready");
    } catch (err) {
      const detail =
        err instanceof Error && "status" in err && (err as { status: number }).status === 403
          ? "That Google account isn't authorized for this dashboard."
          : "Google sign-in failed — try again.";
      setError(detail);
    } finally {
      setBusy(false);
    }
  }, [config]);

  if (phase === "checking") {
    return (
      <div className="flex h-screen items-center justify-center text-fg-muted">
        Connecting…
      </div>
    );
  }

  if (phase === "need-login") {
    const google = config?.google === true;
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-3">
        {google ? (
          <div className="w-full max-w-sm space-y-3 rounded-[20px] border border-border bg-surface p-7 shadow-(--shadow-1) backdrop-blur-[16px]">
            <h1 className="text-lg font-bold">TradingAgents Pro</h1>
            <p className="text-sm text-fg-muted">
              Sign in with your authorized Google account to continue.
            </p>
            <Button
              type="button"
              className="w-full gap-2"
              onClick={() => void googleSignIn()}
              disabled={busy}
              data-testid="google-signin"
            >
              <GoogleMark />
              {busy ? "Signing in…" : "Continue with Google"}
            </Button>
            {error && <p className="text-sm text-bear">{error}</p>}
            <p className="flex items-center justify-center gap-1.5 pt-1 text-[11px] text-fg-subtle">
              <Lock size={11} aria-hidden="true" /> Access limited to
              allowlisted accounts
            </p>
          </div>
        ) : (
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
        )}
        <button
          type="button"
          onClick={() => {
            setError(null);
            setPhase("checking");
            void attempt();
          }}
          className="text-xs text-fg-subtle underline-offset-2 hover:text-fg hover:underline"
          data-testid="auth-retry"
        >
          Trouble connecting? Retry
        </button>
      </div>
    );
  }

  return <>{children}</>;
}
