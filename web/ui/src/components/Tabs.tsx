export interface Tab<K extends string> {
  key: K
  label: string
  /** Row count shown after the label once loaded. */
  count?: number
}

interface Props<K extends string> {
  tabs: Tab<K>[]
  active: K
  onChange: (key: K) => void
}

export function Tabs<K extends string>({ tabs, active, onChange }: Props<K>) {
  return (
    <div role="tablist" className="flex gap-1 border-b border-border">
      {tabs.map((t) => {
        const on = t.key === active
        return (
          <button
            key={t.key}
            role="tab"
            type="button"
            aria-selected={on}
            onClick={() => onChange(t.key)}
            className={`-mb-px border-b-2 px-3 py-1.5 text-[13px] ${
              on ? 'border-accent text-accent' : 'border-transparent text-muted hover:text-fg'
            }`}
          >
            {t.label}
            {t.count !== undefined && <span className="num ml-1.5 text-[11px] text-muted">{t.count}</span>}
          </button>
        )
      })}
    </div>
  )
}
