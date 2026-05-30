# Design: "Sign in with ChatGPT" (OAuth Codex) per TradingAgents

- **Data:** 2026-05-30
- **Stato:** Approvato (in attesa di review dello spec)
- **Branch:** `feat/openai-oauth-codex`

## 1. Obiettivo

Permettere agli utenti di TradingAgents di autenticarsi con il proprio
account **ChatGPT** (Plus/Pro/Team) tramite il flusso OAuth usato dalla
Codex CLI, invece di fornire una `OPENAI_API_KEY`. Le chiamate ai modelli
consumano l'abbonamento ChatGPT passando per il backend Codex anziché per
`api.openai.com`.

Non-obiettivi:
- Non reimplementiamo la Codex CLI né scriviamo nel suo `~/.codex/auth.json`.
- Non gestiamo provider enterprise/Azure in questo lavoro.
- Non cambiamo il comportamento dei provider esistenti.

## 2. Contesto tecnico (come funziona l'OAuth Codex)

- OAuth 2.0 **Authorization Code + PKCE (S256)**, client pubblico
  `app_EMoamEEZ73f0CkXaXp7hrann`.
- Authorize endpoint: `https://auth.openai.com/oauth/authorize`
  - parametri: `response_type=code`, `client_id`, `redirect_uri=http://localhost:1455/auth/callback`,
    `scope=openid profile email offline_access`, `code_challenge`,
    `code_challenge_method=S256`, `state`, `id_token_add_organizations=true`.
- Token endpoint: `https://auth.openai.com/oauth/token`
  - `grant_type=authorization_code` con `code`, `redirect_uri`, `client_id`,
    `code_verifier` → restituisce `id_token`, `access_token`, `refresh_token`,
    `expires_in`.
  - refresh: `grant_type=refresh_token` con `refresh_token`, `client_id`.
- L'`chatgpt_account_id` è un claim dentro l'`id_token` (JWT, sezione
  `https://api.openai.com/auth`).
- **Chiamate al modello:** base URL `https://chatgpt.com/backend-api/codex`,
  formato **Responses API**, header:
  - `Authorization: Bearer <access_token>`
  - `chatgpt-account-id: <account_id>`
  - `OpenAI-Beta: responses=experimental`
  - `originator: codex_cli_rs`
- Il token si rinnova proattivamente entro ~5 min dalla scadenza e in modo
  reattivo su `401`.

## 3. Decisioni di design (confermate con l'utente)

1. **Login PKCE dentro l'app** (non solo riuso di `~/.codex/auth.json`).
2. **Entry point:** voce nel dropdown provider della CLI + auto-login al
   primo uso, più un comando dedicato `tradingagents login`.
3. **Storage token:** file dedicato `~/.tradingagents/oauth_openai.json`
   con permessi `0600` (non tocca i file di Codex).
4. **Refresh:** `httpx` auth hook robusto — token fresco iniettato ad ogni
   richiesta + refresh-and-retry su `401`, così i run lunghi non scadono.

## 4. Architettura

### 4.1 Nuovo provider logico
Chiave provider: **`openai-oauth`**, display *"OpenAI (ChatGPT OAuth)"*.
Riusa il catalogo modelli, le capabilities e i validatori del provider
`openai` (stessi modelli gpt-5.x). Differisce solo per auth + base URL.

### 4.2 Nuovo package `tradingagents/llm_clients/oauth/`

- **`pkce.py`** — funzioni pure:
  - `generate_pkce_pair() -> (verifier, challenge)` (S256, base64url no-pad)
  - `generate_state() -> str`
  - `build_authorize_url(challenge, state) -> str`
  - Nessuna dipendenza di rete → completamente testabile.

- **`store.py`** — `OAuthTokenStore`:
  - `path` default `~/.tradingagents/oauth_openai.json` (override via
    `TRADINGAGENTS_OAUTH_PATH` o `data` home dell'app).
  - `save(tokens)` scrive atomicamente con `chmod 0600`.
  - `load() -> StoredTokens | None`.
  - `account_id` estratto/decodificato dal claim dell'`id_token` (decode
    JWT senza verifica firma — è informativo, non un gate di sicurezza).
  - `is_expired(skew=300s)`, gestione `expires_at` calcolato da `expires_in`.
  - `refresh()` chiama il token endpoint con `refresh_token` e ripersiste.
  - Errori tipizzati: `OAuthNotLoggedIn`, `OAuthRefreshFailed`.

- **`flow.py`** — `login(open_browser=True, timeout=180) -> StoredTokens`:
  - genera PKCE+state, avvia `http.server` su `localhost:1455`
    (`/auth/callback`), apre il browser, attende il `code`, valida `state`,
    scambia il code per i token, li salva via `OAuthTokenStore`.
  - Gestione errori: porta occupata, timeout, `state` non combaciante,
    login annullato dall'utente.
  - Risponde al browser con una pagina HTML minimale di conferma.

- **`__init__.py`** — espone `login`, `OAuthTokenStore`, `ensure_token()`
  (carica; se scaduto fa refresh; se assente solleva `OAuthNotLoggedIn`).

### 4.3 Aggancio al client (`openai_client.py`)
`OpenAIClient` riconosce `provider == "openai-oauth"`:
- `base_url = https://chatgpt.com/backend-api/codex` (un eventuale
  `base_url` esplicito ha precedenza, per proxy aziendali).
