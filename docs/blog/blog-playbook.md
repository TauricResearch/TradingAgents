Utilizing a Jekyll-powered GitHub Pages pipeline as our publishing engine aligns perfectly with the principle of **Deductive Minimalism (`COG-12`)**. It allows us to treat our markdown artifacts as raw, pure source files while offloading the compilation mechanics entirely to GitHub's infrastructure.

By decoupling the content repository from specialized publishing frontends, we establish **Workflow Durability (`PHI-13`)**. This playbook provides the definitive constraint stack for compiling, organizing, and distributing markdown files (such as our System Briefs, Playbooks, and Blog Assets) across public directories, personal spaces, and content distribution channels.

---

# THE AGENTIC PUBLISHING PLAYBOOK: JEKYLL & GITHUB PAGES PIPELINE (APP-002)

## 1. PURPOSE & CORE OPERATIONAL INTENT

This playbook establishes the strict layout parameters, front-matter configurations, and publishing gates required to transform raw Markdown repository assets into optimized web assets via GitHub Pages and Jekyll.

The core architectural boundary requires an **Abstraction Depth $N \le 2$** (`AP-002`). The source files must render into clean static layouts without relying on custom runtime plugins that obscure content structure from AI scrapers, search indices, or content aggregators.

---

## 2. PIPELINE SEPARATION MATRIX

To distribute content cleanly across multi-platform hubs (GitHub Pages, Substack, Medium, Hacker News), the repository layout must follow strict specialized boundaries:

```
[ Your Repository Root ]
 ├── assets/                   <-- Static media assets (Images, SVGs, CSS)
 ├── _layouts/                 <-- Structural layouts (Default, Post, Doc)
 ├── _posts/                   <-- Public long-form content (Substack/Medium targets)
 ├── _briefs/                  <-- Internal system contexts (System Briefs, Playbooks)
 └── _config.yml               <-- Unified pipeline configuration file

```

---

## 3. CORE LIFECYCLE PHASES

### Phase 1: Ingest the Global Configuration (`_config.yml`)

The engine's global settings must be kept strictly minimal to eliminate runtime build overhead. Create an uncompromised configuration at the repository root:

```yaml
title: "Virtual Information Systems Architecture"
description: "Empirical Pragmatism & Synthetic Intelligence Execution Frameworks"
baseurl: "" # Keep blank for user/organization sites (<user>.github.io)
url: "https://virtual-information-systems.github.io"

# Engine Parameters
markdown: kramdown
kramdown:
  syntax_highlighter: rouge # Strict compile-time syntax highlighting

# Specialization Collections (PHI-14)
collections:
  briefs:
    output: true
    permalink: /briefs/:name/

exclude:
  - Gemfile
  - Gemfile.lock
  - node_modules/
  - vendor/

```

### Phase 2: Establish the Structural Base Layers (`_layouts/`)

To preserve code and token locality, layout layers are restricted to two basic templates. Create `_layouts/default.html` to define the system's unyielding outer skin:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{ page.title }} | {{ site.title }}</title>
  <link rel="stylesheet" href="/assets/css/style.css">
</head>
<body>
  <header>
    <nav>
      <a href="/">Home</a> | <a href="/briefs/">System Briefs</a>
    </nav>
  </header>
  
  <main>
    {{ content }} 
  </main>
</body>
</html>

```

### Phase 3: Enforce Token Front-Matter Invariant

Every Markdown file slated for publication must declare its identity explicitly at the exact `Turn 0` token position using YAML Front-Matter. **No exceptions allowed.**

#### Pattern A: Long-Form Blog Assets (`_posts/YYYY-MM-DD-filename.md`)

```markdown
---
layout: default
title: "The Good Parts for Agents: Why LLMs Prefer Flat Code"
date: 2026-05-17 12:00:00 +0000
categories: architecture ai
tags: [master-context, edinburgh-protocol]
canonical_target: "https://substack.com/@yourprofile"
---
# The Content Begins Safely Here...

```

#### Pattern B: Operational Briefs & Frameworks (`_briefs/filename.md`)

```markdown
---
layout: default
title: "The Edinburgh Protocol System Playbook"
type: operational-manifest
version: 2.0
entropy_bounds: "low"
---
# System Guardrails Begin Here...

```

---

## 4. MULTI-PLATFORM EXPORT ROUTING (THE LOGISTICAL GRID)

Jekyll serves as our single source of truth. When content is finalized, use this operational matrix to deploy across our targeted target distributions:

| Target Hub | Distribution Source File | Format Gate Constraint | Optimization Rule |
| --- | --- | --- | --- |
| **GitHub Pages** | Pure Markdown File via Git Commit | Strict Jekyll Layout Rendering (`_layouts/`) | Automatically built and deployed asynchronously via GitHub Actions pipelines. |
| **Substack / Medium** | Raw Body Text of `_posts/` | Pure long-form text blocks, including Footnotes | Strip layout metadata blocks; paste directly into the provider's text interface. |
| **Hacker News** | Dedicated submission block from `Channel Assets Extraction` | Plain Text Block + Live GitHub Link | Post as a Text Submission thread to gather immediate engineering review feedback. |
| **Twitter / X** | Chunked Thread Segments from `Channel Assets Extraction` | Post-Blocks optimized for exact string characters | Sequence using numbers (1/4) to maximize delivery visibility. |

---

## 5. LOCAL PREVIEW VERIFICATION WORKFLOW

Before committing changes to the production branch, you must internally review your layout formatting to prevent rendering regressions.

```bash
# Step 1: Initialize local Ruby dependencies via Bundler
bundle init

# Step 2: Declare the required GitHub Pages environment gems
bundle add github-pages webrick --group :jekyll_plugins

# Step 3: Run the local compiler server bypassing repository base URL properties
bundle exec jekyll serve --baseurl=""

```

*Verification Check:* Open your local browser environment to `http://localhost:4000`. Run an validation pass over headings, footnote bindings, and highlighted code snippets.

---

## 6. ANTI-PATTERNS VS. RECOMMENDED BEST PRACTICES

| ❌ Banned Anti-Patterns (High Entropy) | Recommended Best Practices (Low Entropy) |
| --- | --- |
| **Commiting custom compiled JavaScript plugins** that break standard GitHub Actions compiler runners. | **Using default Jekyll themes or raw custom CSS layouts** located securely in the `/assets/` directory. |
| **Splitting a single post's layout** across multiple sub-include files. | **Keeping long-form content completely continuous** to preserve raw token context for downstream reading sub-agents. |
| **Mixing administrative repository documentation** with public-facing technical publication assets. | **Explicitly separating system operational assets** into standalone custom `collections` layouts (`_briefs`). |

---

## Ctx Persona Opinion

This playbook cleanly bridges our code generation loop with our media distribution channel. By utilizing static files wrapped in standard YAML front-matter metadata, your AI coding sub-agents can automatically author, date, verify, and queue up new technical blog posts directly within the repository file tree (`_posts/`).

The code remains flat, execution remains completely zero-cost, and you maintain perfect content sovereignty over your intellectual assets before cross-posting to external platforms like Substack or Medium.

Should we instruct your coding agent to establish this folder structure inside your repository right away, or should we refine the CSS styles template required to display our footnotes correctly on the static web pages?