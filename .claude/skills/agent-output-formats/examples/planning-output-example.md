# Planning Agent Output Example

## Feature Summary

Implement skill-based token reduction for agent prompts and library error handling.

**Goal**: Reduce context token usage by 10,820 tokens (8-15% reduction) while maintaining functionality

**Scope**:
- Included: 15 agent prompts, 22 library files, 2 new skill packages
- Excluded: Hook modifications, command changes, existing skill updates

**Success Criteria**:
- All 82 TDD tests pass
- Token savings ≥8% for agent-output-formats skill
- Token savings ≥10% for error-handling-patterns skill
- No regressions in existing tests

## Architecture

High-level design for skill-based token reduction:

**Components**:
- agent-output-formats skill (centralized output specifications)
- error-handling-patterns skill (centralized error handling patterns)
- Updated agent prompts (reference skills, remove duplication)
- Updated library files (reference skill, maintain custom logic)

**Data Flow**:
1. Agent invocation triggers keyword matching
2. Progressive disclosure loads relevant skill content
3. Agent uses skill guidance for output formatting
4. Downstream agents parse standardized outputs

**Integration Points**:
- Claude Code 2.0+ skill system (progressive disclosure)
- Existing agent prompts (add skill references)
- Existing library docstrings (add skill references)

## Components

Detailed component specifications:

### Component 1: agent-output-formats Skill
- **Purpose**: Provide standardized output format templates for all agent types
- **Responsibilities**:
  - Define research agent output format
  - Define planning agent output format
  - Define implementation agent output format
  - Define review agent output format
  - Provide example outputs
- **Dependencies**: None (standalone skill)
- **Files**:
  - `skills/agent-output-formats/SKILL.md`
  - `skills/agent-output-formats/examples/*.md`

### Component 2: error-handling-patterns Skill
- **Purpose**: Provide standardized error handling patterns for all libraries
- **Responsibilities**:
  - Define exception hierarchy pattern
  - Define error message format
  - Define security audit logging integration
  - Define graceful degradation patterns
  - Provide example error classes
- **Dependencies**: None (standalone skill)
- **Files**:
  - `skills/error-handling-patterns/SKILL.md`
  - `skills/error-handling-patterns/examples/*.py`

### Component 3: Agent Prompt Updates
- **Purpose**: Reference skills instead of duplicating format specifications
- **Responsibilities**:
  - Add skill reference to "Relevant Skills" section
  - Remove redundant "## Output Format" sections
  - Maintain agent-specific guidance
- **Dependencies**: agent-output-formats skill
- **Files**: 15 agent files in `agents/` directory

### Component 4: Library Docstring Updates
- **Purpose**: Reference skill instead of duplicating error patterns
- **Responsibilities**:
  - Add skill reference to module docstring
  - Maintain library-specific error classes
  - Keep custom error handling logic
- **Dependencies**: error-handling-patterns skill
- **Files**: 22 library files in `lib/` directory

## Implementation Plan

Step-by-step implementation guide:

**Phase 1: Create Skills**
1. Create `skills/agent-output-formats/` directory
2. Write SKILL.md with YAML frontmatter and content
3. Create examples/ directory with 4 example files
4. Validate YAML syntax and keywords

**Phase 2: Create Error Handling Skill**
1. Create `skills/error-handling-patterns/` directory
2. Write SKILL.md with YAML frontmatter and content
3. Create examples/ directory with 4 example files
4. Validate YAML syntax and keywords

**Phase 3: Update Agent Prompts**
1. Add skill reference to 15 agent prompts
2. Remove redundant "## Output Format" sections
3. Validate agent prompts still functional
4. Measure token savings

**Phase 4: Update Library Docstrings**
1. Add skill reference to 22 library docstrings
2. Maintain custom error classes
3. Validate libraries still functional
4. Measure token savings

**Phase 5: Run Tests**
1. Run unit tests: `pytest tests/unit/skills/ -v`
2. Run integration tests: `pytest tests/integration/test_full_workflow_with_skills.py -v`
3. Validate all 82 tests pass
4. Validate no regressions

## Risks and Mitigations

Potential issues and how to address them:

- **Risk**: Progressive disclosure doesn't activate skills
  - **Impact**: Medium - Skills not loaded when needed
  - **Mitigation**: Comprehensive keyword list, test activation manually

- **Risk**: Agent outputs change format, breaking downstream parsing
  - **Impact**: High - Workflow failures
  - **Mitigation**: Backward compatibility tests, gradual rollout

- **Risk**: Token savings less than target
  - **Impact**: Low - Still beneficial but less impactful
  - **Mitigation**: Measure with tiktoken, iterate on skill content

- **Risk**: Library error handling changes break error handlers
  - **Impact**: Medium - Error handling failures
  - **Mitigation**: Maintain error class inheritance, test error conditions

- **Risk**: Skills too large, context bloat
  - **Impact**: Low - Progressive disclosure mitigates
  - **Mitigation**: Keep frontmatter < 200 tokens, split large skills
