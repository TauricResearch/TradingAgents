/**
 * File explorer tree hydration — runs in browser.
 * Two trees:
 *   - Nav tree (POC): site navigation as a tree, selection navigates to URLs.
 *   - File tree: repo explorer, selection loads file content via HTMX.
 * Imported as ESM module, bundled with @pierre/trees via bun build.
 */

import type {
  ContextMenuItem,
  ContextMenuOpenContext,
  FileTreeCompositionOptions,
} from "@pierre/trees"
import { FileTree, prepareFileTreeInput } from "@pierre/trees"

// ── Module-level state ─────────────────────────────────────

let fileTreeInstance: FileTree | null = null
let _navTreeInstance: FileTree | null = null // reserved for future nav tree state

// ── Nav path resolution ────────────────────────────────────

/** Map nav tree paths ("nav/Pages/Portfolio") back to real URLs. */
const NAV_MAP: Record<string, string> = {
  "nav/Pages/Portfolio": "/portfolio",
  "nav/Pages/Intelligence": "/intelligence",
  "nav/Pages/Workflow": "/workflow",
  "nav/Pages/Analyze": "/analyze",
  "nav/Pages/Signals": "/signals",
  "nav/Pages/History": "/history",
  "nav/Pages/Holdings": "/holdings",
  "nav/Pages/Exits": "/exits",
  "nav/Pages/Prospects": "/prospects",
  "nav/Pages/Governance": "/governance",
  "nav/Pages/Benchmark": "/benchmark",
  "nav/Pages/Feedback": "/feedback",
  "nav/Pages/Alerts": "/alerts",
  "nav/Pages/Screenings": "/screenings",
  "nav/Pages/Explorer": "/explorer",
  "nav/Pages/Test Datatype": "/test/datatype",
  "nav/Pages/About": "/about",
  "nav/API/positions": "/api/positions",
  "nav/API/analyze": "/api/analyze",
  "nav/API/signals": "/api/signals",
  "nav/API/prices": "/api/prices",
  "nav/API/analyses": "/api/analyses",
  "nav/API/holdings": "/api/holdings",
  "nav/API/prospects": "/api/prospects",
  "nav/API/workflow": "/api/workflow",
  "nav/API/portfolio/intelligence": "/api/portfolio/intelligence",
  "nav/API/portfolio/balance": "/api/portfolio/balance",
  "nav/API/trade-plan": "/api/trade-plan",
  "nav/API/alerts": "/api/alerts",
  "nav/API/screenings": "/api/screenings",
  "nav/API/portfolio/summary": "/api/portfolio/summary",
}

function resolveNavPath(treePath: string): string | null {
  return NAV_MAP[treePath] ?? null
}

// ── Data helpers ───────────────────────────────────────────

function getPreparedInput(
  elId: string,
  attr: string,
): ReturnType<typeof prepareFileTreeInput> | null {
  const el = document.getElementById(elId)
  if (!el) return null
  const raw = el.getAttribute(attr)
  if (!raw) return null
  try {
    const paths: string[] = JSON.parse(raw)
    return prepareFileTreeInput(paths, { flattenEmptyDirectories: true })
  } catch (_err) {
    return null
  }
}

// ── Search preservation ────────────────────────────────────

function getSearchQuery(): string {
  const tree = fileTreeInstance
  if (!tree) return ""
  const root = (tree as unknown as { shadowRoot: ShadowRoot | null }).shadowRoot
  if (!root) return ""
  const input = root.querySelector(
    'input[type="search"], input[placeholder*="search" i]',
  ) as HTMLInputElement | null
  return input ? input.value : ""
}

function setSearchQuery(query: string): void {
  const tree = fileTreeInstance
  if (!tree) return
  const root = (tree as unknown as { shadowRoot: ShadowRoot | null }).shadowRoot
  if (!root) return
  const input = root.querySelector(
    'input[type="search"], input[placeholder*="search" i]',
  ) as HTMLInputElement | null
  if (input) input.value = query
}

// ── Scroll reset ───────────────────────────────────────────

function scrollContentToTop(): void {
  const panel = document.getElementById("explorer-content")
  if (panel) panel.scrollTop = 0
}

// ── Context menu ───────────────────────────────────────────

