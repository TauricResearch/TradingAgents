---
name: security-patterns
version: 1.0.0
type: knowledge
description: Security best practices, API key management, input validation. Use when handling secrets, user input, or security-sensitive code.
keywords: security, api key, secret, validation, injection, owasp
auto_activate: true
allowed-tools: [Read]
---

# Security Patterns Skill

Security best practices and patterns for [PROJECT_NAME] project.

## When This Activates
- API key handling
- User input validation
- File operations
- Security-sensitive code
- Keywords: "security", "api key", "secret", "validate", "input"

## API Keys & Secrets

### Environment Variables (REQUIRED)
```python
import os
from pathlib import Path
from dotenv import load_dotenv


# ✅ CORRECT: Load from environment
load_dotenv()
api_key = os.getenv("ANTHROPIC_API_KEY")

if not api_key:
    raise ValueError(
        "ANTHROPIC_API_KEY not set\n"
        "Add to .env file: ANTHROPIC_API_KEY=sk-ant-...\n"
        "See: docs/guides/setup.md"
    )


# ❌ WRONG: Hardcoded secret
api_key = "sk-ant-1234567890abcdef"  # NEVER DO THIS!
```

### .env File Setup
```bash
# .env (must be in .gitignore!)
ANTHROPIC_API_KEY=sk-ant-your-key-here
OPENAI_API_KEY=sk-your-key-here
HUGGINGFACE_TOKEN=hf_your-token-here
```

### .gitignore MUST Include
```
# .gitignore
.env
.env.local
.env.*.local
*.key
*.pem
secrets/
```

### Secure API Key Validation
```python
import re


def validate_anthropic_key(api_key: str) -> bool:
    """Validate Anthropic API key format.

    Args:
        api_key: API key to validate

    Returns:
        True if valid format

    Raises:
        ValueError: If invalid format
    """
    if not api_key:
        raise ValueError("API key is empty")

    if not api_key.startswith("sk-ant-"):
        raise ValueError(
            "Invalid Anthropic API key format\n"
            "Expected: sk-ant-...\n"
            "See: docs/guides/api-keys.md"
        )

    # Check length (Anthropic keys are ~40 chars)
    if len(api_key) < 20:
        raise ValueError("API key too short")

    return True
```

## Input Validation

### Path Traversal Prevention
```python
from pathlib import Path


def load_safe_file(filename: str, base_dir: Path) -> str:
    """Load file with path traversal protection.

    Args:
        filename: Requested filename
        base_dir: Base directory (files must be within this)

    Returns:
        File contents

    Raises:
        ValueError: If path traversal detected
        FileNotFoundError: If file doesn't exist
    """
    # Resolve to absolute path
    base_dir = base_dir.resolve()
    file_path = (base_dir / filename).resolve()

    # Check file is within base_dir (prevents ../ attacks)
    if not file_path.is_relative_to(base_dir):
        raise ValueError(
            f"Invalid file path: {filename}\n"
            f"Path traversal detected (../ not allowed)\n"
            f"Allowed directory: {base_dir}"
        )

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    return file_path.read_text()


# ✅ SAFE: Validates path
content = load_safe_file("config.yaml", Path("/data"))

# ❌ BLOCKED: Path traversal attempt
content = load_safe_file("../../etc/passwd", Path("/data"))  # ValueError!
```

### Command Injection Prevention
```python
import subprocess
import shlex


# ✅ CORRECT: Shell=False with list arguments
def run_command_safe(command: str, args: list[str]) -> str:
    """Run command safely without shell injection.

    Args:
        command: Command to run
        args: List of arguments

    Returns:
        Command output
    """
    result = subprocess.run(
        [command] + args,  # List, not string
        shell=False,  # CRITICAL: Never use shell=True
        capture_output=True,
        text=True,
        timeout=30
    )

    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {result.stderr}")

    return result.stdout


# ✅ SAFE: No injection possible
output = run_command_safe("ls", ["-la", "/tmp"])


# ❌ WRONG: Shell injection risk
def run_command_unsafe(user_input: str):
    # User could input: "; rm -rf /"
    subprocess.run(f"ls {user_input}", shell=True)  # NEVER DO THIS!
```

### SQL Injection Prevention
```python
import sqlite3


# ✅ CORRECT: Parameterized queries
def get_user_safe(db, username: str):
    """Safe database query with parameters."""
    cursor = db.cursor()
    cursor.execute(
        "SELECT * FROM users WHERE username = ?",  # Parameterized
        (username,)
    )
    return cursor.fetchone()


# ❌ WRONG: String interpolation
def get_user_unsafe(db, username):
    # User could input: "admin' OR '1'='1"
    cursor = db.cursor()
    cursor.execute(f"SELECT * FROM users WHERE username = '{username}'")
```

## File Operations Security

### Secure File Permissions
```python
from pathlib import Path
import os


def create_secure_file(path: Path, content: str) -> None:
    """Create file with restricted permissions.

    Args:
        path: File path
        content: File content
    """
    # Write file
    path.write_text(content)

    # Set permissions to owner-only (0o600 = rw-------)
    path.chmod(0o600)


def create_secure_directory(path: Path) -> None:
    """Create directory with restricted permissions."""
    path.mkdir(parents=True, exist_ok=True)

    # Owner only (0o700 = rwx------)
    path.chmod(0o700)


# Usage
cache_dir = Path.home() / ".cache" / "[project_name]"
create_secure_directory(cache_dir)

config_file = cache_dir / "api_key.txt"
create_secure_file(config_file, api_key)
```

