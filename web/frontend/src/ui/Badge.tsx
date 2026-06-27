import type { ReactNode } from "react";

type BadgeVariant = "buy" | "sell" | "hold" | "default" | "success" | "warning" | "error" | "info";

interface BadgeProps {
  variant?: BadgeVariant;
  children: ReactNode;
  className?: string;
}

const variantClasses: Record<BadgeVariant, string> = {
  buy: "bg-emerald-500/15 text-emerald-400 border border-emerald-500/25",
  sell: "bg-red-500/15 text-red-400 border border-red-500/25",
  hold: "bg-amber-500/15 text-amber-400 border border-amber-500/25",
  default: "bg-slate-700/40 text-slate-400 border border-slate-600/40",
  success: "bg-emerald-500/15 text-emerald-400 border border-emerald-500/25",
  warning: "bg-amber-500/15 text-amber-400 border border-amber-500/25",
  error: "bg-red-500/15 text-red-400 border border-red-500/25",
  info: "bg-sky-500/15 text-sky-400 border border-sky-500/25",
};

export function Badge({ variant = "default", children, className = "" }: BadgeProps) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider rounded-md ${variantClasses[variant]} ${className}`}>
      {children}
    </span>
  );
}