function renderContextMenu(item: ContextMenuItem, ctx: ContextMenuOpenContext): HTMLElement | null {
  if (item.kind !== "file") return null

  const menu = document.createElement("div")
  menu.className = "explorer-context-menu"
  menu.setAttribute("data-file-tree-context-menu-root", "true")

  const menuItems = [
    {
      label: "Open",
      action: () => {
        ctx.close()
        openFile(item.path)
      },
    },
    {
      label: "Copy Path",
      action: async () => {
        ctx.close()
        await navigator.clipboard.writeText(item.path)
      },
    },
  ]

  for (const mi of menuItems) {
    const btn = document.createElement("button")
    btn.textContent = mi.label
    btn.addEventListener("click", mi.action)
    menu.appendChild(btn)
  }

  return menu
}

// ── Nav tree: navigate on selection ────────────────────────
//
// Routes through /explorer/nav/{url} — the explorer endpoint returns
// just the content panel for the target URL. HTMX swaps #content.
// The explorer shell (nav tree + file tree) is never replaced.

function onNavSelection(selectedPaths: readonly string[]): void {
  const url = resolveNavPath(selectedPaths[0]!)
  if (!url) return

  const navEndpoint = `/explorer/nav${url}`
  const content = document.getElementById("explorer-content")

  if (!content) return

  const handler = () => {
    history.pushState(null, "", url)
    content.removeEventListener("htmx:afterSwap", handler)
  }
  content.addEventListener("htmx:afterSwap", handler)

  ;(
    window as unknown as {
      htmx?: {
        ajax: (verb: string, url: string, opts: { target: string; swap?: string }) => void
      }
    }
  ).htmx?.ajax("GET", navEndpoint, { target: "#explorer-content", swap: "innerHTML" })
}

// ── File tree: load file content via HTMX ──────────────────

function openFile(filePath: string): void {
  const savedQuery = getSearchQuery()

  ;(
    window as unknown as Record<
      string,
      { ajax: (method: string, url: string, options: Record<string, string>) => void }
    >
  ).htmx?.ajax("GET", `/explorer/file/${filePath}`, {
    target: "#explorer-content",
    swap: "innerHTML",
  })

  const panel = document.getElementById("explorer-content")
  if (panel) {
    const restore = () => {
      setSearchQuery(savedQuery)
      scrollContentToTop()
      panel.removeEventListener("htmx:afterSwap", restore)
    }
    panel.addEventListener("htmx:afterSwap", restore)
  }
}

// ── Initialization ─────────────────────────────────────────

function initFileTree(): void {
  const root = document.getElementById("explorer-tree-root")
  const container = root?.querySelector("file-tree-container") as HTMLElement | null
  if (!container) return

  const preparedInput = getPreparedInput("explorer-tree-data", "data-paths")
  if (!preparedInput) return

  const tree = new FileTree({
    preparedInput,
    id: "explorer-tree",
    search: true,
    initialExpandedPaths: ["src/server", "playbooks", "docs"],
    initialVisibleRowCount: 14,
    composition: {
      contextMenu: {
        enabled: true,
        triggerMode: "right-click",
        render: renderContextMenu,
      },
    } satisfies FileTreeCompositionOptions,
    onSelectionChange: (selectedPaths: readonly string[]) => {
      if (selectedPaths.length > 0) {
        openFile(selectedPaths[0]!)
      }
    },
  })

  tree.hydrate({ fileTreeContainer: container })
  fileTreeInstance = tree
}

function initNavTree(): void {
  const root = document.getElementById("explorer-nav-root")
  const container = root?.querySelector("file-tree-container") as HTMLElement | null
  if (!container) return

  const preparedInput = getPreparedInput("explorer-nav-data", "data-nav-paths")
  if (!preparedInput) return

  const tree = new FileTree({
    preparedInput,
    id: "nav-tree",
    search: false,
    initialExpandedPaths: ["nav/Pages", "nav/API"],
    initialVisibleRowCount: 8,
    onSelectionChange: onNavSelection,
  })

  tree.hydrate({ fileTreeContainer: container })
  _navTreeInstance = tree
}

function init(): void {
  initNavTree()
  initFileTree()
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init)
} else {
  init()
}
