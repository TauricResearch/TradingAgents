"""Financial situation memory using hybrid BM25 plus regime-tag retrieval."""

from __future__ import annotations

from rank_bm25 import BM25Okapi
from typing import Any, List, Tuple
import re


class FinancialSituationMemory:
    """Memory system for storing and retrieving financial situations."""

    def __init__(self, name: str, config: dict | None = None):
        self.name = name
        self.config = config or {}
        self.documents: List[str] = []
        self.recommendations: List[str] = []
        self.metadata: List[dict[str, Any]] = []
        self.bm25 = None
        self.default_n_matches = int(self.config.get("memory_n_matches", 2))

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r"\b\w+\b", text.lower())

    def _extract_regime_tags(self, text: str) -> set[str]:
        lowered = text.lower()
        tags: set[str] = set()
        keyword_groups = {
            "volatility": ("volatility", "atr", "drawdown", "swing", "high-volatility"),
            "trend_up": ("uptrend", "trending up", "breakout", "bullish", "momentum"),
            "trend_down": ("downtrend", "trending down", "selloff", "bearish", "breakdown"),
            "range_bound": ("range-bound", "sideways", "consolidation", "choppy"),
            "rates": ("interest rate", "fed", "fomc", "yield", "monetary"),
            "earnings": ("earnings", "guidance", "quarter", "revenue", "eps"),
            "insider": ("insider", "buyback", "share issuance"),
            "kr": ("krx", ".ks", ".kq", "korea", "한국", "원", "krw"),
            "us": ("nasdaq", "nyse", "usd", "federal reserve", "u.s.", "us/eastern"),
            "sentiment": ("sentiment", "narrative", "social", "headline"),
            "macro": ("inflation", "cpi", "gdp", "macro", "employment"),
        }
        for tag, keywords in keyword_groups.items():
            if any(keyword in lowered for keyword in keywords):
                tags.add(tag)
        return tags

    def _rebuild_index(self):
        if self.documents:
            tokenized_docs = [self._tokenize(doc) for doc in self.documents]
            self.bm25 = BM25Okapi(tokenized_docs)
        else:
            self.bm25 = None

    def add_situations(self, situations_and_advice: List[Tuple]):
        for item in situations_and_advice:
            if len(item) == 2:
                situation, recommendation = item
                metadata = {}
            elif len(item) == 3:
                situation, recommendation, metadata = item
            else:
                raise ValueError("Each memory entry must be (situation, recommendation) or (situation, recommendation, metadata).")

            combined_metadata = dict(metadata or {})
            combined_metadata.setdefault("regime_tags", sorted(self._extract_regime_tags(str(situation))))
            self.documents.append(str(situation))
            self.recommendations.append(str(recommendation))
            self.metadata.append(combined_metadata)

        self._rebuild_index()

    def get_memories(
        self,
        current_situation: str,
        n_matches: int | None = None,
        metadata_filters: dict[str, Any] | None = None,
    ) -> List[dict]:
        if not self.documents or self.bm25 is None:
            return []

        limit = n_matches if n_matches is not None else self.default_n_matches
        query_tokens = self._tokenize(current_situation)
        query_tags = self._extract_regime_tags(current_situation)
        scores = self.bm25.get_scores(query_tokens)
        max_score = max(scores) if max(scores) > 0 else 1

        ranked_results = []
        for idx, score in enumerate(scores):
            metadata = self.metadata[idx] if idx < len(self.metadata) else {}
            if metadata_filters:
                if any(metadata.get(key) != value for key, value in metadata_filters.items()):
                    continue

            normalized_bm25 = score / max_score if max_score > 0 else 0
            doc_tags = set(metadata.get("regime_tags", []))
            tag_score = len(query_tags & doc_tags) / len(query_tags | doc_tags) if (query_tags or doc_tags) else 0
            hybrid_score = 0.75 * normalized_bm25 + 0.25 * tag_score
            ranked_results.append((hybrid_score, normalized_bm25, tag_score, idx, metadata))

        ranked_results.sort(key=lambda item: item[0], reverse=True)

        results = []
        for hybrid_score, normalized_bm25, tag_score, idx, metadata in ranked_results[:limit]:
            results.append(
                {
                    "matched_situation": self.documents[idx],
                    "recommendation": self.recommendations[idx],
                    "similarity_score": hybrid_score,
                    "bm25_score": normalized_bm25,
                    "tag_overlap_score": tag_score,
                    "metadata": metadata,
                }
            )

        return results

    def clear(self):
        self.documents = []
        self.recommendations = []
        self.metadata = []
        self.bm25 = None
