"""Single import entry point for the (not yet implemented) time policy module.

A later contract rename only has to change the import here.
"""

try:
    from egta.evidence.time_policy import TimeVerdict, is_admissible  # noqa: F401
except ModuleNotFoundError as exc:
    TARGET_AVAILABLE = False
    MISSING_REASON = str(exc)
    raise
else:
    TARGET_AVAILABLE = True
    MISSING_REASON = ""
