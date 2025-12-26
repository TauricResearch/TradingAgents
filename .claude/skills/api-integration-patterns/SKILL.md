---
name: api-integration-patterns
version: 1.0.0
type: knowledge
description: API integration patterns for autonomous-dev including subprocess safety, GitHub CLI integration, retry logic, authentication, rate limiting, and timeout handling. Use when integrating external APIs or CLI tools.
keywords: api, subprocess, github, gh cli, retry, authentication, rate limiting, timeout, command injection, CWE-78, integration
auto_activate: true
allowed-tools: [Read]
---

# API Integration Patterns Skill

Standardized patterns for integrating external APIs and CLI tools in the autonomous-dev plugin ecosystem. Focuses on safety, reliability, and security when calling external services.

## When This Skill Activates

- Integrating external APIs (GitHub, etc.)
- Executing subprocess commands safely
- Implementing retry logic
- Handling authentication
- Managing rate limits
- Keywords: "api", "subprocess", "github", "gh cli", "retry", "authentication"

---

## Core Patterns

### 1. Subprocess Safety (CWE-78 Prevention)

**Definition**: Execute external commands safely without command injection vulnerabilities.

**Critical Rules**:
- ✅ ALWAYS use argument arrays: `["gh", "issue", "create"]`
- ❌ NEVER use shell=True with user input
- ✅ ALWAYS whitelist allowed commands
- ✅ ALWAYS set timeouts

**Pattern**:
```python
import subprocess
from typing import List

def safe_subprocess(
    command: List[str],
    *,
    allowed_commands: List[str],
    timeout: int = 30
) -> subprocess.CompletedProcess:
    """Execute subprocess with CWE-78 prevention.

    Args:
        command: Command and arguments as list (NOT string!)
        allowed_commands: Whitelist of allowed commands
        timeout: Maximum execution time in seconds

    Returns:
        Completed subprocess result

    Raises:
        SecurityError: If command not in whitelist
        subprocess.TimeoutExpired: If timeout exceeded

    Security:
        - CWE-78 Prevention: Argument arrays (no shell injection)
        - Command Whitelist: Only approved commands
        - Timeout: DoS prevention

    Example:
        >>> result = safe_subprocess(
        ...     ["gh", "issue", "create", "--title", user_title],
        ...     allowed_commands=["gh", "git"]
        ... )
    """
    # Whitelist validation
    if command[0] not in allowed_commands:
        raise SecurityError(f"Command not allowed: {command[0]}")

    # Execute with argument array (NEVER shell=True!)
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True,
        shell=False  # CRITICAL
    )
```

**See**: `docs/subprocess-safety.md`, `examples/safe-subprocess-example.py`

---

### 2. GitHub CLI (gh) Integration

**Definition**: Standardized patterns for GitHub operations via gh CLI.

**Pattern**:
```python
def create_github_issue(
    title: str,
    body: str,
    *,
    labels: Optional[List[str]] = None,
    timeout: int = 30
) -> str:
    """Create GitHub issue using gh CLI.

    Args:
        title: Issue title
        body: Issue body (markdown)
        labels: Issue labels (default: None)
        timeout: Command timeout in seconds

    Returns:
        Issue URL

    Raises:
        subprocess.CalledProcessError: If gh command fails
        RuntimeError: If gh CLI not installed

    Example:
        >>> url = create_github_issue(
        ...     "Bug: Login fails",
        ...     "Login button doesn't work",
        ...     labels=["bug", "p1"]
        ... )
    """
    # Build gh command (argument array)
    cmd = ["gh", "issue", "create", "--title", title, "--body", body]

    if labels:
        for label in labels:
            cmd.extend(["--label", label])

    # Execute safely
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True,
        shell=False
    )

    # Extract URL from output
    return result.stdout.strip()
```

**See**: `docs/github-cli-integration.md`, `examples/github-issue-example.py`

---

### 3. Retry Logic with Exponential Backoff

**Definition**: Automatically retry failed API calls with exponential backoff.

**Pattern**:
```python
import time
from typing import Callable, TypeVar, Any

T = TypeVar('T')

def retry_with_backoff(
    func: Callable[..., T],
    *,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0
) -> T:
    """Retry function with exponential backoff.

    Args:
        func: Function to retry
        max_attempts: Maximum retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds

    Returns:
        Function result

    Raises:
        Exception: Last exception if all retries fail

    Example:
        >>> result = retry_with_backoff(
        ...     lambda: api_call(),
        ...     max_attempts=5,
        ...     base_delay=2.0
        ... )
    """
    last_exception = None

    for attempt in range(max_attempts):
        try:
            return func()
        except Exception as e:
            last_exception = e

            if attempt < max_attempts - 1:
                # Exponential backoff: 1s, 2s, 4s, 8s, ...
                delay = min(base_delay * (2 ** attempt), max_delay)
                time.sleep(delay)

    raise last_exception
```

