import type { Metadata } from "next";
import Link from "next/link";
import { Providers } from "./providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "TradingAgents",
  description:
    "Multi-agent LLM trading research dashboard. Recommendations only — not orders.",
};

const NAV = [
  { href: "/", label: "Home" },
  { href: "/watchlist", label: "Watchlist" },
  { href: "/portfolio", label: "Portfolio" },
  { href: "/run", label: "Run" },
  { href: "/history", label: "History" },
  { href: "/calendar", label: "Calendar" },
  { href: "/news", label: "News" },
  { href: "/simulation", label: "Simulation" },
  { href: "/notes", label: "Notes" },
  { href: "/memory", label: "Memory" },
  { href: "/settings", label: "Settings" },
];

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <Providers>
          <div className="min-h-screen flex">
            <aside className="w-56 shrink-0 border-r border-border p-4 sticky top-0 h-screen">
              <div className="text-lg font-semibold mb-1">TradingAgents</div>
              <div className="text-xs text-muted mb-6">Recommendations, not orders</div>
              <nav className="space-y-1">
                {NAV.map((n) => (
                  <Link
                    key={n.href}
                    href={n.href}
                    className="block px-2 py-1.5 rounded text-sm hover:bg-surface"
                  >
                    {n.label}
                  </Link>
                ))}
              </nav>
            </aside>
            <main className="flex-1 px-6 py-6 max-w-[1400px] mx-auto w-full">
              {children}
            </main>
          </div>
        </Providers>
      </body>
    </html>
  );
}
