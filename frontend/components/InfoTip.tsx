"use client";

import { useState } from "react";

export function InfoTip({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="relative inline-flex align-middle">
      <button
        type="button"
        aria-label="More information"
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        className="ml-1 inline-flex h-4 w-4 items-center justify-center rounded-full border border-line text-[10px] text-mist hover:border-gold hover:text-gold"
      >
        i
      </button>
      {open && (
        <span className="absolute left-1/2 top-5 z-50 w-64 -translate-x-1/2 rounded-md border border-line bg-ink-800 px-3 py-2 text-xs leading-5 text-mist shadow-terminal">
          {text}
        </span>
      )}
    </span>
  );
}
