import { useLogStore } from "../store/logs";

const LEVEL_MAP: Record<string, LogEntry["level"]> = {
  log: "INFO",
  info: "INFO",
  warn: "WARNING",
  error: "ERROR",
  debug: "DEBUG",
};

type LogEntry = ReturnType<typeof useLogStore.getState>["entries"][number];

let _capturing = false;

function makeCapture(method: "log" | "info" | "warn" | "error" | "debug") {
  const original = console[method].bind(console);
  return (...args: unknown[]) => {
    if (!_capturing) {
      original(...args);
      return;
    }
    const msg = args.map((a) => (typeof a === "string" ? a : JSON.stringify(a))).join(" ");
    useLogStore.getState().append({
      id: crypto.randomUUID(),
      ts: new Date().toISOString(),
      level: LEVEL_MAP[method] ?? "INFO",
      logger: "console",
      message: msg,
      source: "client",
    });
    original(...args);
  };
}

_capturing = true;
console.log = makeCapture("log");
console.info = makeCapture("info");
console.warn = makeCapture("warn");
console.error = makeCapture("error");
console.debug = makeCapture("debug");