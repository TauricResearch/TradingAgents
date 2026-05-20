# Brief: kpdf — Local Kreuzberg PDF Wrapper

**Date:** 2026-05-19  
**Stack:** Bun + `@kreuzberg/node` (TypeScript/Node, native speed)  
**Scope:** Local script — test locally, gain experience, publish later if warranted  
**Status:** Implementation brief

---

## Goal

A simple, local CLI for extracting text and metadata from PDFs using Kreuzberg, stored in `scripts/kpdf.ts`. No npm publish until tested.

---

## Installation

```bash
bun add @kreuzberg/node
```

---

## Files

| File | Action |
|------|--------|
| `scripts/kpdf.ts` | Create — thin Bun wrapper around Kreuzberg |

---

## Usage

```bash
# Plain text
bun kpdf.ts --file report.pdf

# Markdown output
bun kpdf.ts --file report.pdf --format markdown

# JSON with metadata
bun kpdf.ts --file report.pdf --format json

# Extract to file
bun kpdf.ts --file report.pdf --format markdown > parsed.md

# Help
bun kpdf.ts --help
```

---

## Implementation

Single file, no dependencies beyond `@kreuzberg/node`. Minimal options — test the core extraction first, add features as needed.

---

## Testing

```bash
# Install
bun add @kreuzberg/node

# Smoke test
bun kpdf.ts --file ./README.md --format markdown | head -20

# Verify output shape
bun kpdf.ts --file ./README.md --format json | python3 -c "import json,sys; d=json.load(sys.stdin); print('content length:', len(d.get('content','')), 'metadata:', list(d.get('metadata',{}).keys()))"
```

---

## Future (post-testing)

- Publish as npm package if value confirmed
- MCP server mode for agent integration
- Structured extraction with JSON schema
- Support for other formats (DOCX, images) if needed

## Status

**Implemented.** `scripts/kpdf.ts` + `@kreuzberg/node` installed.

Tested on `docs/mgf-for-agentic-ai.pdf` — all three formats work:

```bash
# Markdown (clean text with heading structure)
bun run scripts/kpdf.ts --file docs/mgf-for-agentic-ai.pdf --format markdown | head -30

# JSON (structured document nodes — paragraphs, tables, etc.)
bun run scripts/kpdf.ts --file docs/mgf-for-agentic-ai.pdf --format json | jq '.body | length'

# Plain text
bun run scripts/kpdf.ts --file report.pdf --format text
```

Also installed: `kreuzberg` CLI binary (from package)

---

*Keep it simple. Test it. Learn it. Then decide.*