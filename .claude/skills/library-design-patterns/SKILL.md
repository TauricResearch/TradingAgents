---
name: library-design-patterns
version: 1.0.0
type: knowledge
description: Standardized library design patterns for autonomous-dev including two-tier design, progressive enhancement, non-blocking enhancements, and security-first architecture. Use when creating or refactoring Python libraries.
keywords: library, module, two-tier, progressive enhancement, cli, docstring, api, reusability, separation of concerns, graceful degradation, security validation, CWE-22, CWE-59, CWE-117
auto_activate: true
allowed-tools: [Read]
---

# Library Design Patterns Skill

Standardized architectural patterns for Python library design in the autonomous-dev plugin ecosystem. Promotes reusability, testability, security, and maintainability through proven design patterns.

## When This Skill Activates

- Creating new Python libraries
- Refactoring existing libraries
- Designing reusable components
- Implementing CLI interfaces
- Validating library architecture
- Keywords: "library", "module", "two-tier", "progressive enhancement", "cli", "api"

---

## Core Design Patterns

### 1. Two-Tier Design Pattern

**Definition**: Separate core logic (library) from user interface (CLI script) to maximize reusability and testability.

**Structure**:
- **Tier 1 (Core Library)**: Pure Python module with business logic, no I/O assumptions
- **Tier 2 (CLI Interface)**: Thin wrapper script for command-line usage, handles argparse and user interaction

**Benefits**:
- Reusability: Core logic can be imported and reused in other contexts
- Testability: Pure functions are easier to unit test without mocking I/O
- Separation of Concerns: Business logic separate from presentation layer
- Maintainability: Changes to CLI don't affect core logic and vice versa

**Example**:
```
plugin_updater.py       # Core library - pure logic
update_plugin.py        # CLI interface - user interaction
```

**When to Use**:
- Any library that might be used both programmatically and from command line
- Complex business logic that needs thorough testing
- Features that may be integrated into multiple workflows

**See**: `docs/two-tier-design.md`, `templates/library-template.py`, `examples/two-tier-example.py`

---

### 2. Progressive Enhancement Pattern

**Definition**: Start with simple validation (strings), progressively add stronger validation (Path objects, whitelists) without breaking existing code.

**Progression**:
1. **Level 1 (Strings)**: Accept string paths, basic validation
2. **Level 2 (Path Objects)**: Convert to pathlib.Path, add existence checks
3. **Level 3 (Whitelist Validation)**: Restrict to approved directories, prevent path traversal

**Benefits**:
- Graceful Degradation: Works in degraded environments (missing dependencies)
- Backward Compatibility: Existing code continues to work
- Security Hardening: Stronger validation added over time without breaking changes
- Flexibility: Can operate in various security contexts

**Example**:
```python
# Level 1: Accept strings
def process(file: str) -> Result:
    return _process_path(file)

# Level 2: Upgrade to Path objects
def process(file: Union[str, Path]) -> Result:
    path = Path(file) if isinstance(file, str) else file
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return _process_path(path)

# Level 3: Add whitelist validation
def process(file: Union[str, Path], *, allowed_dirs: Optional[List[Path]] = None) -> Result:
    path = Path(file) if isinstance(file, str) else file
    if allowed_dirs and not any(path.is_relative_to(d) for d in allowed_dirs):
        raise SecurityError(f"Path outside allowed directories: {path}")
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return _process_path(path)
```

**See**: `docs/progressive-enhancement.md`, `examples/progressive-enhancement-example.py`

---

### 3. Non-Blocking Enhancement Pattern

**Definition**: Design enhancements (features beyond core functionality) to never block core operations. If enhancement fails, core feature should still succeed.

**Principles**:
- Core operations must complete even if enhancements fail
- Enhancements wrapped in try/except with graceful degradation
- Log enhancement failures but don't raise exceptions
- Provide manual fallback instructions if enhancement unavailable

**Benefits**:
- Reliability: Core features always work
- Resilience: Graceful handling of missing dependencies or permissions
- User Experience: Clear feedback when enhancements unavailable
- Maintainability: Easier to add/remove enhancements without breaking core

**Example**:
```python
def implement_feature(spec: FeatureSpec) -> Result:
    # Core operation (must succeed)
    result = _implement_core_logic(spec)

    # Enhancement: Auto-commit (may fail)
    try:
        if auto_commit_enabled():
            commit_changes(result.files)
    except Exception as e:
        logger.warning(f"Auto-commit failed: {e}")
        logger.info("Manual fallback: git add . && git commit")

    # Feature succeeded regardless of enhancement
    return result
```

**See**: `docs/non-blocking-enhancements.md`, `examples/non-blocking-example.py`

---

### 4. Security-First Design Pattern

**Definition**: Build security validation into library architecture from the start. Validate all inputs, sanitize outputs, audit all operations.

**Core Principles**:
- **Input Validation**: Validate all user input against expected types and ranges
- **Path Traversal Prevention (CWE-22)**: Use whitelists, resolve paths, check boundaries
- **Command Injection Prevention (CWE-78)**: Use subprocess arrays, avoid shell=True
- **Log Injection Prevention (CWE-117)**: Sanitize all log messages, escape newlines
- **Audit Logging**: Log security-relevant operations to audit trail

