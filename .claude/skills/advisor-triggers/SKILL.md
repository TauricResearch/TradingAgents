---
name: advisor-triggers
version: 1.0.0
type: automation
description: Detects when user requests warrant critical analysis via /advise command
auto_activate: false
allowed-tools: [Read, Grep, Glob]
keywords:
  - advisor
  - triggers
  - automation
  - detection
  - patterns
  - analysis

---

# Advisor Auto-Invoke Triggers

## Purpose

Detect patterns in user requests that indicate a need for critical thinking analysis. Suggests running `/advise` when users propose significant changes without first considering trade-offs.

## Detection Patterns

### Pattern 1: New Dependencies

**Triggers:**
- "add [package/library/service]"
- "use [technology]"
- "integrate [external service]"
- "switch to [different tool]"

**Examples:**
- "Let's add Redis for caching"
- "Use TensorFlow for ML"  
- "Integrate Stripe for payments"
- "Switch to PostgreSQL"

**Why advise?** New dependencies increase complexity and maintenance burden.

### Pattern 2: Architecture Changes

**Triggers:**
- "refactor to [pattern]"
- "restructure as [architecture]"
- "migrate to [architecture]"
- "convert to [pattern]"

**Examples:**
- "Refactor to microservices"
- "Restructure as event-driven"
- "Migrate to serverless"
- "Convert to monorepo"

**Why advise?** Architectural changes have far-reaching implications.

### Pattern 3: Scope Expansions

**Triggers:**
- "also add [feature]"
- "extend to [capability]"
- "support [new use case]"
- "make it [do more]"

**Examples:**
- "Also add real-time collaboration"
- "Extend to mobile platforms"
- "Support multi-tenancy"
- "Make it work offline"

**Why advise?** Scope creep can derail projects.

### Pattern 4: Technology Replacements

**Triggers:**
- "[X] instead of [Y]"
- "replace [X] with [Y]"
- "swap [X] for [Y]"

**Examples:**
- "GraphQL instead of REST"
- "Replace Express with Fastify"
- "Swap MySQL for MongoDB"

**Why advise?** Tech replacements have migration costs.

### Pattern 5: Scale Changes

**Triggers:**
- "handle [large number]"
- "scale to [big metric]"
- "support [many users]"

**Examples:**
- "Handle 1M requests/day"
- "Scale to 100K users"
- "Support 10K concurrent"

**Why advise?** Premature optimization is common.

## Detection Logic

```typescript
function shouldInvokeAdvisor(userRequest: string): boolean {
  const triggers = [
    // Dependencies
    /add (redis|mongodb|postgres|graphql|webpack|docker)/i,
    /use (tensorflow|pytorch|react|vue|angular)/i,
    /integrate (stripe|auth0|sendgrid|aws)/i,
    /switch to (typescript|rust|go|kubernetes)/i,
    
    // Architecture
    /refactor to (microservices|serverless|event-driven)/i,
    /restructure as/i,
    /migrate to/i,
    /convert to/i,
    
    // Scope
    /also add/i,
    /extend to/i,
    /support (mobile|multi-tenant|real-time|offline)/i,
    
    // Technology replacement
    /instead of/i,
    /replace \w+ with/i,
    /swap \w+ for/i,
    
    // Scale
    /scale to/i,
    /handle \d+[kmb]/i, // 1k, 1m, 1b
    /support \d+k/i
  ];
  
  return triggers.some(pattern => pattern.test(userRequest));
}
```

## Response Format

When trigger detected:

```markdown
⚠️ **Significant decision detected**

Your request involves [architecture change / new dependency / scope expansion].

Consider running critical analysis first:

/advise "{user's proposal}"

This will provide:
- Alignment check with PROJECT.md
- Complexity assessment
- Trade-off analysis
- Alternative approaches
- Risk identification

Takes 2-3 minutes, could save weeks.

Proceed with analysis? [Y/n]
```

## Configuration

