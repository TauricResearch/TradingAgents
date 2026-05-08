#!/usr/bin/env bun
/**
 * Export a GitNexus subgraph to Graphviz DOT format.
 *
 * Writes to docs/diagrams/ by default with auto-generated filenames:
 *   --symbol → docs/diagrams/gn-impact-<symbol>.dot
 *   --file   → docs/diagrams/gn-file-<filename>.dot
 *
 * Usage:
 *   bun scripts/gitnexus-to-dot.ts --symbol calculateTradePlan          # impact graph
 *   bun scripts/gitnexus-to-dot.ts --file cli/trading/commands/plan.ts   # file graph
 *   bun scripts/gitnexus-to-dot.ts --depth 2 --symbol DatabaseFactory    # deeper traversal
 *   bun scripts/gitnexus-to-dot.ts --symbol calculateTradePlan --render  # output SVG
 *
 * Requires: gitnexus (npm install -g gitnexus), graphviz (dot)
 */

import { execSync } from "node:child_process"
import { writeFileSync } from "node:fs"

// ── Types ───────────────────────────────────────────────────────────────────

interface DotNode {
  id: string
  label: string
  type: string
  filePath?: string
}

interface DotEdge {
  from: string
  to: string
}

interface Options {
  symbol?: string
  file?: string
  depth: number
  render: boolean
  output: string
  maxNodes: number
}

// ── Argument parsing ──────────────────────────────────────────────────────

function parseArgs(): Options {
  const args = Bun.argv.slice(2)
  const opts: Options = {
    depth: 1,
    render: false,
    output: "./docs/diagrams/gn-graph.dot",
    maxNodes: 100,
  }

  for (let i = 0; i < args.length; i++) {
    const arg = args[i]
    if (arg === "--symbol" || arg === "-s") opts.symbol = args[++i]
    else if (arg === "--file" || arg === "-f") opts.file = args[++i]
    else if (arg === "--depth" || arg === "-d") opts.depth = parseInt(args[++i], 10)
    else if (arg === "--render" || arg === "-r") opts.render = true
    else if (arg === "--output" || arg === "-o") opts.output = args[++i]
    else if (arg === "--max-nodes" || arg === "-m") opts.maxNodes = parseInt(args[++i], 10)
  }

  if (!opts.symbol && !opts.file) {
    console.error("Usage: bun scripts/gitnexus-to-dot.ts [--symbol NAME | --file PATH] [options]")
    console.error("  --symbol, -s    Root symbol for impact graph")
    console.error("  --file, -f      Root file for module graph")
    console.error("  --depth, -d     Traversal depth (default: 1)")
    console.error("  --render, -r    Render DOT to SVG with graphviz")
    console.error("  --output, -o    Output DOT path (default: ./graph.dot)")
    console.error("  --max-nodes, -m Max nodes before pruning (default: 100)")
    process.exit(1)
  }

  return opts
}

// ── Graphviz helpers ──────────────────────────────────────────────────────

function sanitizeDotId(id: string): string {
  // DOT IDs must be alphanumeric or underscore. Replace everything else.
  return id.replace(/[^a-zA-Z0-9_]/g, "_")
}

