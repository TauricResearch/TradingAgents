import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, Bell, BellOff, Send, Settings, Trash2 } from "lucide-react";
import {
  addIndicator,
  checkIndicators,
  fetchIndicators,
  fetchNotifierConfig,
  removeIndicator,
  updateIndicator,
  testNotifier,
  updateNotifierConfig,
  base,
  fetchSchedule,
  updateSchedule,
  type IndicatorDefinition,
  type IndicatorKind,
  type NotifierConfig,
} from "../lib/api";

const KIND_ALIASES: Array<[RegExp, IndicatorKind]> = [
  [/\b(vix|volatility)\b/i, "vix"],
  [/\b(fear|greed|f&g)\b/i, "fear_greed"],
  [/\b(red|down)\b/i, "red_days"],
  [/\b(s5fi|breadth)\b/i, "s5fi"],
  [/\b(green|up streak|winning)\b/i, "green_streak"],
  [/\b(ma|moving average|average|50|150|200)\b/i, "price_vs_moving_averages"],
];

function formatThreshold(indicator: IndicatorDefinition): string {
  if (indicator.kind === "price_vs_moving_averages") return `${(indicator.threshold * 100).toFixed(2)}%`;
  if (indicator.unit === "%") return `${indicator.threshold.toFixed(0)}%`;
  if (indicator.unit === "days") return `${indicator.threshold.toFixed(0)}d`;
  return indicator.threshold.toString();
}

function parseKind(text: string): IndicatorKind | null {
  return KIND_ALIASES.find(([pattern]) => pattern.test(text))?.[1] ?? null;
}

function parseThreshold(text: string): number | undefined {
  const match = text.match(/(?:threshold|at|above|below|within|to)?\s*(\d+(?:\.\d+)?)\s*%?/i);
  if (!match) return undefined;
  const value = Number(match[1]);
  if (!Number.isFinite(value)) return undefined;
  return /\b(percent|%)\b/i.test(text) ? value / 100 : value;
}

