"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { api, clearSession, getToken, getUser } from "@/lib/api";
import { StockSearch } from "./StockSearch";

const NAV = [
  { href: "/", label: "Command" },
  { href: "/market", label: "Market" },
  { href: "/watchlist", label: "Watchlist" },
  { href: "/history", label: "History" },
  { href: "/backtest", label: "Evaluation" },
  { href: "/settings", label: "Setup" },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const user = useMemo(() => (ready ? getUser() : null), [ready, pathname]);
  const publicPage = pathname === "/login";

  useEffect(() => {
    setReady(true);
    if (!getToken() && !publicPage) router.replace("/login");
  }, [pathname, publicPage, router]);

  const market = useQuery({
    queryKey: ["market"],
    queryFn: api.market,
    enabled: ready && !publicPage,
    refetchInterval: 60_000,
  });

  if (publicPage) return <>{children}</>;
  if (!ready) return <div className="p-10 text-mist">Loading terminal…</div>;

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-40 border-b border-line bg-ink-950/90 backdrop-blur">
        <div className="mx-auto flex max-w-[1600px] items-center gap-4 px-4 py-3">
          <Link href="/" className="shrink-0 text-sm font-semibold tracking-[0.22em] text-gold">
            TRADINGAGENTS
          </Link>
          <StockSearch />
          <div className="ml-auto flex items-center gap-4 text-xs">
            {market.data?.regime && (
              <span className="rounded border border-line px-2 py-1 text-mist">
                NSE {market.data.regime}
              </span>
            )}
            <span className="text-mist">{user?.email}</span>
            <button
              className="text-mist hover:text-white"
              onClick={() => {
                clearSession();
                router.push("/login");
              }}
            >
              Sign out
            </button>
          </div>
        </div>
        <nav className="mx-auto flex max-w-[1600px] gap-1 px-4 pb-2">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`rounded-md px-3 py-1.5 text-sm ${
                pathname === item.href ? "bg-ink-700 text-white" : "text-mist hover:text-white"
              }`}
            >
              {item.label}
            </Link>
          ))}
          {user?.role === "admin" && (
            <Link
              href="/admin"
              className={`rounded-md px-3 py-1.5 text-sm ${
                pathname === "/admin" ? "bg-ink-700 text-white" : "text-mist hover:text-white"
              }`}
            >
              Admin
            </Link>
          )}
        </nav>
      </header>
      <main className="mx-auto max-w-[1600px] px-4 py-6">{children}</main>
    </div>
  );
}
