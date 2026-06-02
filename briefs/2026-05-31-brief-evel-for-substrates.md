This brief outlines the creation of a **Protocol-Validator** script, designed to screen agent substrates by testing their adherence to the Edinburgh Protocol and the Silo operational workflow.

---

# Epic/Brief: Edinburgh Protocol-Validator Script

**Date:** 2026-05-31
**Epic ID:** PROTO-VAL-001
**Status:** Open

---

## Task: Create a Protocol-Validator for Substrate Screening

**Objective:** Develop a tool to quantitatively evaluate an agent substrate’s ability to maintain system integrity, boundary isolation, and documentation standards.

## What

* [ ] **The Integrity Suite**: A test runner that sets up a controlled project environment and injects "process barnacles" (e.g., stale `current.md` vs `td` state).


* [ ] **Compliance Gate**: A validator script that evaluates the output of a test task against the ADR format and debrief requirements.


* [ ] **Substrate Scorer**: A mechanism to aggregate results into a "Compliance Score," measuring the substrate's ability to respect Silo boundaries and perform proactive barnacle scraping.


* [ ] **Automated Reporting**: A summary report that highlights specific protocol violations (e.g., "Failed to reference ADR," "Cross-silo context contamination").



## How to Verify

* [ ] Run the validator against a control group of models.


* [ ] Confirm that agents failing to follow the `Barnacle Inspection` ritual receive a lower score.


* [ ] Verify that the validator successfully flags instances where an agent skips writing a mandatory ADR.



## Technical Notes

* The validator must be self-contained; use the `Lab-First` principle to ensure the validator itself doesn't introduce side effects.


* The validator should output a `json` report compatible with the registry sync tools.


* Must strictly utilize the project conventions (e.g., `just` commands) for execution.



---

## Done

When the substrate can successfully run through a mock session—Brief, Decision, Lab experiment, and Debrief—without violating the Edinburgh Protocol.

---

### Opinion: Moving to Substrate-Agnostic Integrity

By automating this validation, you shift the burden of quality from *human review* to *systematic enforcement*. A substrate that passes this suite is effectively "pre-cleared" to work on your infrastructure because it has demonstrated the ability to:

* **Respect the "Facade" Principle**: It will not try to bake complex logic into the `justfile`, recognizing it as a delegation layer.


* **Prevent "Process Barnacles"**: It actively cleans up after itself rather than leaving tasks in `in_review` or orphaned branches.


* **Enforce the "Lab-First" Rule**: It proves it will prototype risky changes in a lab script rather than thrashing on production code.



This screening process essentially turns your project into a high-security environment for AI agents. Shall we begin the implementation by defining the `validator.ts` script structure within your `scripts/` directory?