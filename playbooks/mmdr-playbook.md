---
date: 2026-02-01
tags:
  - playbook
  - documentation
  - mermaid
  - rendering
  - rust
agent: antigravity
environment: local
source: "https://medium.com/@trivajay259/mmdr-the-rust-powered-mermaid-renderer-that-makes-your-docs-fly-500-1000-faster-b4c6485d1639"
---

# mmdr Playbook

## Purpose
Use **mmdr**, a native Rust Mermaid renderer, to generate SVG and PNG diagrams 500–1000× faster than `mermaid-cli` by eliminating the headless Chromium cold-start overhead.

## Context & Prerequisites

- **Problem:** `mermaid-cli` pays a heavy "cold start" tax — it boots headless Chromium via Puppeteer for each render, adding ~2–3 seconds of overhead per diagram. Multiply this by dozens of diagrams in CI or a live preview loop and minutes vanish.
- **Solution:** **mmdr** is a native Rust Mermaid renderer that outputs SVG (and PNG via resvg) in **2–6 ms** on typical diagrams.
- **Key difference:** No Node.js, no Puppeteer, no browser — just speed.

### How mmdr works
1. **Parses Mermaid natively** in Rust
2. **Renders directly to SVG**, with optional PNG via **resvg**
3. Ships **without** Chromium, Puppeteer, or Node.js

Result: the "browser startup cost" disappears.

## Performance Benchmarks

**Latest end-to-end results (January 22, 2026)**
Machine: Intel® Core™ Ultra 7 256V (8 cores), Linux 6.18.2-arch2–1
