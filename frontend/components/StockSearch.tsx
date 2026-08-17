"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export function StockSearch() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState<{ symbol: string; name: string; sector: string }[]>([]);

  useEffect(() => {
    const handle = setTimeout(() => {
      api.search(q).then((res) => setResults(res.results)).catch(() => setResults([]));
    }, 160);
    return () => clearTimeout(handle);
  }, [q]);

  return (
    <div className="relative min-w-[280px] flex-1">
      <input
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        placeholder="Search NSE stock — RELIANCE, HDFCBANK, INFY"
        className="w-full rounded-md border border-line bg-ink-800 px-3 py-2 text-sm outline-none ring-gold/40 placeholder:text-mist/60 focus:ring-2"
      />
      {open && results.length > 0 && (
        <div className="absolute z-50 mt-1 w-full overflow-hidden rounded-md border border-line bg-ink-800 shadow-terminal">
          {results.map((row) => (
            <button
              key={row.symbol}
              className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-ink-700"
              onClick={() => {
                setOpen(false);
                setQ("");
                router.push(`/analyze/${row.symbol}`);
              }}
            >
              <span className="font-medium">{row.symbol.replace(".NS", "")}</span>
              <span className="text-mist">{row.name}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
