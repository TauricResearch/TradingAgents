"""Shared proxy client utilities for pydantic-ai / mem0 / graphiti.

The cc-switch proxy at 127.0.0.1:15721 only routes two endpoint families:
  - /claude-desktop/v1/messages  (Anthropic Messages API — Claude Code path)
  - /v1/responses                (OpenAI Responses API — Codex path)

It does NOT route /v1/chat/completions or /v1/embeddings. Authentication
requires `Authorization: Bearer <ccs-token>`, not `x-api-key`.

This module centralizes:
  1. Gateway token resolution (from env or running Claude Code process)
  2. A Bearer-authenticated AsyncAnthropic client (for pydantic-ai + mem0)
  3. A local HuggingFace embedder (for mem0 + graphiti — the proxy has no embeddings)
  4. Factory helpers that wire the above into each library's expected shape
"""

from __future__ import annotations

import logging
import os
import subprocess
from functools import lru_cache
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Iterable

# --- Proxy constants -----------------------------------------------------------

PROXY_BASE = "http://127.0.0.1:15721"
ANTHROPIC_PROXY_BASE = f"{PROXY_BASE}/claude-desktop"
RESPONSES_PROXY_BASE = f"{PROXY_BASE}/v1"

# Model names the proxy actually routes (verified via /v1/responses).
# Claude names are mapped by cc-switch to GLM under the hood.
ANTHROPIC_MODEL = "claude-sonnet-4-6"
RESPONSES_MODEL = "gpt-5.6-sol"

# Local embedding model — 384-dim, small & fast, no proxy dependency.
HF_EMBEDDING_MODEL = "multi-qa-MiniLM-L6-cos-v1"
HF_EMBEDDING_DIM = 384


# --- Token resolution ----------------------------------------------------------


def resolve_gateway_token() -> str:
    """Resolve the cc-switch gateway token (``ccs-`` prefix).

    Priority:
      1. ``TRADINGAGENTS_PROXY_TOKEN`` env var (explicit override)
      2. ``ANTHROPIC_AUTH_TOKEN`` env var (inherited from Claude Code)
      3. Extracted from a running ``claude`` process environment

    Raises:
        RuntimeError: if no token can be resolved.
    """
    for var in ("TRADINGAGENTS_PROXY_TOKEN", "ANTHROPIC_AUTH_TOKEN"):
        val = os.environ.get(var)
        if val and val.startswith("ccs-"):
            return val

    # Fallback: extract from a running claude-code process.
    try:
        ps = subprocess.run(["ps", "eww", "-p"], capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise RuntimeError("Cannot resolve cc-switch gateway token: ps unavailable.") from exc

    for line in ps.stdout.splitlines():
        if "MacOS/claude" not in line:
            continue
        for token in line.split():
            if token.startswith("ANTHROPIC_AUTH_TOKEN=ccs-"):
                resolved = token.split("=", 1)[1]
                logger.debug("Resolved gateway token from running claude process.")
                return resolved

    raise RuntimeError(
        "No cc-switch gateway token found. Set TRADINGAGENTS_PROXY_TOKEN or "
        "run within a Claude Code session."
    )


# --- AsyncAnthropic with Bearer auth -------------------------------------------


@lru_cache(maxsize=1)
def make_anthropic_client() -> "Any":
    """Build an AsyncAnthropic that sends ``Authorization: Bearer``.

    The proxy rejects ``x-api-key`` (set by ``api_key=``) with
    "缺少 Authorization 头". ``auth_token=`` makes the SDK send the Bearer
    header the proxy requires.
    """
    from anthropic import AsyncAnthropic

    return AsyncAnthropic(
        auth_token=resolve_gateway_token(),
        base_url=ANTHROPIC_PROXY_BASE,
    )


# --- Local HuggingFace embedder (shared) ---------------------------------------


@lru_cache(maxsize=1)
def _hf_model() -> "Any":
    """Lazy-load the sentence-transformers model once per process."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(HF_EMBEDDING_MODEL)


def hf_embed(text: str) -> list[float]:
    """Embed a single string locally (normalized)."""
    return _hf_model().encode(text, normalize_embeddings=True).tolist()


def hf_embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a batch of strings locally (normalized)."""
    return _hf_model().encode(texts, normalize_embeddings=True).tolist()


# --- Factory: pydantic-ai Agent ------------------------------------------------


def make_pydantic_ai_agent(output_type: type, instructions: str, **agent_kwargs: Any) -> "Any":
    """Build a pydantic-ai Agent wired to the proxy's anthropic endpoint.

    Args:
        output_type: A Pydantic BaseModel class used as the typed result.
        instructions: System instructions for the agent.
        **agent_kwargs: Forwarded to ``Agent`` (e.g. ``deps_type``, ``tools``).
    """
    from pydantic_ai import Agent
    from pydantic_ai.models.anthropic import AnthropicModel
    from pydantic_ai.providers.anthropic import AnthropicProvider

    model = AnthropicModel(
        ANTHROPIC_MODEL,
        provider=AnthropicProvider(anthropic_client=make_anthropic_client()),
    )
    return Agent(
        model,
        output_type=output_type,
        instructions=instructions,
        **agent_kwargs,
    )


# --- Factory: mem0 Memory ------------------------------------------------------


def make_mem0_memory(user_id: str = "default") -> "Any":
    """Build a mem0 Memory backed by proxy LLM + local HF embedder.

    LLM: langchain provider + ChatAnthropic (Bearer auth via default_headers,
    since ChatAnthropic forwards ``auth_token`` into messages.create() which
    the SDK rejects). Embedder: local HuggingFace (proxy has no embeddings).
    """
    from langchain_anthropic import ChatAnthropic
    from mem0 import Memory

    token = resolve_gateway_token()
    llm = ChatAnthropic(
        model=ANTHROPIC_MODEL,
        base_url=ANTHROPIC_PROXY_BASE,
        api_key="sk-ant-proxy-placeholder",  # required by SDK; proxy ignores x-api-key
        default_headers={"Authorization": f"Bearer {token}"},
        max_tokens=2000,
        temperature=0.1,
    )

    config: dict[str, Any] = {
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "path": os.environ.get("MEM0_QDRANT_PATH", "/tmp/qdrant_tradingagents"),
                "embedding_model_dims": HF_EMBEDDING_DIM,
            },
        },
        "llm": {
            "provider": "langchain",
            "config": {"model": llm, "temperature": 0.1, "max_tokens": 2000},
        },
        "embedder": {
            "provider": "huggingface",
            "config": {
                "model": HF_EMBEDDING_MODEL,
                "embedding_dims": HF_EMBEDDING_DIM,
            },
        },
        "history_db_path": os.environ.get("MEM0_HISTORY_PATH", "/tmp/mem0_tradingagents.db"),
    }
    os.environ.setdefault("MEM0_TELEMETRY", "False")
    return Memory.from_config(config)


