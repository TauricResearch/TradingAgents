"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";

type Quote = { symbol: string; price: number; change: number; pct: number; up: boolean };

/** Bottom ticker tape: every ticker with a live run, red/green.
 *  Turns into a scrolling marquee when items overflow the bar. */
export default function Tape() {
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [marquee, setMarquee] = useState(false);
  const track = useRef<HTMLDivElement>(null);
  const bar = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let alive = true;
    async function poll() {
      try {
        const r = await api.runs();
        const tickers = [...new Set(
          (r.runs || [])
            .filter((x: any) => ["starting", "running"].includes(x.status))
            .map((x: any) => x.ticker)
            .filter(Boolean)
        )] as string[];
        const qs: Quote[] = [];
        for (const t of tickers) {
          try {
            const q = await api.quote(t);
            if (q.ok) qs.push(q);
          } catch { /* one bad quote must not kill the tape */ }
        }
        if (alive) setQuotes(qs);
      } catch { /* API down: hide tape */ }
    }
    poll();
    const t = setInterval(poll, 30000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  useEffect(() => {
    function check() {
      if (track.current && bar.current) {
        setMarquee(track.current.scrollWidth > bar.current.clientWidth + 4);
      }
    }
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, [quotes]);

  if (!quotes.length) return null;

  const items = [...quotes, ...(marquee ? quotes : [])];
  return (
    <footer className="tape" ref={bar}>
      <div ref={track} className={marquee ? "tape-track marquee" : "tape-track"}>
        {items.map((q, i) => (
          <span key={i} className="tape-item">
            <b>{q.symbol}</b>{" "}
            <span style={{ color: q.up ? "#15803d" : "#dc2626" }}>
              {q.price.toFixed(2)} {q.up ? "▲" : "▼"} {q.pct.toFixed(2)}%
            </span>
          </span>
        ))}
      </div>
    </footer>
  );
}
