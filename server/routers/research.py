"""User research notes: upload (PDF/MD/TXT) → LLM summary, list, delete."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile

import user_prefs
from tradingagents.dataflows.user_research import (
    delete_research,
    ingest_research,
    list_research,
)
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients import create_llm_client
from ..deps import require_auth
from ..schemas import OkMessage

router = APIRouter(prefix="/api", tags=["research"])


def _summarizer():
    """A quick-model LLM with an .invoke(prompt)->resp interface."""
    provider = DEFAULT_CONFIG.get("llm_provider", "doubao")
    model = DEFAULT_CONFIG.get("quick_think_llm", "")
    return create_llm_client(provider, model).get_llm()


@router.get("/research")
def research_list(ticker: str, email: str = Depends(require_auth)):
    return list_research(user_prefs.user_home(email), ticker)


@router.post("/research")
async def research_upload(
    ticker: str = Form(...),
    file: UploadFile = File(...),
    email: str = Depends(require_auth),
):
    data = await file.read()
    meta = ingest_research(
        data, file.filename, ticker, user_prefs.user_home(email), _summarizer()
    )
    return meta


@router.delete("/research/{ticker}/{digest}", response_model=OkMessage)
def research_delete(ticker: str, digest: str, email: str = Depends(require_auth)):
    delete_research(user_prefs.user_home(email), ticker, digest)
    return OkMessage(ok=True)
