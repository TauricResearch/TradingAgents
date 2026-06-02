/**
 * File Explorer — raw HTML, inline styles.
 * Nav tree + file tree + content panel.
 * No shadow DOM, no @pierre/trees.
 *
 * Routes:
 *   GET /explorer       — full shell with nav + repo tree
 *   GET /explorer/tree  — standalone tree view (same layout)
 *   GET /explorer/nav/* — dashboard page content (HTMX target)
 *   GET /explorer/file/* — file content (HTMX target)
 */

import { Hono } from "hono"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { getRepoPaths, classifyFile, fileLanguageTag } from "../lib/tree-prep.ts"
import { highlightCode, prettyPrintJson } from "../lib/syntax-highlight.ts"
import { renderMarkdown } from "../lib/markdown.ts"

const explorer = new Hono()

// ── Shared tree builder ────────────────────────────────────

type TreeNode = { name: string; path: string; children: TreeNode[]; expanded: boolean }

function buildTree(paths: string[]): TreeNode[] {
  const roots: TreeNode[] = []
  const map = new Map<string, TreeNode>()
  for (const p of paths) {
    const parts = p.split("/")
    let parentNodes = roots
    for (let i = 0; i < parts.length; i++) {
      const name = parts[i]!
      const nodePath = parts.slice(0, i + 1).join("/")
      let node = map.get(nodePath)
      if (!node) {
        node = { name, path: nodePath, children: [], expanded: i < 2 }
        map.set(nodePath, node)
        parentNodes.push(node)
      }
      parentNodes = node.children
    }
  }
  return roots
}

