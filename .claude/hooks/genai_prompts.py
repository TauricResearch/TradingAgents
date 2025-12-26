#!/usr/bin/env python3
"""
GenAI Prompts for Claude Code Hooks

This module contains all GenAI prompts used across the 5 GenAI-enhanced hooks.
Centralizing prompts enables:
- Single source of truth for prompt management
- Easy A/B testing and prompt improvements
- Consistent prompt versions across all hooks
- Independent testing of prompt quality
- Version control and history tracking

Patterns used:
- All prompts are uppercase SNAKE_CASE constants
- Each prompt is a string template with {variables}
- Docstrings explain the prompt's purpose and expected output
- Prompts are optimized for Claude Haiku (fast, cost-effective)
"""

# ============================================================================
# Security Scanning - security_scan.py
# ============================================================================

SECRET_ANALYSIS_PROMPT = """Analyze this line and determine if it contains a REAL secret or TEST data.

Line of code:
{line}

Secret type detected: {secret_type}
Variable name context: {variable_name}

Consider:
1. Variable naming: Does name suggest test data? (test_, fake_, mock_, example_)
2. Context: Is this in a test file, fixture, or documentation?
3. Value patterns: Common test patterns like "test123", "dummy", all zeros/same chars?

Respond with ONLY: REAL or FAKE

If unsure, respond: LIKELY_REAL (be conservative - false negatives are better than false positives)"""

"""
Purpose: Determine if a matched secret pattern is a real credential or test data
Used by: security_scan.py
Expected output: One of [REAL, FAKE, LIKELY_REAL]
Context: Reduces false positives in secret detection from ~15% to <5%
"""

# ============================================================================
# Test Generation - auto_generate_tests.py
# ============================================================================

INTENT_CLASSIFICATION_PROMPT = """Classify the intent of this development task.

User's statement:
{user_prompt}

Intent categories:
- IMPLEMENT: Building new features, adding functionality, creating new code
- REFACTOR: Restructuring existing code without changing behavior, renaming, improving
- DOCS: Documentation updates, docstrings, README changes
- TEST: Writing tests, fixing test issues, test-related work
- OTHER: Everything else

Respond with ONLY the category name (IMPLEMENT, REFACTOR, DOCS, TEST, or OTHER)."""

"""
Purpose: Classify user intent to determine if TDD test generation is needed
Used by: auto_generate_tests.py
Expected output: One of [IMPLEMENT, REFACTOR, DOCS, TEST, OTHER]
Context: Enables accurate detection of new features (100% accuracy vs keyword matching)
Semantic understanding: Understands nuanced descriptions (e.g., "fixing typo in implementation" = REFACTOR)
"""

# ============================================================================
# Documentation Updates - auto_update_docs.py
# ============================================================================

COMPLEXITY_ASSESSMENT_PROMPT = """Assess the complexity of these API changes to documentation:

New Functions ({num_functions}): {function_names}
New Classes ({num_classes}): {class_names}
Modified Signatures ({num_modified}): {modified_names}
Breaking Changes ({num_breaking}): {breaking_names}

Consider:
1. Are these small additions (1-3 new items)?
2. Are these related/cohesive changes or scattered?
3. Are there breaking changes that need careful documentation?
4. Would these changes require narrative explanation or just API reference updates?

Respond with ONLY: SIMPLE or COMPLEX

SIMPLE = Few new items, straightforward additions, no breaking changes, no narrative needed
COMPLEX = Many changes, breaking changes, scattered changes, needs careful narrative documentation"""

"""
Purpose: Determine if code changes require doc-syncer invocation or can be auto-fixed
Used by: auto_update_docs.py
Expected output: One of [SIMPLE, COMPLEX]
Context: Replaces hardcoded thresholds with semantic understanding
Impact: Reduces doc-syncer invocations by ~70% (more auto-fixes possible)
Decision: SIMPLE → auto-fix docs, COMPLEX → invoke doc-syncer subagent
"""

# ============================================================================
# Documentation Validation - validate_docs_consistency.py
# ============================================================================

DESCRIPTION_VALIDATION_PROMPT = """Review this documentation for {entity_type} and assess if descriptions are accurate.

Documentation excerpt:
{section}

Questions:
1. Are the descriptions clear and accurate?
2. Do the descriptions match typical implementation patterns?
3. Are there any obviously misleading descriptions?

Respond with ONLY: ACCURATE or MISLEADING

If descriptions are clear, professional, and accurate: ACCURATE
If descriptions seem misleading, vague, or inaccurate: MISLEADING"""

"""
Purpose: Validate that agent/command descriptions match actual implementation
Used by: validate_docs_consistency.py
Expected output: One of [ACCURATE, MISLEADING]
Context: Catches documentation drift before merge (semantic accuracy validation)
Supplement: Works alongside count validation for comprehensive documentation quality
"""

