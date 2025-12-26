# Gap Assessment Template

Use this template to document gaps between current state and desired state defined in PROJECT.md.

---

## Gap Summary

**Gap ID**: [Unique identifier, e.g., GAP-2025-001]

**Gap Name**: [Short descriptive name]

**Gap Type**: [Feature / Documentation / Constraint / Architectural]

**Identified Date**: [YYYY-MM-DD]

**Identified By**: [Name/Team/Tool]

**Status**: [Open / In Progress / Resolved / Deferred / Closed]

---

## Quick Assessment

**Impact**: [Critical / High / Medium / Low]

**Effort**: [Quick Win / Tactical / Strategic / Epic]

**Priority Score**: [Number from scoring formula]

**Priority Classification**: [Critical / High / Medium / Low]

**Target Resolution**: [YYYY-MM-DD or Quarter]

---

## Current State

### What Exists Today
[Detailed description of current implementation/state]

**Evidence**:
- Code location: [Path/file references]
- Metrics: [Current performance, coverage, etc.]
- Documentation: [What's currently documented]

**Current Behavior**:
[How system currently behaves in this area]

**Stakeholders Affected**:
- [Stakeholder 1]: [How they're affected]
- [Stakeholder 2]: [How they're affected]

---

## Desired State

### What PROJECT.md Defines
[Detailed description of desired state per PROJECT.md]

**PROJECT.md Reference**:
- Section: [GOALS / SCOPE / CONSTRAINTS / ARCHITECTURE]
- Quote: "[Exact quote from PROJECT.md]"
- Location: [Section, subsection, line reference]

**Expected Behavior**:
[How system should behave according to PROJECT.md]

**Success Criteria**:
[How to know when gap is closed]

---

## Gap Analysis

### Specific Differences
**What's Missing**:
1. [Missing item 1]
2. [Missing item 2]
3. [Missing item 3]

**What's Incorrect**:
1. [Incorrect item 1]
2. [Incorrect item 2]

**What's Inconsistent**:
1. [Inconsistency 1]
2. [Inconsistency 2]

### Gap Details
[Detailed explanation of the gap]

**Examples**:
- **Example 1**: [Specific instance where gap is evident]
- **Example 2**: [Another instance]

**Quantification** (if measurable):
- Current: [Measurement]
- Desired: [Measurement]
- Gap: [Difference]

---

## Root Cause Analysis

### Primary Root Cause
[Main reason gap exists]

### Contributing Factors
1. **[Factor 1]**: [Description]
2. **[Factor 2]**: [Description]
3. **[Factor 3]**: [Description]

### Timeline
- **[Date]**: [Event that led to gap]
- **[Date]**: [Another relevant event]
- **[Date]**: [Gap first detected]

### Intentional or Drift?
[Was this intentional decision or accidental drift?]

**If Intentional**:
- Reason: [Why gap was accepted]
- Should it remain?: [Yes / No - why?]

**If Drift**:
- How did it happen?: [Explanation]
- How to prevent recurrence?: [Preventive measures]

---

## Impact Assessment

### Overall Impact
**Impact Level**: [Critical / High / Medium / Low]

**Impact Score**: [0-10 from scoring formula]

### User Impact
**Severity**: [0-3 points]

**Affected Users**:
- User type: [Which users affected]
- Number: [How many users]
- Frequency: [How often they encounter gap]

**User Experience Impact**:
[How gap affects user experience]

### Business Impact
**Severity**: [0-3 points]

**Revenue Impact**:
[How gap affects revenue/growth]

**Brand Impact**:
[How gap affects reputation/brand]

**Operational Impact**:
[How gap affects operations/efficiency]

### Technical Impact
**Severity**: [0-2 points]

**Code Quality**:
[How gap affects maintainability, testability]

**Technical Debt**:
[Does gap create or worsen technical debt?]

**Dependencies**:
[Does gap block other work?]

### Risk Impact
**Severity**: [0-2 points]

**Security Risks**:
[Any security implications]

**Compliance Risks**:
[Any regulatory implications]

**Stability Risks**:
[Any system stability implications]

---

## Effort Estimation

### Overall Effort
**Effort Level**: [Quick Win / Tactical / Strategic / Epic]

**Effort Score**: [0-10 from scoring formula]

### Time Estimation
**Score**: [0-3 points]

**Estimated Duration**: [Days/weeks/months]

**Breakdown**:
- Research: [Time]
- Design: [Time]
- Implementation: [Time]
- Testing: [Time]
- Documentation: [Time]
- Deployment: [Time]

### Complexity Assessment
**Score**: [0-3 points]

**Technical Complexity**: [Low / Medium / High]

**Domain Complexity**: [Low / Medium / High]

**Integration Complexity**: [Low / Medium / High]

**Explanation**:
[What makes this simple or complex]

### Dependencies
**Score**: [0-2 points]

**Prerequisite Gaps**:
1. [Gap ID] - [Must be closed first]
2. [Gap ID] - [Must be closed first]

**External Dependencies**:
1. [Dependency] - [Why needed]
2. [Dependency] - [Why needed]

**Team Dependencies**:
[Other teams that need to be involved]

### Risk Assessment
**Score**: [0-2 points]

**Implementation Risks**:
1. [Risk] - Probability: [H/M/L] - Impact: [H/M/L]
2. [Risk] - Probability: [H/M/L] - Impact: [H/M/L]

**Mitigation Strategies**:
1. [Strategy for risk 1]
2. [Strategy for risk 2]

---

## Priority Calculation

### Scoring Formula
**Priority Score = Impact Score - (Effort Score × 0.5)**

**Calculations**:
- Impact Score: [0-10]
  - User: [0-3]
  - Business: [0-3]
  - Technical: [0-2]
  - Risk: [0-2]
- Effort Score: [0-10]
  - Time: [0-3]
  - Complexity: [0-3]
  - Dependencies: [0-2]
  - Risk: [0-2]
- **Priority Score**: [Impact - (Effort × 0.5)]

### Priority Classification
**Score ≥ 7**: Critical Priority (Quick Win)
**Score 4-6**: High Priority (Tactical)
**Score 1-3**: Medium Priority (Balanced)
**Score ≤ 0**: Low Priority (Defer)

**This Gap's Classification**: [Critical / High / Medium / Low]

---

## Recommended Actions

### Recommended Approach
[Detailed description of how to close gap]

**Strategy**: [Update PROJECT.md / Modify Implementation / Both]

**Phased Approach** (if applicable):
- **Phase 1**: [Quick fixes / Low-hanging fruit]
- **Phase 2**: [Core improvements]
- **Phase 3**: [Complete resolution]

### Detailed Action Plan
**Step 1**: [Action]
- Owner: [Name]
- Duration: [Time]
- Dependencies: [List]
- Output: [Deliverable]

**Step 2**: [Action]
- Owner: [Name]
- Duration: [Time]
- Dependencies: [List]
- Output: [Deliverable]

**Step 3**: [Action]
- Owner: [Name]
- Duration: [Time]
- Dependencies: [List]
- Output: [Deliverable]

### Required Resources
**Team**:
- [Role 1]: [Hours/days]
- [Role 2]: [Hours/days]

**Budget**:
- [Item 1]: [Cost]
- [Item 2]: [Cost]
- **Total**: [Cost]

**Tools/Services**:
- [Tool 1]: [Why needed]
- [Tool 2]: [Why needed]

---

## Alternative Approaches

### Alternative 1: [Name]
**Description**: [What this approach would do]

**Pros**:
- [Pro 1]
- [Pro 2]

**Cons**:
- [Con 1]
- [Con 2]

**Effort**: [Comparison to recommended approach]

**Why Not Chosen**: [Reason]

### Alternative 2: [Name]
[Repeat template]

---

## Success Criteria

### Definition of Done
- [ ] [Criterion 1]
- [ ] [Criterion 2]
- [ ] [Criterion 3]

### Validation Tests
**How to verify gap is closed**:
1. [Test 1]: [Expected result]
2. [Test 2]: [Expected result]
3. [Test 3]: [Expected result]

### Metrics to Track
**Before**:
- [Metric 1]: [Current value]
- [Metric 2]: [Current value]

**Target**:
- [Metric 1]: [Target value]
- [Metric 2]: [Target value]

**Acceptance Criteria**:
[When metrics indicate gap is closed]

---

## Dependencies and Blockers

### Prerequisite Gaps
**Must Be Closed First**:
1. [Gap ID] - [Reason]
2. [Gap ID] - [Reason]

**Impact If Not Resolved**:
[What happens if we try to close this gap before prerequisites]

### Blocking Gaps
**This Gap Blocks**:
1. [Gap ID] - [How it blocks]
2. [Gap ID] - [How it blocks]

**Urgency Impact**:
[Why this increases urgency]

### External Dependencies
**Dependencies**:
1. [Dependency] - Status: [Available / Pending / Blocked]
2. [Dependency] - Status: [Available / Pending / Blocked]

**Contingency Plans**:
[What to do if dependencies not available]

---

## Risk Management

### Implementation Risks
**Risk 1**: [Description]
- Probability: [High / Medium / Low]
- Impact: [High / Medium / Low]
- Mitigation: [Strategy]
- Contingency: [Backup plan]

**Risk 2**: [Description]
- Probability: [High / Medium / Low]
- Impact: [High / Medium / Low]
- Mitigation: [Strategy]
- Contingency: [Backup plan]

### Opportunity Risks
**Risk of Not Closing Gap**:
- Lost opportunities: [List]
- Competitive impact: [Description]
- User impact: [Description]

---

## Communication Plan

### Stakeholders
**Who Needs to Know**:
1. [Stakeholder] - [Why / What they need to know]
2. [Stakeholder] - [Why / What they need to know]

### Communication Schedule
- **Initial**: [When to first communicate]
- **Updates**: [Frequency of updates]
- **Completion**: [When to announce closure]

### Message
**Key Points to Communicate**:
1. [Point 1]
2. [Point 2]
3. [Point 3]

---

## Timeline

### Target Milestones
- **Start Date**: [YYYY-MM-DD]
- **Milestone 1**: [YYYY-MM-DD] - [What's completed]
- **Milestone 2**: [YYYY-MM-DD] - [What's completed]
- **Milestone 3**: [YYYY-MM-DD] - [What's completed]
- **Completion Date**: [YYYY-MM-DD]

### Review Schedule
- **Weekly Check-in**: [Day/time]
- **Monthly Review**: [Date]
- **Final Assessment**: [Date]

---

## Status Tracking

### Current Status
**Status**: [Open / In Progress / Resolved / Deferred / Closed]

**Last Updated**: [YYYY-MM-DD]

**Updated By**: [Name]

### Progress Log
**[Date]**: [Update]
- Status: [Change]
- Progress: [What was accomplished]
- Blockers: [Any new blockers]
- Next steps: [What's next]

**[Date]**: [Update]
[Repeat for each update]

---

## Closure

### Resolution Summary
[How gap was closed]

### Final Validation
- [Validation test 1]: ✓ Passed
- [Validation test 2]: ✓ Passed
- [Validation test 3]: ✓ Passed

### Actual vs Estimated
- **Estimated effort**: [Original estimate]
- **Actual effort**: [Actual time taken]
- **Variance**: [Difference and why]

### Lessons Learned
1. [Lesson 1]
2. [Lesson 2]
3. [Lesson 3]

### Follow-up Items
- [ ] [Follow-up task 1]
- [ ] [Follow-up task 2]

---

## References

### PROJECT.md Sections
- [Link to section 1]
- [Link to section 2]

### Related Gaps
- [Gap ID] - [Relationship]
- [Gap ID] - [Relationship]

### Supporting Documents
- [Document 1] - [Link]
- [Document 2] - [Link]

---

**Template Version**: 1.0
**Gap Assessment Date**: [YYYY-MM-DD]
**Next Review Date**: [YYYY-MM-DD]
