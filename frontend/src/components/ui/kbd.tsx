export function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="rounded-md border border-border bg-surface-solid px-1.5 py-0.5 font-mono text-[11px] text-fg-muted shadow-sm">
      {children}
    </kbd>
  );
}