export function IndicatorRailView() {
  const qc = useQueryClient();
  const [chat, setChat] = useState("");
  const [reply, setReply] = useState("Ask me to add or remove an indicator.");
  const [showNotifierSettings, setShowNotifierSettings] = useState(false);
  const [notifierForm, setNotifierForm] = useState({ bot_token: "", chat_id: "" });
  const [notifierTestMsg, setNotifierTestMsg] = useState("");
  const [autoCheckInterval, setAutoCheckInterval] = useState(0);
  const [countdown, setCountdown] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState<string>("");

  const notifierQuery = useQuery({
    queryKey: ["notifier-config"],
    queryFn: fetchNotifierConfig,
    staleTime: 60_000,
    retry: false,
  });

  const notifierMutation = useMutation({
    mutationFn: (body: { enabled?: boolean; bot_token?: string | null; chat_id?: string | null }) =>
      updateNotifierConfig(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notifier-config"] });
      setNotifierTestMsg("");
    },
    onError: (err: Error) => {
      const apiErr = err as { detail?: string };
      setNotifierTestMsg(apiErr.detail || err.message);
    },
  });

  const testMutation = useMutation({
    mutationFn: testNotifier,
    onSuccess: () => {
      setNotifierTestMsg("Test message sent!");
      setTimeout(() => setNotifierTestMsg(""), 4000);
    },
    onError: (err: Error) => {
      const apiErr = err as { message: string; detail?: unknown };
      const detail = apiErr.detail;
      const msg =
        typeof detail === "string"
          ? detail
          : (detail as { detail?: string })?.detail || err.message;
      setNotifierTestMsg(msg);
      setTimeout(() => setNotifierTestMsg(""), 6000);
    },
  });

  useEffect(() => {
    if (notifierQuery.data) {
      setNotifierForm({
        bot_token: notifierQuery.data.bot_token ?? "",
        chat_id: notifierQuery.data.chat_id ?? "",
      });
    }
  }, [notifierQuery.data]);

  const notifierEnabled = notifierQuery.data?.enabled ?? false;

  const scheduleQuery = useQuery({
    queryKey: ["indicator-schedule"],
    queryFn: fetchSchedule,
    staleTime: 60_000,
  });

  const scheduleMutation = useMutation({
    mutationFn: updateSchedule,
    onSuccess: (data) => {
      qc.setQueryData(["indicator-schedule"], data);
    },
  });

  useEffect(() => {
    if (scheduleQuery.data && typeof scheduleQuery.data.interval_ms === "number") {
      setAutoCheckInterval(scheduleQuery.data.interval_ms);
    }
  }, [scheduleQuery.data]);

  // Countdown timer for next auto-check
  useEffect(() => {
    const intervalMs = scheduleQuery.data?.interval_ms;
    const lastCheckAt = scheduleQuery.data?.last_check_at;
    if (!intervalMs || intervalMs === 0) {
      setCountdown("");
      return;
    }
    const tick = () => {
      if (!lastCheckAt) {
        setCountdown("waiting...");
        return;
      }
      const nextCheck = new Date(lastCheckAt).getTime() + intervalMs;
      const diff = nextCheck - Date.now();
      if (diff <= 0) {
        setCountdown("now");
        return;
      }
      const h = Math.floor(diff / 3600000);
      const m = Math.floor((diff % 3600000) / 60000);
      const s = Math.floor((diff % 60000) / 1000);
      setCountdown(h > 0 ? `${h}h ${m}m ${s}s` : `${m}m ${s}s`);
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [scheduleQuery.data]);

  const indicatorsQuery = useQuery({
    queryKey: ["indicators"],
    queryFn: fetchIndicators,
    staleTime: 30_000,
  });

  const checksMutation = useMutation({
    mutationFn: checkIndicators,
  });
  const addMutation = useMutation({
    mutationFn: addIndicator,
    onSuccess: (indicator) => {
      qc.invalidateQueries({ queryKey: ["indicators"] });
      setReply(`Added ${indicator.name} at ${formatThreshold(indicator)}.`);
    },
  });
  const removeMutation = useMutation({
    mutationFn: removeIndicator,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["indicators"] });
      setReply("Removed indicator.");
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: { threshold?: number; enabled?: boolean } }) =>
      updateIndicator(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["indicators"] });
      setReply("Threshold updated.");
    },
    onError: (err: Error) => {
      const apiErr = err as { message: string; body?: unknown };
      const detail = apiErr.body as { detail?: string } | undefined;
      const msg = detail?.detail || apiErr.message;
      setReply(msg);
    },
  });

  const indicators = indicatorsQuery.data?.indicators ?? [];
  const checksById = useMemo(() => {
    const map = new Map();
    for (const check of checksMutation.data?.checks ?? []) {
      map.set(check.indicator.id, check.result);
    }
    return map;
  }, [checksMutation.data]);

  const handleChatSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const text = chat.trim();
    if (!text) return;
    setChat("");

    if (/\b(remove|delete)\b/i.test(text)) {
      const lower = text.toLowerCase();
      const target =
        indicators.find((item) => lower.includes(item.id.toLowerCase())) ??
        indicators.find((item) => lower.includes(item.name.toLowerCase())) ??
        (parseKind(text)
          ? indicators.find((item) => item.kind === parseKind(text))
          : undefined);
      if (!target) {
        setReply("I could not tell which indicator to remove.");
        return;
      }
      removeMutation.mutate(target.id);
      return;
    }

    if (/\b(add|create|new)\b/i.test(text)) {
      const kind = parseKind(text);
      if (!kind) {
        setReply("Name the indicator type: VIX, fear greed, red days, S5FI, green streak, or moving averages.");
        return;
      }
      const threshold = parseThreshold(text);
      addMutation.mutate({ kind, threshold });
      return;
    }

    setReply("Try: add VIX threshold 25, add fear greed 15, or remove VIX.");
  };

  return (
    <div className="flex h-full flex-col">
      <div className="shrink-0 px-4 py-3 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <Activity className="h-3.5 w-3.5 text-emerald-400" aria-hidden="true" />
          <span className="text-xs font-semibold uppercase tracking-widest text-slate-400">Indicators</span>
          <span className="ml-auto text-[10px] text-slate-600">{indicators.length}</span>
          <button
            type="button"
            onClick={() => setShowNotifierSettings((v) => !v)}
            className={`rounded-md p-1 transition-colors ${
              notifierEnabled ? "text-emerald-400 hover:bg-emerald-400/10" : "text-slate-600 hover:text-slate-400"
            }`}
            title={notifierEnabled ? "Telegram notifications enabled" : "Telegram notifications disabled"}
          >
            {notifierEnabled ? <Bell className="h-3.5 w-3.5" /> : <BellOff className="h-3.5 w-3.5" />}
          </button>
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-slate-500">Schedule:</span>
          <select
            className="bg-slate-800 text-xs text-slate-200 border border-slate-600 rounded px-1.5 py-1 cursor-pointer"
            value={scheduleQuery.data?.interval_ms ?? 0}
            onChange={(e) => scheduleMutation.mutate(Number(e.target.value))}
          >
            <option value={0}>Off (manual only)</option>
            <option value={3600000}>Every 1h</option>
            <option value={7200000}>Every 2h</option>
            <option value={14400000}>Every 4h</option>
            <option value={28800000}>Every 8h</option>
            <option value={43200000}>Every 12h</option>
            <option value={86400000}>Every 24h</option>
            <option value={172800000}>Every 48h</option>
          </select>
          <button
            type="button"
            onClick={() => checksMutation.mutate()}
            disabled={checksMutation.isPending}
            className="btn-primary text-xs"
          >
            {checksMutation.isPending ? "Checking…" : "Run Now"}
          </button>
          {countdown && (
            <span className="ml-2 text-[10px] text-slate-500">
              Next check in: <span className={`font-mono ${countdown === "now" ? "text-emerald-400" : "text-sky-400"}`}>{countdown}</span>
            </span>
          )}
        </div>

        {showNotifierSettings && (
          <div className="mt-3 rounded-lg border border-slate-700/50 bg-slate-900/60 p-3 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-300">Telegram Notifications</span>
              <button
                type="button"
                onClick={() => setShowNotifierSettings(false)}
                className="text-slate-500 hover:text-slate-300 text-lg leading-none"
              >
                ×
              </button>
            </div>

            <label className="flex items-center gap-2 text-xs text-slate-400 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={notifierEnabled}
                onChange={(e) =>
                  notifierMutation.mutate({ enabled: e.target.checked })
                }
                className="w-3.5 h-3.5 rounded accent-emerald-400 cursor-pointer"
              />
              Enable notifications
            </label>

            <div>
              <label className="block text-[10px] uppercase tracking-wider text-slate-500 mb-1">
                Bot Token
              </label>
              <input
                type="password"
                value={notifierForm.bot_token}
                onChange={(e) => setNotifierForm((f) => ({ ...f, bot_token: e.target.value }))}
                onBlur={() => notifierMutation.mutate({ bot_token: notifierForm.bot_token || null })}
                placeholder="123456:ABC-..."
                className="w-full rounded bg-slate-800 border border-slate-700 px-2 py-1 text-xs text-slate-200 outline-none focus:border-slate-500"
              />
            </div>

            <div>
              <label className="block text-[10px] uppercase tracking-wider text-slate-500 mb-1">
                Chat ID
              </label>
              <input
                type="text"
                value={notifierForm.chat_id}
                onChange={(e) => setNotifierForm((f) => ({ ...f, chat_id: e.target.value }))}
                onBlur={() => notifierMutation.mutate({ chat_id: notifierForm.chat_id || null })}
                placeholder="123456789"
                className="w-full rounded bg-slate-800 border border-slate-700 px-2 py-1 text-xs text-slate-200 outline-none focus:border-slate-500"
              />
            </div>

            <button
              type="button"
              disabled={testMutation.isPending}
              onClick={() => testMutation.mutate()}
              className="w-full rounded bg-slate-700 hover:bg-slate-600 px-2 py-1 text-xs text-slate-300 transition-colors disabled:opacity-50"
            >
              {testMutation.isPending ? "Sending..." : "Send Test Message"}
            </button>

            {notifierTestMsg && (
              <p className={`text-[10px] ${testMutation.isError ? "text-red-400" : "text-emerald-400"}`}>
                {notifierTestMsg}
              </p>
            )}
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-2 space-y-2">
        {indicatorsQuery.isLoading && <p className="px-2 py-6 text-center text-xs text-slate-500">Loading indicators...</p>}
        {indicators.map((indicator) => {
          const result = checksById.get(indicator.id);
          return (
            <div key={indicator.id} className="rounded-lg border border-slate-700/50 bg-slate-800/40 p-2.5">
              <div className="flex items-start gap-2">
                <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${
                  result?.triggered ? "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]" : result ? "bg-slate-500" : "bg-slate-700"
                }`} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline gap-1.5">
                    <p className="truncate text-sm font-semibold text-slate-100">{indicator.name}</p>
                    <span className="text-[9px] uppercase tracking-wider text-slate-600">{indicator.source}</span>
                  </div>
                  <p className="mt-0.5 text-[11px] leading-snug text-slate-500">{indicator.description}</p>
                  <div className="mt-2 flex items-center gap-1.5 text-[10px] text-slate-500">
                    {editingId === indicator.id ? (
                      <input
                        type="number"
                        value={editValue}
                        onChange={(e) => setEditValue(e.target.value)}
                        onBlur={() => {
                          const newThreshold = parseFloat(editValue);
                          if (!isNaN(newThreshold)) {
                            updateMutation.mutate({ id: indicator.id, body: { threshold: newThreshold } });
                          }
                          setEditingId(null);
                        }}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            const newThreshold = parseFloat(editValue);
                            if (!isNaN(newThreshold)) {
                              updateMutation.mutate({ id: indicator.id, body: { threshold: newThreshold } });
                            }
                            setEditingId(null);
                          } else if (e.key === "Escape") {
                            setEditingId(null);
                          }
                        }}
                        autoFocus
                        className="w-20 rounded border border-sky-500 bg-slate-900 px-1.5 py-0.5 text-xs text-sky-300 outline-none"
                      />
                    ) : (
                      <span
                        onClick={() => {
                          setEditingId(indicator.id);
                          setEditValue(indicator.threshold.toString());
                        }}
                        className="cursor-pointer rounded border border-slate-700/60 bg-slate-900/40 px-1.5 py-0.5 text-xs text-slate-300 hover:border-slate-500"
                      >
                        {indicator.comparator} {formatThreshold(indicator)}
                      </span>
                    )}
                    {result?.checked_at && <span>{result.checked_at.slice(0, 16).replace("T", " ")}</span>}
                  </div>
                  {result?.message && (
                    <p className={`mt-2 text-xs leading-snug ${result.triggered ? "text-emerald-300" : "text-slate-400"}`}>
                      {result.message}
                    </p>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => removeMutation.mutate(indicator.id)}
                  disabled={removeMutation.isPending}
                  className="rounded-md p-1 text-slate-600 transition-colors hover:text-red-400"
                  title={`Remove ${indicator.name}`}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          );
        })}
      </div>

      <form onSubmit={handleChatSubmit} className="shrink-0 border-t border-slate-800 p-2">
        <p className="mb-2 rounded-lg bg-slate-800/50 px-2 py-1.5 text-[11px] leading-snug text-slate-400">{reply}</p>
        <div className="flex items-center gap-1.5 rounded-lg border border-slate-700/50 bg-slate-950/40 px-2 py-1.5">
          <input
            value={chat}
            onChange={(e) => setChat(e.target.value)}
            placeholder="add VIX 25..."
            className="min-w-0 flex-1 bg-transparent text-xs text-slate-200 outline-none placeholder:text-slate-600"
            aria-label="Indicator chat command"
          />
          <button
            type="submit"
            disabled={!chat.trim() || addMutation.isPending || removeMutation.isPending}
            className="rounded-md p-1 text-sky-400 transition-colors hover:bg-sky-500/10 disabled:text-slate-600"
            aria-label="Send indicator command"
          >
            <Send className="h-3.5 w-3.5" />
          </button>
        </div>
      </form>
    </div>
  );
}
