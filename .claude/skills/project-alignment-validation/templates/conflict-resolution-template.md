# Conflict Resolution Template

Use this template to document and resolve alignment conflicts between PROJECT.md sections or between PROJECT.md and implementation.

---

## Conflict Identification

**Conflict ID**: [Unique identifier, e.g., CONFLICT-2025-001]

**Conflict Name**: [Short descriptive name]

**Detected Date**: [YYYY-MM-DD]

**Detected By**: [Name/Team/Tool]

**Status**: [Identified / Analyzing / Resolving / Resolved / Escalated]

---

## Conflict Type

**Primary Type**: [Goal / Scope / Constraint / Architecture / Documentation]

**Conflict Category**: [Check all that apply]
- [ ] Goal vs Goal (competing goals)
- [ ] Goal vs Constraint (goal requires violating constraint)
- [ ] Scope vs Constraint (scope exceeds constraints)
- [ ] Architecture vs Goal (architecture doesn't support goal)
- [ ] PROJECT.md vs Implementation (documentation drift)
- [ ] Other: [Specify]

---

## Conflict Description

### Summary
[Brief description of the conflict in 1-2 sentences]

### Detailed Description
[Comprehensive explanation of the conflict]

**Side A** (e.g., PROJECT.md / Goal 1 / Feature):
[What one side says or requires]

**Side B** (e.g., Implementation / Goal 2 / Constraint):
[What the other side says or requires]

**Why They Conflict**:
[Explanation of the incompatibility]

---

## Affected Sections

### PROJECT.md Sections
**Section 1**: [GOALS / SCOPE / CONSTRAINTS / ARCHITECTURE]
- Subsection: [Name]
- Quote: "[Exact quote]"
- Location: [Line/section reference]

**Section 2**: [GOALS / SCOPE / CONSTRAINTS / ARCHITECTURE]
- Subsection: [Name]
- Quote: "[Exact quote]"
- Location: [Line/section reference]

### Code Components (if applicable)
**Component 1**: [Name]
- Location: [Path/file]
- Current behavior: [Description]

**Component 2**: [Name]
- Location: [Path/file]
- Current behavior: [Description]

---

## Root Cause Analysis

### Primary Root Cause
[Main reason conflict exists]

### Contributing Factors
1. **[Factor 1]**: [Description]
2. **[Factor 2]**: [Description]
3. **[Factor 3]**: [Description]

### Timeline of Conflict
- **[Date]**: [Event that established Side A]
- **[Date]**: [Event that established Side B]
- **[Date]**: [Conflict first became apparent]
- **[Date]**: [Conflict formally identified]

### Intentional or Accidental?
[Was this conflict known and accepted, or did it emerge unexpectedly?]

---

## Impact Assessment

### Impact Level
**Overall Impact**: [Critical / High / Medium / Low]

### Stakeholders Affected
**Stakeholder 1**: [Name/Role]
- How affected: [Description]
- Priority: [High / Medium / Low]

**Stakeholder 2**: [Name/Role]
- How affected: [Description]
- Priority: [High / Medium / Low]

### Project Impact
**Goals**: [Which goals are affected and how]

**Timeline**: [How conflict affects schedule]

**Resources**: [How conflict affects budget/team]

**Quality**: [How conflict affects quality metrics]

### User Impact
**User Experience**: [How users are affected]

**Severity**: [How bad is user impact]

**Frequency**: [How often do users encounter this]

---

## Resolution Options

### Option 1: [Name - e.g., "Update PROJECT.md"]

#### Approach
[Detailed description of this resolution approach]

**What Changes**:
- PROJECT.md: [Specific changes]
- Code: [Specific changes]
- Other: [Any other changes]

#### Pros
1. [Pro 1]
2. [Pro 2]
3. [Pro 3]

#### Cons
1. [Con 1]
2. [Con 2]
3. [Con 3]

#### Trade-offs
**Gains**:
- [What we gain]

**Losses**:
- [What we lose]

**Net Effect**: [Overall assessment]

#### Effort Required
**Time**: [Duration]

**Resources**:
- Team: [Who's needed]
- Budget: [Cost if any]

**Complexity**: [Low / Medium / High]

#### Risk Assessment
**Risks**:
1. [Risk 1] - Probability: [H/M/L] - Impact: [H/M/L]
2. [Risk 2] - Probability: [H/M/L] - Impact: [H/M/L]

**Risk Mitigation**:
1. [Mitigation for risk 1]
2. [Mitigation for risk 2]

#### Impact on Goals
**Goal Alignment**:
- [Goal 1]: [Positive / Neutral / Negative]
- [Goal 2]: [Positive / Neutral / Negative]

**Overall Goal Impact**: [Assessment]

---

### Option 2: [Name - e.g., "Modify Implementation"]
[Repeat Option 1 template]

---

### Option 3: [Name - e.g., "Negotiate Compromise"]
[Repeat Option 1 template]

---

### Option 4: [Name - e.g., "Escalate Decision"]
[Repeat Option 1 template]

---

## Option Comparison

### Comparison Matrix
| Criterion        | Option 1 | Option 2 | Option 3 | Option 4 |
|------------------|----------|----------|----------|----------|
| Effort           | [Score]  | [Score]  | [Score]  | [Score]  |
| Risk             | [Score]  | [Score]  | [Score]  | [Score]  |
| Goal Alignment   | [Score]  | [Score]  | [Score]  | [Score]  |
| Timeline Impact  | [Score]  | [Score]  | [Score]  | [Score]  |
| User Impact      | [Score]  | [Score]  | [Score]  | [Score]  |
| **Total Score**  | [Sum]    | [Sum]    | [Sum]    | [Sum]    |

### Scoring
- 3 = Best
- 2 = Acceptable
- 1 = Poor
- 0 = Unacceptable

---

## Recommended Resolution

### Selected Option
**Option [Number]**: [Name]

### Rationale
[Detailed explanation of why this option is recommended]

**Key Factors**:
1. [Factor 1 and why it matters]
2. [Factor 2 and why it matters]
3. [Factor 3 and why it matters]

**Why Not Other Options**:
- Option [X]: [Reason for rejection]
- Option [Y]: [Reason for rejection]

### Stakeholder Alignment
**Stakeholders Consulted**:
- [Stakeholder 1]: [Opinion / Preference]
- [Stakeholder 2]: [Opinion / Preference]

**Consensus Level**: [Full / Partial / None]

---

## Implementation Plan

### Resolution Strategy
**Strategy Type**: [Update PROJECT.md / Modify Implementation / Compromise / Escalate]

### Action Items
**Task 1**: [Description]
- Owner: [Name]
- Due Date: [YYYY-MM-DD]
- Dependencies: [List]
- Success Criteria: [How to know it's done]

**Task 2**: [Description]
- Owner: [Name]
- Due Date: [YYYY-MM-DD]
- Dependencies: [List]
- Success Criteria: [How to know it's done]

**Task 3**: [Description]
- Owner: [Name]
- Due Date: [YYYY-MM-DD]
- Dependencies: [List]
- Success Criteria: [How to know it's done]

### PROJECT.md Updates
**Changes Required**: [Yes / No]

**If Yes**:
- **Section**: [Name]
- **Current Text**: [Quote]
- **Proposed Text**: [New text]
- **Rationale**: [Why change is needed]

### Code Changes
**Changes Required**: [Yes / No]

**If Yes**:
- **Component**: [Name]
- **Current Behavior**: [Description]
- **New Behavior**: [Description]
- **Migration Plan**: [How to transition]

### Testing Requirements
**Tests to Run**:
1. [Test 1]: [What it validates]
2. [Test 2]: [What it validates]
3. [Test 3]: [What it validates]

**Acceptance Criteria**:
[How to know resolution is successful]

---

## Communication Plan

### Stakeholder Communication

**Who to Inform**:
1. [Stakeholder] - [Why they need to know]
2. [Stakeholder] - [Why they need to know]
3. [Stakeholder] - [Why they need to know]

**Communication Timeline**:
- **Pre-Implementation**: [What to communicate and when]
- **During Implementation**: [Update frequency]
- **Post-Implementation**: [What to communicate and when]

### Message
**Key Points**:
1. [Point 1 - What the conflict was]
2. [Point 2 - How we're resolving it]
3. [Point 3 - What changes for stakeholders]

**FAQ**:
- **Q**: [Common question]
- **A**: [Answer]

---

## Timeline

### Milestones
- **Decision Date**: [YYYY-MM-DD] - [Resolution option selected]
- **Start Date**: [YYYY-MM-DD] - [Implementation begins]
- **Milestone 1**: [YYYY-MM-DD] - [Description]
- **Milestone 2**: [YYYY-MM-DD] - [Description]
- **Completion Date**: [YYYY-MM-DD] - [Resolution complete]
- **Validation Date**: [YYYY-MM-DD] - [Verify resolution successful]

### Review Schedule
- **Daily**: [Status check-in format]
- **Weekly**: [Progress review format]
- **Monthly**: [Strategic review format]

---

## Risk Management

### Implementation Risks
**Risk 1**: [Description]
- Probability: [High / Medium / Low]
- Impact: [High / Medium / Low]
- Mitigation: [Strategy]
- Owner: [Who monitors]
- Contingency: [Backup plan]

**Risk 2**: [Description]
- Probability: [High / Medium / Low]
- Impact: [High / Medium / Low]
- Mitigation: [Strategy]
- Owner: [Who monitors]
- Contingency: [Backup plan]

### Monitoring Plan
**Risk Indicators**:
- [Indicator 1]: [Threshold that triggers concern]
- [Indicator 2]: [Threshold that triggers concern]

**Review Frequency**: [How often to check indicators]

**Escalation Criteria**: [When to escalate to stakeholders]

---

## Success Criteria

### Definition of Done
- [ ] Conflict no longer exists
- [ ] PROJECT.md updated (if applicable)
- [ ] Code updated (if applicable)
- [ ] Tests pass
- [ ] Documentation updated
- [ ] Stakeholders informed
- [ ] No new conflicts introduced
- [ ] Resolution rationale documented

### Validation Tests
**Test 1**: [Description]
- Expected Result: [What should happen]
- Actual Result: [To be filled after testing]
- Status: [Pass / Fail]

**Test 2**: [Description]
- Expected Result: [What should happen]
- Actual Result: [To be filled after testing]
- Status: [Pass / Fail]

### Metrics
**Before Resolution**:
- [Metric 1]: [Value]
- [Metric 2]: [Value]

**After Resolution** (Target):
- [Metric 1]: [Target value]
- [Metric 2]: [Target value]

**Acceptance Threshold**:
[When metrics indicate successful resolution]

---

## Progress Tracking

### Status Updates
**[Date]**: [Update]
- Status: [Current phase]
- Progress: [What was accomplished]
- Blockers: [Any impediments]
- Next Steps: [What's next]

**[Date]**: [Update]
[Repeat for each update]

---

## Resolution Outcome

### Final Resolution
**Resolution Date**: [YYYY-MM-DD]

**Approach Taken**: [Which option was implemented]

**Changes Made**:
- PROJECT.md: [Summary of changes or "No changes"]
- Code: [Summary of changes or "No changes"]
- Other: [Any other changes]

### Validation Results
**Conflict Resolved**: ✓ Yes / ⚠ Partially / ✗ No

**Validation Tests**:
- [Test 1]: ✓ Passed / ✗ Failed
- [Test 2]: ✓ Passed / ✗ Failed
- [Test 3]: ✓ Passed / ✗ Failed

**Stakeholder Acceptance**:
- [Stakeholder 1]: ✓ Approved / ⚠ Conditional / ✗ Rejected
- [Stakeholder 2]: ✓ Approved / ⚠ Conditional / ✗ Rejected

### Actual vs Planned
**Effort**:
- Planned: [Original estimate]
- Actual: [Actual effort]
- Variance: [Difference and why]

**Timeline**:
- Planned: [Original timeline]
- Actual: [Actual timeline]
- Variance: [Difference and why]

**Outcome**:
- Planned: [Expected outcome]
- Actual: [Actual outcome]
- Delta: [How results differed]

---

## Lessons Learned

### What Went Well
1. [Success 1]
2. [Success 2]
3. [Success 3]

### What Could Be Improved
1. [Area for improvement 1]
2. [Area for improvement 2]
3. [Area for improvement 3]

### Process Improvements
**Preventive Measures**:
1. [Change to prevent similar conflicts]
2. [Change to prevent similar conflicts]

**Detection Improvements**:
1. [Change to detect conflicts earlier]
2. [Change to detect conflicts earlier]

**Resolution Improvements**:
1. [Change to resolve conflicts faster]
2. [Change to resolve conflicts faster]

---

## Follow-up Items

### Immediate Follow-ups
- [ ] [Task 1] - Owner: [Name] - Due: [Date]
- [ ] [Task 2] - Owner: [Name] - Due: [Date]

### Long-term Follow-ups
- [ ] [Task 1] - Owner: [Name] - Due: [Date]
- [ ] [Task 2] - Owner: [Name] - Due: [Date]

### Monitoring
**What to Monitor**: [Metrics/indicators to watch]

**Frequency**: [How often to check]

**Duration**: [How long to monitor]

**Success Indicator**: [What indicates issue is fully resolved]

---

## References

### Related Conflicts
- [Conflict ID] - [Relationship]
- [Conflict ID] - [Relationship]

### PROJECT.md Sections
- [Link to section 1]
- [Link to section 2]

### Code References
- [Component 1] - [Path/file]
- [Component 2] - [Path/file]

### Supporting Documents
- [Document 1] - [Link]
- [Document 2] - [Link]

---

**Template Version**: 1.0
**Conflict Report Date**: [YYYY-MM-DD]
**Last Updated**: [YYYY-MM-DD]
**Next Review**: [YYYY-MM-DD]
