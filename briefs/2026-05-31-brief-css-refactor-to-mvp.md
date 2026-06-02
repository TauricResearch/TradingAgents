This is the final seal on your operational environment. By moving to **Semantic-First Rendering** and **CSS Isolation**, you are effectively "compiling out" the visual fragility that plagues modern web development.

Here is the implementation plan, drafted for immediate execution.

---

### 1. New Brief: CSS & Semantic Integrity

**Epic/Brief: CSS Firewall & Semantic Rendering**

**Date:** 2026-05-31
**Epic ID:** SILO-OS-003
**Status:** Open

---

## Task: Establish Semantic-First Rendering

**Objective:** Eliminate visual entropy by decoupling structure from style and enforcing a strict isolation policy for third-party components.

## What

* [ ] **Global CSS Reset**: Replace current styling with `MVP.css` or `Pico.css` as a single, immutable global file.


* [ ] **Purge Utility Classes**: Remove all `Tailwind` or other utility-class dependencies from web views.


* [ ] **Component Audit**: Audit existing third-party components for external style dependencies.


* [ ] **Isolation Gate**: Implement a strict "Encapsulated Styling" rule for all future component additions.



## How to Verify

* [ ] Verify that pages render correctly using native HTML elements without custom CSS classes.


* [ ] Confirm no inline `style="..."` attributes remain in agent-generated views.


* [ ] Verify third-party components are self-contained and do not break the global semantic theme.



---

### 2. Update to `playbooks/conventions-playbook.md`

Add the following under the **Semantic Rendering Standard** section:

```markdown
## Semantic Rendering Standard (CSS-less Architecture)

To maintain data integrity and prevent agentic layout hallucinations, we follow a
strict semantic-first rendering rule. Agents are responsible for *structure*,
not *decoration*.

1. **No Inline Styling**: Agents are strictly forbidden from writing CSS or 
   inline `style="..."` attributes[cite: 6].
2. **Semantic Hierarchy**: Use native HTML5 elements (`<article>`, `<nav>`, 
   `<aside>`, `<table>`, `<dl>`) to convey data relationships[cite: 6]. 
3. **Data-Driven Reactivity**: Use `data-` attributes to represent the 
   state of the Silo; keep the logic for rendering those states in an 
   external, CSS/JS file that the agent never touches[cite: 6, 9].
4. **Component Integrity Rule**: All third-party components must be fully 
   self-contained. Any component that requires external CSS modifications or 
   global style overrides is considered non-compliant and will be rejected[cite: 9].

**Why**: An ugly, perfectly organized document is infinitely more useful 
to an agent than a beautiful one where the structure is obscured by CSS soup[cite: 9, 10].

```

