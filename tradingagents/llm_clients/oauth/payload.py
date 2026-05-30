"""Trasformazione del payload Responses per il backend ChatGPT-Codex.

Il backend `chatgpt.com/backend-api/codex` rifiuta con HTTP 400 le richieste
`/responses` che non rispettano i suoi vincoli. Verificato dal sorgente
openai/codex e dal comportamento live:

- ``store`` DEVE essere ``false``;
- ``stream`` DEVE essere ``true``;
- ``instructions`` DEVE essere una stringa non vuota (il system prompt);
- ``input`` NON può contenere messaggi ``system``/``developer``
  (-> 400 "System messages are not allowed"): vanno spostati in ``instructions``;
- ``max_output_tokens`` non è accettato.

langchain-openai (Responses API) mette il SystemMessage in ``input`` come
``{"role": "system", ...}`` e non emette mai ``instructions``. Questa funzione
ricostruisce il payload corretto a partire da quello prodotto da langchain.

Applicata in ``CodexChatOpenAI._get_request_payload`` (prima della
serializzazione), quindi funziona identica su path sync e async — a differenza
di un event-hook httpx, che invierebbe ``request.stream`` non modificato e
romperebbe il path async (await su hook sincrono).
"""
from __future__ import annotations

from typing import Any

# Usato solo se non c'è alcun system prompt da promuovere (il backend esige
# instructions non vuoto). Neutro per non alterare il comportamento degli agenti.
_DEFAULT_INSTRUCTIONS = "You are a helpful assistant."

_SYSTEM_ROLES = ("system", "developer")


def _extract_text(content: Any) -> str:
    """Estrae il testo da un content che può essere stringa o lista di parti."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(part, str):
                parts.append(part)
        return "\n".join(parts)
    return ""


def apply_codex_payload_constraints(payload: dict) -> dict:
    """Riscrive in-place il payload Responses per soddisfare il backend Codex.

    No-op se non è un payload Responses (manca la chiave ``input``), così non
    interferisce con eventuali richieste Chat Completions.
    """
    if "input" not in payload:
        return payload

    payload["store"] = False
    payload["stream"] = True
    payload.pop("max_output_tokens", None)

    # Promuovi i messaggi system/developer da input a instructions.
    system_texts = []
    remaining = []
    for item in payload.get("input") or []:
        if isinstance(item, dict) and item.get("role") in _SYSTEM_ROLES:
            text = _extract_text(item.get("content"))
            if text:
                system_texts.append(text)
        else:
            remaining.append(item)
    payload["input"] = remaining

    existing = payload.get("instructions")
    existing = existing if isinstance(existing, str) and existing.strip() else ""
    hoisted = "\n\n".join(system_texts)
    combined = "\n\n".join(t for t in (hoisted, existing) if t)
    payload["instructions"] = combined or _DEFAULT_INSTRUCTIONS

    return payload
