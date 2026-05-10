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
          <div className="app-shell">
            <aside className="app-sidebar">
              <div className="app-brand">
                <div className="text-lg font-semibold">TradingAgents</div>
                <div className="text-xs text-muted">Recommendations, not orders</div>
              </div>
              <nav className="app-nav" aria-label="Primary navigation">
                {NAV.map((n) => (
                  <Link
                    key={n.href}
                    href={n.href}
                    className="app-nav-link"
                  >
                    {n.label}
                  </Link>
                ))}
              </nav>
            </aside>
            <main className="app-main">
              {children}
            </main>
          </div>
        </Providers>
      </body>
    </html>
  );
}
