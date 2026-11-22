# D5 transcript submission — instructions for each member

Each member submits **their own** one main OpenCode session + their AI-use log
entry. **E: PARTIAL** (raw + annotations done; pending D acceptance); **A / B / C / D are PENDING** (see `INDEX.md`). **This covers only the E part — D5 is NOT complete until A/B/C/D submit.**

## What each member must provide
1. **`transcripts/<student-id>-<name>.md`** — your **main** OpenCode session,
   exported raw (`opencode export <sessionID>`) and rendered to Markdown. Any
   secondary sessions go in `transcripts/appendix/` (they do **not** replace the
   main session). Do not fabricate; raw session only.
2. **`docs/ai-use-log.yaml`** — your entry for that session (fields per
   `execution_plan` §10.1): `session_id, student, agent/tool/model, time,
   task_requirement_ids, writable_path, generated_files, human_intervention,
   verification_output, cost, session_path (the transcript file), export_sha256`.
   Bind to the final commit(s)/PR(s) you authored.

## Annotation format (§10.1) for human interventions
For each human action (not agent-internal steps), record:
```
HUMAN-INTERVENTION
  time:    <ISO timestamp>
  type:    interrupt | redirect | approve | reject
  reason:  <what the human saw / why they acted>
  affects: <REQ-id / ADR-id / INV-id>
```
Do not invent events; unknown time/subject → mark `unknown`.

## Rules
- One **main** session per member; it must be a real export, not a summary.
- Do not edit other members' files or entries.
- Update your row in `transcripts/INDEX.md` from **PENDING** to **READY** when done.
- **C: no AI-use log entry exists on `main` yet — C must create one.**

## Status
- **E: PARTIAL** — complete raw (`61069361-ZHOU-Jianmin.raw.json`) + complete markdown (`61069361-ZHOU-Jianmin.md`) + annotations (`61069361-ZHOU-Jianmin-annotations.md`) present; marked PARTIAL pending D’s acceptance / final freeze. Session `ses_e095275cbffeefLAOdxMbkW2QF`.
- **A / B / C / D: PENDING.**
