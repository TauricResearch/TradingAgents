import type { SelectHTMLAttributes } from "react";

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  options: Array<{ value: string; label: string }>;
}

export function Select({ label, options, className = "", ...rest }: SelectProps) {
  return (
    <label className="flex flex-col gap-0.5">
      {label && <span className="text-[10px] font-medium text-slate-600 uppercase tracking-wider">{label}</span>}
      <select
        className={`bg-slate-800 border border-slate-700/50 rounded-lg px-2 py-1.5 text-sm text-slate-300
          focus:outline-none focus:ring-2 focus:ring-sky-500/30 transition-colors ${className}`}
        {...rest}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>
    </label>
  );
}
