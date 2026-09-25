import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useTradingApi } from "../hooks/useTradingApi";

const AppContext = createContext(null);

/**
 * Holds the state every page needs: the API client (from useTradingApi),
 * the loaded account, and a way to refresh it. Centralized here instead of
 * prop-drilled through the router so the navbar's quota chip and any page
 * that changes the account (Profile renaming, upgrading) stay in sync
 * without each needing to know about the others.
 */
export function AppProvider({ children }) {
  const api = useTradingApi();
  const [account, setAccount] = useState(null);
  const [accountStatus, setAccountStatus] = useState("idle"); // idle | loading | error
  const [accountMessage, setAccountMessage] = useState("");

  const loadAccount = useCallback(async () => {
    if (!api.apiKey) {
      setAccount(null);
      return;
    }
    setAccountStatus("loading");
    setAccountMessage("Loading…");
    try {
      const data = await api.fetchMe();
      setAccount(data);
      setAccountStatus("idle");
      setAccountMessage("");
    } catch (err) {
      setAccountStatus("error");
      setAccountMessage(err.message);
    }
  }, [api]);

  // Load once whenever the key changes (including on first mount, if a
  // remembered key was restored from localStorage).
  useEffect(() => {
    loadAccount();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api.apiKey]);

  const value = useMemo(
    () => ({ api, account, accountStatus, accountMessage, loadAccount }),
    [api, account, accountStatus, accountMessage, loadAccount]
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used within AppProvider");
  return ctx;
}