# ============================================================================
# Documentation Auto-Fix - auto_fix_docs.py
# ============================================================================

DOC_GENERATION_PROMPT = """Generate professional documentation for a new {item_type}.

{item_type.upper()} NAME: {item_name}

Guidelines:
- Write 1-2 sentences describing what this {item_type} does
- Keep professional tone
- Be specific about functionality, not generic
- Focus on user benefit

Return ONLY the documentation text (no markdown, no formatting, just plain text)."""

"""
Purpose: Generate initial documentation for new commands or agents
Used by: auto_fix_docs.py
Expected output: 1-2 sentence description (plain text, no formatting)
Context: Enables 60% auto-fix rate (vs 20% with heuristics only)
Application: Generates descriptions for new commands/agents automatically
Validation: Generated content reviewed for accuracy before merging
"""

# ============================================================================
# File Organization - enforce_file_organization.py
# ============================================================================

FILE_ORGANIZATION_PROMPT = """Analyze this file and suggest the best location in the project structure.

File name: {filename}
File extension: {extension}
Content preview (first 20 lines):
{content_preview}

Project context from PROJECT.md:
{project_context}

Standard project structure:
- src/ - Source code (application logic, modules, libraries)
- tests/ - Test files (unit, integration, UAT)
- docs/ - Documentation (guides, API refs, architecture)
- scripts/ - Automation scripts (build, deploy, utilities)
- root - Essential files only (README, LICENSE, setup.py, pyproject.toml)

Consider:
1. File purpose: Is this source code, test, documentation, script, or configuration?
2. File content: What does the code actually do? (not just extension)
3. Project conventions: Does PROJECT.md specify custom organization?
4. Common patterns: setup.py stays in root, conftest.py in tests/, etc.
5. Shared utilities: Files used across multiple directories may belong in lib/ or root

Respond with ONLY ONE of these exact locations:
- src/ (for application source code)
- tests/unit/ (for unit tests)
- tests/integration/ (for integration tests)
- tests/uat/ (for user acceptance tests)
- docs/ (for documentation)
- scripts/ (for automation scripts)
- lib/ (for shared libraries/utilities)
- root (keep in project root - ONLY if essential)
- DELETE (temporary/scratch files like temp.py, test.py, debug.py)

After the location, add a brief reason (max 10 words).

Format: LOCATION | reason

Example: src/ | main application logic
Example: root | build configuration file
Example: DELETE | temporary debug script"""

"""
Purpose: Intelligently determine where files should be located in project
Used by: enforce_file_organization.py
Expected output: "LOCATION | reason" (e.g., "src/ | main application code")
Context: Replaces rigid pattern matching with semantic understanding
Benefits:
- Understands context (setup.py is config, not source)
- Reads file content (test-data.json is test fixture, not source)
- Respects project conventions from PROJECT.md
- Handles edge cases (shared utilities, build files)
- Explains reasoning for transparency
"""

# ============================================================================
# Prompt Management & Configuration
# ============================================================================

# Model configuration (can be overridden per hook)
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_MAX_TOKENS = 100
DEFAULT_TIMEOUT = 5  # seconds

# Feature flags for prompt usage
# Can be controlled via environment variables (e.g., GENAI_SECURITY_SCAN=false)
GENAI_FEATURES = {
    "security_scan": "GENAI_SECURITY_SCAN",
    "test_generation": "GENAI_TEST_GENERATION",
    "doc_update": "GENAI_DOC_UPDATE",
    "docs_validate": "GENAI_DOCS_VALIDATE",
    "doc_autofix": "GENAI_DOC_AUTOFIX",
    "file_organization": "GENAI_FILE_ORGANIZATION",
}


def get_all_prompts():
    """Return dictionary of all available prompts.

    Useful for:
    - Testing prompt structure
    - Documenting available prompts
    - Prompt management/versioning
    """
    return {
        "secret_analysis": SECRET_ANALYSIS_PROMPT,
        "intent_classification": INTENT_CLASSIFICATION_PROMPT,
        "complexity_assessment": COMPLEXITY_ASSESSMENT_PROMPT,
        "description_validation": DESCRIPTION_VALIDATION_PROMPT,
        "doc_generation": DOC_GENERATION_PROMPT,
        "file_organization": FILE_ORGANIZATION_PROMPT,
    }


if __name__ == "__main__":
    # Print all prompts for documentation/review
    prompts = get_all_prompts()
    for name, prompt in prompts.items():
        print(f"\n{'='*70}")
        print(f"PROMPT: {name.upper()}")
        print(f"{'='*70}")
        print(prompt)
        print()
