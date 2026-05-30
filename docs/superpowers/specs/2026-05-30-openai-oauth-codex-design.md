# Design: "Sign in with ChatGPT" (OAuth Codex) per TradingAgents

- **Data:** 2026-05-30
- **Stato:** Approvato — aggiornato con verifica dal sorgente ufficiale `openai/codex` (main, commit 8acaec73, 2026-05-30)
- **Branch:** `feat/openai-oauth-codex`

## 1. Obiettivo

Permettere agli utenti di TradingAgents di autenticarsi con il proprio account
**ChatGPT** (Plus/Pro) tramite il flusso OAuth PKCE usato dalla Codex CLI, invece
di fornire una `OPENAI_API_KEY`. Le chiamate ai modelli consumano l'abbonamento
ChatGPT passando per il backend Codex (`https://chatgpt.com/backend-api/codex`).

Non-obiettivi: non reimplementiamo la Codex CLI né scriviamo nel suo
`~/.codex/auth.json`; non gestiamo Azure/enterprise; non cambiamo i provider
esistenti; NON implementiamo lo step opzionale token-exchange→API-key (non serve
per il backend ChatGPT).

## 2. Protocollo verificato (AUTORITATIVO — da openai/codex)

Tutti i valori sotto sono verificati nel sorgente Rust di `openai/codex` (branch
main, 2026-05-30) salvo dove indicato "empirico/community".

### 2.1 OAuth
- Client pubblico: `app_EMoamEEZ73f0CkXaXp7hrann` (nessun client_secret).
- Issuer `https://auth.openai.com`; authorize `…/oauth/authorize`; token `…/oauth/token`.
- PKCE **S256**: `code_challenge = base64url-nopad(SHA256(code_verifier))`.
- Redirect: `http://localhost:{port}/auth/callback`. Porta **1455** (fallback
  **1457**); solo queste due sono nella allow-list Hydra di OpenAI — niente porte
  arbitrarie.
- **Scope** (esteso): `openid profile email offline_access api.connectors.read api.connectors.invoke`.
- **Parametri authorize** (oltre ai base): `response_type=code`, `client_id`,
  `redirect_uri`, `scope`, `code_challenge`, `code_challenge_method=S256`,
  `id_token_add_organizations=true`, `codex_cli_simplified_flow=true`, `state`
  (32 byte random base64url-nopad), `originator=codex_cli_rs`. Nessun `prompt`.

### 2.2 Token exchange (authorization_code)
- POST `…/oauth/token`, `Content-Type: application/x-www-form-urlencoded`,
  **5 campi**: `grant_type=authorization_code`, `code`, `redirect_uri`,
  `client_id`, `code_verifier`.
- Risposta letta dal client: `id_token`, `access_token`, `refresh_token`
  (i campi `expires_in/scope/token_type` NON sono usati dal client).

### 2.3 Refresh
- POST `…/oauth/token`, **`Content-Type: application/json`** (NON form),
  **3 campi**: `{client_id, grant_type:"refresh_token", refresh_token}`. Nessuno `scope`.
- Risposta JSON (campi opzionali): `id_token`, `access_token`, `refresh_token`.
  **Rotazione**: se torna un nuovo `refresh_token` salvalo; altrimenti riusa il
  vecchio. I refresh token usati possono essere invalidati (one-time-use).
- **Scadenza**: derivata dal claim **`exp`** del JWT access_token (NON da
  `expires_in`). Refresh proattivo quando mancano **≤5 min**; retry-on-401.
- Errori permanenti → re-login: `refresh_token_expired`, `refresh_token_reused`,
  `refresh_token_invalidated`.

### 2.4 account_id e claim
- Decodifica del payload JWT (base64url, **senza** verifica firma).
- `account_id = id_token.claims["https://api.openai.com/auth"].chatgpt_account_id`.
- Stesso claim: `chatgpt_account_is_fedramp` (bool) → header `X-OpenAI-Fedramp: true`
  per account FedRAMP; `chatgpt_data_residency`/`chatgpt_compute_residency` →
  header `x-openai-internal-codex-residency` per workspace con residency.

### 2.5 Chiamata al modello (backend ChatGPT)
- Base URL `https://chatgpt.com/backend-api/codex`, path **`/responses`** (NO `/v1`).
  Wire API = **Responses**, solo **SSE streaming** (nessun JSON non-streaming).
