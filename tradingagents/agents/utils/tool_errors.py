import json
from typing import Any, Dict, Optional


def tool_error_payload(*, tool: str, error: Exception, vendor: Optional[str] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "error": True,
        "tool": tool,
        "type": type(error).__name__,
        "message": str(error),
    }
    if vendor is not None:
        payload["vendor"] = vendor
    return payload


def tool_error_text(*, tool: str, error: Exception, vendor: Optional[str] = None) -> str:
    return json.dumps(tool_error_payload(tool=tool, error=error, vendor=vendor), ensure_ascii=False)