### File Upload Validation
```python
from pathlib import Path


ALLOWED_EXTENSIONS = {".json", ".yaml", ".yml", ".txt", ".csv"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


def validate_upload(file_path: Path) -> None:
    """Validate uploaded file.

    Args:
        file_path: Path to uploaded file

    Raises:
        ValueError: If file invalid
    """
    # Check extension
    if file_path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Invalid file type: {file_path.suffix}\n"
            f"Allowed: {ALLOWED_EXTENSIONS}"
        )

    # Check size
    size = file_path.stat().st_size
    if size > MAX_FILE_SIZE:
        raise ValueError(
            f"File too large: {size / 1024 / 1024:.1f}MB\n"
            f"Maximum: {MAX_FILE_SIZE / 1024 / 1024}MB"
        )

    # Check not executable
    if os.access(file_path, os.X_OK):
        raise ValueError("Executable files not allowed")
```

## Cryptographic Operations

### Secure Random Generation
```python
import secrets


# ✅ CORRECT: Cryptographically secure
def generate_token() -> str:
    """Generate secure random token."""
    return secrets.token_hex(32)  # 64 characters


def generate_session_id() -> str:
    """Generate secure session ID."""
    return secrets.token_urlsafe(32)


# ❌ WRONG: Not cryptographically secure
import random
token = str(random.randint(0, 999999))  # NEVER for security!
```

### Password Hashing (if needed)
```python
import hashlib
import secrets


def hash_password(password: str) -> tuple[str, str]:
    """Hash password with salt.

    Args:
        password: Plain text password

    Returns:
        Tuple of (salt, hashed_password)
    """
    # Generate random salt
    salt = secrets.token_hex(16)

    # Hash with salt
    hashed = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000  # iterations
    )

    return salt, hashed.hex()


def verify_password(
    password: str,
    salt: str,
    expected_hash: str
) -> bool:
    """Verify password against hash."""
    hashed = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    )

    return hashed.hex() == expected_hash
```

## Model Download Security

### Validate HuggingFace Repo
```python
import re


def validate_repo_id(repo_id: str) -> bool:
    """Validate HuggingFace repository ID.

    Args:
        repo_id: Repository ID (org/model)

    Returns:
        True if valid

    Raises:
        ValueError: If invalid format
    """
    # Expected format: org/model-name
    pattern = r'^[a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+$'

    if not re.match(pattern, repo_id):
        raise ValueError(
            f"Invalid repo ID: {repo_id}\n"
            f"Expected format: organization/model-name\n"
            f"Example: [model_repo]/Llama-3.2-1B-Instruct-4bit"
        )

    # Prevent malicious patterns
    if '..' in repo_id or '/' * 2 in repo_id:
        raise ValueError("Invalid characters in repo ID")

    return True


# ✅ SAFE
validate_repo_id("[model_repo]/Llama-3.2-1B-Instruct-4bit")

# ❌ BLOCKED
validate_repo_id("../../../etc/passwd")  # ValueError!
```

## Logging Security

### Never Log Secrets
```python
import logging


# ✅ CORRECT: Redact sensitive data
def log_api_call(api_key: str, endpoint: str):
    """Log API call without exposing key."""
    masked_key = api_key[:7] + "***" + api_key[-4:]
    logging.info(f"API call to {endpoint} with key {masked_key}")


# ❌ WRONG: Logs full API key
def log_api_call_unsafe(api_key, endpoint):
    logging.info(f"API call: {endpoint} | Key: {api_key}")  # NEVER!
```

## Dependencies Security

### Check for Vulnerabilities
```bash
# Install safety
pip install safety

# Check dependencies
safety check

# Check specific requirements
safety check -r requirements.txt

# Alternative: pip-audit
pip install pip-audit
pip-audit
```

## Security Checklist

### Code Review
- [ ] No hardcoded API keys/secrets
- [ ] All secrets in .env (gitignored)
- [ ] .env file in .gitignore
- [ ] Input validation on user data
- [ ] Path traversal prevention
- [ ] No shell=True in subprocess
- [ ] Parameterized database queries
- [ ] Secure file permissions
- [ ] Cryptographically secure random
- [ ] No secrets in logs
- [ ] Dependencies scanned for vulnerabilities

### File Operations
- [ ] Validate file extensions
- [ ] Check file size limits
- [ ] Prevent path traversal
- [ ] Restrict file permissions
- [ ] Validate before deserialize

### API Operations
- [ ] API keys from environment
- [ ] Keys validated before use
- [ ] Keys masked in logs
- [ ] Rate limiting considered
- [ ] Error messages don't expose secrets

## Common Vulnerabilities (OWASP Top 10)

1. **Injection** → Use parameterized queries
2. **Authentication** → Use secure tokens (secrets module)
3. **Sensitive Data** → Never hardcode, use .env
4. **XXE** → Disable external entities in XML
5. **Access Control** → Validate file paths
6. **Security Config** → Secure defaults
7. **XSS** → Sanitize output (if web)
8. **Deserialization** → Don't unpickle untrusted data
9. **Components** → Keep dependencies updated
10. **Logging** → Don't log secrets

## Key Takeaways

1. **Never hardcode secrets** - Use environment variables
2. **Validate all inputs** - User data, file paths, commands
3. **Prevent path traversal** - Use `is_relative_to()`
4. **No shell=True** - Use list arguments with subprocess
5. **Parameterized queries** - Never string interpolation
6. **Secure random** - Use `secrets` module
7. **Restrict permissions** - Files 0o600, dirs 0o700
8. **Mask secrets in logs** - Show only first/last few chars
9. **Scan dependencies** - Use safety/pip-audit
10. **.gitignore secrets** - .env, *.key, *.pem
