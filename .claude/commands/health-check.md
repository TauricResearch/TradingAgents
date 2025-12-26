---
name: health-check
description: Validate all plugin components are working correctly (agents, hooks, commands)
argument_hint: "[--verbose]"
allowed-tools: [Read, Bash, Grep, Glob]
---

## Implementation

```bash
PYTHONPATH=. python "$(dirname "$0")/../hooks/health_check.py"
```

# Health Check - Plugin Component Validation

Validates all autonomous-dev plugin components to ensure the system is functioning correctly.

## Usage

```bash
/health-check
```

**Time**: < 5 seconds
**Scope**: All plugin components (agents, hooks, commands)

## What This Does

Validates 3 critical component types:

1. **Agents** (8 active agents - Issue #147)
   - Pipeline: researcher-local, planner, test-master, implementer, reviewer, security-auditor, doc-master
   - Utility: issue-creator

2. **Hooks** (12 core automation hooks - Issue #144)
   - auto_format.py, auto_test.py, enforce_file_organization.py
   - enforce_pipeline_complete.py, enforce_tdd.py, security_scan.py
   - unified_pre_tool.py, unified_prompt_validator.py, unified_session_tracker.py
   - validate_claude_alignment.py, validate_command_file_ops.py, validate_project_alignment.py

3. **Commands** (8 active commands)
   - Core: advise, auto-implement, batch-implement, align, setup, sync, health-check, create-issue

4. **Marketplace Version** (optional)
   - Detects version differences between marketplace and project plugin
   - Shows available upgrades/downgrades

## Expected Output

```
Running plugin health check...

============================================================
PLUGIN HEALTH CHECK REPORT
============================================================

Agents: 8/8 loaded
  doc-master .................... PASS
  implementer ................... PASS
  issue-creator ................. PASS
  planner ....................... PASS
  researcher-local .............. PASS
  reviewer ...................... PASS
  security-auditor .............. PASS
  test-master ................... PASS

Hooks: 12/12 executable
  auto_format.py ................ PASS
  auto_test.py .................. PASS
  enforce_file_organization.py .. PASS
  enforce_pipeline_complete.py .. PASS
  enforce_tdd.py ................ PASS
  security_scan.py .............. PASS
  unified_pre_tool.py ........... PASS
  unified_prompt_validator.py ... PASS
  unified_session_tracker.py .... PASS
  validate_claude_alignment.py .. PASS
  validate_command_file_ops.py .. PASS
  validate_project_alignment.py . PASS

Commands: 8/8 present
  /advise ....................... PASS
  /align ........................ PASS
  /auto-implement ............... PASS
  /batch-implement .............. PASS
  /create-issue ................. PASS
  /health-check ................. PASS
  /setup ........................ PASS
  /sync ......................... PASS

Marketplace: N/A | Project: N/A | Status: UNKNOWN

============================================================
OVERALL STATUS: HEALTHY
============================================================

All plugin components are functioning correctly!
```

## Failure Example

```
Running plugin health check...

============================================
PLUGIN HEALTH CHECK REPORT
============================================

Agents: 7/8 loaded
  doc-master .................. PASS
  implementer ................. FAIL (file missing: implementer.md)
  [... other agents ...]

Commands: 7/8 present
  /sync ....................... FAIL (file missing)
  [... other commands ...]

============================================
OVERALL STATUS: DEGRADED (2 issues found)
============================================

Issues detected:
  1. Agent 'implementer' missing
  2. Command '/sync' missing

Action: Run /sync --marketplace to reinstall
```

## When to Use

- After plugin installation (verify setup)
- Before starting a new feature (validate environment)
- After plugin updates (ensure compatibility)
- When debugging plugin issues (identify missing components)
- To check for marketplace updates

## Related Commands

- `/setup` - Interactive setup wizard
- `/align` - Validate PROJECT.md alignment
- `/sync` - Sync plugin files

---

**Validates plugin component integrity with pass/fail status for each component.**
