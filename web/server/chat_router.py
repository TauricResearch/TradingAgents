"""Chat router with auto-generated tool discovery and proxy endpoint."""

from __future__ import annotations

import re
from typing import Any

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ProxyRequest(BaseModel):
    method: str
    path: str
    params: dict[str, Any] | None = None
    body: dict[str, Any] | None = None


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
