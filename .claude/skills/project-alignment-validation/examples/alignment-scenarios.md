# Alignment Scenarios - Common Cases and Resolutions

Real-world scenarios showing how to validate feature alignment and resolve common conflicts.

---

## Scenario 1: Feature Fully Aligned

### Feature Request
"Add JWT-based authentication for API endpoints"

### Alignment Validation

**GOALS Check**: ✓ Aligned
- Primary Goal: "Secure user access and data protection"
- Feature serves goal by implementing industry-standard authentication
- Measurable: Track unauthorized access attempts (should decrease)

**SCOPE Check**: ✓ Aligned
- PROJECT.md: "User authentication and authorization - In Scope"
- Feature explicitly mentioned in scope
- No out-of-scope dependencies

**CONSTRAINTS Check**: ✓ Aligned
- Technology: JWT library (PyJWT) already approved in stack
- Performance: JWT validation < 10ms, within budget
- Security: Follows OWASP best practices, addresses CWE-287

**ARCHITECTURE Check**: ✓ Aligned
- Follows existing middleware pattern for API security
- Integrates with current user model and session management
- Maintains stateless API design principle

### Recommendation
**Decision**: ✓ Proceed with implementation

**Next Steps**:
1. Implement JWT middleware
2. Add unit tests for token validation
3. Update API documentation with authentication requirements
4. Deploy to staging for security review

---

## Scenario 2: Feature Needs Scope Clarification

### Feature Request
"Add OAuth integration for Google sign-in"

### Initial Alignment Check

**GOALS Check**: ✓ Aligned
- Goal: "Easy user onboarding and authentication"
- OAuth improves user experience (no password management)

**SCOPE Check**: ⚠ Ambiguous
- In Scope: "User authentication"
- Out of Scope: "Third-party integrations"
- **Conflict**: OAuth requires third-party provider (Google)

**CONSTRAINTS Check**: ✓ Aligned (if approved)
- Technology: OAuth 2.0 libraries available
- Security: Google OAuth meets security requirements

**ARCHITECTURE Check**: ✓ Aligned (if approved)
- Can integrate with existing auth middleware
- Follows authentication abstraction pattern

### Resolution: Clarify Scope

**Analysis**:
- OAuth serves authentication goal (in scope)
- Google is auth *provider*, not business integration
- Out-of-scope "third-party integrations" means business logic, not auth

**Decision**: Update PROJECT.md to clarify

**PROJECT.md Update**:
```markdown
## SCOPE

### In Scope
- User authentication (local credentials, OAuth providers)
- Authorization and role-based access control

### Out of Scope
- Third-party business integrations (payment processors, analytics platforms)
- Note: Authentication providers (OAuth) are IN scope
```

**Recommendation**: ✓ Proceed after PROJECT.md update

---

## Scenario 3: Feature Violates Performance Constraint

### Feature Request
"Add comprehensive audit logging for all API requests"

### Alignment Validation

**GOALS Check**: ✓ Aligned
- Goal: "Security and compliance"
- Audit logging critical for compliance requirements

**SCOPE Check**: ✓ Aligned
- Audit logging explicitly in scope for compliance

**CONSTRAINTS Check**: ✗ Violates Performance
- Constraint: "API response time < 200ms"
- Naive logging: Adds 150ms per request (synchronous DB writes)
- **Violation**: Would push response times to 350ms average

**ARCHITECTURE Check**: ⚠ Needs Adjustment
- Current architecture: Synchronous request handling
- Required: Async logging to meet performance constraint

### Resolution: Modify Implementation

**Decision**: ⚠ Modify feature to align with constraints

**Modified Approach**:
1. **Use async logging queue** (Redis/RabbitMQ)
   - Log to queue: < 2ms overhead
   - Background worker persists to database
   - Meets 200ms constraint

2. **Implement sampling for high-volume endpoints**
   - Critical endpoints: 100% logging
   - High-volume endpoints: 10% sampling
   - Balances compliance and performance

3. **Add performance monitoring**
   - Track P95 response times
   - Alert if approaching 200ms threshold

**Updated Alignment**:
- ✓ GOALS: Still serves security/compliance
- ✓ SCOPE: Still in scope
- ✓ CONSTRAINTS: Now meets performance requirement
- ✓ ARCHITECTURE: Improved with async pattern

**Recommendation**: ✓ Proceed with modified approach

---

## Scenario 4: Goal Conflict - Speed vs Quality

### Feature Request
"Launch MVP with basic features in 4 weeks"

### Alignment Validation

**GOALS Check**: ⚠ Conflict
- Goal A: "Fast time-to-market"
- Goal B: "High code quality and test coverage"
- **Conflict**: 4-week MVP timeline incompatible with 80% test coverage goal

**SCOPE Check**: ✓ Aligned
- MVP features clearly defined in scope

**CONSTRAINTS Check**: ⚠ Timeline vs Quality
- Constraint: "Minimum 80% test coverage"
- Constraint: "Launch by Q1 end" (4 weeks)
- **Conflict**: Cannot achieve both simultaneously

