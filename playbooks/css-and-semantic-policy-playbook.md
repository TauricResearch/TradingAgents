# Playbook: CSS & Semantic Policy

## The Problem: Decorative Drift
We have moved away from Tailwind because "co-location" of style and structure
created agentic nightmare scenarios[cite: 9]. Agents that should be reasoning 
about data were instead hallucinating layout classes[cite: 6, 9].

## The Philosophy: The "Sad Web"
We embrace semantic HTML because it is **machine-readable, durable, and 
agent-aligned**[cite: 9].

1. **Content is King**: The Silo’s data must be accessible and correctly 
   structured.
2. **Design is Global**: If the site needs a theme, it is applied globally via 
   an immutable CSS file (e.g., `mvp.css`)[cite: 9, 10].
3. **Components are Encapsulated**: If a component needs style, it brings it. 
   If it leaks style, it is rejected[cite: 9].

## Governance
- **Agent Instruction**: "Render semantic HTML only. No classes. No inline 
  styles. Use tables for data and sections for hierarchy."[cite: 6, 9]
- **Review Gate**: If an agent proposes a PR adding utility classes or inline 
  styles, the human review gate must **reject it**[cite: 2, 9].

## Why this works
This approach reduces reasoning effort. The agent no longer wonders "which 
shade of blue is this?" It only asks "what is the semantic meaning of this 
data?"[cite: 9]