**Security Layers**:
1. **Input Validation**: Type checking, range validation, format verification
2. **Path Validation**: Whitelist checking, symlink resolution, boundary verification
3. **Command Validation**: Argument array construction, shell prevention
4. **Output Sanitization**: Log message escaping, error message filtering
5. **Audit Trail**: Security operations logged to `logs/security_audit.log`

**Example**:
```python
from plugins.autonomous_dev.lib.security_utils import validate_path, audit_log

def process_file(filepath: str, *, allowed_dirs: List[Path]) -> None:
    """Process file with security validation.

    Security:
        - CWE-22 Prevention: Path traversal validation
        - CWE-117 Prevention: Sanitized audit logging
    """
    # Validate path (CWE-22 prevention)
    safe_path = validate_path(
        filepath,
        must_exist=True,
        allowed_dirs=allowed_dirs
    )

    # Audit security operation (CWE-117 safe)
    audit_log("file_processed", filepath=str(safe_path))

    # Process file
    return _process(safe_path)
```

**See**: `docs/security-patterns.md`, `examples/security-validation-example.py`

---

### 5. Docstring Standards Pattern

**Definition**: Consistent Google-style docstrings with comprehensive documentation for all public APIs.

**Structure**:
```python
def function(arg1: Type1, arg2: Type2, *, kwarg: Type3 = default) -> ReturnType:
    """One-line summary (imperative mood).

    Optional detailed description explaining behavior, edge cases,
    and important implementation details.

    Args:
        arg1: Description of first argument
        arg2: Description of second argument
        kwarg: Description of keyword argument (default: value)

    Returns:
        Description of return value and its structure

    Raises:
        ExceptionType: When and why this exception is raised
        AnotherException: Another error condition

    Example:
        >>> result = function("value1", "value2", kwarg="custom")
        >>> print(result.status)
        'success'

    Security:
        - CWE-XX: How this function prevents security issue
        - Validation: What input validation is performed

    See:
        - Related function or documentation
        - External reference or skill
    """
```

**Required Sections**:
- Summary line (one line, imperative mood)
- Args section (all parameters documented)
- Returns section (return value structure)
- Raises section (all exceptions)
- Security section (for security-sensitive functions)

**See**: `docs/docstring-standards.md`, `templates/docstring-template.py`

---

## Usage Guidelines

### For Library Authors

When creating or refactoring libraries:

1. **Use two-tier design** for any library with CLI interface
2. **Apply progressive enhancement** for validation and security
3. **Make enhancements non-blocking** so core features always work
4. **Build security in from start** with input validation and audit logging
5. **Document thoroughly** using Google-style docstrings

### For Claude

When creating or analyzing libraries:

1. **Load this skill** when keywords match ("library", "module", "two-tier", etc.)
2. **Follow design patterns** for consistent architecture
3. **Validate security** using CWE prevention patterns
4. **Check docstrings** against standards
5. **Reference templates** in `templates/` directory

### Token Savings

By centralizing library design patterns in this skill:

- **Before**: ~40 tokens per library for inline pattern documentation
- **After**: ~10 tokens for skill reference comment
- **Savings**: ~30 tokens per library
- **Total**: ~1,200 tokens across 40 libraries (5-6% reduction)

---

## Progressive Disclosure

This skill uses Claude Code 2.0+ progressive disclosure architecture:

- **Metadata** (frontmatter): Always loaded (~200 tokens)
- **Full content**: Loaded only when keywords match
- **Result**: Efficient context usage, scales to 100+ skills

When you use terms like "library design", "two-tier", "progressive enhancement", or "security validation", Claude Code automatically loads the full skill content to provide detailed guidance.

---

## Templates and Examples

### Templates (reusable code structures)
- `templates/library-template.py`: Two-tier library template
- `templates/cli-template.py`: CLI interface template
- `templates/docstring-template.py`: Comprehensive docstring examples

### Examples (real implementations)
- `examples/two-tier-example.py`: plugin_updater.py pattern
- `examples/progressive-enhancement-example.py`: security_utils.py pattern
- `examples/security-validation-example.py`: Path validation patterns

### Documentation (detailed guides)
- `docs/two-tier-design.md`: Two-tier architecture guide
- `docs/progressive-enhancement.md`: Progressive validation guide
- `docs/security-patterns.md`: Security-first design guide
- `docs/docstring-standards.md`: Docstring formatting standards

---

## Cross-References

This skill integrates with other autonomous-dev skills:

- **error-handling-patterns**: Exception handling and recovery strategies
- **python-standards**: Python code style and type hints
- **security-patterns**: Comprehensive security guidance (OWASP, CWE)
- **testing-guide**: Unit testing and TDD for libraries
- **documentation-guide**: API documentation standards

**See**: `skills/error-handling-patterns/`, `skills/python-standards/`, `skills/security-patterns/`

---

## Maintenance

This skill should be updated when:

- New library design patterns emerge in the codebase
- Security best practices evolve
- Python language features enable better patterns
- Common anti-patterns are identified

**Last Updated**: 2025-11-16 (Phase 8.8 - Initial creation)
**Version**: 1.0.0
