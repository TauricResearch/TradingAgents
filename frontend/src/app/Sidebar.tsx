/** Left icon rail (desktop) / bottom tab bar (mobile). */
import {
  BrainCircuit,
  CandlestickChart,
  Globe,
  LayoutDashboard,
  Settings,
  Wallet,
} from "lucide-react";
import { NavLink } from "react-router-dom";

import { cn } from "@/lib/utils";
import { useUiStore } from "@/stores/ui";

export const NAV_ITEMS = [
  { to: "/", label: "Home", icon: LayoutDashboard, key: "h", end: true },
  { to: "/trade", label: "Trade", icon: CandlestickChart, key: "t" },
  { to: "/decisions", label: "Decisions", icon: BrainCircuit, key: "d" },
  { to: "/portfolio", label: "Portfolio", icon: Wallet, key: "p" },
  { to: "/intel", label: "Intel", icon: Globe, key: "i" },
  { to: "/settings", label: "Settings", icon: Settings, key: "s" },
] as const;

export function Sidebar() {
  const symbol = useUiStore((s) => s.symbol);
  return (
    <nav
      aria-label="Main"
      className={cn(
        "z-30 flex shrink-0 border-border bg-surface",
        // desktop: left rail; mobile: bottom bar
        "max-md:fixed max-md:bottom-0 max-md:left-0 max-md:right-0 max-md:flex-row max-md:justify-around max-md:border-t",
        "md:w-16 md:flex-col md:items-center md:gap-1 md:border-r md:py-3",
      )}
    >
      {NAV_ITEMS.map((item) => {
        const to = item.to === "/trade" ? `/trade/${symbol}` : item.to;
        return (
          <NavLink
            key={item.to}
            to={to}
            end={"end" in item && item.end}
            className={({ isActive }) =>
              cn(
                "flex flex-col items-center gap-0.5 rounded-md p-2 text-[10px]",
                isActive
                  ? "bg-accent-muted text-accent"
                  : "text-fg-subtle hover:bg-surface-2 hover:text-fg",
              )
            }
          >
            <item.icon size={18} aria-hidden="true" />
            <span>{item.label}</span>
          </NavLink>
        );
      })}
    </nav>
  );
}