```yaml
# .claude/config.yml
advisor_triggers:
  enabled: true
  
  # Sensitivity
  sensitivity: medium  # low | medium | high
  
  # Specific triggers
  triggers:
    new_dependencies: true
    architecture_changes: true
    scope_expansions: true
    technology_swaps: true
    scale_changes: true
  
  # Auto-activation (don't ask, just run)
  auto_activate: false  # If true, runs /advise automatically
```

## Integration Points

### Point 1: Before /plan Command

```markdown
User: "Let's add Redis caching"
  ↓
advisor-triggers: Detected new dependency
  ↓
[Suggest /advise]
  ↓
User: Accepts suggestion
  ↓
/advise "Add Redis caching"
  ↓
User: Reviews analysis, decides
  ↓
/plan [chosen approach]
```

### Point 2: Before /auto-implement

```markdown
User: "/auto-implement add WebSocket support"
  ↓
advisor-triggers: Detected architecture change
  ↓
[Suggest /advise first]
  ↓
User: Either runs /advise or proceeds anyway
```

### Point 3: In Orchestrator Agent

```markdown
orchestrator receives feature request
  ↓
Check advisor-triggers
  ↓
IF significant decision detected
  ↓
Invoke advisor agent first
  ↓
Present analysis to user
  ↓
THEN proceed with planning
```

## False Positives

Some requests trigger falsely:

**False Positive:**
- "Fix bug in Redis connection" ← mentions Redis but not adding it
- "Document the microservices" ← mentions architecture but not changing it

**Solution:** Context-aware detection:
```typescript
// Only trigger if action verb present
if (containsActionVerb(request) && containsTriggerKeyword(request)) {
  return true;
}
```

## Override

Users can bypass:

```bash
# Explicit skip
/plan --skip-advisor "Add Redis caching"

# Or acknowledge in prompt
"Add Redis caching (already analyzed, proceeding)"
```

## Success Metrics

**This skill is successful if:**
- ✅ Catches 80%+ of significant decisions
- ✅ False positive rate < 20%
- ✅ Users find suggestions helpful (not annoying)
- ✅ Reduces regretted decisions (measured via rollbacks)

## Example Outputs

### Example 1: New Dependency

```
User: "Let's add Elasticsearch for search"

⚠️ Significant decision detected

Your request involves adding a new dependency (Elasticsearch).

Consider critical analysis first:
  /advise "Add Elasticsearch for full-text search"

This will check:
  - Alignment with PROJECT.md goals
  - Complexity cost (Elasticsearch cluster, maintenance)
  - Alternatives (PostgreSQL full-text search, simple indexing)
  - Trade-offs (features vs operational complexity)

Takes 2-3 minutes. Run analysis? [Y/n]
```

### Example 2: Architecture Change

```
User: "Refactor to event-driven architecture"

⚠️ Significant decision detected

Your request involves a major architectural change.

Consider critical analysis first:
  /advise "Refactor to event-driven architecture"

This will evaluate:
  - Alignment with current architecture (PROJECT.md:78)
  - Migration complexity (message bus, event schemas)
  - Pros/cons of event-driven vs current approach
  - Alternative patterns (queue-based, CQRS lite)

This is a 6-8 week decision. Run analysis? [Y/n]
```

### Example 3: Scope Expansion

```
User: "Also add mobile app support"

⚠️ Significant decision detected

Your request expands project scope to mobile platforms.

Consider critical analysis first:
  /advise "Add mobile app (iOS + Android)"

This will check:
  - Alignment with PROJECT.md scope (currently web-only)
  - Effort estimate (React Native vs native vs PWA)
  - Trade-offs (mobile features vs maintenance burden)
  - MVP options (PWA first, native later)

Major scope change. Run analysis? [Y/n]
```

## Disabling

If users find this annoying:

```bash
# Disable globally
echo "advisor_triggers:\n  enabled: false" >> .claude/config.yml

# Or reduce sensitivity
echo "advisor_triggers:\n  sensitivity: low" >> .claude/config.yml
```

## Version History

- **1.0.0** (2025-10-26): Initial release
  - Pattern detection for 5 trigger types
  - Configurable sensitivity
  - Integration with /advise command

---

**Philosophy**: Help users pause and think before committing to significant changes. The goal is not to slow down development, but to prevent costly mistakes.
