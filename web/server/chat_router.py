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

            # Extract parameters from path and known query params
            parameters: dict[str, dict[str, str]] = {}
            path_params = re.findall(r"\{(\w+)\}", route.path)
            for param in path_params:
                parameters[param] = {
                    "type": "string",
                    "description": (
                        f"ticker symbol, e.g. 'SPY', 'AAPL', 'QQQ', 'MSFT'. "
                        f"Pass the actual symbol from the user's question. "
                    ),
                }

            # Add known query parameters for commonly used endpoints
            if tool_name == "prices":
                parameters["ticker"] = {
                    "type": "string",
                    "description": "ticker symbol to get price for, e.g. 'SPY', 'AAPL'",
                }
            if tool_name == "tickers__ticker__history":
                parameters["range"] = {
                    "type": "string",
                    "description": "Time range for historical data (e.g. '1mo', '3mo', '6mo', '1y'). Default: '1mo'.",
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
    
    # Sanitize path: replace any remaining {param} placeholders with param name
    # This handles cases where the LLM passes literal {TICKER} instead of a real value
    import re as _re_path
    sanitized_path = _re_path.sub(r'[{}]', '', proxy_req.path)
    
    target_url = f"{base_url}{sanitized_path}"

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
    if req.stream:
        return StreamingResponse(
            _stream_chat(req, request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    try:
        return await _non_stream_chat(req, request)
    except Exception as e:
        return JSONResponse(
            content={"error": str(e)},
            status_code=500,
        )


async def _stream_chat(req: ChatCompletionRequest, request: Request):
    """Generator for SSE streaming chat completions."""
    import re as _re
    import uuid as _uuid

    try:
        from tradingagents.llm_clients import create_llm_client
        from pathlib import Path

        # Read .env
        env = {}
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

        for k, v in env.items():
            if v and k not in os.environ:
                os.environ[k] = v

        base_url = backend_url
        if provider == "ollama":
            base_url = None

        client = create_llm_client(provider=provider, model=model_name, base_url=base_url)
        llm = client.get_llm()

        from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

        langchain_messages = _build_langchain_messages(req)

        # Try streaming with tools; fall back to non-streaming on failure
        use_tools = bool(req.tools)
        lc_tools = []
        if use_tools:
            from langchain_core.tools import StructuredTool
            for tool in req.tools:
                func_info = tool.get("function", {})
                lc_tools.append(StructuredTool(
                    name=func_info["name"],
                    description=func_info.get("description", ""),
                    args_schema=None,
                    func=None,
                ))

        # Attempt streaming
        stream_iter = None
        try:
            if use_tools:
                llm_with_tools = llm.bind_tools(lc_tools)
                stream_iter = llm_with_tools.stream(langchain_messages)
            else:
                stream_iter = llm.stream(langchain_messages)
        except Exception:
            # Streaming not supported - fall back to non-streaming with simulated chunks
            stream_iter = None

        if stream_iter is not None:
            full_text = ""
            tool_calls_buffer: list[dict] = []

            try:
                for chunk in stream_iter:
                    chunk_content = chunk.content if hasattr(chunk, "content") else ""
                    chunk_tool_calls = getattr(chunk, "tool_calls", None) or []

                    if chunk_content:
                        full_text += chunk_content
                        yield f"data: {json.dumps({'type': 'text', 'text': chunk_content})}\n\n"

                    if chunk_tool_calls:
                        for tc in chunk_tool_calls:
                            tc_id = tc.get("id", f"call_{_uuid.uuid4().hex[:12]}")
                            tc_func = tc.get("function", tc)
                            tc_name = tc_func.get("name", "")
                            tc_args = tc_func.get("arguments", "")

                            existing = next((t for t in tool_calls_buffer if t["id"] == tc_id), None)
                            if existing:
                                existing["function"]["arguments"] += tc_args
                            else:
                                tool_calls_buffer.append({
                                    "id": tc_id,
                                    "type": "function",
                                    "function": {"name": tc_name, "arguments": tc_args},
                                })
                        yield f"data: {json.dumps({'type': 'tool_calls', 'tool_calls': tool_calls_buffer})}\n\n"
            except Exception as stream_err:
                yield f"data: {json.dumps({'type': 'error', 'error': str(stream_err)})}\n\n"

            # Parse text-based tool calls
            if not tool_calls_buffer and full_text:
                tool_pattern = _re.compile(
                    r'<tool_call>\s*<name>(.*?)</name>\s*<parameters>(.*?)</parameters>\s*</tool_call>',
                    _re.DOTALL,
                )
                matches = tool_pattern.findall(full_text)
                if matches:
                    full_text = tool_pattern.sub("", full_text).strip()
                    for name, params_str in matches:
                        try:
                            params = json.loads(params_str)
                        except json.JSONDecodeError:
                            params = {}
                        tool_calls_buffer.append({
                            "id": f"call_{_uuid.uuid4().hex[:12]}",
                            "type": "function",
                            "function": {"name": name, "arguments": json.dumps(params)},
                        })

            finish_reason = "tool_calls" if tool_calls_buffer else "stop"
            yield f"data: {json.dumps({'type': 'done', 'finish_reason': finish_reason, 'tool_calls': tool_calls_buffer, 'content': full_text})}\n\n"
        else:
            # Non-streaming fallback
            if use_tools:
                llm_with_tools = llm.bind_tools(lc_tools)
                response = llm_with_tools.invoke(langchain_messages)
            else:
                response = llm.invoke(langchain_messages)

            text = response.content if hasattr(response, "content") else str(response)
            tool_calls_from_llm = getattr(response, "tool_calls", None) or []

            if text:
                yield f"data: {json.dumps({'type': 'text', 'text': text})}\n\n"

            if tool_calls_from_llm:
                yield f"data: {json.dumps({'type': 'tool_calls', 'tool_calls': tool_calls_from_llm})}\n\n"

            finish_reason = "tool_calls" if tool_calls_from_llm else "stop"
            yield f"data: {json.dumps({'type': 'done', 'finish_reason': finish_reason, 'tool_calls': tool_calls_from_llm, 'content': text})}\n\n"

    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    yield "data: [DONE]\n\n"


async def _non_stream_chat(req: ChatCompletionRequest, request: Request):
    """Non-streaming chat completion."""
    from tradingagents.llm_clients import create_llm_client
    from pathlib import Path

    env = {}
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

    for k, v in env.items():
        if v and k not in os.environ:
            os.environ[k] = v

    base_url = backend_url
    if provider == "ollama":
        base_url = None

    client = create_llm_client(provider=provider, model=model_name, base_url=base_url)
    llm = client.get_llm()

    langchain_messages = _build_langchain_messages(req)

    if req.tools:
        from langchain_core.tools import StructuredTool
        lc_tools = []
        for tool in req.tools:
            func_info = tool.get("function", {})
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

    # Fallback: parse text-based tool calls
    if not tool_calls_from_llm and text:
        import re as _re
        import uuid as _uuid
        tool_pattern = _re.compile(
            r'<tool_call>\s*<name>(.*?)</name>\s*<parameters>(.*?)</parameters>\s*</tool_call>',
            _re.DOTALL,
        )
        matches = tool_pattern.findall(text)
        if matches:
            clean_text = tool_pattern.sub("", text).strip()
            for name, params_str in matches:
                try:
                    params = json.loads(params_str)
                except json.JSONDecodeError:
                    params = {}
                tool_calls_from_llm.append({
                    "id": f"call_{_uuid.uuid4().hex[:12]}",
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(params)},
                })
            if clean_text:
                text = clean_text

    if not tool_calls_from_llm and text:
        import re as _re
        import uuid as _uuid
        block_pattern = _re.compile(r'```tool_call\s*(.*?)\s*```', _re.DOTALL)
        block_matches = block_pattern.findall(text)
        if block_matches:
            for block in block_matches:
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
                            "function": {"name": name, "arguments": json.dumps(params)},
                        })
            text = block_pattern.sub("", text).strip()

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
        "choices": [{"index": 0, "message": result_msg, "finish_reason": finish_reason}],
        "model": model_name,
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _build_langchain_messages(req: ChatCompletionRequest):
    """Convert OpenAI-format messages to LangChain format."""
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

    messages = []
    for msg in req.messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "system":
            messages.append(SystemMessage(content=content))
        elif role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            if msg.get("tool_calls"):
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
                messages.append(AIMessage(content=content or "", tool_calls=tool_calls))
            else:
                messages.append(AIMessage(content=content))
        elif role == "tool":
            messages.append(ToolMessage(
                content=content,
                tool_call_id=msg.get("tool_call_id", ""),
            ))
    return messages
