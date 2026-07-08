/** One registry powers keyboard handling, the command palette, and the
 * `?` cheatsheet. Deliberate omission: the kill switch has NO bare
 * shortcut — halting trading must be fast to find (palette) and
 * impossible to fat-finger. */

export interface Command {
  id: string;
  title: string;
  group: "Navigate" | "Trade context" | "Actions" | "System";
  keys?: string; // display string, e.g. "g h"
  run: () => void;
}

type Registry = Map<string, Command>;
const registry: Registry = new Map();

export function registerCommands(commands: Command[]): () => void {
  commands.forEach((c) => registry.set(c.id, c));
  return () => commands.forEach((c) => registry.delete(c.id));
}

export function allCommands(): Command[] {
  return [...registry.values()];
}

const isEditable = (el: EventTarget | null) =>
  el instanceof HTMLElement &&
  (el.tagName === "INPUT" ||
    el.tagName === "TEXTAREA" ||
    el.tagName === "SELECT" ||
    el.isContentEditable);

/** Two-key chords: `g` then a letter, vim style. */
export function installKeyboardHandler(handlers: {
  go: (key: string) => void;
  openPalette: () => void;
  openSearch: () => void;
  openCheatsheet: () => void;
  toggleSymbol: () => void;
  setTimeframe: (index: number) => void;
  toggleTheme: () => void;
}): () => void {
  let chord: "g" | null = null;
  let chordTimer: ReturnType<typeof setTimeout> | null = null;

  const onKeyDown = (event: KeyboardEvent) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      handlers.openPalette();
      return;
    }
    if (isEditable(event.target) || event.metaKey || event.ctrlKey || event.altKey)
      return;

    if (chord === "g") {
      chord = null;
      if (chordTimer) clearTimeout(chordTimer);
      handlers.go(event.key.toLowerCase());
      return;
    }

    switch (event.key) {
      case "g":
        chord = "g";
        chordTimer = setTimeout(() => (chord = null), 1500);
        break;
      case "/":
        event.preventDefault();
        handlers.openSearch();
        break;
      case "?":
        handlers.openCheatsheet();
        break;
      case "x":
        handlers.toggleSymbol();
        break;
      case "D":
        handlers.toggleTheme();
        break;
      default: {
        const n = parseInt(event.key, 10);
        if (n >= 1 && n <= 7) handlers.setTimeframe(n - 1);
      }
    }
  };

  window.addEventListener("keydown", onKeyDown);
  return () => window.removeEventListener("keydown", onKeyDown);
}

export const SHORTCUT_CHEATSHEET: { keys: string; action: string }[] = [
  { keys: "⌘K / Ctrl+K", action: "Command palette" },
  { keys: "g h / t / d / p / i / s", action: "Go Home / Trade / Decisions / Portfolio / Intel / Settings" },
  { keys: "/", action: "Global search" },
  { keys: "x", action: "Toggle symbol (XAUUSD ↔ BTC-USD)" },
  { keys: "1…7", action: "Timeframe 1m 5m 15m 1h 4h 1D 1W" },
  { keys: "⇧D", action: "Toggle theme" },
  { keys: "?", action: "This cheatsheet" },
  { keys: "Esc", action: "Close dialog / palette" },
];
