# Google OAuth for TradingAgents Dashboard

## Purpose
Add Google OAuth login so only authorized users can access the dashboard. Currently the app is completely open — no auth at all.

## Constraint
- Only `idshapira051@gmail.com` may access the app (configurable via `ALLOWED_EMAILS` env var)

## Approach

**Backend-handled OAuth with signed session cookies.** No frontend token juggling, no database for sessions.

### Components

1. **Auth Module** (`web/server/auth.py`)
   - OAuth client configured with `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`
   - Routes: `/api/auth/login` → redirect to Google, `/api/auth/callback` → verify + set cookie, `/api/auth/logout` → clear cookie, `/api/auth/me` → return user info or 401
   - On callback: verify Google's token, check email against `ALLOWED_EMAILS`, set signed session cookie

2. **Session Cookie**
   - Signed with `itsdangerous.URLSafeTimedSerializer` using `AUTH_SECRET` env var
   - Payload: email, name, picture
   - Expiry: 24 hours
   - Stateless — no DB needed

3. **Route Protection**
   - All `/api/*` routes except `/api/auth/*` require a valid session via a `require_auth` dependency
   - WebSocket endpoints check the cookie during handshake
   - Static files and frontend root are unprotected (frontend shows login if `/api/auth/me` returns 401)

4. **Frontend Changes**
   - Zustand `useAuthStore` with `user`, `loading`, `login()`, `logout()` — persisted to localStorage
   - `<LoginPage>` component with a Google sign-in button (links to `/api/auth/login`)
   - `<AuthGate>` wrapper that checks `/api/auth/me` on mount, shows `LoginPage` if unauthenticated
   - The login button is a simple `window.location.href = '/api/auth/login'` — no Google JS SDK needed

5. **Dependencies Added** (Python)
   - `authlib>=1.3.0` — OAuth 2.0 client
   - `httpx>=0.27.0` — HTTP client for Google token verification
   - `itsdangerous>=2.2.0` — signed session cookies
   - `python-multipart>=0.0.9` — already present, needed for OAuth callback form data

### Railway Env Vars
| Variable | Value |
|----------|-------|
| `GOOGLE_CLIENT_ID` | `474009787186-4ev1vgpd7flvng5q92oilgi8p9a0cl53.apps.googleusercontent.com` |
| `GOOGLE_CLIENT_SECRET` | `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` |
| `AUTH_SECRET` | random 32+ char string |
| `ALLOWED_EMAILS` | `idshapira051@gmail.com` |

## Unprotected Routes
- `/api/auth/login` — must be open to initiate login
- `/api/auth/callback` — must be open for Google to redirect to
- `/` + static files — open, but frontend shows login page if no session

## WebSocket Auth
- During WS handshake, read the session cookie from the request
- If invalid/missing/expired, close the connection with 4001
- Since the frontend and API are same-origin, cookies are sent automatically
