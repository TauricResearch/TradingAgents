"""OpenSandbox/E2B isolation wrapper — safe code exec with fallback."""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

_SECRET_KEYS = ("ALPACA_API_KEY", "ALPACA_SECRET_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "FRED_API_KEY", "BYMA_TOKEN", "ALPHA_VANTAGE_API_KEY")
_GENERIC_RE = r"api[_-]?key|secret|token|password"
_SECRET_RE = re.compile(r"(" + "|".join(_SECRET_KEYS) + r"|" + _GENERIC_RE + r")(\s*[:=]\s*)(['\"]?)([^'\"\s,;\)\}\n]+)(['\"]?)", re.IGNORECASE)
_BLOCKED_RE = re.compile(r"(__import__|chr\s*\(|getattr\s*\(|getattr|eval\s*\(|exec\s*\(|open\s*\(|socket|subprocess|os\.system|os\.popen|urllib|requests\.)")


def _redact_code(code: str) -> str:
    if not code:
        return code
    def _repl(m: re.Match) -> str:
        key, sep, q1, _, q2 = m.group(1), m.group(2), m.group(3) or "", m.group(4), m.group(5) or ""
        if q1 or q2:
            return f"{key}{sep}{q1}***{q2}"
        return f'{key}{sep}"***"'
    return _SECRET_RE.sub(_repl, code)


def run_in_sandbox(code: str, timeout: int = 30) -> dict:
    """Execute Python code in isolation; returns {success, output, error}."""
    redacted = _redact_code(code)
    # Try E2B
    try:
        import e2b  # type: ignore
        sb = e2b.Sandbox(timeout=timeout)  # type: ignore[attr-defined]
        try:
            result = sb.run_code(redacted)  # type: ignore
            text = getattr(result, "text", None) or getattr(result, "output", "") or str(result)
            err = getattr(result, "stderr", "") or ""
            return {"success": not err, "output": _redact_code(str(text)), "error": _redact_code(str(err))}
        finally:
            try:
                sb.kill()  # type: ignore
            except Exception:
                pass
    except ImportError:
        pass
    except Exception as exc:
        return {"success": False, "output": "", "error": _redact_code(f"E2B error: {exc}")}
    # Try boxlite
    try:
        import boxlite  # type: ignore
        result = boxlite.run(redacted, timeout=timeout)  # type: ignore
        return {"success": True, "output": _redact_code(str(result)), "error": ""}
    except ImportError:
        pass
    except Exception:
        pass
    # Fallback: subprocess with timeout — deny by default unless E2B/Boxlite configured
    if isinstance(code, str) and _BLOCKED_RE.search(code):
        return {"success": False, "output": "", "error": "blocked: disallowed pattern"}
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            wrapped = textwrap.dedent(f"""
import sys
try:
{textwrap.indent(redacted, '    ')}
except SystemExit as _e:
    sys.stderr.write(f"SystemExit: {{_e}}\\n")
    raise
except Exception as _e:
    import traceback
    traceback.print_exc()
""")
            f.write(wrapped)
            tmp_path = f.name
        proc = subprocess.run([sys.executable, tmp_path], capture_output=True, text=True, timeout=timeout, env={"PYTHONPATH": "", "PATH": ""})
        return {"success": proc.returncode == 0, "output": _redact_code(proc.stdout or ""), "error": _redact_code(proc.stderr or "")}
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "", "error": f"timeout after {timeout}s"}
    except Exception as exc:
        return {"success": False, "output": "", "error": _redact_code(str(exc))}
    finally:
        if tmp_path:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass
