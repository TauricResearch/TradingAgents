---
name: docs
description: Generate or update Google-style docstrings for public functions and classes
allowed-tools: Read, Edit, Glob
---

Generate or update docstrings for $ARGUMENTS (file or module path).

**Rules:**
- Use **Google-style** docstrings.
- Cover all public functions and classes (skip `_private` unless asked).
- Include: one-line summary, `Args:`, `Returns:`, `Raises:` where applicable.
- Do not describe *how* the code works — describe *what* it does and *why*.
- Do not alter logic, signatures, or formatting outside of docstrings.

**Template:**
```python
def my_function(arg1: str, arg2: int = 0) -> bool:
    """One-line summary of what the function does.

    Args:
        arg1: Description of arg1.
        arg2: Description of arg2. Defaults to 0.

    Returns:
        True if successful, False otherwise.

    Raises:
        ValueError: If arg1 is empty.
    """
```

After writing, briefly list which functions/classes were updated.