- **Header**: `Authorization: Bearer <access_token>`, `ChatGPT-Account-ID: <account_id>`,
  `originator: codex_cli_rs` (raccomandato). Condizionali: `X-OpenAI-Fedramp`,
  `x-openai-internal-codex-residency`. `OpenAI-Beta` non è più inviato sul path
  HTTP nel codice attuale; se inviato, `responses=experimental` è il valore sicuro.
- **Vincoli del body (HTTP 400 se violati — empirico, openclaw#67740, coerente col sorgente):**
  - `store` **= false** (altrimenti 400 "Store must be set to false").
  - `stream` **= true** (altrimenti 400 "Stream must be set to true").
  - `instructions` = stringa **non vuota** (altrimenti 400 "Instructions are required").
  - `input` = array di message objects.
- **Stateless**: `store:false` rompe `previous_response_id` (404 sui tool result).
  Rimandare l'intera history ogni turno (LangGraph lo fa già). Per i modelli
  reasoning, round-trip di `include:["reasoning.encrypted_content"]`.

### 2.6 Modelli accettati
- Il client NON ha whitelist: passa lo slug as-is; valida il **backend**.
- Catalogo Codex (bundled fallback 2026-05-30 / doc): `gpt-5.5`, `gpt-5.4`,
  `gpt-5.4-mini`, `gpt-5.3-codex`, `gpt-5.2` (+ `gpt-5.3-codex-spark` solo Pro).
  Lista reale per-account via `GET …/codex/models` (richiede auth).
- **Modelli generici RIFIUTATI** (400 "Unsupported model"): `gpt-5`, `gpt-5-mini`,
  `gpt-5-nano`, `gpt-4.1`, ecc. → `openai-oauth` NON può riusare il catalogo `openai`.
- Default scelto: **`gpt-5.3-codex`** (Codex, non riservato a Pro).
- Errori 400 in due formati: `{"detail": …}` oppure `{"type":"error","error":{"message": …}}`.

## 3. Decisioni di design (confermate)

1. Login PKCE dentro l'app (server callback locale 1455/1457).
2. CLI: voce dropdown "OpenAI (ChatGPT OAuth)" + auto-login + comando `tradingagents login`.
3. Storage token in `~/.tradingagents/oauth_openai.json` (0600).
4. Refresh robusto via `httpx.Auth` (bearer fresco per richiesta + refresh-on-401).

## 4. Architettura

### 4.1 Provider `openai-oauth`
Display "OpenAI (ChatGPT OAuth)". **Catalogo modelli dedicato Codex** (non alias
di `openai`). Capabilities riusano la dispatch per-modello esistente.

### 4.2 Package `tradingagents/llm_clients/oauth/`
- **`pkce.py`** — costanti OAuth/backend; `generate_pkce_pair()` (S256),
  `generate_state()`, `build_authorize_url(challenge, state)` con lo scope esteso
  e i parametri verificati. Costanti `CODEX_BASE_URL`, `CODEX_DEFAULT_HEADERS`
  (`originator: codex_cli_rs`).
- **`store.py`** — `OAuthTokenStore` (path `~/.tradingagents/oauth_openai.json`,
  0600, scrittura atomica): `save()`, `load()→StoredTokens`, decode `account_id`
  + `is_fedramp` + `residency` dall'`id_token`; **`expires_at` dal claim `exp`
  del JWT access_token**; `is_expired(skew=300)`; `refresh()` con **body JSON**,
  gestione rotazione refresh_token, errori `OAuthNotLoggedIn`/`OAuthRefreshFailed`.
- **`flow.py`** — `login(open_browser, timeout, store)`: PKCE+state, server
  `localhost:1455` (fallback 1457) su `/auth/callback`, apre browser, valida
  `state`, `exchange_code()` (form-urlencoded, 5 campi), salva. Risposta HTML
  inline di conferma con `Connection: close`. `OAuthLoginError`.
- **`auth.py`** — `CodexOAuth(httpx.Auth)`: inietta `Authorization: Bearer`
  fresco (refresh proattivo se `is_expired`), refresh+retry singolo su 401.
- **`body.py`** — `enforce_codex_constraints(httpx request)`: event-hook che,
  per le POST a `/responses`, riscrive il body JSON forzando `store=false`,
  `stream=true` e, se `instructions` manca o è vuoto, imposta un default non
  vuoto. (Cintura+bretelle rispetto ai parametri langchain.) NB: `stream` resta
  governato anche da `streaming=True` su ChatOpenAI per il corretto parsing SSE.
- **`__init__.py`** — espone `login`, `OAuthTokenStore`, `ensure_token`,
  `CodexOAuth`, costanti, eccezioni.

### 4.3 `OpenAIClient` ramo `openai-oauth` (`openai_client.py`)
Costruisce `NormalizedChatOpenAI` con:
- `base_url = CODEX_BASE_URL` (o override esplicito).
- `use_responses_api = True`, **`streaming = True`** (così `.invoke()` usa SSE),
  **`store = False`** (param langchain; rinforzato dall'event-hook).
- `http_client`/`http_async_client` = `httpx.Client/AsyncClient(auth=CodexOAuth(store),
  event_hooks={"request": [enforce_codex_constraints]})`.
- `default_headers` = `{ChatGPT-Account-ID, originator, [X-OpenAI-Fedramp],
  [x-openai-internal-codex-residency]}`. `api_key="oauth"` placeholder.
- `ensure_token(store)` all'avvio → solleva `OAuthNotLoggedIn` se non loggato.

### 4.4 Wiring
- `factory.py`: `openai-oauth` → `OpenAIClient(provider="openai-oauth")`.
- `api_key_env.py`: `"openai-oauth": None`.
- `model_catalog.py`: **nuova entry `openai-oauth`** con i modelli Codex
  (quick: gpt-5.4-mini, gpt-5.3-codex, gpt-5.2; deep: gpt-5.3-codex, gpt-5.4, gpt-5.5).
- `validators.py`: valida contro il catalogo Codex di `openai-oauth`.

### 4.5 CLI
- `select_llm_provider()`: voce `("OpenAI (ChatGPT OAuth)", "openai-oauth", None)`.
- `ensure_oauth_login(provider)`: se `openai-oauth` e nessun token valido → `login()`.
- `cli/main.py`: branch nel flusso interattivo; comando `tradingagents login`.

## 5. Error handling
Porta 1455/1457 occupata; login annullato/timeout; `state` mismatch (CSRF);
refresh fallito → re-login; 400 "Unsupported model" → suggerisci un modello del
catalogo Codex; 400 store/stream/instructions → errore di configurazione body;
401 residency → header residency mancante; store file corrotto → re-login.
Parser errori 400 robusto su `detail` e `error.message`.

## 6. Testing
Unit deterministici (no rete): pkce (challenge=S256), authorize URL (scope+params),
store round-trip + 0600 + `exp`-based expiry + account_id/fedramp/residency decode
+ refresh JSON mockato + rotazione, `CodexOAuth` (inject + 401 retry),
`enforce_codex_constraints` (store/stream/instructions sul body), `exchange_code`
form-urlencoded, factory dispatch, `OpenAIClient` (base_url/headers/streaming/store),
catalogo modelli Codex, validators, CLI (dropdown + ensure_oauth_login).
Integrazione live (browser + account reale) = **manuale, fuori CI**.

## 7. Documentazione
README: sezione "Sign in with ChatGPT (OAuth)" con caveat non-ufficiale/ToS.
`.env.example`: nota provider `openai-oauth` (no key) + `TRADINGAGENTS_OAUTH_PATH`.

## 8. Rischi
- Backend `chatgpt.com/backend-api/codex` **non documentato/privato** → può
  cambiare senza preavviso. Dettagli wire da reverse-engineering del sorgente.
- **Non verificabile end-to-end** senza account ChatGPT Plus/Pro reale: unit test
  coprono il wiring, ma l'accettazione live (specie shape Responses di langchain)
  resta da validare manualmente.
- **ToS**: riuso del client_id ufficiale Codex e `originator=codex_cli_rs` da
  un'app non-Codex = area grigia. Dichiarato come feature community/non ufficiale;
  responsabilità d'uso dell'utente.
- Drift di versione (verifica su main, non su tag). Entitlement modelli per piano
  (Plus vs Pro) differente.