function escapeDotLabel(label: string): string {
  return label.replace(/"/g, '\\"').replace(/\n/g, "\\n")
}

function typeToColor(type: string): string {
  const colors: Record<string, string> = {
    Function: "#4a90d9",
    Class: "#e8a838",
    Method: "#c990e8",
    Interface: "#50c878",
    Variable: "#d9d9d9",
    Const: "#b8b8b8",
    File: "#f5f5f5",
    Route: "#ff6b6b",
    Process: "#9b59b6",
    Community: "#3498db",
  }
  return colors[type] ?? "#cccccc"
}

// ── Cypher query execution ──────────────────────────────────────────────────

function runCypher(query: string): Array<Record<string, unknown>> {
  // Write query to temp file to avoid shell quoting nightmares with parentheses
  const tmpFile = `/tmp/gn_query_${Date.now()}.cypher`
  const outFile = `/tmp/gn_result_${Date.now()}.json`
  writeFileSync(tmpFile, query)

  const cmd = `gitnexus cypher "$(cat ${tmpFile})" > "${outFile}" 2>/dev/null && cat "${outFile}"`
  try {
    const raw = execSync(cmd, { encoding: "utf-8", timeout: 30000, shell: "/bin/bash" })
    const parsed = JSON.parse(raw)
    if (parsed.error) {
      throw new Error(`Cypher error: ${parsed.error}`)
    }
    if (parsed.markdown) {
      return parseMarkdownTable(parsed.markdown)
    }
    return []
  } catch (e) {
    console.error(`Cypher query failed: ${e instanceof Error ? e.message : String(e)}`)
    return []
  } finally {
    try {
      execSync(`rm -f "${tmpFile}" "${outFile}"`, { encoding: "utf-8" })
    } catch {
      // ignore cleanup errors
    }
  }
}

function parseMarkdownTable(markdown: string): Array<Record<string, unknown>> {
  const lines = markdown
    .trim()
    .split("\n")
    .filter((l) => l.trim() && !l.startsWith("|---"))
  if (lines.length < 2) return []

  // First line is headers
  const headerLine = lines[0]
  const headers = headerLine
    .split("|")
    .map((h) => h.trim())
    .filter(Boolean)

  const rows: Array<Record<string, unknown>> = []
  for (let i = 2; i < lines.length; i++) {
    const cells = lines[i]
      .split("|")
      .map((c) => c.trim())
      .filter(Boolean)
    if (cells.length === headers.length) {
      const row: Record<string, unknown> = {}
      for (let j = 0; j < headers.length; j++) {
        row[headers[j]] = cells[j]
      }
      rows.push(row)
    }
  }
  return rows
}

// ── Graph builders ─────────────────────────────────────────────────────────

function buildImpactGraph(
  symbol: string,
  depth: number,
  maxNodes: number,
): { nodes: DotNode[]; edges: DotEdge[] } {
  const nodes = new Map<string, DotNode>()
  const edges: DotEdge[] = []
  const visited = new Set<string>()
  const queue: Array<{ id: string; name: string; type: string; d: number }> = []

  // Get root node info
  const rootQuery = `MATCH (n) WHERE n.name = '${symbol.replace(/'/g, "\\'")}' RETURN n.id AS id, labels(n) AS labels, n.filePath AS filePath LIMIT 1`
  const rootRows = runCypher(rootQuery)
  if (rootRows.length === 0) {
    console.error(`Symbol not found: ${symbol}`)
    return { nodes: [], edges: [] }
  }

  const root = rootRows[0]
  const rootId = String(root.id || symbol)
  const rootType = String((root.labels as string)?.split(",")[0] || "Unknown")
  queue.push({ id: rootId, name: symbol, type: rootType, d: 0 })
  nodes.set(rootId, {
    id: rootId,
    label: symbol,
    type: rootType,
    filePath: String(root.filePath || ""),
  })

  while (queue.length > 0 && nodes.size < maxNodes) {
    const current = queue.shift()
    if (!current) continue
    if (visited.has(current.id)) continue
    visited.add(current.id)

    if (current.d >= depth) continue

    // Outgoing edges (what this node calls)
    const outQuery = `MATCH (a)-[r]->(b) WHERE a.id = '${current.id.replace(/'/g, "\\'")}' RETURN b.id AS id, b.name AS name, labels(b) AS labels, b.filePath AS filePath LIMIT 20`
    for (const row of runCypher(outQuery)) {
      const id = String(row.id)
      if (!id || visited.has(id)) continue
      const type = String((row.labels as string)?.split(",")[0] || "Unknown")
      nodes.set(id, {
        id,
        label: String(row.name || id),
        type,
        filePath: String(row.filePath || ""),
      })
      edges.push({ from: current.id, to: id })
      if (!visited.has(id)) {
        queue.push({ id, name: String(row.name), type, d: current.d + 1 })
      }
    }

    // Incoming edges (what calls this node)
    const inQuery = `MATCH (a)-[r]->(b) WHERE b.id = '${current.id.replace(/'/g, "\\'")}' RETURN a.id AS id, a.name AS name, labels(a) AS labels, a.filePath AS filePath LIMIT 20`
    for (const row of runCypher(inQuery)) {
      const id = String(row.id)
      if (!id || visited.has(id)) continue
      const type = String((row.labels as string)?.split(",")[0] || "Unknown")
      nodes.set(id, {
        id,
        label: String(row.name || id),
        type,
        filePath: String(row.filePath || ""),
      })
      edges.push({ from: id, to: current.id })
      if (!visited.has(id)) {
        queue.push({ id, name: String(row.name), type, d: current.d + 1 })
      }
    }
  }

  return { nodes: Array.from(nodes.values()), edges }
}

function buildFileGraph(
  filePath: string,
  maxNodes: number,
): { nodes: DotNode[]; edges: DotEdge[] } {
  const nodes = new Map<string, DotNode>()
  const edges: DotEdge[] = []

  // Get all symbols in the file
  const query = `MATCH (n) WHERE n.filePath = '${filePath.replace(/'/g, "\\'")}' RETURN n.id AS id, n.name AS name, labels(n) AS labels LIMIT ${maxNodes}`
  const rows = runCypher(query)

  for (const row of rows) {
    const id = String(row.id)
    const type = String((row.labels as string)?.split(",")[0] || "Unknown")
    nodes.set(id, {
      id,
      label: String(row.name || id),
      type,
      filePath,
    })
  }

  // Get edges between symbols in this file
  const ids = Array.from(nodes.keys())
    .map((id) => `'${id.replace(/'/g, "\\'")}'`)
    .join(",")
  if (ids) {
    const edgeQuery = `MATCH (a)-[r]->(b) WHERE a.id IN [${ids}] AND b.id IN [${ids}] RETURN a.id AS fromId, b.id AS toId LIMIT 200`
    for (const row of runCypher(edgeQuery)) {
      edges.push({ from: String(row.fromId), to: String(row.toId) })
    }
  }

  return { nodes: Array.from(nodes.values()), edges }
}

// ── DOT generation ────────────────────────────────────────────────────────

function toDot(nodes: DotNode[], edges: DotEdge[], title: string): string {
  const nodeLines: string[] = []
  const edgeLines: string[] = []
  const seenIds = new Set<string>()

  for (const node of nodes) {
    const id = sanitizeDotId(node.id)
    if (seenIds.has(id)) continue
    seenIds.add(id)
    const label = escapeDotLabel(node.label)
    const type = escapeDotLabel(node.type)
    const file = node.filePath ? escapeDotLabel(node.filePath.split("/").pop() || "") : ""
    const tooltip = file ? `${type}: ${file}` : type
    const color = typeToColor(node.type)
    nodeLines.push(
      `  ${id} [label="${label}", fillcolor="${color}", style="filled", fontcolor="white", tooltip="${tooltip}"];`,
    )
  }

  for (const edge of edges) {
    const fromId = sanitizeDotId(edge.from)
    const toId = sanitizeDotId(edge.to)
    if (seenIds.has(fromId) && seenIds.has(toId)) {
      edgeLines.push(`  ${fromId} -> ${toId};`)
    }
  }

  return `digraph "${escapeDotLabel(title)}" {
  rankdir=LR;
  node [shape=box, fontname="Helvetica", fontsize=10];
  edge [fontname="Helvetica", fontsize=9, color="#666666"];
  bgcolor="#fafafa";

${nodeLines.join("\n")}

${edgeLines.join("\n")}
}
`
}

// ── Main ────────────────────────────────────────────────────────────────────

function defaultOutputPath(opts: Options): string {
  const base = "./docs/diagrams"
  if (opts.symbol) {
    const safe = opts.symbol.replace(/[^a-zA-Z0-9_-]/g, "_")
    return `${base}/gn-impact-${safe}.dot`
  }
  if (opts.file) {
    const name = opts.file.replace(/\//g, "_").replace(/\..+$/, "")
    return `${base}/gn-file-${name}.dot`
  }
  return `${base}/gn-graph.dot`
}

function main() {
  const opts = parseArgs()

  // Auto-generate output path if not explicitly overridden
  const output =
    opts.output === "./docs/diagrams/gn-graph.dot" ? defaultOutputPath(opts) : opts.output

  console.log(
    `Building graph: ${opts.symbol ? `symbol=${opts.symbol}` : `file=${opts.file}`}, depth=${opts.depth}`,
  )

  let nodes: DotNode[]
  let edges: DotEdge[]
  let title: string

  if (opts.symbol) {
    const result = buildImpactGraph(opts.symbol, opts.depth, opts.maxNodes)
    nodes = result.nodes
    edges = result.edges
    title = `Impact of ${opts.symbol}`
  } else if (opts.file) {
    const result = buildFileGraph(opts.file, opts.maxNodes)
    nodes = result.nodes
    edges = result.edges
    title = `Symbols in ${opts.file?.split("/").pop()}`
  }

  console.log(`  Nodes: ${nodes.length}, Edges: ${edges.length}`)

  if (nodes.length === 0) {
    console.error("No nodes found. Check symbol name or file path.")
    process.exit(1)
  }

  const dot = toDot(nodes, edges, title)
  writeFileSync(output, dot)
  console.log(`  DOT written: ${output}`)

  if (opts.render) {
    const svgPath = output.replace(/\.dot$/, ".svg")
    const pngPath = output.replace(/\.dot$/, ".png")
    try {
      execSync(`dot -Tsvg "${output}" -o "${svgPath}"`, { encoding: "utf-8" })
      console.log(`  SVG rendered: ${svgPath}`)
    } catch (e) {
      console.error(`  SVG render failed: ${e instanceof Error ? e.message : String(e)}`)
    }
    try {
      execSync(`dot -Tpng "${output}" -o "${pngPath}"`, { encoding: "utf-8" })
      console.log(`  PNG rendered: ${pngPath}`)
    } catch (e) {
      console.error(`  PNG render failed: ${e instanceof Error ? e.message : String(e)}`)
    }
  }
}

main()
