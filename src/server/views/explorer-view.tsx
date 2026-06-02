/**
 * File Explorer — Shell + Content panels.
 *
 * Shell (ExplorerShell): nav tree + file tree + content panel wrapper.
 *   Rendered on full page load. Never swapped by HTMX.
 *
 * Content (ExplorerContent): the inner content area that HTMX swaps.
 *   Rendered on HTMX requests from the nav tree.
 */

/** @jsxImportSource hono/jsx */

import type { FileTreeSsrPayload } from "@pierre/trees"
import { serializeFileTreeSsrPayload, preloadFileTree } from "@pierre/trees/ssr"
import { renderMarkdown } from "../lib/markdown.ts"
import { buildRepoTree, buildNavTreePaths } from "../lib/tree-prep.ts"

// ── Types ──────────────────────────────────────────────────

export interface ExplorerShellProps {
  payload: FileTreeSsrPayload
  paths: readonly string[]
  /** Content to show inside the content panel. Default: empty state. */
  children?: unknown
}

export interface ExplorerContentProps {
  path: string
  content: string
  kind: "markdown" | "html" | "raw" | "image"
  language?: string
}

// ── Shared nav tree data (used by both shell and content) ──

const NAV_PATHS = buildNavTreePaths()
const NAV_PREPARED = buildRepoTree(NAV_PATHS)
const NAV_PAYLOAD = preloadFileTree({
  preparedInput: NAV_PREPARED,
  id: "nav-tree",
  search: false,
  initialExpandedPaths: ["nav/Pages", "nav/API"],
  initialVisibleRowCount: 8,
})
const NAV_SERIALIZED = serializeFileTreeSsrPayload(NAV_PAYLOAD, "dom")
export { NAV_PATHS, NAV_SERIALIZED }

// ── ExplorerShell ──────────────────────────────────────────

export function ExplorerShell({ payload, paths, children }: ExplorerShellProps) {
  const serializedPayload = serializeFileTreeSsrPayload(payload, "dom")
  const pathsJson = JSON.stringify(paths)

  return (
    <div class="explorer-layout">
      {/* ── Left panel: nav tree (POC) + file tree ── */}
      <div class="explorer-tree-panel" id="explorer-tree-panel">
        {/* Nav tree */}
        <div class="explorer-nav-tree">
          <div class="explorer-nav-header">
            <h2>Navigation</h2>
          </div>
          <div id="explorer-nav-root" dangerouslySetInnerHTML={{ __html: NAV_SERIALIZED.replace('style="--trees-item-height:30px;--trees-density-override:1"', 'style="background-color:#ff0000;--trees-item-height:30px;--trees-density-override:1;--trees-bg-override:#ff0000"') }} />
          <textarea id="explorer-nav-data" hidden data-nav-paths={JSON.stringify(NAV_PATHS)} />
        </div>

        <div class="explorer-tree-divider" />

        {/* File tree */}
        <div class="explorer-file-tree">
          <div class="explorer-tree-header">
            <h2>Repository</h2>
          </div>
          <div id="explorer-tree-root" dangerouslySetInnerHTML={{ __html: serializedPayload.replace('style="--trees-item-height:30px;--trees-density-override:1"', 'style="background-color:#ffffff;--trees-item-height:30px;--trees-density-override:1;--trees-bg-override:#ffffff"') }} />
          <textarea id="explorer-tree-data" hidden data-paths={pathsJson} />
        </div>
      </div>

      {/* ── Content panel — HTMX swap target ── */}
      {/* data-id="content" for HTMX target resolution by the explorer client */}
      <div class="explorer-content-panel" id="explorer-content" data-id="content" style="background:#0000ff">
        {children ?? (
          <div class="explorer-content-empty">
            <p>Select a file from the tree, or use the Navigation to explore the app.</p>
          </div>
        )}
      </div>

      <script src="/static/scripts/explorer-tree.bundle.js" type="module" />
    </div>
  )
}

// ── ExplorerContent ────────────────────────────────────────

export function ExplorerContent({ path, content, kind, language }: ExplorerContentProps) {
  return (
    <div class="explorer-file-view">
      <div class="explorer-file-header">
        <span class="explorer-file-path">{path}</span>
        <button class="explorer-file-copy" data-action="copyPath" data-path={path}>
          Copy Path
        </button>
      </div>
      <div class="explorer-file-content">
        {kind === "markdown" ? (
          <div class="markdown-body" dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }} />
        ) : kind === "html" ? (
          <pre class="file-content-pre">
            <code
              class={`language-${language ?? "text"} hljs`}
              dangerouslySetInnerHTML={{ __html: content }}
            />
          </pre>
        ) : kind === "image" ? (
          <div class="explorer-image-view">
            <img src={content} alt={path.split("/").pop() ?? "image"} />
          </div>
        ) : (
          <pre class="file-content-pre">
            <code>{content}</code>
          </pre>
        )}
      </div>
    </div>
  )
}

/** Error view for missing files or permission issues. */
export function ExplorerError({ path, message }: { path: string; message: string }) {
  return (
    <div class="explorer-file-view">
      <div class="explorer-file-header">
        <span class="explorer-file-path">{path}</span>
      </div>
      <div class="explorer-file-content">
        <div class="explorer-error">
          <p>{message}</p>
        </div>
      </div>
    </div>
  )
}