**See**: `docs/retry-logic.md`, `templates/retry-decorator-template.py`

---

### 4. Authentication Patterns

**Definition**: Secure handling of API credentials and tokens.

**Principles**:
- Use environment variables for credentials
- Never hardcode API keys
- Never log credentials
- Validate credentials before use

**Pattern**:
```python
import os
from typing import Optional

def get_github_token() -> str:
    """Get GitHub token from environment.

    Returns:
        GitHub personal access token

    Raises:
        RuntimeError: If token not found

    Security:
        - Environment Variables: Never hardcode tokens
        - Validation: Check token format
        - No Logging: Never log credentials
    """
    token = os.getenv("GITHUB_TOKEN")

    if not token:
        raise RuntimeError(
            "GITHUB_TOKEN not found in environment\n"
            "Set with: export GITHUB_TOKEN=your_token\n"
            "Or add to .env file"
        )

    # Validate token format (basic check)
    if not token.startswith("ghp_") and not token.startswith("github_pat_"):
        raise ValueError("Invalid GitHub token format")

    return token
```

**See**: `docs/authentication-patterns.md`, `templates/github-api-template.py`

---

### 5. Rate Limiting and Quota Management

**Definition**: Handle API rate limits gracefully.

**Pattern**:
```python
import time
from datetime import datetime, timedelta

class RateLimiter:
    """Simple rate limiter for API calls.

    Attributes:
        max_calls: Maximum calls per window
        window_seconds: Time window in seconds
    """

    def __init__(self, max_calls: int, window_seconds: int):
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self.calls = []

    def wait_if_needed(self) -> None:
        """Wait if rate limit would be exceeded."""
        now = datetime.now()
        cutoff = now - timedelta(seconds=self.window_seconds)

        # Remove old calls outside window
        self.calls = [c for c in self.calls if c > cutoff]

        # Wait if at limit
        if len(self.calls) >= self.max_calls:
            oldest = self.calls[0]
            wait_until = oldest + timedelta(seconds=self.window_seconds)
            wait_seconds = (wait_until - now).total_seconds()

            if wait_seconds > 0:
                time.sleep(wait_seconds)

            # Retry removal after wait
            self.calls = [c for c in self.calls if c > cutoff]

        # Record this call
        self.calls.append(now)
```

**See**: `docs/rate-limiting.md`, `examples/github-api-example.py`

---

## Usage Guidelines

### For Library Authors

When integrating external APIs:

1. **Use subprocess safely** with argument arrays
2. **Whitelist commands** to prevent injection
3. **Add retry logic** for transient failures
4. **Handle authentication** securely via environment
5. **Respect rate limits** to avoid quota exhaustion

### For Claude

When creating API integrations:

1. **Load this skill** when keywords match
2. **Follow safety patterns** for subprocess
3. **Implement retries** for reliability
4. **Reference templates** for common patterns

### Token Savings

By centralizing API integration patterns:

- **Before**: ~45 tokens per library for subprocess safety docs
- **After**: ~10 tokens for skill reference
- **Savings**: ~35 tokens per library
- **Total**: ~280 tokens across 8 libraries (3-4% reduction)

---

## Progressive Disclosure

This skill uses Claude Code 2.0+ progressive disclosure architecture:

- **Metadata** (frontmatter): Always loaded (~170 tokens)
- **Full content**: Loaded only when keywords match
- **Result**: Efficient context usage

---

## Templates and Examples

### Templates
- `templates/subprocess-executor-template.py`: Safe subprocess execution
- `templates/retry-decorator-template.py`: Retry logic decorator
- `templates/github-api-template.py`: GitHub API integration

### Examples
- `examples/github-issue-example.py`: Issue creation via gh CLI
- `examples/github-pr-example.py`: PR creation patterns
- `examples/safe-subprocess-example.py`: Command execution safety

### Documentation
- `docs/subprocess-safety.md`: CWE-78 prevention
- `docs/github-cli-integration.md`: gh CLI patterns
- `docs/retry-logic.md`: Retry strategies
- `docs/authentication-patterns.md`: Credential handling

---

## Cross-References

This skill integrates with other autonomous-dev skills:

- **library-design-patterns**: Security-first design
- **security-patterns**: CWE-78 prevention
- **error-handling-patterns**: Retry and recovery

---

## Maintenance

Update when:

- New API integration patterns emerge
- Security best practices evolve
- gh CLI adds new features

**Last Updated**: 2025-11-16 (Phase 8.8 - Initial creation)
**Version**: 1.0.0
