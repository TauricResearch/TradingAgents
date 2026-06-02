If you drop CSS from the agent's responsibilities, you solve the "agentic visual hallucination" problem instantly. By moving to a **CSS-less HTML architecture**, you convert the web into a document-oriented medium rather than a design-oriented one, which perfectly aligns with the agent’s text-first cognitive model.

### The Impact of CSS-less HTML for Agents

* **Semantic Purity**: Agents excel at structure. When an agent is asked to render a `<table>` or a `<dl>` (description list) without worrying about `div` nesting or `flexbox` properties, it focuses entirely on the semantic hierarchy of the data.


* **Predictable DOM**: Without CSS, the document becomes a predictable, browser-default stream. The agent doesn't need to reason about layout engines; it only needs to reason about the data relationships.


* **Decoupled Design**: By handling CSS as a separate, global layer (e.g., a single project-wide `style.css` or a Tachyons-style functional class layer), you prevent the agent from ever having to touch styling code. The agent manages *content*; you manage the *presentation*.



### The "Silo" Web Strategy: Data-to-View

You are right: displaying data is not rocket science, and HTML is the perfect format if you strip away the "design debt".

1. **Data-Centric (The Silo Outbox)**: Your Silo logic continues to generate raw data (JSON/Markdown/CSV).


2. **Deterministic Converter**: Instead of having the agent "build a web view," use a simple script (e.g., `scripts/data-to-html.ts`) that takes the output of a Silo and maps it to a standard, CSS-free HTML template.


3. **Agent's Role**: The agent's only responsibility is to populate the *data attributes* or *semantic tags*. It doesn't write "how it looks"; it writes "what it is".


4. **CSS Layer**: The web view consumes the agent-generated HTML and applies a global CSS layer that handles all the layout, spacing, and typography.



### Opinion: The "Sad Web" Is the Best Web

A "sad," CSS-less web (the default browser style) is actually a superior debug tool. If an agent-generated web view looks broken without CSS, the *data structure* is broken. If it looks correct (simple, clean text), the data is sound.

* **Pros**: You eliminate 100% of the "agent-CSS-hallucination" friction. You gain a "view source" auditability that is essentially a text dump.


* **Cons**: It will look like the 1993 web. This is a feature, not a bug, in an operational silo where **data fidelity > visual flair**.



### Moving Forward

If you instruct the agent that its output must conform to a **"Semantic HTML Schema"** (e.g., "Use tables for ledgers, definition lists for status, and headers for milestones"), you remove the need for it to understand web design entirely. You turn the agent into a content-provider, which is exactly where their reasoning strengths lie.

Should we formalize this "No-CSS-for-Agents" rule in your `Conventions Playbook` to ensure that no future agent attempts to "help" by adding inline styles?
