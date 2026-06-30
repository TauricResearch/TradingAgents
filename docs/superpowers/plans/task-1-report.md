# Task 1 Report: Backend - Chat Router with Tool Discovery

## Status: DONE

## What I Implemented

- **`web/server/chat_router.py`**: New router with two endpoints:
  - `GET /api/chat/tools` — Returns auto-generated tool definitions extracted from all registered FastAPI routes (excludes `/api/chat/*` and `/ws/*` routes). Each tool includes name, description, HTTP method, path, and extracted path parameters.
  - `POST /api/chat/proxy` — Forwards requests to any backend endpoint using httpx, passing through cookies and JSON body.
  - `extract_tool_definitions(app)` — Pure function that inspects `app.routes` to build tool metadata from route paths, methods, and docstrings.

- **`web/server/app.py`**: Added `from web.server.chat_router import router as chat_router` and `app.include_router(chat_router)` alongside the auth router.

- **`web/server/tests/test_chat_router.py`**: 11 tests covering:
  - `extract_tool_definitions` unit tests: route discovery, method/path extraction, path parameter extraction, fallback description, root path handling
  - `GET /api/chat/tools` integration tests: 200 response, tool shape validation, chat route exclusion
  - `POST /api/chat/proxy` integration tests: 422 for missing body, GET forwarding, POST body forwarding (with httpx mocked)

## Test Results

11/11 passing, output pristine (1 pre-existing StarletteDeprecationWarning about httpx).

## Files Changed

| File | Action |
|------|--------|
| `web/server/chat_router.py` | Created |
| `web/server/app.py` | Modified (2 lines: import + include_router) |
| `web/server/tests/test_chat_router.py` | Created |

## Self-Review

- **Completeness**: All 4 steps from the plan implemented. Tool discovery correctly filters chat/WS routes, extracts path params, and uses docstrings for descriptions.
- **Quality**: Clean module structure, follows existing codebase patterns (Pydantic models, APIRouter, TestClient usage).
- **Testing**: Tests verify both the pure `extract_tool_definitions` function and the live endpoints through TestClient. Proxy tests mock httpx to avoid network calls.
- **Concerns**: None. Implementation matches the plan exactly.

## Commit

`577e074` — feat: add chat router with auto-generated tool discovery and proxy endpoint
