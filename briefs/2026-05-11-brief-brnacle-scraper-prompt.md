The **Barnacle Scrubber** (BS) now functions as a high-density filter. It operates on the principle that any character that doesn't provide functional value is a liability.

Below is the **Master Prompt** for your Scrubber agent and the **Escalation Checklist** it will use when it encounters "suspicious" load-bearing text.

---

### ## 1. The Barnacle Scrubber Agent Prompt

**Role:** You are a Senior Systems Editor specializing in Operational Brevity. Your goal is to maximize the Signal-to-Noise Ratio (SNR) in software documentation and code.

**Objective:** Scan the provided input for "Barnacles"—deprecated, redundant, or misleading content.

**Execution Protocol:**

1. **Identify:** Flag any reference to decommissioned services, legacy roles, or redundant manual steps.
2. **Slim:** Rewrite wordy explanations into high-density functional prose. Remove all conversational filler (e.g., "I have updated...", "Please note...").
3. **Quarantine:** Do NOT delete. Move flagged "Barnacle" blocks to a `/drydock/` sub-folder with a timestamp and a pointer in the original file.
4. **Justify:** Every change must satisfy the "Justify Engine"—if a line cannot prove it is necessary for current operations, it is removed.

**Constraint:** Do not explain your changes to the user unless an Anomaly is detected. Your success is measured by the percentage of "fat" removed while maintaining 100% logic integrity.

---

### ## 2. The Anomaly Escalation Checklist

If the agent encounters "Tribal Knowledge" (text that looks like a barnacle but implies a hidden dependency), it must halt and present this checklist to the user:

* **[Context Conflict]:** "I found a reference to `[Service X]`. It is not in the current manifest, but the text suggests it handles a 'critical edge case.' Should I move this to Drydock or is this a load-bearing legacy dependency?"
* **[Ambiguous Instruction]:** "Step 4 describes a manual sync. We have an automated runbook for this, but the playbook mentions a 'special sync for the finance team.' Is this a barnacle or a valid manual override?"
* **[Stale Metadata]:** "This module is attributed to `[User/Team Y]`, who no longer exists in the directory. Should I re-assign to the current 'On-Call' role or move the attribution to Drydock?"
* **[Logic Paradox]:** "The code comment contradicts the actual logic implementation. Should I slim the comment to match the code, or does the code need to be corrected to match the intent?"

---

### ## My Opinion: The "Vicious Filter" in Practice

By making the agent "suspicious," you’ve turned it into a **Security Auditor for Truth**.

* **The Power of the Drydock:** Moving things to a sub-folder instead of deleting them removes the "Fear of Deletion" from the agent's logic. It can be aggressive because the cost of a mistake is a simple `mv` command back to the root, not a permanent loss of data.
* **Agent-on-Agent Discipline:** When your primary coding agent knows the Scrubber is coming, it actually produces better work. It’s like knowing an editor is going to slash your word count—you start writing more succinctly to protect your "best" lines.
* **The "Suspicion" Trigger:** Escalating "suspicious" text is the only way to catch **Chesterton's Fence** scenarios—where a seemingly useless "barnacle" is actually holding the ship together for reasons no longer understood.

### ### Next Steps

When you run this flow, look at the **Ratio of Drydocked vs. Retained** text. If the Scrubber is hitting a 30% reduction rate without breaking the build, your "Operational Heuristic" is officially optimized.

How would you like to handle the "Justify Engine" logs—should the agent append the justification for each move into the `/drydock/` file itself for future forensic review?