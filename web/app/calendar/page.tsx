"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Calendar } from "@/lib/api";
import type { CalendarEvent } from "@/lib/types";

const KIND_COLOR: Record<string, string> = {
  earnings: "bg-warning/20 text-warning",
  dividend: "bg-success/20 text-success",
  run: "bg-accent/20 text-accent",
  ex_dividend: "bg-muted/20 text-muted",
};

function isoMonthEdge(d: Date, kind: "start" | "end"): string {
  const x = new Date(d);
  if (kind === "start") {
    x.setDate(1);
  } else {
    x.setMonth(x.getMonth() + 1);
    x.setDate(0);
  }
  return x.toISOString().slice(0, 10);
}

export default function CalendarPage() {
  const [cursor, setCursor] = useState(() => {
    const d = new Date();
    d.setDate(1);
    return d;
  });

  const from = isoMonthEdge(cursor, "start");
  const to = isoMonthEdge(cursor, "end");

  const q = useQuery({
    queryKey: ["calendar", from, to],
    queryFn: () => Calendar.events({ from, to }),
  });

  // Build a grid: weeks × days, each cell holds events for that date.
  const cells = useMemo(() => {
    const events = q.data ?? [];
    const byDate: Record<string, CalendarEvent[]> = {};
    for (const e of events) {
      (byDate[e.date] ??= []).push(e);
    }
    const start = new Date(from);
    const end = new Date(to);
    const firstDow = start.getDay(); // 0 = Sunday
    const out: Array<{ iso: string; day: number; events: CalendarEvent[]; in_month: boolean }> = [];
    // Lead with empty cells from prior month for grid alignment.
    for (let i = 0; i < firstDow; i++) {
      out.push({ iso: "", day: 0, events: [], in_month: false });
    }
    for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
      const iso = d.toISOString().slice(0, 10);
      out.push({ iso, day: d.getDate(), events: byDate[iso] ?? [], in_month: true });
    }
    while (out.length % 7 !== 0) out.push({ iso: "", day: 0, events: [], in_month: false });
    return out;
  }, [q.data, from, to]);

  const monthLabel = cursor.toLocaleString("en-US", { month: "long", year: "numeric" });

  return (
    <div className="space-y-4">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold">Calendar</h1>
          <p className="text-muted text-sm">
            Earnings, dividends, and your past+upcoming runs across watchlist tickers.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn" onClick={() => { const d = new Date(cursor); d.setMonth(d.getMonth() - 1); setCursor(d); }}>← Prev</button>
          <div className="text-lg font-semibold w-44 text-center">{monthLabel}</div>
          <button className="btn" onClick={() => { const d = new Date(cursor); d.setMonth(d.getMonth() + 1); setCursor(d); }}>Next →</button>
          <button className="btn text-xs" onClick={() => { const d = new Date(); d.setDate(1); setCursor(d); }}>Today</button>
        </div>
      </header>

      <div className="card">
        <div className="grid grid-cols-7 gap-px bg-border">
          {["Sun","Mon","Tue","Wed","Thu","Fri","Sat"].map((d) => (
            <div key={d} className="bg-surface text-center py-2 text-xs uppercase tracking-wider text-muted">{d}</div>
          ))}
          {cells.map((c, i) => (
            <div
              key={i}
              className={`bg-bg min-h-[110px] p-1.5 ${c.in_month ? "" : "opacity-30"}`}
            >
              {c.in_month && (
                <>
                  <div className="text-xs text-muted mb-1">{c.day}</div>
                  <div className="space-y-0.5">
                    {c.events.slice(0, 5).map((e, j) => (
                      <EventChip key={j} ev={e} />
                    ))}
                    {c.events.length > 5 && (
                      <div className="text-xs text-muted">+{c.events.length - 5} more</div>
                    )}
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-2 text-xs">
        <span className={`pill ${KIND_COLOR.run}`}>● run</span>
        <span className={`pill ${KIND_COLOR.earnings}`}>● earnings</span>
        <span className={`pill ${KIND_COLOR.dividend}`}>● dividend</span>
      </div>
    </div>
  );
}

function EventChip({ ev }: { ev: CalendarEvent }) {
  const cls = KIND_COLOR[ev.kind] ?? "bg-muted/20 text-muted";
  const label = ev.ticker
    ? `${ev.ticker}${ev.detail ? ` ${ev.detail}` : ""}`
    : ev.title;

  if (ev.kind === "run" && ev.payload?.run_id) {
    return (
      <Link
        href={`/history/${ev.payload.run_id}`}
        className={`block ${cls} text-xs px-1.5 py-0.5 rounded truncate hover:underline`}
        title={ev.title + (ev.detail ? ` — ${ev.detail}` : "")}
      >
        {label}
      </Link>
    );
  }
  return (
    <div
      className={`${cls} text-xs px-1.5 py-0.5 rounded truncate`}
      title={ev.title + (ev.detail ? ` — ${ev.detail}` : "")}
    >
      {label}
    </div>
  );
}
