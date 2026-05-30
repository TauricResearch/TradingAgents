"""Smoke test live del provider openai-oauth: una sola chiamata al backend Codex.

Prerequisito: aver eseguito `tradingagents login` (token in ~/.tradingagents/).
Uso:  .venv/bin/python scripts/oauth_smoke.py [model]
"""
import sys

from tradingagents.llm_clients import create_llm_client
from tradingagents.llm_clients.oauth import OAuthTokenStore, OAuthNotLoggedIn


def main() -> int:
    model = sys.argv[1] if len(sys.argv) > 1 else "gpt-5.3-codex"
    try:
        tokens = OAuthTokenStore().load()
    except OAuthNotLoggedIn:
        print("❌ Nessun login OAuth. Esegui prima:  tradingagents login")
        return 2
    print(f"✓ Token trovato (account: {tokens.account_id}, scaduto: {tokens.is_expired()})")
    print(f"→ Chiamata live al backend Codex con model '{model}'...")

    llm = create_llm_client("openai-oauth", model).get_llm()
    # Usa un system message: riproduce lo scenario reale degli agenti (il backend
    # Codex rifiuta i system message in input -> devono finire in instructions).
    from langchain_core.messages import SystemMessage, HumanMessage
    messages = [
        SystemMessage("You are a terse assistant. Follow the user instruction exactly."),
        HumanMessage("Reply with exactly this token and nothing else: TRADINGAGENTS_OK"),
    ]
    try:
        resp = llm.invoke(messages)
    except Exception as exc:  # noqa: BLE001 — vogliamo mostrare l'errore reale del backend
        print(f"❌ Chiamata fallita: {type(exc).__name__}: {exc}")
        return 1

    content = getattr(resp, "content", resp)
    print(f"✓ Risposta del modello: {content!r}")
    print("✅ SMOKE TEST OK — il provider openai-oauth funziona end-to-end."
          if "TRADINGAGENTS_OK" in str(content)
          else "⚠️ Risposta ricevuta ma inattesa (il backend ha risposto, il modello ha deviato).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
