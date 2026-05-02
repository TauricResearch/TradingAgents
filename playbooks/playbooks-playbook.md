---
date: 2026-02-01
tags:
  - playbook
  - meta
  - process
  - documentation
agent: antigravity
environment: local
---

# Playbook for Playbooks

## Purpose
A **Playbook** is a codified set of instructions, patterns, or standards for a specific repeatable task. It exists to reduce cognitive load, ensure consistency, and capture "tribal knowledge" into an explicit protocol.

## When to Write a Playbook
1.  **Repeatability:** If a task will be done more than twice, write a playbook.
2.  **Complexity:** If a task involves >3 steps or critical constraints, write a playbook.
3.  **Discovery:** If you solve a novel problem ("First Contact"), write a playbook to guide future agents.
4.  **Standards:** If there is a "Right Way" to do something (e.g., File Naming, Design Style), write a playbook.

## The Structure of a Playbook
Every playbook MUST follow this structure to be machine-readable and human-navigable.

### 1. Frontmatter
Standard YAML metadata.
```yaml
---
date: YYYY-MM-DD
tags: [playbook, topic, subtopic]
agent: (optional)
environment: (optional)
---
```

### 2. Title & Purpose
*   **H1 Title:** Clear, operational title (e.g., "Postgres Migration Playbook").
*   **Purpose:** A single sentence explaining *what* this does and *why*.

### 3. Context & Prerequisites
*   What tools are needed?
*   What state must the system be in?
*   Reference other playbooks if necessary.

### 4. The Protocol (The "How-To")
This is the core. Use numbered lists. Be imperative.
*   **Step 1:** Do X.
*   **Step 2:** Check Y.
    *   *Constraint:* Watch out for Z.

### 5. Standards & Patterns (Optional)
If the playbook defines a *style* rather than a *process*, list the rules here.
*   "Always use `kebab-case`."
*   "Never use `table` for layout."

### 6. Validation (How do I know I'm done?)
*   Clear acceptance criteria.
*   "The script runs without error."
*   "The file exists."

## Maintenance
*   Playbooks are living documents.
*   If a playbook fails, UPDATE IT. Do not just bypass it.
*   **Deprecation:** If a playbook is obsolete, add a `> **DEPRECATED**` banner at the top and link to the successor.

## Location
All playbooks reside in `playbooks/`.
Filename convention: `topic-subtopic-playbook.md` (unless it's a specific protocol like `grep-strategy.md`).
