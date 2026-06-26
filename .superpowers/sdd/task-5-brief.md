# Task 5: Frontend — Inline Threshold Editing in Indicator Cards

## Task Description

**File:** `web/frontend/src/components/IndicatorRailView.tsx`

## Requirements

Add inline threshold editing to each indicator card. When a user clicks the threshold badge on an indicator card, it becomes an editable `<input type="number">`. On blur or Enter, it sends a PATCH request to update the threshold. On Escape, it cancels.

### Step 1: Import `updateIndicator` in the existing import from `../lib/api`

### Step 2: Add state for editing

Add after existing state declarations (~line 55):

```typescript
const [editingId, setEditingId] = useState<string | null>(null);
const [editValue, setEditValue] = useState<string>("");
```

### Step 3: Add `useMutation` for updates

Add after the existing `removeMutation`:

```typescript
const updateMutation = useMutation({
  mutationFn: ({ id, body }: { id: string; body: { threshold?: number; enabled?: boolean } }) =>
    updateIndicator(id, body),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ["indicators"] });
    setReply("Threshold updated.");
  },
  onError: (err: Error) => {
    const apiErr = err as { detail?: string };
    setReply(apiErr.detail || err.message);
  },
});
```

### Step 4: Replace the static threshold badge with an editable input

Find the static threshold span in the `indicators.map` block (~line 351):

```jsx
<span className="rounded border border-slate-700/60 bg-slate-900/40 px-1.5 py-0.5">
  {indicator.comparator} {formatThreshold(indicator)}
</span>
```

Replace with:

```jsx
{editingId === indicator.id ? (
  <input
    type="number"
    value={editValue}
    onChange={(e) => setEditValue(e.target.value)}
    onBlur={() => {
      const newThreshold = parseFloat(editValue);
      if (!isNaN(newThreshold)) {
        updateMutation.mutate({ id: indicator.id, body: { threshold: newThreshold } });
      }
      setEditingId(null);
    }}
    onKeyDown={(e) => {
      if (e.key === "Enter") {
        const newThreshold = parseFloat(editValue);
        if (!isNaN(newThreshold)) {
          updateMutation.mutate({ id: indicator.id, body: { threshold: newThreshold } });
        }
        setEditingId(null);
      } else if (e.key === "Escape") {
        setEditingId(null);
      }
    }}
    autoFocus
    className="w-20 rounded border border-sky-500 bg-slate-900 px-1.5 py-0.5 text-xs text-sky-300 outline-none"
  />
) : (
  <span
    onClick={() => {
      setEditingId(indicator.id);
      setEditValue(indicator.threshold.toString());
    }}
    className="cursor-pointer rounded border border-slate-700/60 bg-slate-900/40 px-1.5 py-0.5 text-xs text-slate-300 hover:border-slate-500"
  >
    {indicator.comparator} {formatThreshold(indicator)}
  </span>
)}
```

### Step 5: Verify TypeScript compilation

Run: `cd web/frontend && npx tsc --noEmit`
Expected: Clean build, no errors.

## Context

The `updateIndicator` API fetcher was added in Task 4. The `IndicatorRailView.tsx` already imports `IndicatorDefinition` and other indicator functions from `../lib/api` — just add `updateIndicator` to that import line.

## Report File

Write to: `.superpowers/sdd/task-5-report.md`

Report back with:
- Status, commits, TS compilation result, report path