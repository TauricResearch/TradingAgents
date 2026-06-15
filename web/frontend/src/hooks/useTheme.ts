import { useState, useEffect, useCallback } from "react";

const STORAGE_KEY = "tradingagents-theme";

function getInitialTheme(): "dark" | "light" {
  if (typeof window === "undefined") return "dark";
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "light" || stored === "dark") return stored;
  return "dark";
}

function applyTheme(theme: "dark" | "light") {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem(STORAGE_KEY, theme);
}

export function useTheme() {
  const [theme, setThemeState] = useState<"dark" | "light">(getInitialTheme);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const toggleTheme = useCallback(() => {
    setThemeState((prev) => (prev === "dark" ? "light" : "dark"));
  }, []);

  return { theme, toggleTheme };
}
