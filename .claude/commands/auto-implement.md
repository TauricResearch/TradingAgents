---
name: auto-implement
description: Autonomously implement a feature with full SDLC workflow
argument_hint: Feature description (e.g., "user authentication with JWT tokens")
allowed-tools: [Task, Read, Write, Edit, Bash, Grep, Glob, WebSearch, WebFetch]
---

## Implementation

**You (Claude) are the coordinator for this workflow.**

Execute the following steps IN ORDER. Each step is MANDATORY - NO EXCEPTIONS.

---

### STEP 0: Validate PROJECT.md Alignment

**ACTION REQUIRED**: Before any implementation work:

1. Read `.claude/PROJECT.md` from the repository
2. Extract GOALS, SCOPE, and CONSTRAINTS sections
3. Check alignment:
   - Does the feature serve any GOAL?
   - Is the feature explicitly IN SCOPE?
   - Does the feature violate any CONSTRAINT?

**If NOT aligned**, BLOCK immediately and respond:

```
❌ BLOCKED: Feature not aligned with PROJECT.md

Feature requested: [user request]
Why blocked: [specific reason]
  - Not in SCOPE: [what scope says]
  - OR doesn't serve GOALS: [which goals]
  - OR violates CONSTRAINTS: [which constraints]

Options:
1. Modify feature to align with current SCOPE
2. Update PROJECT.md if strategy changed
3. Don't implement
```

**If aligned**, proceed to STEP 1.

---

### STEP 1: Parallel Research (researcher-local + researcher-web Simultaneously)

⚠️ **ACTION REQUIRED NOW**: Invoke TWO research agents in PARALLEL (single response).