- `use_responses_api = True`.
- costruisce un **`httpx.Client`/`httpx.AsyncClient`** con un `auth` custom
  (`CodexOAuth(httpx.Auth)`) che:
  - ad ogni richiesta legge il token corrente dallo store (refresh proattivo
    se in scadenza) e setta `Authorization: Bearer <token>`;
  - su risposta `401`, fa un refresh e ritenta una volta.
- `default_headers` con `chatgpt-account-id`, `OpenAI-Beta`, `originator`.
- Passa gli `http_client`/`http_async_client` a `ChatOpenAI` (già nei
  `_PASSTHROUGH_KWARGS`). La `api_key` passata a ChatOpenAI è un placeholder
  ("oauth") perché l'auth reale è gestita dall'hook httpx.

`factory.py`: aggiunge `openai-oauth` all'insieme OpenAI-compatibile (o un
ramo dedicato) → `OpenAIClient(..., provider="openai-oauth")`.

`api_key_env.py`: `"openai-oauth": None` (nessuna env key; l'auth è OAuth).

`validators.py` / `model_catalog.py` / `capabilities.py`: `openai-oauth`
mappa sul provider `openai` per validazione modelli e capabilities.

### 4.4 CLI (`cli/`)
- `select_llm_provider()`: nuova voce `("OpenAI (ChatGPT OAuth)",
  "openai-oauth", None)`.
- `cli/utils.py`: nuova `ensure_oauth_login(provider)` che, per
  `openai-oauth`, verifica lo store; se manca un token valido avvia
  `oauth.login()`. Sostituisce `ensure_api_key()` per questo provider.
- `cli/main.py`: nel flusso interattivo, branch su `openai-oauth` →
  `ensure_oauth_login`; selezione modelli riusa quella di `openai`;
  reasoning effort riusa il flusso openai.
- Nuovo comando typer **`login`** in `cli/main.py`:
  `tradingagents login` → esegue `oauth.login()` e stampa l'esito
  (account, scadenza). Flag `--no-browser` per stampare l'URL manualmente.

## 5. Flusso dati (run tipico)

```
CLI: utente sceglie "OpenAI (ChatGPT OAuth)"
  -> ensure_oauth_login(): store vuoto -> oauth.login()
       -> browser -> auth.openai.com -> callback :1455 -> /oauth/token
       -> tokens salvati in ~/.tradingagents/oauth_openai.json (0600)
  -> config["llm_provider"]="openai-oauth"
TradingAgentsGraph -> create_llm_client("openai-oauth", model, ...)
  -> OpenAIClient.get_llm():
       base_url=chatgpt backend, http_client con CodexOAuth auth,
       default_headers con chatgpt-account-id
  -> ChatOpenAI (Responses API)
Ogni richiesta: CodexOAuth inietta bearer fresco; su 401 refresh+retry.
```

## 6. Error handling

| Situazione | Comportamento |
|---|---|
| Porta 1455 occupata | Errore chiaro: chiudere il processo o riprovare; suggerisce `--no-browser` |
| Login annullato / timeout | Messaggio azionabile, nessun token salvato |
| `state` non combaciante | Abort (possibile CSRF), nessun token salvato |
| Refresh token revocato | `OAuthRefreshFailed` -> invita a rifare `tradingagents login` |
| Account senza entitlement Codex | Propaga l'errore API con hint sull'abbonamento |
| File store corrotto | Trattato come "non loggato", si rifà login |

## 7. Testing

Unit (no rete, deterministici):
- `pkce`: challenge = base64url(sha256(verifier)); lunghezze e charset.
- `store`: round-trip save/load; permessi `0600`; `is_expired` con skew;
  decode `account_id` da id_token fittizio; refresh con httpx mockato.
- `CodexOAuth` auth: inietta header; su 401 fa refresh+retry una sola volta.
- `factory`: `openai-oauth` -> `OpenAIClient` con provider corretto.
- `OpenAIClient.get_llm()`: base_url e default_headers attesi (token mockato).
- CLI: `ensure_api_key` skippa `openai-oauth`; provider presente nel dropdown.

Integrazione (guardato da env var, non in CI):
- `login()` reale e una chiamata `responses` end-to-end.

## 8. Documentazione e impatto

- `README`: sezione "Sign in with ChatGPT (OAuth)".
- `.env.example`: nota sul provider `openai-oauth` (nessuna key) e su
  `TRADINGAGENTS_OAUTH_PATH` opzionale.
- Nessuna modifica ai provider esistenti; nuove dipendenze: nessuna oltre a
  `httpx` (già transitiva via openai SDK). JWT decodificato manualmente
  (base64) per evitare nuove dipendenze.

## 9. Rischi e note

- Il client ID e gli endpoint sono pubblici ma **non ufficialmente
  documentati per uso esterno**: l'integrazione è "best effort" e potrebbe
  rompersi se OpenAI cambia il backend. Documentato nel README come
  funzionalità community/non ufficiale.
- I token sono credenziali sensibili: file `0600`, mai loggati.
- Conformità ToS di OpenAI è responsabilità dell'utente; lo dichiariamo.