**ARCHITECTURE Check**: ✓ Aligned
- MVP architecture is sound

### Resolution: Negotiate Compromise

**Analysis**:
- Both goals are valid
- Different priorities for different project phases
- Need tiered quality approach

**Compromise Solution**:
```markdown
## Tiered Quality Requirements

### MVP Phase (Weeks 1-4)
- Critical paths: 90% coverage (auth, payments, data security)
- Core features: 70% coverage (main user workflows)
- UI/utilities: 50% coverage
- **Overall target**: 65% average coverage

### Beta Phase (Weeks 5-8)
- Critical paths: 95% coverage
- Core features: 80% coverage
- UI/utilities: 70% coverage
- **Overall target**: 75% average coverage

### Production (Week 9+)
- Critical paths: 95% coverage
- Core features: 85% coverage
- UI/utilities: 75% coverage
- **Overall target**: 80% average coverage (original goal)
```

**PROJECT.md Updates**:
1. Update CONSTRAINTS: Add phased quality requirements
2. Update GOALS: Add "Achieve 80% coverage by production" timeline

**Recommendation**: ✓ Proceed with phased approach

---

## Scenario 5: Architecture Misalignment

### Feature Request
"Add real-time collaborative editing"

### Alignment Validation

**GOALS Check**: ✓ Aligned
- Goal: "Modern, collaborative user experience"

**SCOPE Check**: ⚠ Not Explicit
- Current scope: "Document editing"
- Real-time collaboration not mentioned

**CONSTRAINTS Check**: ✗ Multiple Violations
- Technology: No WebSocket infrastructure
- Architecture: REST-only API (no real-time support)
- Performance: Real-time requires persistent connections

**ARCHITECTURE Check**: ✗ Major Deviation
- Current: Stateless REST API
- Required: Stateful WebSocket connections
- **Conflict**: Fundamental architecture change

### Resolution: Strategic Decision Required

**Analysis**:
- Feature has merit but requires major architecture shift
- Cannot be "added" to current system
- Requires stakeholder decision on strategic direction

**Options for Stakeholders**:

**Option 1: Defer Real-Time** (Recommended)
- Pros: Stay on current timeline, simpler architecture
- Cons: Less modern UX
- Approach: Implement polling-based collaboration (good enough)
- Timeline: No delay

**Option 2: Hybrid Architecture**
- Pros: Support both REST and WebSocket
- Cons: Increased complexity, infrastructure costs
- Approach: Add WebSocket layer alongside REST
- Timeline: +6 weeks

**Option 3: Full Migration to Real-Time**
- Pros: Modern architecture, best UX
- Cons: Major rewrite, significant delay
- Approach: Redesign as event-driven system
- Timeline: +12 weeks

**Escalation**:
- Present options to product owner and CTO
- Decision needed: Timeline vs features trade-off

**Temporary Resolution**:
```markdown
Decision: Option 1 (Defer Real-Time)

Rationale:
- MVP timeline is priority
- Polling-based collaboration acceptable for MVP
- Can add real-time in v2.0 after market validation

PROJECT.md Updates:
- SCOPE: Add "polling-based collaboration" to In Scope
- SCOPE: Add "real-time collaboration" to Future Scope
- ARCHITECTURE: Document polling pattern for collaboration
```

**Recommendation**: ✓ Proceed with Option 1, revisit post-MVP

---

## Scenario 6: Documentation Drift

### Situation
Code review discovers mismatch between PROJECT.md and implementation

**PROJECT.md Says**:
- "Python 3.9+ compatible"
- "SQLite database for simplicity"

**Code Actually Uses**:
- Python 3.11 features (match statements, walrus operator)
- PostgreSQL database with advanced features

### Alignment Analysis

**Type**: Documentation Gap

**Root Cause**:
- PROJECT.md written at project start
- Team evolved tech stack during implementation
- Documentation not kept in sync

**Impact**:
- New developers confused
- Deployment assumptions incorrect
- Onboarding documentation misleading

### Resolution: Update PROJECT.md

**Decision**: Code is correct, update documentation

**Rationale**:
- Python 3.11 provides better developer experience
- PostgreSQL better serves scaling goals
- Changes were intentional and beneficial

**PROJECT.md Updates**:
```markdown
## CONSTRAINTS

### Technical Constraints
- **Python**: 3.11+ required (uses match statements, walrus operator)
- **Database**: PostgreSQL 14+ (uses JSONB, CTEs, window functions)
- **Why changed from 3.9/SQLite**: Better performance and developer experience

## ARCHITECTURE

### Database Strategy
- PostgreSQL for robust querying and ACID guarantees
- Migration path: SQLite → PostgreSQL documented in docs/migration.md
```

**Additional Actions**:
1. Add Python version check to startup (fail fast if < 3.11)
2. Update README.md with correct requirements
3. Update CI/CD to use Python 3.11
4. Document migration from SQLite to PostgreSQL

