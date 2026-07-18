/** Left navigation: white-glass panel on desktop (216px, icon-only 72px
 * below 1150px), bottom tab bar on mobile. Same NAV_ITEMS and routes as
 * before the reskin — presentation only. */
import {
  BrainCircuit,
  CandlestickChart,
  Globe,
  LayoutDashboard,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  Trophy,
  Wallet,
} from "lucide-react";
import { NavLink } from "react-router-dom";

import { usePrefs } from "@/lib/api/queries";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/stores/ui";

export const NAV_ITEMS = [
  { to: "/", label: "Home", icon: LayoutDashboard, key: "h", end: true },
  { to: "/trade", label: "Trade", icon: CandlestickChart, key: "t" },
  { to: "/decisions", label: "Decisions", icon: BrainCircuit, key: "d" },
  { to: "/portfolio", label: "Portfolio", icon: Wallet, key: "p" },
  { to: "/track-record", label: "Record", icon: Trophy, key: "r" },
  { to: "/intel", label: "Intel", icon: Globe, key: "i" },
] as const;

const SYSTEM_ITEMS = [
  { to: "/settings", label: "Settings", icon: Settings, key: "s" },
] as const;

/* labels hide when the rail collapses (<=1150px), when manually collapsed,
   and never on mobile */
const LABEL = "max-md:block max-[1150px]:md:hidden";

function SectionLabel({
  children,
  collapsed,
}: {
  children: string;
  collapsed: boolean;
}) {
  return (
    <div
      className={cn(
        "px-3 pb-1 pt-4 text-[10px] font-bold uppercase tracking-[0.12em] text-fg-subtle",
        "max-md:hidden max-[1150px]:md:hidden",
        collapsed && "md:hidden",
      )}
    >
      {children}
    </div>
  );
}

function Item({
  item,
  to,
  collapsed,
}: {
  item: (typeof NAV_ITEMS)[number] | (typeof SYSTEM_ITEMS)[number];
  to: string;
  collapsed: boolean;
}) {
  return (
    <NavLink
      to={to}
      end={"end" in item && item.end}
      title={collapsed ? item.label : undefined}
      className={({ isActive }) =>
        cn(
          "flex items-center gap-2.5 rounded-xl px-3 py-[9px] text-[13px] font-semibold",
          "max-md:flex-col max-md:gap-0.5 max-md:px-2 max-md:py-2 max-md:text-[10px]",
          "max-[1150px]:md:justify-center max-[1150px]:md:px-2",
          collapsed && "md:justify-center md:px-2",
          isActive
            ? "bg-accent text-on-solid shadow-[0_8px_18px_-8px_rgba(36,86,197,0.6)]"
            : "text-fg-muted hover:bg-surface-2 hover:text-fg",
        )
      }
    >
      <span className="relative inline-flex" aria-hidden="true">
        <item.icon size={19} />
        {item.to === "/trade" && (
          <span className="live-dot absolute -right-1 -top-1 h-[6px] w-[6px]" />
        )}
      </span>
      <span className={cn(collapsed ? "max-md:block md:hidden" : LABEL)}>
        {item.label}
      </span>
    </NavLink>
  );
}

export function Sidebar() {
  const prefs = usePrefs();
  const operatorLabel = prefs.data?.operator_label ?? "Operator";
  const symbol = useUiStore((s) => s.symbol);
  const collapsed = useUiStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useUiStore((s) => s.toggleSidebar);
  return (
    <nav
      aria-label="Main"
      data-collapsed={collapsed || undefined}
      className={cn(
        "z-30 flex shrink-0 border-border bg-surface",
        // mobile: bottom tab bar (unchanged behavior)
        "max-md:fixed max-md:bottom-0 max-md:left-0 max-md:right-0 max-md:flex-row max-md:justify-around max-md:border-t max-md:px-1 max-md:py-1",
        // desktop: floating glass panel; icon-only under 1150px OR collapsed
        "md:flex-col md:gap-0.5 md:rounded-[20px] md:border md:p-3 md:shadow-(--shadow-1) md:backdrop-blur-[16px]",
        collapsed
          ? "md:w-[72px] md:items-center"
          : "md:w-[216px] max-[1150px]:md:w-[72px] max-[1150px]:md:items-center",
      )}
    >
      <div
        className={cn(
          "flex items-start justify-between px-3 pb-2 pt-1 max-md:hidden",
          "max-[1150px]:md:hidden",
          collapsed && "md:hidden",
        )}
      >
        <div>
          <div className="text-[15px] font-extrabold leading-tight">
            TradingAgents{" "}
            <span className="font-normal text-fg-subtle">Pro</span>
          </div>
          <div className="text-[10.5px] text-fg-subtle">
            multi-agent trading terminal
          </div>
        </div>
      </div>

      {/* collapse toggle (desktop only): reclaim chart width on demand */}
      <button
        type="button"
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        aria-pressed={collapsed}
        title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        onClick={toggleSidebar}
        className={cn(
          "mb-1 hidden items-center gap-2 rounded-xl px-3 py-[9px] text-[13px]",
          "font-semibold text-fg-muted hover:bg-surface-2 hover:text-fg md:flex",
          "max-[1150px]:md:hidden", // the auto-collapsed rail has no room
          collapsed && "md:justify-center md:px-2",
        )}
      >
        {collapsed ? (
          <PanelLeftOpen size={19} />
        ) : (
          <PanelLeftClose size={19} />
        )}
        {!collapsed && <span>Collapse</span>}
      </button>

      <SectionLabel collapsed={collapsed}>MENU</SectionLabel>
      {NAV_ITEMS.map((item) => (
        <Item
          key={item.to}
          item={item}
          collapsed={collapsed}
          to={item.to === "/trade" ? `/trade/${symbol}` : item.to}
        />
      ))}

      <SectionLabel collapsed={collapsed}>SYSTEM</SectionLabel>
      {SYSTEM_ITEMS.map((item) => (
        <Item key={item.to} item={item} to={item.to} collapsed={collapsed} />
      ))}

      <div className="grow max-md:hidden" />
      <div
        className={cn(
          "mt-2 flex items-center gap-2.5 rounded-[14px] bg-surface-2 p-2.5",
          "max-md:hidden",
          // collapsed rail (768–1150px or manual): avatar-only, centered
          "max-[1150px]:md:justify-center max-[1150px]:md:bg-transparent max-[1150px]:md:p-0",
          collapsed && "md:justify-center md:bg-transparent md:p-0",
        )}
      >
        <span
          aria-hidden="true"
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[linear-gradient(135deg,#7a5cf0,#5b3fd6)] text-sm font-extrabold text-white"
        >
          {operatorLabel.charAt(0).toUpperCase()}
        </span>
        <div className={cn("min-w-0 text-xs max-[1150px]:md:hidden", collapsed && "md:hidden")}>
          <div className="truncate font-semibold">{operatorLabel}</div>
          <div className="flex items-center gap-1 text-[10.5px] text-bull">
            <span className="live-dot h-[6px] w-[6px]" aria-hidden="true" />
            Session Active
          </div>
        </div>
      </div>
    </nav>
  );
}
