# Google OAuth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Google OAuth so only authorized emails can access the trading dashboard.

**Architecture:** Backend-handled OAuth (authlib) with signed session cookies (itsdangerous). Frontend checks auth on mount via `/api/auth/me`. All API routes protected by a FastAPI dependency. WebSocket protected via cookie check on handshake.

**Tech Stack:** FastAPI, authlib, itsdangerous, httpx, React, Zustand

---

### Task 1: Backend Auth Module

**Files:**
- Create: `web/server/auth.py`
- Modify: `web/server/__init__.py` (if it exists, just ensure it's a package)
- Modify: `pyproject.toml` (add deps)

**Interfaces:**
- Produces: `auth_router` (FastAPI APIRouter), `require_auth` (callable dependency returns dict), `optional_auth` (callable dependency returns dict|None), `verify_websocket_session` (function), `SESSION_COOKIE_NAME` (string)

- [ ] **Step 1: Add dependencies to pyproject.toml**

Edit `pyproject.toml` to add:
```
authlib>=1.3.0
httpx>=0.28.0
itsdangerous>=2.2.0
```

- [ ] **Step 2: Create web/server/auth.py**

```python
import os
from datetime import timedelta
from typing import Optional

from authlib.integrations.httpx_oauth_client import OAuthClient
from fastapi import APIRouter, HTTPException, Request, Response, WebSocket, WebSocketException, status
from itsdangerous import URLSafeTimedSerializer
from pydantic import BaseModel

SESSION_COOKIE_NAME = "session"
SESSION_MAX_AGE = int(timedelta(hours=24).total_seconds())

_serializer: Optional[URLSafeTimedSerializer] = None
_allowed_emails: list[str] = []


def _get_serializer() -> URLSafeTimedSerializer:
    global _serializer
    if _serializer is None:
        secret = os.environ.get("AUTH_SECRET", "")
        if not secret:
            raise RuntimeError("AUTH_SECRET environment variable is required")
        _serializer = URLSafeTimedSerializer(secret, salt="session")
    return _serializer


def _get_client() -> OAuthClient:
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise RuntimeError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are required")
    redirect_uri = os.environ.get("OAUTH_REDIRECT_URI", "/api/auth/callback")
    return OAuthClient(
        client_id=client_id,
        client_secret=client_secret,
        authorization_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
        token_endpoint="https://oauth2.googleapis.com/token",
        userinfo_endpoint="https://www.googleapis.com/oauth2/v3/userinfo",
        redirect_uri=redirect_uri,
    )


def get_allowed_emails() -> list[str]:
    global _allowed_emails
    if not _allowed_emails:
        raw = os.environ.get("ALLOWED_EMAILS", "")
        _allowed_emails = [e.strip() for e in raw.split(",") if e.strip()]
    return _allowed_emails


def make_session_cookie(email: str, name: str = "", picture: str = "") -> str:
    data = {"email": email, "name": name, "picture": picture}
    return _get_serializer().dumps(data)


def read_session(request: Request) -> Optional[dict]:
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if not cookie:
        return None
    try:
        data = _get_serializer().loads(cookie, max_age=SESSION_MAX_AGE)
        if isinstance(data, dict) and "email" in data:
            return data
    except Exception:
        pass
    return None


def read_session_from_ws(websocket: WebSocket) -> Optional[dict]:
    cookie = websocket.cookies.get(SESSION_COOKIE_NAME)
    if not cookie:
        return None
    try:
        data = _get_serializer().loads(cookie, max_age=SESSION_MAX_AGE)
        if isinstance(data, dict) and "email" in data:
            return data
    except Exception:
        pass
    return None


async def require_auth(request: Request) -> dict:
    session = read_session(request)
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return session


async def optional_auth(request: Request) -> Optional[dict]:
    return read_session(request)


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/login")
async def login():
    redirect_uri = os.environ.get("OAUTH_REDIRECT_URI", "")
    client = _get_client()
    auth_url = client.create_authorization_url(
        redirect_uri=redirect_uri,
        scope="openid email profile",
    )
    return {"auth_url": auth_url}


@router.get("/callback")
async def callback(code: str, request: Request, response: Response):
    client = _get_client()
    token = await client.fetch_token(
        url=os.environ.get("OAUTH_REDIRECT_URI", ""),
        authorization_response=str(request.url),
        code=code,
    )
    userinfo = await client.parse_id_token(token)
    email = (userinfo or {}).get("email", "")
    if not email:
        raise HTTPException(status_code=400, detail="No email from Google")
    allowed = get_allowed_emails()
    if allowed and email not in allowed:
        raise HTTPException(status_code=403, detail="Access denied")
    session_data = userinfo or {"email": email, "name": "", "picture": ""}
    cookie_value = make_session_cookie(
        email=session_data.get("email", email),
        name=session_data.get("name", ""),
        picture=session_data.get("picture", ""),
    )
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=cookie_value,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=True,
    )
    return {"ok": True}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE_NAME, httponly=True, samesite="lax", secure=True)
    return {"ok": True}


@router.get("/me")
async def me(request: Request):
    session = read_session(request)
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return session
```

- [ ] **Step 3: Run quick import check**

Run: `uv run python -c "from authlib.integrations.httpx_oauth_client import OAuthClient; from itsdangerous import URLSafeTimedSerializer; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml web/server/auth.py
git commit -m "feat: add auth module with Google OAuth routes and session management"
```

---

### Task 2: Protect Backend Routes

**Files:**
- Modify: `web/server/app.py`

**Interfaces:**
- Consumes: `auth_router` from `web/server/auth.py`, `require_auth` dependency

- [ ] **Step 1: Read web/server/app.py to understand current route registration**

- [ ] **Step 2: Add auth router and dependency protection**

Add import at top:
```python
from web.server.auth import router as auth_router, require_auth, optional_auth, read_session_from_ws, SESSION_COOKIE_NAME
```

After imports, before `create_app`:
```python
# Auth exceptions
class AuthWebSocketException(Exception):
    def __init__(self, code: int = 4001, reason: str = "Unauthorized"):
        self.code = code
        self.reason = reason
```

In `create_app()`, before any route definitions, add the auth router:
```python
app.include_router(auth_router)
```

Add auth dependency to every route except WebSocket and auth routes. The cleanest way is to add a middleware that checks the session cookie for all `/api/*` routes except `/api/auth/*`.

Actually, the cleanest approach is to add a middleware:
```python
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and not path.startswith("/api/auth/"):
        session = read_session(request)
        if not session:
            return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
        request.state.user = session
    return await call_next(request)
```

For WebSocket routes, add a check at the start of each handler:
```python
session = read_session_from_ws(websocket)
if not session:
    await websocket.close(code=4001)
    return
```

- [ ] **Step 3: Add middleware and WS checks to app.py**

Read the current app.py, then add:
1. Import `read_session` and `read_session_from_ws` from auth module
2. Middleware before first route
3. `read_session_from_ws` check at the top of each WebSocket handler

- [ ] **Step 4: Commit**

```bash
git add web/server/app.py
git commit -m "feat: protect API routes with session auth middleware and WS auth checks"
```

---

### Task 3: Frontend Auth Components

**Files:**
- Create: `web/frontend/src/stores/authStore.ts`
- Create: `web/frontend/src/components/LoginPage.tsx`
- Create: `web/frontend/src/components/AuthGate.tsx`
- Modify: `web/frontend/src/App.tsx`
- Modify: `web/frontend/src/main.tsx` (if needed)

- [ ] **Step 1: Create auth store**

`web/frontend/src/stores/authStore.ts`:
```typescript
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface User {
  email: string;
  name: string;
  picture: string;
}

interface AuthState {
  user: User | null;
  loading: boolean;
  setUser: (user: User | null) => void;
  setLoading: (loading: boolean) => void;
  check: () => Promise<void>;
  logout: () => Promise<void>;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      loading: true,
      setUser: (user) => set({ user }),
      setLoading: (loading) => set({ loading }),
      check: async () => {
        set({ loading: true });
        try {
          const res = await fetch('/api/auth/me');
          if (res.ok) {
            const user = await res.json();
            set({ user, loading: false });
          } else {
            set({ user: null, loading: false });
          }
        } catch {
          set({ user: null, loading: false });
        }
      },
      logout: async () => {
        await fetch('/api/auth/logout', { method: 'POST' });
        set({ user: null });
      },
    }),
    { name: 'auth-storage' }
  )
);
```

- [ ] **Step 2: Create LoginPage component**

`web/frontend/src/components/LoginPage.tsx`:
```tsx
import { useAuthStore } from '../stores/authStore';

export function LoginPage() {
  const { check } = useAuthStore();

  const handleLogin = async () => {
    try {
      const res = await fetch('/api/auth/login');
      const data = await res.json();
      if (data.auth_url) {
        window.location.href = data.auth_url;
      }
    } catch {
      // fallback
    }
  };

  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-950">
      <div className="text-center">
        <h1 className="text-2xl font-bold text-white mb-6">TradingAgents</h1>
        <button
          onClick={handleLogin}
          className="inline-flex items-center gap-3 px-6 py-3 bg-white text-gray-900 rounded-lg hover:bg-gray-100 transition-colors font-medium"
        >
          <svg className="w-5 h-5" viewBox="0 0 24 24">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"/>
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
          </svg>
          Sign in with Google
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create AuthGate component**

`web/frontend/src/components/AuthGate.tsx`:
```tsx
import { useEffect, type ReactNode } from 'react';
import { useAuthStore } from '../stores/authStore';
import { LoginPage } from './LoginPage';

interface AuthGateProps {
  children: ReactNode;
}

export function AuthGate({ children }: AuthGateProps) {
  const { user, loading, check } = useAuthStore();

  useEffect(() => {
    check();
  }, [check]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-950">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white" />
      </div>
    );
  }

  if (!user) {
    return <LoginPage />;
  }

  return <>{children}</>;
}
```

- [ ] **Step 4: Update App.tsx**

Wrap the existing app content with `<AuthGate>`:
```tsx
// top of file
import { AuthGate } from './components/AuthGate';

// in the render:
<AuthGate>
  <div className="...existing app content...">
    ...
  </div>
</AuthGate>
```

- [ ] **Step 5: Commit**

```bash
git add web/frontend/src/stores/authStore.ts web/frontend/src/components/LoginPage.tsx web/frontend/src/components/AuthGate.tsx web/frontend/src/App.tsx
git commit -m "feat: add frontend auth gate with login page"
```

---

### Task 4: Deploy to Railway

**Files:**
- Modify: Railway env vars

- [ ] **Step 1: Set Railway environment variables**

```bash
railway env set GOOGLE_CLIENT_ID=<your-google-client-id>.apps.googleusercontent.com
railway env set GOOGLE_CLIENT_SECRET=<your-google-client-secret>
railway env set AUTH_SECRET=<random 32-char string>
railway env set ALLOWED_EMAILS=you@gmail.com
railway env set OAUTH_REDIRECT_URI=https://your-app.up.railway.app/api/auth/callback
```

- [ ] **Step 2: Update pyproject.toml install to include new deps**

- [ ] **Step 3: Deploy**

```bash
railway up -d --service gleaming-light
```

- [ ] **Step 4: Verify**

Check `railway logs --lines 20` for startup messages. Visit the app URL to see the login page.
