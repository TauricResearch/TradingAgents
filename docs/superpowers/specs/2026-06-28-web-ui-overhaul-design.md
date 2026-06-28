# TradingAgents Web UI Overhaul

## Overview

Complete refactoring of the web frontend to improve code structure, visual polish, and user experience. The app is a React 19 + TypeScript + Vite + Tailwind CSS trading dashboard with real-time WebSocket streaming, Recharts charts, and multi-agent pipeline visualization.

## 1. Layout Restructure

### Current Layout
- Fixed left sidebar (WatchlistRail) + main content area
- Inline header in App.tsx with scattered action buttons
- Drawers slide from right/bottom

### New Layout
```
┌─────────────────────────────────────────────────────────┐
│ TopBar                                                  │
│ Logo + version | Search ticker | Past Runs | Agent      │
│ Download | Settings | User menu | Status indicator      │
├────────────┬────────────────────────────────────────────┤
│ Sidebar    │ Main Content                               │
│ (collaps.) │  TickerHeader (sticky)                     │
│ Watchlist  │  PipelineFlow                              │
│ Groups     │  TraceTabs [Events | Observatory | LLM]   │
│ Tickers    │  LiveEventStream / AgentObservatory / LLM  │
│ Indicators │  ReportPanel                               │
│            │  DecisionPanel                             │
└────────────┴────────────────────────────────────────────┘
```

### Changes
- Extract header into `TopBar` component
- Sidebar collapsible on desktop too (persisted state)
- TickerHeader gets sticky positioning
- View tabs become a reusable `TraceTabs` component
- Consistent drawer patterns (standardized slide direction, widths, headers)

## 2. Shared UI Component Library (`src/ui/`)

| Component | Props | Notes |
|-----------|-------|-------|
| Button | variant, size, loading, disabled, icon | primary/secondary/danger/ghost |
| Input | label, error, icon, type | Consistent styled input |
| Select | label, options, value, onChange | Consistent styled select |
| Toggle | checked, onChange, label | Switch toggle |
| Modal | open, onClose, title, children | Overlay + dialog |
| Drawer | open, onClose, side, title, children | Configurable slide direction |
| Badge | variant, children | buy/sell/hold/status/accuracy |
| Skeleton | variant, width, height, lines | Panel/card/text/avatar variants |
| EmptyState | icon, title, description, action | With optional CTA button |
| Spinner | size | Unified spinner |
| Toast | message, type, duration | Notification system via zustand store |

## 3. Component Extraction

### From App.tsx (440 lines)
- `TopBar.tsx` — Header with logo, buttons, search, user menu
- `LoadingScreen.tsx` — Server-ready + watchlist-loading
- `EmptyWatchlist.tsx` — Empty state with illustration
- `StaleBanner.tsx` — Stale ticker warning
- `TraceTabs.tsx` — 3 view tabs

### From WatchlistRail.tsx (697 lines)
- `WatchlistFilter.tsx` — Search + add ticker
- `WatchlistGroup.tsx` — Group header with rename/delete/drag/color
- `WatchlistGroupList.tsx` — All groups + ungrouped
- `AgentTickerSection.tsx` — Agent tickers section

### From PipelineFlow.tsx (715 lines)
- `TeamCard.tsx` — Team card (already semi-extracted)
- `AgentRow.tsx` — Single agent status row
- `StageDetailPanel.tsx` — Accordion detail panel
- `PipelineStats.tsx` — Stats bar

## 4. Visual Polish

- Loading skeletons for all major panels (8 variants)
- Empty states with icons + contextual CTAs
- Page transitions (fade-in/slide-up)
- Toast notifications via zustand store
- Consistent spacing/alignment across all panels
- TopBar status indicator (connection, last update)

## 5. Small Fixes

- `AgentObservatory` onClose prop type mismatch
- Standardize all icons to lucide-react
- Keyboard navigation in watchlist
- Aria labels on interactive elements
- Consistent scrollbar styling
- Fix password input autocomplete

## Implementation Order

1. Create `src/ui/` shared component library
2. Extract App.tsx → TopBar, LoadingScreen, EmptyWatchlist, TraceTabs
3. Restructure main layout (TopBar + collapsible sidebar)
4. Extract WatchlistRail sub-components
5. Extract PipelineFlow sub-components
6. Add loading skeletons + empty states
7. Add toast notification system
8. Apply small fixes
9. Verify build + tests pass
