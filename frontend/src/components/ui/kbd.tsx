export function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="rounded border border-border-strong bg-surface-2 px-1.5 py-0.5 font-mono text-[11px] text-fg-muted">
      {children}
    </kbd>
  );
}
