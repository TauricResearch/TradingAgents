# PR31: Cockpit Interaction Polish

## Purpose

PR31 builds on the task-focused PR30 layout by making action state and control
behavior explicit. It remains a frontend-only increment: no endpoint, artifact
contract, research workflow, or TradingAgents graph behavior changes.

## Operation feedback

- Header status messages carry neutral, busy, success, warning, or error state.
- Busy state uses a small functional status indicator and `aria-busy` on the
  active research/update command.
- Watchlist refresh reports completed jobs and final failures.
- Single-symbol research distinguishes queue, running, success, and failure.
- Add/remove actions report their own progress and outcome.
- A successful background action retains its result while the refreshed local
  snapshot renders, rather than immediately replacing it with a generic load
  message.

## Product filtering

The product matrix includes a compact segmented control:

- all products;
- live and legacy-live products;
- pipeline products.

Filtering is local and instant. The panel reports displayed and total counts,
and an empty result has a specific state.

## Progressive decisions

Data provider, analysis mode, and decision direction remain visible. Horizon,
confidence, proposed position, and rationale stay hidden until the user chooses
a decision direction. This keeps ordinary research runs free of irrelevant
decision fields while preserving the existing optional manual-signal payload.

## Keyboard and menu behavior

- Left/Right arrows move between research views.
- Home/End select the first/last view.
- Focus moves with the selected tab.
- The watchlist menu closes on Escape or an outside click.
- Existing focus-visible styling remains available for all controls.

## Verification

Static tests cover filters, progressive fields, status wiring, keyboard events,
unique render targets, and the PR30 navigation structure. Browser verification
checks filtering, decision expansion, keyboard navigation, URL persistence,
responsive layout, and console errors.
