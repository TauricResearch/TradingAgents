"""Chat router with auto-generated tool discovery and proxy endpoint."""

from __future__ import annotations

import re
import os
import json
from typing import Any

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ProxyRequest(BaseModel):
    method: str
    path: str
    params: dict[str, Any] | None = None
    body: dict[str, Any] | None = None


class ChatCompletionRequest(BaseModel):
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]] | None = None
    stream: bool = False


def extract_tool_definitions(app) -> list[dict[str, Any]]:
    """Extract tool definitions from FastAPI routes."""
    tools: list[dict[str, Any]] = []
    for route in app.routes:
        if not (hasattr(route, "methods") and hasattr(route, "path")):
            continue
        # Skip chat routes and websocket routes
        if route.path.startswith("/api/chat") or route.path.startswith("/ws"):
            continue

        for method in route.methods:
            if method not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                continue

            tool_name = route.path.replace("/api/", "").replace("/", "_").strip("_")
            # Replace dots and other invalid chars with underscores
            tool_name = re.sub(r"[^a-zA-Z0-9_]", "_", tool_name)
            # Ensure it starts with a letter
            if tool_name and not tool_name[0].isalpha():
                tool_name = "action_" + tool_name
            if not tool_name:
                tool_name = "root"

            # Get description from route or generate one
            description = ""
            if hasattr(route, "endpoint") and route.endpoint.__doc__:
                description = route.endpoint.__doc__.strip().split("\n")[0]
            else:
                description = f"Execute {method} on {route.path}"

            # Extract parameters from path
            parameters: dict[str, dict[str, str]] = {}
            path_params = re.findall(r"\{(\w+)\}", route.path)
            for param in path_params:
                parameters[param] = {
                    "type": "string",
                    "description": f"Path parameter: {param}",
                }

            tools.append(
                {
                    "name": f"{method.lower()}_{tool_name}",
                    "description": description,
                    "method": method,
                    "path": route.path,
                    "parameters": parameters,
                }
            )
    return tools


@router.get("/tools")
async def get_tools(request: Request):
    """Get available tool definitions auto-generated from API routes."""
    app = request.app
    tools = extract_tool_definitions(app)
    return {"tools": tools}


@router.api_route(
    "/proxy", methods=["GET", "POST", "PUT", "PATCH", "DELETE"]
)
async def proxy_request(proxy_req: ProxyRequest, request: Request):
    """Forward requests to any backend endpoint."""
    base_url = str(request.base_url).rstrip("/")
    target_url = f"{base_url}{proxy_req.path}"

    async with httpx.AsyncClient() as client:
        response = await client.request(
            method=proxy_req.method.upper(),
            url=target_url,
            params=proxy_req.params or {},
            json=proxy_req.body
            if proxy_req.method.upper() in ("POST", "PUT", "PATCH")
            else None,
            headers={"Cookie": request.headers.get("cookie", "")},
        )

    content = (
        response.json()
        if response.headers.get("content-type", "").startswith("application/json")
        else response.text
    )
    return JSONResponse(content=content, status_code=response.status_code)