# --- Factory: graphiti Graphiti ------------------------------------------------


def make_graphiti(db_path: str = ":memory:") -> "Any":
    """Build a graphiti Graphiti wired to the proxy + local embedder.

    LLM: OpenAIClient (responses API — the proxy routes /v1/responses).
    Embedder: local HuggingFace (proxy has no embeddings endpoint).
    Cross-encoder: no-op (avoids requiring an OpenAI reranker key).
    Graph: Kuzu embedded (zero infrastructure). Note Kuzu's fulltext search
    is broken in graphiti — use direct Cypher queries via the driver instead
    of ``graphiti.search()``.
    """
    from graphiti_core import Graphiti
    from graphiti_core.cross_encoder import CrossEncoderClient
    from graphiti_core.driver.kuzu_driver import KuzuDriver
    from graphiti_core.embedder import EmbedderClient
    from graphiti_core.llm_client.config import LLMConfig
    from graphiti_core.llm_client.openai_client import OpenAIClient

    token = resolve_gateway_token()

    class _NoOpReranker(CrossEncoderClient):
        async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
            return [(p, 1.0) for p in passages]

    class _HuggingFaceEmbedder(EmbedderClient):
        def __init__(self) -> None:
            self.config = type(
                "C",
                (),
                {"embedding_model": HF_EMBEDDING_MODEL, "embedding_dim": HF_EMBEDDING_DIM},
            )()

        async def create(
            self, input_data: "str | list[str] | Iterable[int] | Iterable[Iterable[int]]"
        ) -> list[float]:
            return hf_embed(input_data)  # type: ignore[arg-type]

        async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
            return hf_embed_batch(input_data_list)

    llm_config = LLMConfig(
        api_key=token,
        model=RESPONSES_MODEL,
        small_model=RESPONSES_MODEL,  # default gpt-4.1-nano is not routed by the proxy
        base_url=RESPONSES_PROXY_BASE,
        max_tokens=4000,
    )
    return Graphiti(
        graph_driver=KuzuDriver(db=db_path),
        llm_client=OpenAIClient(config=llm_config),
        embedder=_HuggingFaceEmbedder(),
        cross_encoder=_NoOpReranker(),
    )
