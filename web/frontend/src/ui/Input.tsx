import type { InputHTMLAttributes, ReactNode } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  icon?: ReactNode;
}

export function Input({ label, error, icon, className = "", ...rest }: InputProps) {
  return (
    <label className="flex flex-col gap-0.5">
      {label && <span className="text-[10px] font-medium text-slate-600 uppercase tracking-wider">{label}</span>}
      <div className="relative">
        {icon && (
          <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none">
            {icon}
          </span>
        )}
        <input
          className={`w-full bg-slate-800/60 border rounded-lg px-2.5 py-1.5 text-sm text-slate-200
            placeholder-slate-500 outline-none focus:border-sky-500/50 focus:ring-1 focus:ring-sky-500/30
            transition-colors font-mono tabular-nums
            ${icon ? "pl-8" : ""}
            ${error ? "border-red-500/50" : "border-slate-700/50"}
            ${className}`}
          {...rest}
        />
      </div>
      {error && <span className="text-[10px] text-red-400 mt-0.5">{error}</span>}
    </label>
  );
}
