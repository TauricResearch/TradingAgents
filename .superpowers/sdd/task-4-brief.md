# Task 4: Frontend — Add `updateIndicator` API Fetcher

## Task Description

**File:** `web/frontend/src/lib/api.ts`

## Requirements

Add the `updateIndicator` function after the existing `removeIndicator` function (~line 221):

```typescript
export async function updateIndicator(
  id: string,
  body: Partial<{ threshold: number; enabled: boolean }>
): Promise<IndicatorDefinition> {
  const r = await fetch(`${base}/api/indicators/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new ApiError(`update-indicator ${r.status}`, r.status, await readJsonOrNull(r));
  return r.json();
}
```

Verify with: `cd web/frontend && npx tsc --noEmit` (no TypeScript errors related to the new function)

## Context

The backend `PATCH /api/indicators/{id}` was added in Task 2. This exports the frontend fetcher.

## Report File

Write to: `.superpowers/sdd/task-4-report.md`

Report back with:
- **Status:** DONE | BLOCKED
- Commits created
- TypeScript compilation result
- Report file path