// Render tree nodes as HTML with expand/collapse and context menu
function renderTree(nodes: TreeNode[], depth = 0): string {
  return nodes.map(node => {
    const isDir = node.children.length > 0
    const icon = isDir ? (node.expanded ? "📂" : "📁") : "📄"
    const indent = "padding-left:" + (depth * 16 + 8) + "px"
    const kids = isDir && node.expanded ? renderTree(node.children, depth + 1) : ""
    const pathAttr = "data-path=\"" + node.path.replace(/"/g, "&quot;") + "\""
    const typeAttr = isDir ? "" : "data-file=\"true\""
    const clickAttr = isDir
      ? `onclick="toggleDir(this)"`
      : `onclick="loadFile('${node.path.replace(/'/g, "\\'")}')"`
    return `<div style="${indent};padding-top:1px;padding-bottom:1px">` +
      `<span class="tree-item" ${pathAttr} ${typeAttr} onclick="handleTreeClick(event, '${node.path.replace(/'/g, "\\'")}', ${isDir})" oncontextmenu="showContextMenu(event, '${node.path.replace(/'/g, "\\'")}', ${isDir})" style="cursor:pointer;color:#1a1a1a;font-size:13px;user-select:none;display:inline-block;min-width:150px;padding:1px 4px;border-radius:3px">${icon} ${node.name}</span>` +
      (isDir ? `<div class="tree-children" style="${node.expanded ? "" : "display:none"}">${kids}</div>` : "") +
      `</div>`
  }).join("")
}

// Nav links HTML
function navLinksHtml(): string {
  const links = [
    ["Portfolio", "/portfolio"],
    ["Intelligence", "/intelligence"],
    ["Workflow", "/workflow"],
    ["Analyze", "/analyze"],
    ["Signals", "/signals"],
    ["History", "/history"],
    ["Holdings", "/holdings"],
    ["Exits", "/exits"],
    ["Prospects", "/prospects"],
    ["Governance", "/governance"],
    ["Benchmark", "/benchmark"],
    ["Feedback", "/feedback"],
    ["Alerts", "/alerts"],
    ["Screenings", "/screenings"],
    ["About", "/about"],
  ]
  return links.map(([label, href]) =>
    `<div class="nav-link" onclick="navigateTo('${href}')" style="padding:4px 8px;cursor:pointer;color:#1a1a1a;font-size:13px">${label}</div>`
  ).join("")
}

// Full explorer shell HTML (reused by /explorer and /explorer/tree)
function explorerShell(contentHtml: string): string {
  const repoPaths = getRepoPaths()
  const tree = buildTree(repoPaths.slice(0, 300))
  const fileTreeHtml = renderTree(tree)
  const nav = navLinksHtml()

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>File Explorer — TradingAgents</title>
<link rel="stylesheet" href="/static/hljs.css"/>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #ffffff; color: #1a1a1a; }
  .layout { display: flex; height: 100vh; }
  .tree-panel { width: 300px; min-width: 240px; background: #ff0000; overflow-y: auto; display: flex; flex-direction: column; }
  .panel-header { padding: 12px 12px 8px; border-bottom: 1px solid #cc0000; }
  .panel-header h2 { font-size: 10px; text-transform: uppercase; letter-spacing: 0.1em; color: rgba(255,255,255,0.65); margin: 0; }
  .nav-items { padding: 4px 0; }
  .file-section { flex: 1; padding: 8px 0; overflow-y: auto; }
  .search-box { padding: 8px 12px; border-bottom: 1px solid #cc0000; }
  .search-box input { width: 100%; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2); color: white; padding: 5px 8px; border-radius: 3px; font-size: 12px; outline: none; }
  .search-box input::placeholder { color: rgba(255,255,255,0.5); }
  .search-box input:focus { border-color: rgba(255,255,255,0.4); }
  .tree-item:hover { background: rgba(255,255,255,0.1); }
  .content-panel { flex: 1; background: #ffffff; overflow-y: auto; padding: 0; display: flex; flex-direction: column; }
  .content-empty { color: #888; text-align: center; padding-top: 40vh; font-size: 14px; }
  .file-view { padding: 20px 24px; }
  .file-header { display: flex; align-items: center; gap: 12px; padding-bottom: 12px; border-bottom: 1px solid #eee; margin-bottom: 16px; }
  .file-path { font-family: monospace; font-size: 12px; color: #888; }
  .file-copy-btn { background: none; border: 1px solid #ddd; color: #666; font-size: 11px; padding: 2px 8px; border-radius: 3px; cursor: pointer; }
  .file-copy-btn:hover { background: #f5f5f5; }
  .file-content pre { background: #f8f8f8; padding: 16px; border-radius: 4px; overflow-x: auto; font-size: 13px; line-height: 1.5; border: 1px solid #eee; }
  .file-content code { font-family: 'SF Mono', Menlo, monospace; }
  .error-view { color: #c00; padding: 20px; }
  .context-menu { position: fixed; background: white; border: 1px solid #ddd; border-radius: 4px; box-shadow: 0 2px 8px rgba(0,0,0,0.15); padding: 4px 0; z-index: 9999; min-width: 140px; display: none; }
  .context-menu-item { padding: 6px 16px; font-size: 13px; cursor: pointer; color: #333; }
  .context-menu-item:hover { background: #f0f0f0; }
  .context-menu-sep { height: 1px; background: #eee; margin: 4px 0; }
  .search-highlight { background: rgba(255,200,0,0.4); border-radius: 2px; }
</style>
</head>
<body>
${contentHtml}
<div class="context-menu" id="ctx-menu">
  <div class="context-menu-item" id="ctx-open">Open</div>
  <div class="context-menu-sep"></div>
  <div class="context-menu-item" id="ctx-copy">Copy Path</div>
</div>
<script>
var currentCtxPath = null;

function handleTreeClick(e, path, isDir) {
  if (isDir) {
    var kids = e.target.nextElementSibling;
    if (kids && kids.className === 'tree-children') {
      kids.style.display = kids.style.display === 'none' ? '' : 'none';
      e.target.textContent = e.target.textContent.startsWith('📂') ? '📁 ' + e.target.textContent.slice(2) : '📂 ' + e.target.textContent.slice(2);
    }
  } else {
    loadFile(path);
  }
}

function toggleDir(el) {
  var kids = el.nextElementSibling;
  if (kids && kids.className === 'tree-children') {
    kids.style.display = kids.style.display === 'none' ? '' : 'none';
    el.textContent = el.textContent.startsWith('📂') ? '📁 ' + el.textContent.slice(2) : '📂 ' + el.textContent.slice(2);
  }
}

function loadFile(path) {
  fetch('/explorer/file/' + encodeURIComponent(path))
    .then(function(r) { return r.text() })
    .then(function(html) {
      document.getElementById('content-panel').innerHTML = html;
    });
}

function navigateTo(url) {
  fetch('/explorer/nav' + url)
    .then(function(r) { return r.text() })
    .then(function(html) {
      document.getElementById('content-panel').innerHTML = html;
      history.pushState(null, '', url);
    });
}

function showContextMenu(e, path, isFile) {
  e.preventDefault();
  e.stopPropagation();
  currentCtxPath = path;
  var menu = document.getElementById('ctx-menu');
  menu.style.left = (e.clientX || e.pageX) + 'px';
  menu.style.top = (e.clientY || e.pageY) + 'px';
  menu.style.display = 'block';
  document.getElementById('ctx-open').style.display = isFile ? 'block' : 'none';
}

document.getElementById('ctx-open').addEventListener('click', function() {
  if (currentCtxPath) loadFile(currentCtxPath);
  document.getElementById('ctx-menu').style.display = 'none';
});

document.getElementById('ctx-copy').addEventListener('click', function() {
  if (currentCtxPath) {
    var el = document.createElement('textarea');
    el.value = currentCtxPath;
    document.body.appendChild(el);
    el.select();
    document.execCommand('copy');
    document.body.removeChild(el);
  }
  document.getElementById('ctx-menu').style.display = 'none';
});

document.addEventListener('click', function() {
  document.getElementById('ctx-menu').style.display = 'none';
});

document.getElementById('search-input').addEventListener('input', function(e) {
  var q = e.target.value.toLowerCase();
  document.querySelectorAll('.tree-item').forEach(function(el) {
    el.style.display = (!q || el.textContent.toLowerCase().includes(q)) ? 'inline-block' : 'none';
  });
});

window.addEventListener('popstate', function() {
  fetch('/explorer/nav' + location.pathname)
    .then(function(r) { return r.text() })
    .then(function(html) {
      document.getElementById('content-panel').innerHTML = html;
    });
});
</script>
</body>
</html>`
}

// ── Layout HTML pieces ─────────────────────────────────────

function treePanelHtml(): string {
  return `<div class="tree-panel">
    <div class="search-box">
      <input id="search-input" type="text" placeholder="Search files..."/>
    </div>
    <div class="panel-header">
      <h2>Navigation</h2>
    </div>
    <div class="nav-items">
      ${navLinksHtml()}
    </div>
    <div class="panel-header" style="margin-top:8px">
      <h2>Repository</h2>
    </div>
    <div class="file-section">
      ${renderTree(buildTree(getRepoPaths().slice(0, 300)))}
    </div>
  </div>`
}

function contentPanelHtml(inner = '<div class="content-empty"><p>Select a file from the tree, or use the Navigation to explore the app.</p></div>'): string {
  return `<div class="content-panel" id="content-panel">${inner}</div>`
}

// ── Routes ─────────────────────────────────────────────────

// GET /explorer — full shell
explorer.get("/", (c) => {
  const layout = `<div class="layout">${treePanelHtml()}${contentPanelHtml()}</div>`
  return c.html(explorerShell(layout))
})

// GET /explorer/tree — standalone tree view
explorer.get("/tree", (c) => {
  const layout = `<div class="layout">${treePanelHtml()}${contentPanelHtml()}</div>`
  return c.html(explorerShell(layout))
})

// GET /explorer/nav/* — nav link → dashboard page content
explorer.get("/nav/*", async (c) => {
  const navUrl = "/" + c.req.path.replace("/explorer/nav/", "")

  const pageViews: Record<string, () => Promise<unknown>> = {
    "/portfolio": async () => { const { PortfolioView } = await import("../views/portfolio.tsx"); return <PortfolioView /> },
    "/intelligence": async () => { const { IntelligenceView } = await import("../views/intelligence.tsx"); return <IntelligenceView /> },
    "/workflow": async () => { const { WorkflowView } = await import("../views/workflow.tsx"); return <WorkflowView /> },
    "/analyze": async () => { const { AnalysisView } = await import("../views/analysis.tsx"); return <AnalysisView /> },
    "/signals": async () => { const { SignalsView } = await import("../views/signals.tsx"); return <SignalsView /> },
    "/history": async () => { const { HistoryView } = await import("../views/history.tsx"); return <HistoryView /> },
    "/holdings": async () => { const { HoldingsPage } = await import("../views/holdings.tsx"); return <HoldingsPage holdingsData={{ holdings: [], platforms: [], cash: [] }} positionsData={{ positions: [] }} /> },
    "/exits": async () => { const { ExitsView } = await import("../views/exits.tsx"); return <ExitsView /> },
    "/prospects": async () => { const { ProspectsView } = await import("../views/prospects.tsx"); return <ProspectsView /> },
    "/governance": async () => { const { GovernanceView } = await import("../views/governance.tsx"); return <GovernanceView /> },
    "/benchmark": async () => { const { BenchmarkView } = await import("../views/benchmark.tsx"); return <BenchmarkView /> },
    "/feedback": async () => { const { FeedbackView } = await import("../views/feedback.tsx"); return <FeedbackView /> },
    "/alerts": async () => { const { AlertsView } = await import("../views/alerts-view.tsx"); return <AlertsView /> },
    "/screenings": async () => { const { ScreeningsView } = await import("../views/screenings-view.tsx"); return <ScreeningsView /> },
    "/about": async () => { const { AboutView } = await import("../views/about.tsx"); return <AboutView /> },
  }

  const viewFn = pageViews[navUrl]
  if (!viewFn) return c.html(`<div class="error-view"><p>Unknown page: ${navUrl}</p></div>`)
  try {
    const view = await viewFn()
    return c.html(view as unknown as string)
  } catch (err) {
    return c.html(`<div class="error-view"><p>Failed to load: ${String(err)}</p></div>`)
  }
})

// GET /explorer/file/* — file content
explorer.get("/file/*", (c) => {
  const filePath = c.req.path.replace("/explorer/file/", "")
  if (!filePath) return c.html(`<div class="error-view"><p>No file path specified.</p></div>`)

  const fullPath = resolve(process.cwd(), filePath)
  if (!fullPath.startsWith(resolve(process.cwd()))) {
    return c.html(`<div class="error-view"><p>Access denied — path outside project.</p></div>`)
  }

  const kind = classifyFile(filePath)

  // Image: return base64 data URL
  if (kind === "image") {
    let buf: Buffer
    try { buf = readFileSync(fullPath) } catch {
      return c.html(`<div class="error-view"><p>File not found.</p></div>`)
    }
    const ext = filePath.split(".").pop()?.toLowerCase() ?? ""
    const mimeMap: Record<string, string> = { png: "image/png", svg: "image/svg+xml", gif: "image/gif", webp: "image/webp" }
    return c.html(`<div class="file-view"><div class="file-header"><span class="file-path">${filePath}</span><button class="file-copy-btn" onclick="navigator.clipboard.writeText('${filePath.replace(/'/g, "\\'")}')">Copy Path</button></div><img src="data:${mimeMap[ext] ?? "application/octet-stream"};base64,${buf.toString("base64")}" alt="${filePath}" style="max-width:100%;border-radius:4px"/></div>`)
  }

  // Read text file
  let content: string
  try { content = readFileSync(fullPath, "utf-8") } catch {
    return c.html(`<div class="error-view"><p>File not found.</p></div>`)
  }

  const ext = filePath.split(".").pop()?.toLowerCase() ?? ""

  if (kind === "markdown") {
    return c.html(`<div class="file-view"><div class="file-header"><span class="file-path">${filePath}</span><button class="file-copy-btn" onclick="navigator.clipboard.writeText('${filePath.replace(/'/g, "\\'")}')">Copy Path</button></div><div class="markdown-body">${renderMarkdown(content)}</div></div>`)
  }

  if (kind === "text") {
    if (ext === "json") {
      return c.html(`<div class="file-view"><div class="file-header"><span class="file-path">${filePath}</span><button class="file-copy-btn" onclick="navigator.clipboard.writeText('${filePath.replace(/'/g, "\\'")}')">Copy Path</button></div><div class="file-content"><pre><code>${prettyPrintJson(content)}</code></pre></div></div>`)
    }
    const lang = fileLanguageTag(filePath)
    return c.html(`<div class="file-view"><div class="file-header"><span class="file-path">${filePath}</span><button class="file-copy-btn" onclick="navigator.clipboard.writeText('${filePath.replace(/'/g, "\\'")}')">Copy Path</button></div><div class="file-content"><pre><code class="language-${lang}">${highlightCode(content, lang)}</code></pre></div></div>`)
  }

  // Raw (binary or unknown)
  return c.html(`<div class="file-view"><div class="file-header"><span class="file-path">${filePath}</span><button class="file-copy-btn" onclick="navigator.clipboard.writeText('${filePath.replace(/'/g, "\\'")}')">Copy Path</button></div><div class="file-content"><pre>${content.replace(/</g, "&lt;").replace(/>/g, "&gt;")}</pre></div></div>`)
})

export { explorer }