@router.post("/completions")
async def chat_completions(req: ChatCompletionRequest, request: Request):
    """Handle chat completions using the backend's LLM configuration."""
    try:
        from tradingagents.llm_clients import create_llm_client

        # Read .env directly like the rest of the app
        env = {}
        from pathlib import Path
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if "=" in stripped:
                    key, _, val = stripped.partition("=")
                    env[key.strip()] = val.strip()

        provider = env.get("TRADINGAGENTS_LLM_PROVIDER", "ollama").replace("-", "_")
        model_name = env.get("TRADINGAGENTS_QUICK_THINK_LLM", "gpt-4o-mini")
        backend_url = env.get("TRADINGAGENTS_LLM_BACKEND_URL") or None

        # Set env vars so create_llm_client can find API keys
        for k, v in env.items():
            if v and k not in os.environ:
                os.environ[k] = v

        # For Ollama, don't pass base_url (client handles it)
        base_url = backend_url
        if provider == "ollama":
            base_url = None

        client = create_llm_client(
            provider=provider,
            model=model_name,
            base_url=base_url,
        )
        llm = client.get_llm()

        # Convert messages to LangChain format
        from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

        langchain_messages = []
        for msg in req.messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "system":
                langchain_messages.append(SystemMessage(content=content))
            elif role == "user":
                langchain_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                if msg.get("tool_calls"):
                    # Handle tool calls - need to include them in the message
                    tool_calls = []
                    for tc in msg["tool_calls"]:
                        tool_calls.append({
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["function"]["name"],
                                "arguments": tc["function"]["arguments"],
                            },
                        })
                    langchain_messages.append(AIMessage(
                        content=content or "",
                        tool_calls=tool_calls,
                    ))
                else:
                    langchain_messages.append(AIMessage(content=content))
            elif role == "tool":
                tool_call_id = msg.get("tool_call_id", "")
                langchain_messages.append(ToolMessage(
                    content=content,
                    tool_call_id=tool_call_id,
                ))

        # Bind tools if provided
        if req.tools:
            from langchain_core.tools import StructuredTool

            lc_tools = []
            for tool in req.tools:
                func_info = tool.get("function", {})
                params = func_info.get("parameters", {})
                lc_tools.append(StructuredTool(
                    name=func_info["name"],
                    description=func_info.get("description", ""),
                    args_schema=None,
                    func=None,
                ))

            llm_with_tools = llm.bind_tools(lc_tools)
            response = llm_with_tools.invoke(langchain_messages)
        else:
            response = llm.invoke(langchain_messages)

        text = response.content if hasattr(response, "content") else str(response)
        tool_calls_from_llm = getattr(response, "tool_calls", None) or []

        # Fallback: parse text-based tool calls if LLM outputs <tool_call> as text
        if not tool_calls_from_llm and text:
            import re as _re
            import uuid as _uuid
            tool_pattern = _re.compile(
                r'<tool_call>\s*<name>(.*?)</name>\s*<parameters>(.*?)</parameters>\s*</tool_call>',
                _re.DOTALL,
            )
            matches = tool_pattern.findall(text)
            if matches:
                # Remove tool call text from the response
                clean_text = tool_pattern.sub("", text).strip()
                for name, params_str in matches:
                    try:
                        params = json.loads(params_str)
                    except json.JSONDecodeError:
                        params = {}
                    tool_calls_from_llm.append({
                        "id": f"call_{_uuid.uuid4().hex[:12]}",
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": json.dumps(params),
                        },
                    })
                if clean_text:
                    text = clean_text

        # Also parse ```tool_call...``` format
        if not tool_calls_from_llm and text:
            import re as _re
            import uuid as _uuid
            block_pattern = _re.compile(
                r'```tool_call\s*(.*?)\s*```',
                _re.DOTALL,
            )
            block_matches = block_pattern.findall(text)
            if block_matches:
                for block in block_matches:
                    # Try to parse as JSON first
                    try:
                        tc = json.loads(block)
                        tool_calls_from_llm.append({
                            "id": f"call_{_uuid.uuid4().hex[:12]}",
                            "type": "function",
                            "function": {
                                "name": tc.get("name", ""),
                                "arguments": json.dumps(tc.get("arguments", tc.get("parameters", {}))),
                            },
                        })
                    except json.JSONDecodeError:
                        # Parse name="..." parameters="..." format
                        name_match = _re.search(r'name="([^"]*)"', block)
                        params_match = _re.search(r'parameters="({.*?})"', block, _re.DOTALL)
                        if name_match:
                            name = name_match.group(1)
                            params_str = params_match.group(1) if params_match else "{}"
                            try:
                                params = json.loads(params_str)
                            except json.JSONDecodeError:
                                params = {}
                            tool_calls_from_llm.append({
                                "id": f"call_{_uuid.uuid4().hex[:12]}",
                                "type": "function",
                                "function": {
                                    "name": name,
                                    "arguments": json.dumps(params),
                                },
                            })
                text = block_pattern.sub("", text).strip()

        # Format as OpenAI-compatible response
        result_msg: dict[str, Any] = {"role": "assistant"}
        if tool_calls_from_llm:
            result_msg["content"] = text or None
            result_msg["tool_calls"] = tool_calls_from_llm
            finish_reason = "tool_calls"
        else:
            result_msg["content"] = text
            finish_reason = "stop"

        return {
            "id": "chatcmpl-backend",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "message": result_msg,
                    "finish_reason": finish_reason,
                }
            ],
            "model": model_name,
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        }

    except Exception as e:
        return JSONResponse(
            content={"error": str(e)},
            status_code=500,
        )
