To publish a successful agentic skill to a repository like the "Awesome Skills" ecosystem, you must move beyond functional code and provide **Standardized Metadata** and **Reproducible Environments**. A skill is only "awesome" if it works out-of-the-box for the next user.

Below is the `brief` you requested, structured to produce a high-quality, publishable skill.

---

# Epic/Brief: Agentic Skill Silo Packaging

**Date:** 2026-05-31
**Epic ID:** SKILL-PKG-001
**Status:** Open

---

## Task: Create Skill Delivery & Installable Template

**Objective:** Standardize the packaging of `AI-Trader` skills so they can be installed and executed as independent, self-contained silos on external systems.

## What

* [ ] Create `skills/templates/skill-manifest.json` defining inputs, outputs, and dependencies.
* [ ] Implement a `scripts/publish-skill.ts` that bundles a Silo into a portable archive (including `flox.toml`, `justfile`, and necessary playbooks).
* [ ] Create a `README.md` template for skills that strictly follows the `Edinburgh Protocol` for integrity.


* [ ] Implement a `just install-skill <path>` command that automatically initializes a local environment via `flox` and registers the skill’s registry index.



## How to Verify

* [ ] Run `just publish-skill <skill-name>` and verify a self-contained archive is created.
* [ ] In a new, empty directory, run `just install-skill <archive-path>` and verify the environment activates successfully using `flox`.


* [ ] Ensure the installed skill generates a valid `silo` structure (briefs, decisions, debriefs) upon first run.



## Technical Notes

* Skills must remain decoupled; do not allow the skill to rely on global `AI-Trader` state.
* Use `flox` for environment isolation so the skill works on any host OS.


* Include a `Barnacle Inspection` step in the skill's installation workflow to ensure the host environment is not polluted.



---

## Opinion: The Path to "Awesome"

For a skill to be considered "awesome" in the current agentic ecosystem, it needs to satisfy the **Three Pillars of Agentic Adoption**:

1. **Observability (The Edinburgh Standard):** Your skill must produce the `Brief-Decision-Debrief` audit trail. Agents are prone to "drift"—a skill that documents its reasoning via ADRs and debriefs builds trust immediately.


2. **Zero-Friction Reproducibility:** By using `flox`, you guarantee that your skill’s toolchain (Bun, Python versions, CLI tools) doesn't fail on the user's machine. If a user has to troubleshoot dependencies, your skill will be deleted.


3. **Process Integration:** Don't just ship code; ship the **process**. Include the `playbooks/` that define how the skill should be maintained. A skill that comes with its own `Barnacle Inspection` routine is objectively more valuable than one that just provides a functional API.



By packaging your project this way, you aren't just shipping a tool; you are shipping a **self-maintaining operational methodology**.

Does this structure align with your target platform's requirements for skill manifest formats, or should we adjust the `skill-manifest.json` schema?