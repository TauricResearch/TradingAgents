import { useEffect, useState } from "react";

const STORAGE_KEY = "tradingagents.theme";

function systemPrefersDark() {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
}

export function ThemeToggle() {
  const [theme, setTheme] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) || "system";
    } catch {
      return "system";
    }
  });

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") {
      root.removeAttribute("data-theme");
    } else {
      root.setAttribute("data-theme", theme);
    }
    try {
      if (theme === "system") localStorage.removeItem(STORAGE_KEY);
      else localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // ignore unavailable storage
    }
  }, [theme]);

  function toggle() {
    const resolved = theme === "system" ? (systemPrefersDark() ? "dark" : "light") : theme;
    setTheme(resolved === "dark" ? "light" : "dark");
  }

  const isDark = theme === "dark" || (theme === "system" && systemPrefersDark());

  return (
    <button type="button" className="theme-toggle" onClick={toggle} aria-pressed={isDark}>
      {isDark ? "light mode" : "dark mode"}
    </button>
  );
}
