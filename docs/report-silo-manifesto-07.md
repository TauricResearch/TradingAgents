I have updated the **Conventions Playbook** to include the **Semantic Rendering Standard**. This ensures that all future agentic output focuses on data structure rather than presentation, effectively eliminating the "CSS-hallucination" friction.

---

### Addition to `playbooks/conventions-playbook.md`

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
4. **Accessibility First**: Use `aria-labels` and `aria-roles` where necessary 
   to ensure the Silo’s data is machine-readable and accessible by default[cite: 6].

**Why**: An ugly, perfectly organized document is infinitely more useful 
to an agent than a beautiful one where the structure is obscured by CSS soup 
[cite: 9, 10].

```

---

### Implementation Path for Today

To operationalize this immediately, you can follow these steps in your current session:

1. **Update the Playbook**: Commit this addition to `playbooks/conventions-playbook.md`.


2. **Run `just reg-sync**`: Ensure the updated playbook is captured in your Silo’s registry.


3. **Audit Existing Views**: Have the agent perform a "Barnacle Inspection" on your `src/server/` views to identify and strip inline styles or non-semantic `div`-soup.


4. **Adopt the "Sad Web"**: For your next web-view feature, instruct the agent to "render semantic HTML only," leaving the CSS to your global stylesheet.



This approach transforms the agent into a reliable "Content Architect" rather than a struggling "Web Designer". You have officially moved the project toward a CSS-less, protocol-compliant web story.

Is there anything else you need to finalize before you start the implementation?