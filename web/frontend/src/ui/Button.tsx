import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Spinner } from "./Spinner";

type Variant = "primary" | "secondary" | "danger" | "ghost";
type Size = "xs" | "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
}

const variantClasses: Record<Variant, string> = {
  primary:
    "bg-sky-500/20 text-sky-400 border border-sky-500/30 hover:bg-sky-500/30 hover:border-sky-500/50",
  secondary:
    "bg-slate-700/50 text-slate-300 border border-slate-600/50 hover:bg-slate-600/50 hover:text-slate-200",
  danger:
    "bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30 hover:border-red-500/50",
  ghost:
    "text-slate-400 border border-transparent hover:text-slate-200 hover:bg-slate-800/60",
};

const sizeClasses: Record<Size, string> = {
  xs: "px-2 py-1 text-[10px]",
  sm: "px-2.5 py-1.5 text-xs",
  md: "px-3 py-1.5 text-sm",
  lg: "px-4 py-2 text-sm",
};

export function Button({
  variant = "secondary",
  size = "sm",
  loading = false,
  icon,
  children,
  disabled,
  className = "",
  ...rest
}: ButtonProps) {
  return (
    <button
      disabled={disabled || loading}
      className={`inline-flex items-center justify-center gap-1.5 font-medium rounded-lg
        transition-all duration-200
        disabled:opacity-40 disabled:cursor-not-allowed
        ${variantClasses[variant]} ${sizeClasses[size]} ${className}`}
      {...rest}
    >
      {loading ? <Spinner size="sm" /> : icon ? <span className="shrink-0">{icon}</span> : null}
      {children && <span>{children}</span>}
    </button>
  );
}