**CRITICAL**: You MUST call Task tool TWICE in a single response. This enables parallel execution and reduces research time from 5-6 minutes to 3 minutes (45% faster - Issue #128).

**WRONG** ❌: "I will search codebase, then search web..."
**WRONG** ❌: Invoking researcher-local, waiting for completion, then invoking researcher-web (sequential)

**CORRECT** ✅: Make TWO Task tool calls in ONE response with these EXACT parameters:

#### Task Tool Call 1: researcher-local

Use the Task tool with these parameters:
- **subagent_type**: `"researcher-local"`
- **model**: `"haiku"`
- **description**: `"Search codebase for [feature name]"`
- **prompt**: Search codebase for patterns related to [user's feature]. Find existing patterns, files to update, architecture notes, similar implementations. Output JSON.

#### Task Tool Call 2: Web Research (using general-purpose)

⚠️ **CRITICAL**: Must use `general-purpose` subagent with `model: "sonnet"` for web research. Custom subagent types (like researcher-web) don't reliably get WebSearch tool access - the `tools:` frontmatter is documentation-only, not enforced.

Use the Task tool with these parameters:
- **subagent_type**: `"general-purpose"` ← NOT researcher-web (custom agents don't get WebSearch)
- **model**: `"sonnet"` ← MANDATORY - WebSearch requires Sonnet+
- **description**: `"Research best practices for [feature name]"`
- **prompt**: "You are a web researcher. You MUST use the WebSearch tool to search the web. Search for best practices and standards for: [user's feature description]. Use WebSearch to find: industry best practices (2024-2025), recommended libraries, security considerations (OWASP), common pitfalls. IMPORTANT: Actually call WebSearch - do not answer from memory. Output JSON with best_practices, recommended_libraries, security_considerations, common_pitfalls, and include source URLs."

**DO BOTH NOW IN ONE RESPONSE**. This allows them to run simultaneously.

---

### STEP 1.1: Validate Web Research (MANDATORY)

⚠️ **BEFORE MERGING**: Check the tool use counts from both agents:

| Agent | Expected | If 0 tool uses |
|-------|----------|----------------|
| researcher-local | 10-30 tool uses | Acceptable if codebase is small |
| web research (general-purpose) | **1+ tool uses** | ❌ **FAIL - web search didn't happen** |

**If web research shows 0 tool uses**:
1. **DO NOT PROCEED** - the results are hallucinated, not from actual web search
2. **Report failure**: "❌ Web research failed: 0 WebSearch calls made. Results would be hallucinated."
3. **Retry**: Re-invoke the web research agent with this explicit prompt:
   "You MUST call WebSearch tool at least once. Search for [topic]. Do not answer from memory."

**Only proceed to merge if web research shows 1+ tool uses.**

---

### STEP 1.2: Merge Research Findings

**After VALIDATING both agents completed with actual tool use**, merge findings into unified context for planner.

Combine:
- **Codebase context** (from researcher-local): existing_patterns, files_to_update, architecture_notes, similar_implementations
- **External guidance** (from researcher-web): best_practices, recommended_libraries, security_considerations, common_pitfalls

Create synthesized recommendations by:
1. **Pattern matching**: Check if local patterns align with best practices
2. **Security flagging**: Highlight high-priority security considerations
3. **Conflict detection**: Note where local code conflicts with best practices
4. **Library recommendations**: Match recommended libraries to project needs

This merged context will be passed to the planner step (next).

---

### STEP 1.3: Verify Parallel Research

**After merging research**, verify parallel execution succeeded:

```bash
python plugins/autonomous-dev/scripts/session_tracker.py auto-implement "Parallel exploration completed - processing results"
python plugins/autonomous-dev/scripts/agent_tracker.py status
```

⚠️ **CHECKPOINT 1**: Call `verify_parallel_research()` to validate:

NOTE: This checkpoint uses portable path detection (Issue #85) that works on any machine:
- Walks directory tree upward until `.git` or `.claude` marker found
- Works from any subdirectory in the project (not just from project root)
- Compatible with heredoc execution context (avoids `__file__` variable)
- Same approach as tracking infrastructure (session_tracker, batch_state_manager)

```bash
python3 << 'EOF'
import sys
from pathlib import Path

# Portable project root detection (works from any directory)
current = Path.cwd()
while current != current.parent:
    if (current / ".git").exists() or (current / ".claude").exists():
        project_root = current
        break
    current = current.parent
else:
    raise FileNotFoundError(
        "Could not find project root. Expected .git or .claude directory marker.\n"
        "Make sure you are running this command from within the repository."
    )

# Add project root to sys.path so plugins can be imported
sys.path.insert(0, str(project_root))

# Optional verification - gracefully degrade if AgentTracker unavailable
try:
    from plugins.autonomous_dev.lib.agent_tracker import AgentTracker
    result = AgentTracker.verify_parallel_research()
    success = result.get("parallel", False)

    print(f"\n{'✅ PARALLEL RESEARCH: SUCCESS' if success else '❌ PARALLEL RESEARCH: FAILED'}")
    if not success:
        reason = result.get("reason", "Unknown error")
        found = result.get("found_agents", [])
        print(f"\n⚠️ {reason}")
        print(f"   Found agents: {', '.join(found) if found else 'none'}")
        print("Re-invoke missing agents before continuing to STEP 2.\n")
except ImportError:
    # User project without plugins/ directory - skip verification
    print("\nℹ️  Parallel exploration verification skipped (AgentTracker not available)")
    print("    This is normal for user projects. Verification only runs in autonomous-dev repo.")
    success = True
except AttributeError as e:
    # plugins.autonomous_dev.lib.agent_tracker exists but missing methods
    print(f"\n⚠️  Parallel research verification unavailable: {e}")
    print("    Continuing workflow. Verification is optional.")
    success = True
except Exception as e:
    # Any other error - don't block workflow
    print(f"\n⚠️  Parallel research verification error: {e}")
    print("    Continuing workflow. Verification is optional.")
    success = True
EOF
```

**If checkpoint FAILS** (returns False):
1. Check which agent is missing: `python plugins/autonomous-dev/scripts/agent_tracker.py status`
2. Re-invoke missing agent sequentially
3. Re-run checkpoint verification

**If checkpoint PASSES** (returns True):
- Check session file for parallel execution metrics:
  - `time_saved_seconds`: How much time parallelization saved
  - `efficiency_percent`: Parallelization efficiency (target: ≥50%)
  - `status`: "parallel" or "sequential"
- Proceed to STEP 2 (planner with merged research context)

---

### STEP 2: Invoke Planner Agent (With Merged Research Context)

⚠️ **ACTION REQUIRED**: Invoke planner NOW with merged research findings.

**CRITICAL**: Planner receives BOTH codebase context (from researcher-local) AND external guidance (from researcher-web). This ensures the plan leverages existing patterns while following best practices.

**CORRECT** ✅: Call Task tool with:

```
subagent_type: "planner"
description: "Plan [feature name]"
prompt: "Create detailed implementation plan for: [user's feature description].

**Codebase Context** (from researcher-local):
[Paste existing_patterns, files_to_update, architecture_notes, similar_implementations from researcher-local JSON output]

**External Guidance** (from researcher-web):
[Paste best_practices, recommended_libraries, security_considerations, common_pitfalls from researcher-web JSON output]

Based on this research, create a plan that:
- Follows existing project patterns and conventions
- Aligns with industry best practices
- Addresses security considerations
- Avoids common pitfalls
- Reuses existing code where appropriate

Include:
- File structure (what files to create/modify)
- Dependencies (libraries, services needed)
- Integration points (how it fits with existing code)
- Edge cases to handle
- Security requirements
- Testing strategy

Output: Step-by-step implementation plan with file-by-file breakdown."

model: "sonnet"
```

**DO IT NOW**.

**After planner completes**, VERIFY invocation succeeded:
```bash
python plugins/autonomous-dev/scripts/session_tracker.py auto-implement "Planner completed - plan created"
python plugins/autonomous-dev/scripts/agent_tracker.py status
```

⚠️ **CHECKPOINT 2 - VERIFY RESEARCH + PLANNING**: Verify output shows 3 agents ran (researcher-local, researcher-web, planner).

If count != 3, STOP and invoke missing agents NOW.

---

### STEP 3: Invoke Test-Master Agent (TDD - Tests BEFORE Implementation)

⚠️ **ACTION REQUIRED**: Invoke Task tool NOW with timeout enforcement.

**This is the TDD checkpoint** - Tests MUST be written BEFORE implementation.

**CRITICAL - Issue #90 Fix**: Test-master can run for 5-15 minutes writing comprehensive test suites. **Enforce 20-minute timeout to prevent indefinite freeze** (subprocess pipe deadlock when pytest generates large output). The timeout provides graceful degradation: if test-master exceeds 20 minutes, workflow continues with clear error message rather than freezing indefinitely.

**Timeout Rationale**:
- Typical test-master execution: 5-15 minutes
- Safety buffer: 5 minutes
- Total: 20 minutes (1200 seconds)

**CORRECT** ✅: Call Task tool with:

```
subagent_type: "test-master"
description: "Write tests for [feature name]"
prompt: "Write comprehensive tests for: [user's feature description].

**Codebase Testing Patterns** (from researcher-local):
- Test file patterns: [Paste testing_guidance.test_file_patterns]
- Edge cases to test: [Paste testing_guidance.edge_cases_to_test]
- Mocking patterns: [Paste testing_guidance.mocking_patterns]

**External Testing Guidance** (from researcher-web):
- Testing frameworks: [Paste testing_guidance.testing_frameworks]
- Coverage recommendations: [Paste testing_guidance.coverage_recommendations]
- Testing antipatterns to avoid: [Paste testing_guidance.testing_antipatterns]

**Implementation Plan**: [Paste planner output]

Based on this context, write tests that:
- Follow existing test patterns from codebase
- Apply best practices from external guidance
- Cover edge cases identified by researcher
- Use mocking patterns found in similar tests

Output: Comprehensive test files with unit tests, integration tests, edge case coverage."

model: "sonnet"
timeout: 1200  # 20 minutes - prevents indefinite freeze (Issue #90)
```

**DO IT NOW**.

**After test-master completes**, VERIFY invocation succeeded:
```bash
python plugins/autonomous-dev/scripts/session_tracker.py auto-implement "Test-master completed - tests: [count] tests written"
python plugins/autonomous-dev/scripts/agent_tracker.py status
```

⚠️ **CHECKPOINT 3 - CRITICAL TDD GATE**: Verify output shows 4 agents ran (researcher-local, researcher-web, planner, test-master).

This is the TDD checkpoint - tests MUST exist before implementation.
If count != 4, STOP and invoke missing agents NOW.

---

### STEP 4: Invoke Implementer Agent

⚠️ **ACTION REQUIRED**: Now that tests exist, implement to make them pass.

**CORRECT** ✅: Call Task tool with:

```
subagent_type: "implementer"
description: "Implement [feature name]"
prompt: "Implement production-quality code for: [user's feature description].

**Codebase Implementation Patterns** (from researcher-local):
- Reusable functions: [Paste implementation_guidance.reusable_functions]
- Import patterns: [Paste implementation_guidance.import_patterns]
- Error handling patterns: [Paste implementation_guidance.error_handling_patterns]

**External Implementation Guidance** (from researcher-web):
- Design patterns: [Paste implementation_guidance.design_patterns]
- Performance tips: [Paste implementation_guidance.performance_tips]
- Library integration tips: [Paste implementation_guidance.library_integration_tips]

**Implementation Plan**: [Paste planner output]
**Tests to Pass**: [Paste test-master output summary]

Based on this context, implement code that:
- Reuses existing functions where appropriate
- Follows import and error handling patterns
- Applies design patterns and performance tips
- Makes all tests pass

Output: Production-quality code following the architecture plan."

model: "sonnet"
```

**DO IT NOW**.

**After implementer completes**, VERIFY invocation succeeded:
```bash
python plugins/autonomous-dev/scripts/session_tracker.py auto-implement "Implementer completed - files: [list modified files]"
python plugins/autonomous-dev/scripts/agent_tracker.py status
```

⚠️ **CHECKPOINT 4**: Verify 5 agents ran (researcher-local, researcher-web, planner, test-master, implementer). If not, invoke missing agents before continuing.

---

### STEP 4.1: Parallel Validation (3 Agents Simultaneously)

⚠️ **ACTION REQUIRED**: Invoke THREE validation agents in PARALLEL (single response).

**CRITICAL**: You MUST call Task tool THREE TIMES in a single response. This enables parallel execution and reduces validation time from 5 minutes to 2 minutes.

**DO NOT** invoke agents sequentially. **DO NOT** wait between invocations. Call all three NOW:

#### Validator 1: Reviewer (Quality Gate)

**Call Task tool with**:

```
subagent_type: "reviewer"
description: "Review [feature name]"
prompt: "Review implementation in: [list files].

Check:
- Code quality (readability, maintainability)
- Pattern consistency with codebase
- Test coverage (all cases covered?)
- Error handling (graceful failures?)
- Edge cases (handled properly?)
- Documentation (clear comments?)

Output: APPROVAL or list of issues to fix with specific recommendations."

model: "sonnet"
```

#### Validator 2: Security-Auditor (Security Scan)

**Call Task tool with**:

```
subagent_type: "security-auditor"
description: "Security scan [feature name]"
prompt: "Scan implementation in: [list files].

Check for:
- Hardcoded secrets (API keys, passwords)
- SQL injection vulnerabilities
- XSS vulnerabilities
- Insecure dependencies
- Authentication/authorization issues
- Input validation missing
- OWASP Top 10 compliance

Output: Security PASS/FAIL with any vulnerabilities found (severity, location, fix)."

model: "haiku"
```

#### Validator 3: Doc-Master (Documentation)

**Call Task tool with**:

```
subagent_type: "doc-master"
description: "Update docs for [feature name]"
prompt: "Update documentation for feature: [feature name].

Changed files: [list all modified/created files]

Update:
- README.md (if public API changed)
- API documentation (docstrings, comments)
- CHANGELOG.md (add entry for this feature)
- Inline code comments (explain complex logic)
- Integration examples (if applicable)

Output: All documentation files updated and synchronized."

model: "haiku"
```

**DO ALL THREE NOW IN ONE RESPONSE**.

---

### STEP 4.2: Handle Validation Results

**After all three validators complete**, analyze combined results:

```bash
python plugins/autonomous-dev/scripts/session_tracker.py auto-implement "Parallel validation completed - processing results"
python plugins/autonomous-dev/scripts/agent_tracker.py status
```

#### Check for Critical Issues (Blocking)

**Security-auditor found CRITICAL vulnerabilities?**
- ❌ BLOCK: Must fix before git operations
- Fix vulnerabilities immediately
- Re-run security-auditor to verify fix
- Continue to next check

**Security passed or no critical issues?**
- ✅ Continue to reviewer results

#### Check for Code Quality Issues (Non-Blocking)

**Reviewer requested changes?**
- ⚠️ INFORM USER: "Code review suggested improvements: [list]"
- ASK USER: "Fix now? (yes/no/later)"
  - If "yes": Fix issues, re-run reviewer
  - If "no" or "later": Continue (non-blocking)

**Reviewer approved?**
- ✅ Continue to doc-master results

#### Check Documentation Updates

**Doc-master failed to update docs?**
- ⚠️ LOG WARNING: "Documentation sync incomplete: [reason]"
- Continue (non-blocking - can fix later)

**Doc-master completed successfully?**
- ✅ All validators passed

---

### STEP 4.3: Verify Parallel Validation Checkpoint (NEW - Phase 7)

⚠️ **CHECKPOINT 4.3 - VERIFY PARALLEL EXECUTION METRICS**:

After all three validators (reviewer, security-auditor, doc-master) complete, verify parallel execution succeeded and check efficiency metrics:

NOTE: This checkpoint uses the same portable path detection as CHECKPOINT 1 (Issue #85):
- Walks directory tree upward until `.git` or `.claude` marker found
- Works from any subdirectory in the project (not just from project root)
- Compatible with heredoc execution context (avoids `__file__` variable)
- Consistent with tracking infrastructure and batch processing

```bash
python3 << 'EOF'
import sys
from pathlib import Path

# Portable project root detection (works from any directory)
current = Path.cwd()
while current != current.parent:
    if (current / ".git").exists() or (current / ".claude").exists():
        project_root = current
        break
    current = current.parent
else:
    raise FileNotFoundError(
        "Could not find project root. Expected .git or .claude directory marker.\n"
        "Make sure you are running this command from within the repository."
    )

# Add project root to sys.path so plugins can be imported
sys.path.insert(0, str(project_root))

# Optional verification - gracefully degrade if AgentTracker unavailable
try:
    from plugins.autonomous_dev.lib.agent_tracker import AgentTracker
    tracker = AgentTracker()
    success = tracker.verify_parallel_validation()

    if success:
        # Extract parallel_validation metrics from session
        import json
        if tracker.session_file.exists():
            try:
                data = json.loads(tracker.session_file.read_text())
                metrics = data.get("parallel_validation", {})

                status = metrics.get("status", "unknown")
                time_saved = metrics.get("time_saved_seconds", 0)
                efficiency = metrics.get("efficiency_percent", 0)

                print(f"\n✅ PARALLEL VALIDATION: SUCCESS")
                print(f"   Status: {status}")
                print(f"   Time saved: {time_saved} seconds")
                print(f"   Efficiency: {efficiency}%")

                if status == "parallel":
                    print(f"\n   ✅ All 3 validation agents executed in parallel!")
                    print(f"      Sequential execution would take: {metrics.get('sequential_time_seconds')} seconds")
                    print(f"      Parallel execution took: {metrics.get('parallel_time_seconds')} seconds")
                else:
                    print(f"\n   ⚠️  Agents executed sequentially (not in parallel)")
                    print(f"      Consider optimizing for parallel execution in next iteration")
            except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
                # Malformed JSON or file read error - still show success but skip metrics
                print(f"\n✅ PARALLEL VALIDATION: SUCCESS")
                print(f"   (Metrics display unavailable: {type(e).__name__})")
        else:
            # Session file doesn't exist yet - show success without metrics
            print(f"\n✅ PARALLEL VALIDATION: SUCCESS")
            print(f"   (Metrics not yet available)")
    else:
        print("\n❌ PARALLEL VALIDATION: FAILED")
        print("   One or more validation agents did not complete successfully")
        print("   Check session file for details on which agent(s) failed")
        print("   Re-invoke failed/missing agents and retry checkpoint")
except ImportError:
    # User project without plugins/ directory - skip verification
    print("\nℹ️  Parallel validation verification skipped (AgentTracker not available)")
    print("    This is normal for user projects. Verification only runs in autonomous-dev repo.")
    success = True
except AttributeError as e:
    # plugins.autonomous_dev.lib.agent_tracker exists but missing methods
    print(f"\n⚠️  Parallel validation verification unavailable: {e}")
    print("    Continuing workflow. Verification is optional.")
    success = True
except Exception as e:
    # Any other error - don't block workflow
    print(f"\n⚠️  Parallel validation verification error: {e}")
    print("    Continuing workflow. Verification is optional.")
    success = True
EOF
```

**If checkpoint PASSES** (returns True):
- All 3 validation agents (reviewer, security-auditor, doc-master) executed successfully
- Check efficiency metrics:
  - `status`: "parallel" (good!) or "sequential" (agents didn't overlap)
  - `time_saved_seconds`: Actual time saved by parallelization
  - `efficiency_percent`: Parallelization effectiveness (target: 50%+)
- Proceed to STEP 4.4 (Final Agent Verification)

**If checkpoint FAILS** (returns False):
1. Check which agent failed/is missing: `python plugins/autonomous-dev/scripts/agent_tracker.py status`
2. Re-invoke the failed agent(s) now
3. Re-run checkpoint verification
4. Only proceed to STEP 4.4 once checkpoint passes

---

### STEP 4.4: Final Agent Verification

⚠️ **CHECKPOINT 4.4 - VERIFY ALL 8 AGENTS RAN**:

Expected agents:
1. researcher-local ✅
2. researcher-web ✅
3. planner ✅
4. test-master ✅
5. implementer ✅
6. reviewer ✅
7. security-auditor ✅
8. doc-master ✅

**Verify all 8 agents completed**:
```bash
python plugins/autonomous-dev/scripts/agent_tracker.py status
```

**If count != 8, YOU HAVE FAILED THE WORKFLOW.**

Identify which agents are missing and invoke them NOW before proceeding.

**If count == 8**: Proceed to STEP 4.5 (Regression Gate).

---

### STEP 4.5: Regression Smoke Test Gate

⚠️ **CHECKPOINT 4.5 - VERIFY NO REGRESSIONS**:

Before committing, run smoke tests to ensure the implementation didn't break existing functionality.

```bash
python3 -m pytest tests/regression/smoke/ -q --tb=line -o "addopts="
```

**Expected**: All smoke tests pass (10/10 or similar).

**If tests FAIL**:
1. Review failure output to identify broken functionality
2. Fix the regression (may need to invoke implementer again)
3. Re-run smoke tests until passing
4. Then proceed to Step 5

**If tests PASS**: Proceed to STEP 5 (Report Completion).

**Note**: This is a fast gate (~10-30 seconds). Full regression suite runs in CI/CD on push.

---

### STEP 5: Report Completion

**AFTER** all 8 agents complete successfully, offer to commit and push changes.

**IMPORTANT**: This step is OPTIONAL and consent-based. If user declines or prerequisites fail, feature is still successful (graceful degradation).

#### Check Prerequisites

Before offering git automation, verify:

```python
from git_operations import validate_git_repo, check_git_config

# Check git is available
is_valid, error = validate_git_repo()
if not is_valid:
    # Log warning but continue
    print(f"⚠️  Git automation unavailable: {error}")
    print("✅ Feature complete! Commit manually when ready.")
    # SKIP to Step 9

# Check git config
is_configured, error = check_git_config()
if not is_configured:
    # Log warning but continue
    print(f"⚠️  Git config incomplete: {error}")
    print("Set with: git config --global user.name 'Your Name'")
    print("         git config --global user.email 'your@email.com'")
    print("✅ Feature complete! Commit manually when ready.")
    # SKIP to Step 9
```

#### Check User Consent (Environment-based Bypass)

**NEW (Issue #96)**: Before showing interactive prompt, check if consent is pre-configured via environment variables. This enables batch processing workflows to proceed without blocking on prompts.

```python
from auto_implement_git_integration import check_consent_via_env

# Check consent via environment variables (defaults to True for opt-out model)
consent = check_consent_via_env()

# If AUTO_GIT_ENABLED explicitly set to false, skip git operations
if not consent['enabled']:
    print("ℹ️  Git automation disabled (AUTO_GIT_ENABLED=false)")
    print("✅ Feature complete! Commit manually when ready:")
    print("  git add .")
    print("  git commit -m 'feat: [feature name]'")
    print("  git push")
    # SKIP to Step 9

# If AUTO_GIT_ENABLED is true (explicit or default), bypass interactive prompt
if consent['enabled']:
    # Auto-proceed with git operations (no prompt needed)
    # Set user_response based on consent['push'] flag
    user_response = "yes" if consent['push'] else "commit-only"
    print(f"🔄 Auto-proceeding with git operations (AUTO_GIT_ENABLED=true)")
    # Jump to "Execute Based on User Response" section below
```

**Behavior**:
- `AUTO_GIT_ENABLED=false`: Skip git operations entirely, no prompt
- `AUTO_GIT_ENABLED=true`: Auto-proceed with git operations (use consent['push'] for push decision)
- Not set: Uses default (True) - auto-proceed with git operations

**Backward Compatibility**: If you need interactive prompt despite environment settings, the user can explicitly set `AUTO_GIT_ENABLED=false` to skip or leave it unset to use defaults.

#### Offer Commit and Push (Interactive Prompt - Legacy)

**NOTE**: This section is now bypassed when AUTO_GIT_ENABLED is set. Kept for backward compatibility and manual override scenarios.

If prerequisites passed and consent not pre-configured, ask user for consent:

```
✅ Feature implementation complete!

Would you like me to commit and push these changes?

📝 Commit message: "feat: [feature name]

Implemented by /auto-implement pipeline:
- [1-line summary of what changed]
- Tests: [count] tests added/updated
- Security: Passed audit
- Docs: Updated [list]"

🔄 Actions:
1. Stage all changes (git add .)
2. Commit with message above
3. Push to remote (branch: [current_branch])

Reply 'yes' to commit and push, 'commit-only' to commit without push, or 'no' to skip git operations.
```

#### Execute Based on User Response

**If user says "yes" or "y"**:
```python
from git_operations import auto_commit_and_push

result = auto_commit_and_push(
    commit_message=commit_msg,
    branch=current_branch,
    push=True
)

if result['success'] and result['pushed']:
    print(f"✅ Committed ({result['commit_sha']}) and pushed to {current_branch}")
elif result['success']:
    print(f"✅ Committed ({result['commit_sha']})")
    print(f"⚠️  Push failed: {result['error']}")
    print("Push manually with: git push")
else:
    print(f"❌ Commit failed: {result['error']}")
    print("Commit manually when ready")
```

**If user says "commit-only" or "commit"**:
```python
from git_operations import auto_commit_and_push

result = auto_commit_and_push(
    commit_message=commit_msg,
    branch=current_branch,
    push=False  # Don't push
)

if result['success']:
    print(f"✅ Committed ({result['commit_sha']})")
    print("Push manually with: git push")
else:
    print(f"❌ Commit failed: {result['error']}")
    print("Commit manually when ready")
```

**If user says "no" or "n"**:
```
✅ Feature complete! Changes ready to commit.

Commit manually when ready:
  git add .
  git commit -m "feat: [feature name]"
  git push
```

#### Error Handling (Graceful Degradation)

Handle common errors gracefully:

**Merge conflict detected**:
```
❌ Cannot commit: Merge conflict detected in: [files]

Resolve conflicts first:
1. Edit conflicted files
2. Run: git add .
3. Run: git commit

Feature implementation is complete - just needs manual conflict resolution.
```

**Detached HEAD state**:
```
❌ Cannot commit: Repository is in detached HEAD state

Create a branch first:
  git checkout -b [branch-name]

Feature implementation is complete - just needs to be on a branch.
```

**Network timeout during push**:
```
✅ Committed successfully: [sha]
❌ Push failed: Network timeout

Try pushing manually:
  git push

Feature is committed locally - just needs to reach remote.
```

**Protected branch**:
```
✅ Committed successfully: [sha]
❌ Push failed: Branch '[branch]' is protected

Create a feature branch and push there:
  git checkout -b feature/[name]
  git cherry-pick [sha]
  git push -u origin feature/[name]

Or push manually if you have override permissions.
```

#### Philosophy: Always Succeed

Git operations are a **convenience, not a requirement**.

- Feature implemented? ✅ SUCCESS
- Tests passing? ✅ SUCCESS
- Security audited? ✅ SUCCESS
- Docs updated? ✅ SUCCESS

**Commit fails?** Still SUCCESS - user commits manually.
**Push fails?** Still SUCCESS - commit worked, push manually.
**Git not available?** Still SUCCESS - feature is done.

This is **graceful degradation** - automate where possible, but never block success on automation.

---

### STEP 5.1: Auto-Close GitHub Issue (If Applicable)

**AFTER** git push succeeds (if enabled), attempt to automatically close the GitHub issue.

**IMPORTANT**: This step is OPTIONAL and consent-based. If user declines, issue number not found, or gh CLI unavailable, feature is still successful (graceful degradation).

#### Issue Number Extraction

The hook automatically extracts issue numbers from the feature request using these patterns:

- `"issue #8"` → extracts 8
- `"#8"` → extracts 8
- `"Issue 8"` → extracts 8
- Case-insensitive
- Uses first occurrence if multiple mentions

Examples:
```
/auto-implement implement issue #8
/auto-implement Add feature for #42
/auto-implement Issue 91 implementation
```

If no issue number is found, this step is skipped gracefully.

#### Consent Prompt

If an issue number is detected, the user is prompted for consent:

```
Close issue #8 (Add GitHub issue auto-close capability)? [yes/no]:
```

**User says "yes" or "y"**: Proceed with issue closing
**User says "no" or "n"**: Skip issue closing (feature still successful)
**User presses Ctrl+C**: Cancel entire workflow (KeyboardInterrupt propagates)

#### Issue State Validation

Before closing, validates via `gh` CLI:
- Issue exists
- Issue is currently open (not already closed)
- User has permission to close issue

If already closed: Skip gracefully (idempotent - already closed is success)
If doesn't exist: Skip with warning (feature still successful)
If network error: Skip with warning (feature still successful)

#### Close Summary Generation

Generates markdown summary with workflow metadata:

```markdown
## Issue #8 Completed via /auto-implement
### Workflow Status
All 8 agents passed:
- researcher-local
- researcher-web
- planner
- test-master
- implementer
- reviewer
- security-auditor
- doc-master
### Pull Request
- https://github.com/user/repo/pull/42
### Commit
- abc123def456
### Files Changed
15 files changed:
- file1.py
- file2.py
... 13 more
---
Generated by autonomous-dev /auto-implement workflow
```

#### Close Issue via gh CLI

Uses `gh issue close` command with security protections:
- **CWE-20**: Validates issue number is positive integer (1-999999)
- **CWE-78**: Uses subprocess list args (never `shell=True`)
- **CWE-117**: Sanitizes newlines and control chars from file names
- Audit logs all gh CLI operations

If successful:
```
✅ Issue #8 closed automatically
```

If failed (gh CLI error, network timeout, etc.):
```
⚠️  Could not auto-close issue #8: [error message]
Feature complete - close issue manually if needed:
  gh issue close 8 --comment "Completed via /auto-implement"
```

#### Edge Cases and Troubleshooting

**gh CLI not installed**:
```
⚠️  gh CLI not found - cannot auto-close issue
Feature complete - install gh CLI or close issue manually:
  brew install gh  # macOS
  apt install gh   # Ubuntu
```

**Not authenticated with GitHub**:
```
⚠️  GitHub authentication required
Feature complete - authenticate and close issue manually:
  gh auth login
  gh issue close 8
```

**Issue already closed**:
```
✅ Issue #8 already closed (idempotent success)
```

**Permission denied**:
```
⚠️  Permission denied - cannot close issue #8
Feature complete - ask repository admin to close issue
```

**Network timeout**:
```
⚠️  Network timeout - cannot verify issue state
Feature complete - close issue manually when network available:
  gh issue close 8
```

#### Philosophy: Non-Blocking Enhancement

Issue auto-close is a **convenience, not a requirement**.

- Feature implemented? ✅ SUCCESS
- Tests passing? ✅ SUCCESS
- Git pushed? ✅ SUCCESS
- Issue closed? ✅ **BONUS** (nice to have)

**Issue close fails?** Still SUCCESS - close manually.
**gh CLI unavailable?** Still SUCCESS - feature is done.
**User declines?** Still SUCCESS - their choice.

This is **graceful degradation** - enhance workflow where possible, but never block success.

---

**ONLY AFTER** confirming all 8 agents ran (checkpoint 4.4 passed), tell the user:

```
✅ Feature complete! All 8 agents executed successfully.

📊 Pipeline Summary:
1. researcher-local: [1-line summary]
2. researcher-web: [1-line summary]
3. planner: [1-line summary]
4. test-master: [1-line summary]
5. implementer: [1-line summary]
6. reviewer: [1-line summary]
7. security-auditor: [1-line summary]
8. doc-master: [1-line summary]

📁 Files changed: [count] files
🧪 Tests: [count] tests created/updated
🔒 Security: [PASS/FAIL with findings if any]
📖 Documentation: [list docs updated]

🎯 Next steps:
1. Review agent outputs in docs/sessions/ if needed
2. Run `/clear` before starting next feature (recommended for performance)

Feature is ready to commit!
```

---

## Mandatory Full Pipeline Policy

⚠️ **ALL features MUST go through all 8 agents. NO EXCEPTIONS.**

**Why**:
- Simulation proved even "simple" features need full pipeline
- test-master: Created 47 tests (0% → 95% coverage)
- security-auditor: Found CRITICAL vulnerability (CVSS 7.1)
- doc-master: Updated 5 files, not just 1
- Split research: Ensures both local patterns AND best practices are considered

**Examples from real simulation**:
- "Simple command file" → security-auditor found path traversal attack
- "Trivial doc update" → doc-master found 5 files needing consistency updates
- "Quick fix" → reviewer caught pattern violations
- "Standard feature" → researcher-local found reusable pattern, researcher-web found security pitfall

**Result**: Full pipeline prevents shipping bugs, vulnerabilities, and incomplete features.

**Exception**: If you believe a feature genuinely needs < 8 agents, ASK USER FIRST:

"This seems like a simple change. Should I run:
1. Full 8-agent pipeline (recommended - guaranteed quality)
2. Subset: [which agents you think are needed]

Default is FULL PIPELINE if you don't specify."

Let user decide. But recommend full pipeline.

---

## Context Management

- **After feature completes**: Prompt user to run `/clear` before next feature
- **Log efficiently**: Record file paths, not full content
- **If approaching token limit**: Save state and ask user to continue in new session

---

## What This Command Does (User-Facing Documentation)

**For users**: This command provides autonomous feature implementation with full SDLC workflow:

1. **Validates alignment** - Checks PROJECT.md to ensure feature fits project goals
2. **Invokes 8 specialist agents** - Each handles one part of SDLC:
   - researcher-local: Searches codebase for existing patterns
   - researcher-web: Researches industry best practices
   - planner: Designs implementation approach (with merged research context)
   - test-master: Writes tests FIRST (TDD)
   - implementer: Makes tests pass
   - reviewer: Quality gate
   - security-auditor: Finds vulnerabilities
   - doc-master: Updates documentation
3. **Verifies completeness** - Ensures all 8 agents ran before declaring done
4. **Ready to commit** - All quality gates passed

**Time**: 20-40 minutes for professional-quality feature

**Output**:
- Implementation code
- Comprehensive tests
- Security audit report
- Updated documentation
- Pipeline log showing all agents ran

**Workflow**:
```bash
/auto-implement "add user authentication"
# ... 8 agents execute ...
# ✅ Feature complete!

/clear            # Reset context for next feature
```

---

## Batch Mode Behavior (For /batch-implement)

When invoked from `/batch-implement`, this command runs in **batch mode** which modifies error handling to be non-blocking.

### Detecting Batch Mode

Check if batch processing is active:

```python
import os
from pathlib import Path

def is_batch_mode():
    """Check if running inside /batch-implement workflow."""
    # Check 1: Batch state file exists and is in_progress
    batch_state = Path(".claude/batch_state.json")
    if batch_state.exists():
        import json
        try:
            state = json.loads(batch_state.read_text())
            if state.get("status") == "in_progress":
                return True
        except:
            pass

    # Check 2: Environment variable
    if os.environ.get("BATCH_MODE") == "true":
        return True

    return False
```

### Batch Mode Modifications

| Checkpoint | Interactive Mode | Batch Mode |
|------------|------------------|------------|
| **STEP 0: Alignment** | BLOCK and ask user | WARN and continue (log to batch state) |
| **STEP 1.1: Web research fail** | STOP and wait | Retry once, then continue without web research |
| **STEP 4.2: Reviewer issues** | ASK "Fix now?" | Auto-skip (defer to next iteration) |
| **STEP 4.4: Agent count < 8** | STOP | Record missing agents, continue |
| **STEP 4.5: Regression fail** | STOP | Record failure, mark feature as failed, continue to next |
| **Git operations** | Prompt for consent | Use environment defaults (AUTO_GIT_*) |
| **Issue close** | Prompt for consent | Auto-close if issue number found |

### Non-Blocking Error Handling

In batch mode, errors are **recorded but not blocking**:

```python
def handle_batch_error(step: str, error: str, severity: str = "warning"):
    """Record error in batch state instead of blocking."""
    if not is_batch_mode():
        # Interactive mode: raise/stop as usual
        raise Exception(f"{step}: {error}")

    # Batch mode: record and continue
    import json
    from pathlib import Path
    from datetime import datetime

    batch_state_path = Path(".claude/batch_state.json")
    if batch_state_path.exists():
        state = json.loads(batch_state_path.read_text())

        # Add error to current feature's record
        current_idx = state.get("current_index", 0)
        if "feature_errors" not in state:
            state["feature_errors"] = {}
        if str(current_idx) not in state["feature_errors"]:
            state["feature_errors"][str(current_idx)] = []

        state["feature_errors"][str(current_idx)].append({
            "step": step,
            "error": error,
            "severity": severity,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        })

        batch_state_path.write_text(json.dumps(state, indent=2))

    # Log warning but continue
    print(f"⚠️  [{step}] {error} (continuing in batch mode)")
```

### Retry Logic for Transient Failures

Batch mode automatically retries transient failures:

```python
def batch_retry_step(step_func, step_name: str, max_retries: int = 2):
    """Retry step with exponential backoff in batch mode."""
    import time

    for attempt in range(max_retries + 1):
        try:
            return step_func()
        except Exception as e:
            error_str = str(e).lower()

            # Transient errors: retry
            transient_patterns = ["timeout", "connection", "rate limit", "503", "502"]
            is_transient = any(p in error_str for p in transient_patterns)

            if is_transient and attempt < max_retries:
                wait_time = 2 ** attempt  # 1, 2, 4 seconds
                print(f"⚠️  [{step_name}] Transient error, retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue

            # Permanent error or max retries: handle
            if is_batch_mode():
                handle_batch_error(step_name, str(e), "error")
                return None  # Continue to next step
            else:
                raise
```

### Modified Checkpoints for Batch Mode

#### STEP 0: Alignment (Batch Mode)

```python
if not is_aligned:
    if is_batch_mode():
        # Don't block - record warning and proceed
        handle_batch_error("STEP 0: Alignment",
            f"Feature may not align with PROJECT.md: {reason}",
            severity="warning")
        print("⚠️  Proceeding despite alignment warning (batch mode)")
        # Continue to STEP 1
    else:
        # Interactive mode: block as usual
        print("❌ BLOCKED: Feature not aligned with PROJECT.md")
        return
```

#### STEP 1.1: Web Research (Batch Mode)

```python
if web_research_tool_uses == 0:
    if is_batch_mode():
        # Retry once
        print("⚠️  Web research failed, retrying...")
        retry_result = invoke_web_research()

        if retry_result.tool_uses == 0:
            # Still failed - continue without web research
            handle_batch_error("STEP 1.1: Web Research",
                "Web research unavailable, using local research only",
                severity="warning")
            # Continue to STEP 1.2 with local-only context
        else:
            # Retry succeeded
            web_research_results = retry_result
    else:
        # Interactive mode: stop as usual
        print("❌ Web research failed: 0 WebSearch calls made")
        return
```

#### STEP 4.2: Reviewer Issues (Batch Mode)

```python
if reviewer_requested_changes:
    if is_batch_mode():
        # Auto-defer changes (don't block batch)
        handle_batch_error("STEP 4.2: Review",
            f"Reviewer suggested improvements: {issues}. Deferred.",
            severity="info")
        print("ℹ️  Reviewer issues deferred (batch mode)")
        # Continue to next step
    else:
        # Interactive mode: ask user
        response = ask_user("Fix now? (yes/no/later)")
        # ... handle response
```

#### STEP 4.5: Regression Test (Batch Mode)

```python
if regression_tests_failed:
    if is_batch_mode():
        # Mark feature as failed, continue to next feature
        handle_batch_error("STEP 4.5: Regression",
            f"Regression tests failed: {test_output}",
            severity="error")
        # Update batch state to mark this feature as failed
        mark_feature_failed(current_index, "Regression tests failed")
        print("❌ Feature marked as failed (regression). Continuing to next feature.")
        return  # Exit this feature, batch will continue
    else:
        # Interactive mode: stop and fix
        print("❌ Regression tests failed. Fix before continuing.")
        return
```

### Summary: Batch Mode Guarantees

1. **Never blocks on prompts** - Uses environment defaults or auto-skips
2. **Never stops batch on soft errors** - Records and continues
3. **Retries transient failures** - Network issues, timeouts, rate limits
4. **Marks failures properly** - Failed features recorded in batch_state.json
5. **Full audit trail** - All errors logged with timestamps
6. **Feature isolation** - One failed feature doesn't stop others

This enables `/batch-implement` to run 50+ features unattended overnight.

---

## Troubleshooting

**If fewer than 8 agents ran**:
```bash
# Check the summary table above for which agents completed
# Solution: Re-run /auto-implement
# Claude will invoke missing agents
```

**If agent fails**:
- Claude will report the failure
- Review error in docs/sessions/
- Fix the issue
- Re-run /auto-implement (idempotent)

**If alignment blocked**:
- Either modify feature to fit PROJECT.md scope
- Or update PROJECT.md if strategy changed
- Then re-run /auto-implement

---

## Related Commands

- `/health-check` - Verify plugin integrity
- `/clear` - Reset context (run after each feature)

---

**Philosophy**: This command embodies "not a toolkit, a team" - You describe what you want, Claude coordinates 8 specialists to build it professionally.