**Recommendation**: ✓ Update PROJECT.md to reflect reality

---

## Scenario 7: Scope Creep Detection

### Feature Request
"Add AI-powered recommendation engine"

### Alignment Validation

**GOALS Check**: ⚠ Tangential
- Goals: "User engagement", "Personalization"
- AI recommendations *could* serve these goals
- Not mentioned as approach in goals

**SCOPE Check**: ✗ Out of Scope
- In Scope: "Manual curation and tagging"
- Out of Scope: "AI/ML features for MVP"
- **Clear violation**: AI explicitly out of scope

**CONSTRAINTS Check**: ✗ Multiple Violations
- Budget: ML infrastructure exceeds budget
- Timeline: Delays MVP by 8+ weeks
- Team: No ML expertise on current team

**ARCHITECTURE Check**: ✗ Not Planned
- No ML infrastructure in architecture
- Would require major additions

### Resolution: Reject (Scope Creep)

**Decision**: ✗ Reject for MVP, add to future roadmap

**Rationale**:
- Feature is out of scope (explicitly listed)
- Violates budget and timeline constraints
- Team lacks required expertise
- Manual curation sufficient for MVP

**Alternative Approach**:
```markdown
## MVP (Current Scope)
- Manual curation with tagging system
- Simple rule-based recommendations (if user likes X, show similar)
- Validate user interest in recommendations

## Post-MVP (Future Scope)
- If users engage with recommendations
- If budget allows ML infrastructure
- Consider AI-powered enhancement
- Add to v2.0 roadmap
```

**Communication to Stakeholder**:
"Great idea! However, AI/ML is explicitly out of scope for MVP to meet our timeline and budget. Let's validate user interest with simple rule-based recommendations first, then invest in AI for v2.0 if data shows it's valuable."

**Recommendation**: ✗ Reject for now, add to future roadmap

---

## Scenario 8: Successful Constraint Relaxation

### Feature Request
"Implement end-to-end encryption for all user data"

### Initial Alignment Check

**GOALS Check**: ✓ Aligned
- Goal: "Privacy and security"
- E2E encryption serves goal perfectly

**SCOPE Check**: ✓ Aligned
- Security features in scope

**CONSTRAINTS Check**: ✗ Violates Performance
- Current constraint: "Search all user content < 500ms"
- E2E encryption: Cannot index encrypted content
- **Conflict**: Search performance impossible with E2E encryption

**ARCHITECTURE Check**: ⚠ Major Change
- Requires client-side encryption/decryption
- Requires key management system
- Search architecture must change

### Resolution: Update Constraint

**Analysis**:
- Privacy goal more important than search performance
- Users value privacy over search speed
- Industry trend toward E2E encryption

**Decision**: Relax search performance constraint

**Trade-off Accepted**:
```markdown
Original Constraint: "Search all content < 500ms"
Updated Constraint: "Search metadata < 500ms, encrypted content search < 5s"

Rationale:
- E2E encryption critical for user privacy
- Privacy goal outweighs search speed goal
- Users willing to wait longer for secure search
- Can optimize search UX (streaming results, progress indicators)
```

**PROJECT.md Updates**:
- CONSTRAINTS: Update search performance requirements
- ARCHITECTURE: Add E2E encryption architecture section
- GOALS: Emphasize privacy priority

**Recommendation**: ✓ Proceed with constraint relaxation

---

## Common Patterns

### Pattern 1: Quick Alignment Checks
For simple features, use quick checklist:
1. Which goal does it serve? (must have answer)
2. Is it in scope? (check PROJECT.md)
3. Any constraint violations? (check all constraints)
4. Fits architecture? (check patterns)

### Pattern 2: When to Update PROJECT.md
Update when:
- Strategic direction changed
- New goals emerged
- Constraints evolved
- Architecture improved
- Code is right, documentation wrong

### Pattern 3: When to Modify Feature
Modify when:
- Feature violates valid constraints
- Better approach exists that aligns better
- Trade-offs favor modification
- Quick fixes available

### Pattern 4: When to Escalate
Escalate when:
- Strategic priority decision needed
- Resource allocation required
- Multiple stakeholders affected
- Timeline vs quality trade-offs

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Forcing Alignment
❌ "Let's reword the goal so feature fits"
✓ "Let's understand if feature truly serves goals"

### Anti-Pattern 2: Ignoring Constraints
❌ "We can fix performance later"
✓ "Let's design for performance from start"

### Anti-Pattern 3: Scope Creep Justification
❌ "Users will love this, so it's in scope"
✓ "Does PROJECT.md say this is in scope?"

### Anti-Pattern 4: Documentation Drift
❌ "We'll update PROJECT.md later"
✓ "Update PROJECT.md as we make decisions"

---

**See Also**:
- `../docs/alignment-checklist.md` - Systematic validation checklist
- `../docs/semantic-validation-approach.md` - Philosophy behind scenarios
- `misalignment-examples.md` - What NOT to do
- `project-md-structure-example.md` - Well-structured PROJECT.md
