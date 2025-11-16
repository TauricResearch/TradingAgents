"""
OpenRouter client for LLM-powered sentiment analysis and embeddings.
"""

import json
import logging
import os

import requests

from tradingagents.config import TradingAgentsConfig

logger = logging.getLogger(__name__)


class SentimentResult:
    """Structured sentiment analysis result."""

    def __init__(self, sentiment: str, confidence: float, reasoning: str | None = None):
        self.sentiment = sentiment
        self.confidence = confidence
        self.reasoning = reasoning


class OpenRouterClient:
    """OpenRouter client for sentiment analysis and embeddings."""

    def __init__(self, config: TradingAgentsConfig):
        self.config = config
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY environment variable is required")

        self.base_url = "https://openrouter.ai/api/v1"
        self.sentiment_model = (
            config.news_sentiment_llm
        )  # Use dedicated news sentiment model
        self.embedding_model = config.news_embedding_llm

    def analyze_sentiment(self, text: str) -> SentimentResult:
        """
        Analyze sentiment of news article content using OpenRouter LLM.

        Args:
            text: News article content to analyze

        Returns:
            SentimentResult with structured sentiment data
        """
        if not text or len(text.strip()) < 50:
            return SentimentResult(
                sentiment="neutral",
                confidence=0.0,
                reasoning="Insufficient text for analysis",
            )

        prompt = self._create_sentiment_prompt(text)

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/martinrichards23/TradingAgents",
                "X-Title": "TradingAgents News Sentiment Analysis",
            }

            payload = {
                "model": self.sentiment_model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a financial news sentiment analyst. Always respond with valid JSON in the specified format.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.1,  # Low temperature for consistent results
                "max_tokens": 200,
            }

            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30,
            )

            if response.status_code != 200:
                logger.error(
                    f"OpenRouter API error: {response.status_code} - {response.text}"
                )
                raise Exception(f"OpenRouter API error: {response.status_code}")

            result = response.json()
            content = result["choices"][0]["message"]["content"]

            # Parse structured response
            try:
                sentiment_data = json.loads(content)
                return SentimentResult(
                    sentiment=sentiment_data.get("sentiment", "neutral"),
                    confidence=sentiment_data.get("confidence", 0.0),
                    reasoning=sentiment_data.get("reasoning", "LLM analysis complete"),
                )
            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f"Failed to parse sentiment response: {content} - {e}")
                # Fallback to neutral sentiment
                return SentimentResult(
                    sentiment="neutral",
                    confidence=0.0,
                    reasoning="Failed to parse LLM response",
                )

        except requests.exceptions.Timeout:
            logger.error("OpenRouter sentiment analysis timeout")
            return SentimentResult(
                sentiment="neutral", confidence=0.0, reasoning="Analysis timeout"
            )
        except Exception as e:
            logger.error(f"OpenRouter sentiment analysis failed: {e}")
            return SentimentResult(
                sentiment="neutral",
                confidence=0.0,
                reasoning=f"Analysis failed: {str(e)}",
            )

    def create_embedding(self, text: str) -> list[float]:
        """
        Create vector embedding for text using OpenRouter embeddings API.

        Args:
            text: Text to embed (truncated to token limits)

        Returns:
            List of float values representing the embedding vector
        """
        if not text:
            raise ValueError("Text cannot be empty for embedding")

        # Truncate text for embedding model (token limit ~8192)
        truncated_text = text[:8000] if len(text) > 8000 else text

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/martinrichards23/TradingAgents",
                "X-Title": "TradingAgents News Embeddings",
            }

            payload = {"model": self.embedding_model, "input": truncated_text}

            response = requests.post(
                f"{self.base_url}/embeddings", headers=headers, json=payload, timeout=30
            )

            if response.status_code != 200:
                error_text = response.text
                logger.error(
                    f"OpenRouter embeddings API error: {response.status_code} - {error_text}"
                )
                raise Exception(
                    f"OpenRouter embeddings API error: {response.status_code}"
                )

            result = response.json()
            embedding = result["data"][0]["embedding"]

            if len(embedding) != 1536:
                logger.error(
                    f"Unexpected embedding dimension: {len(embedding)}, expected 1536"
                )

            return embedding

        except requests.exceptions.Timeout:
            logger.error("OpenRouter embedding generation timeout")
            raise
        except Exception as e:
            logger.error(f"OpenRouter embedding generation failed: {e}")
            raise

    def _create_sentiment_prompt(self, text: str) -> str:
        """Create structured prompt for sentiment analysis."""
        # Truncate very long articles for cost efficiency
        truncated_text = text[:2000] if len(text) > 2000 else text

        return f"""Analyze the sentiment of this financial news article. Respond with JSON in this exact format:
{{
  "sentiment": "positive|negative|neutral",
  "confidence": 0.0-1.0,
  "reasoning": "Brief explanation"
}}

Article:
{truncated_text}

Focus on:
- Overall market/stock sentiment impact
- Financial performance indicators
- Risk factors mentioned
- Business outlook expressed

Consider financial context and avoid overreacting to minor fluctuations. Be objective and data-driven."""
