# Alignment Report Template

Use this template to document feature alignment validation against PROJECT.md.

---

## Feature Alignment Validation

**Feature Name**: [Name of feature]

**Feature Description**: [Brief description of what feature does]

**Validation Date**: [YYYY-MM-DD]

**Validated By**: [Name/Team]

**Validation Type**: [Pre-implementation / Post-implementation / Retrofit]

---

## Summary

**Overall Alignment Status**: ✓ ALIGNED / ⚠ NEEDS WORK / ✗ NOT ALIGNED

**Recommendation**: [Proceed / Modify / Defer / Reject]

**Key Points**:
- [Summary point 1]
- [Summary point 2]
- [Summary point 3]

---

## Findings

Detailed alignment analysis across all PROJECT.md sections.

### GOALS Alignment

**Status**: ✓ Aligned / ⚠ Partially Aligned / ✗ Not Aligned

### Primary Goal Served
**Goal**: [Name of primary goal from PROJECT.md]

**How Feature Serves Goal**:
[Explain how feature contributes to achieving this goal]

**Measurable Impact**:
[How we can measure feature's contribution to goal]

### Secondary Goals
**Goals Supported**:
1. [Goal name] - [How it's supported]
2. [Goal name] - [How it's supported]

**Goals NOT Supported** (that might be expected):
1. [Goal name] - [Why not supported]

### Goal Conflicts
**Conflicts Identified**: [None / List conflicts]

**Conflict Details** (if any):
- **Conflict**: [Description]
- **Impact**: [How it affects goals]
- **Mitigation**: [How to resolve]

### GOALS Assessment
**Priority Alignment**: ✓ Yes / ⚠ Partial / ✗ No
- Feature priority: [High / Medium / Low]
- Goal priority: [High / Medium / Low]
- Alignment: [Explanation]

**Success Metrics Alignment**: ✓ Yes / ⚠ Partial / ✗ No
- Feature metrics: [List]
- Goal metrics: [List]
- Alignment: [Explanation]

---

## SCOPE Alignment

**Status**: ✓ Aligned / ⚠ Partially Aligned / ✗ Not Aligned

### In-Scope Validation
**Is Feature Explicitly In Scope?**: ✓ Yes / ⚠ Implicit / ✗ No

**Scope Section Reference**:
[Quote or cite specific section from PROJECT.md SCOPE]

**Scope Interpretation**:
[Explain how feature fits within stated scope]

### Out-of-Scope Validation
**Does Feature Touch Out-of-Scope Areas?**: ✓ No / ⚠ Partially / ✗ Yes

**Out-of-Scope Items Affected** (if any):
1. [Item name] - [How it's affected] - [Justification]

**Boundary Clarity**: ✓ Clear / ⚠ Needs Clarification / ✗ Unclear
[Explain boundaries between in-scope and out-of-scope]

### Dependency Validation
**All Dependencies In Scope?**: ✓ Yes / ⚠ Some / ✗ No

**In-Scope Dependencies**:
1. [Dependency] - ✓ In scope
2. [Dependency] - ✓ In scope

**Out-of-Scope Dependencies** (if any):
1. [Dependency] - ✗ Out of scope - [How to handle]

### Scope Creep Assessment
**Does Feature Expand Scope?**: ✓ No / ⚠ Maybe / ✗ Yes

**If Yes, Justification**:
[Explain why scope expansion is warranted]

**PROJECT.md Update Needed?**: ✓ Yes / ✗ No
[What sections need updating]

---

## CONSTRAINTS Alignment

**Status**: ✓ Aligned / ⚠ Partially Aligned / ✗ Not Aligned

### Technical Constraints
**Technology Stack Compliance**: ✓ Yes / ⚠ Partial / ✗ No

**Approved Technologies Used**:
1. [Technology] - ✓ Approved
2. [Technology] - ✓ Approved

**New Technologies Introduced** (if any):
1. [Technology] - [Justification for introduction]

**Performance Requirements**: ✓ Met / ⚠ At Risk / ✗ Violated
- Requirement: [Specific requirement from PROJECT.md]
- Expected: [Feature's expected performance]
- Compliance: [Explanation]

**Scalability Requirements**: ✓ Met / ⚠ At Risk / ✗ Violated
- Requirement: [Specific requirement]
- Expected: [Feature's scalability]
- Compliance: [Explanation]

**Security Requirements**: ✓ Met / ⚠ At Risk / ✗ Violated
- CWE validations: [List applicable CWEs]
- Audit logging: [Yes / No / N/A]
- Compliance: [Explanation]

### Resource Constraints
**Budget Compliance**: ✓ Within Budget / ⚠ At Limit / ✗ Over Budget
- Estimated cost: [Amount]
- Budget available: [Amount]
- Compliance: [Explanation]

**Timeline Compliance**: ✓ On Schedule / ⚠ At Risk / ✗ Delayed
- Estimated time: [Duration]
- Available time: [Duration]
- Compliance: [Explanation]

**Team Capacity**: ✓ Available / ⚠ Stretched / ✗ Insufficient
- Required skills: [List]
- Available team: [List]
- Compliance: [Explanation]

### Policy Constraints
**Regulatory Compliance**: ✓ Compliant / ⚠ Review Needed / ✗ Non-Compliant
- Regulations: [List applicable regulations]
- Compliance status: [Explanation]

**Licensing Compliance**: ✓ Compliant / ⚠ Review Needed / ✗ Non-Compliant
- Dependencies: [List with licenses]
- Compliance status: [Explanation]

**Privacy Compliance**: ✓ Compliant / ⚠ Review Needed / ✗ Non-Compliant
- Data handling: [Description]
- Compliance status: [Explanation]

### Constraint Trade-offs
**Trade-offs Accepted** (if any):
1. [Constraint] - [Trade-off] - [Justification]

**Stakeholder Approval Needed?**: ✓ Yes / ✗ No
[Which stakeholders need to approve trade-offs]

---

## ARCHITECTURE Alignment

**Status**: ✓ Aligned / ⚠ Partially Aligned / ✗ Not Aligned

### Design Principles
**Pattern Consistency**: ✓ Consistent / ⚠ Minor Deviation / ✗ Major Deviation

**Architectural Patterns Used**:
1. [Pattern] - ✓ Consistent with existing
2. [Pattern] - ✓ Consistent with existing

**Pattern Deviations** (if any):
1. [Pattern] - [Deviation] - [Justification]

**Design Principle Compliance**:
- [Principle 1]: ✓ Yes / ⚠ Partial / ✗ No - [Explanation]
- [Principle 2]: ✓ Yes / ⚠ Partial / ✗ No - [Explanation]
- [Principle 3]: ✓ Yes / ⚠ Partial / ✗ No - [Explanation]

### Component Integration
**Integration Approach**: ✓ Clean / ⚠ Acceptable / ✗ Problematic

**Existing Components Affected**:
1. [Component] - [How affected] - [Impact assessment]

**New Components Introduced**:
1. [Component] - [Purpose] - [Integration points]

**Interface Contracts**: ✓ Respected / ⚠ Modified / ✗ Broken
[Explanation of interface changes if any]

**Data Flow**: ✓ Consistent / ⚠ New Pattern / ✗ Problematic
[How data flows through system with this feature]

### Quality Attributes
**Maintainability**: ✓ High / ⚠ Medium / ✗ Low
[Code structure, documentation, understandability]

**Testability**: ✓ High / ⚠ Medium / ✗ Low
[Unit test coverage, integration test coverage]

**Observability**: ✓ High / ⚠ Medium / ✗ Low
[Logging, metrics, debugging support]

**Documentation**: ✓ Complete / ⚠ Partial / ✗ Missing
[Architecture documentation, code comments, API docs]

### Technical Debt Assessment
**Technical Debt Introduced**: ✓ None / ⚠ Acceptable / ✗ Significant

**Debt Details** (if any):
- [Debt item 1] - [Impact] - [Repayment plan]

**Mitigation Strategy**:
[How to address technical debt]

---

## Combined Assessment

### Cross-Section Consistency
**Internal Consistency**: ✓ Consistent / ⚠ Minor Issues / ✗ Major Issues

**Consistency Check**:
- GOALS + SCOPE: [Explanation of consistency]
- SCOPE + CONSTRAINTS: [Explanation]
- CONSTRAINTS + ARCHITECTURE: [Explanation]
- ARCHITECTURE + GOALS: [Explanation]

**Identified Conflicts**:
1. [Section A] vs [Section B] - [Conflict description]

### Strategic Fit
**Overall Project Vision Alignment**: ✓ Strong / ⚠ Moderate / ✗ Weak

**Vision Statement** (from PROJECT.md):
[Quote vision statement]

**How Feature Serves Vision**:
[Explanation of strategic alignment]

### Risk Assessment
**Overall Risk Level**: ✓ Low / ⚠ Medium / ✗ High

**Identified Risks**:
1. **[Risk name]** - Probability: [H/M/L] - Impact: [H/M/L]
   - Description: [Risk description]
   - Mitigation: [How to mitigate]

**Risk Acceptance**:
[Which risks are accepted and why]

---

## Recommendations

### Overall Recommendation
**Decision**: [Proceed / Modify / Defer / Reject]

**Rationale**:
[Clear explanation of why this recommendation]

### Required Modifications (if any)
**Before Implementation**:
1. [Modification] - [Reason]
2. [Modification] - [Reason]

**During Implementation**:
1. [Consideration] - [Reason]

**After Implementation**:
1. [Follow-up] - [Reason]

### PROJECT.md Updates Needed
**Sections to Update**: [None / List sections]

**Proposed Updates**:
- **Section**: [Name]
- **Current**: [What it says now]
- **Proposed**: [What it should say]
- **Reason**: [Why update needed]

### Next Steps
**Immediate Actions**:
1. [Action] - Owner: [Name] - Due: [Date]
2. [Action] - Owner: [Name] - Due: [Date]

**Follow-up Actions**:
1. [Action] - Owner: [Name] - Due: [Date]

**Validation Points**:
- [Milestone 1]: [What to validate]
- [Milestone 2]: [What to validate]

---

## Approval

**Technical Approval**: [Name] - Date: [YYYY-MM-DD]

**Product Approval**: [Name] - Date: [YYYY-MM-DD]

**Stakeholder Sign-off** (if needed):
- [Stakeholder]: [Approved / Pending / Rejected] - Date: [YYYY-MM-DD]

---

## Appendices

### Appendix A: PROJECT.md References
[Relevant quotes from PROJECT.md sections]

### Appendix B: Supporting Analysis
[Additional analysis, metrics, research]

### Appendix C: Alternative Approaches Considered
[Other approaches and why not chosen]

---

**Report Version**: 1.0
**Last Updated**: [YYYY-MM-DD]
**Next Review**: [YYYY-MM-DD]
