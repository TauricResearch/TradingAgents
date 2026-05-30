"""Event-hook httpx che impone i vincoli del backend Codex sul body /responses.

Il backend ChatGPT-Codex rifiuta con HTTP 400 le richieste /responses che non
rispettano: ``store=false``, ``stream=true`` e ``instructions`` non vuoto
(empirico, openclaw#67740; coerente con codex-rs/core/src/client.rs). langchain
imposta già ``streaming=True`` per lo stream e ``store=False`` come parametro,
ma questo hook è la cintura+bretelle: riscrive il body in uscita per garantire
i tre vincoli anche se un parametro langchain cambia in futuro.
"""
from __future__ import annotations

import json

# Istruzioni di default minime quando il payload non ne ha (il backend le esige
# non vuote). Restano neutre per non alterare il comportamento degli agenti.
_DEFAULT_INSTRUCTIONS = "You are a helpful assistant."


def _coerce_constraints(payload: dict) -> bool:
    """Applica i vincoli al payload in-place. Ritorna True se è cambiato qualcosa."""
    changed = False
    if payload.get("store") is not False:
        payload["store"] = False
        changed = True
    if payload.get("stream") is not True:
        payload["stream"] = True
        changed = True
    instructions = payload.get("instructions")
    if not isinstance(instructions, str) or not instructions.strip():
        payload["instructions"] = _DEFAULT_INSTRUCTIONS
        changed = True
    return changed


def enforce_codex_constraints(request) -> None:
    """httpx request event-hook: forza store/stream/instructions sulle POST /responses."""
    if request.method != "POST" or not request.url.path.endswith("/responses"):
        return
    raw = request.content
    if not raw:
        return
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return
    if not isinstance(payload, dict):
        return
    if _coerce_constraints(payload):
        new_body = json.dumps(payload).encode("utf-8")
        request._content = new_body
        request.headers["Content-Length"] = str(len(new_body))
