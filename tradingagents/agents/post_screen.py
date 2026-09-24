"""Social-post screening with TypeSafe's Jev, when ``TYPESAFE_API_KEY`` is set.

Jev answers typed questions with calibrated probabilities. Each StockTwits or
Reddit post is asked two: is it about the instrument, and which way does it
lean on the instrument's stock. Code turns the answers into what the Sentiment
Analyst reads: posts that are clearly about something else are dropped, and a
stance count over the rest heads the source's block.

Configured by TypeSafe's own SDK variables, ``TYPESAFE_API_KEY`` and
``TYPESAFE_DEFAULT_MODEL``. Without a key nothing here runs; if any request fails, the source's posts are kept unscreened and the
block says screening was unavailable.
"""

import logging
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from tradingagents.agents.context import resolve_instrument_identity

logger = logging.getLogger(__name__)

_URL = "https://api.typesafe.ai/v1/systemone"
_DEFAULT_MODEL = "jev-latest"
_RETRY_STATUSES = (429, 529)    # rate limited, overloaded: back off and retry
_TRANSIENT = (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError)
_ATTEMPTS = 3
_MAX_WAIT = 30.0
_TIMEOUT = 15.0
_WORKERS = 16                   # well inside the documented 1,200 requests per minute

# A post is dropped only on a clear "not about it"; the uncertain middle stays.
_OFF_TOPIC_BELOW = 0.3
# A stance counts only when Jev is not genuinely uncertain about it.
_STANCE_CONFIDENCE = 0.5

QUESTIONS = {
    "about": {
        "type": "noul",
        "instructions": "Is `post` about `instrument`: the company, its stock, its products or its outlook?",
        "criteria": {
            "true": "`post` discusses `instrument` itself.",
            "false": "`post` names `instrument` only in passing or in a list of tickers, is spam or "
                     "promotion, or is about a different company.",
        },
    },
    "stance": {
        "type": "choice",
        "instructions": "What does the author of `post` expect for the stock price of `instrument`?",
        "criteria": {
            "bullish": "The author expects `instrument`'s stock to rise, or is buying or holding it long.",
            "bearish": "The author expects `instrument`'s stock to fall, or is selling or shorting it.",
            "neutral": "The author gives no view of their own on `instrument`'s stock: a question, "
                       "news without opinion, or someone else's view quoted.",
        },
    },
}


class TypeSafeError(Exception):
    """A System One request that did not produce answers."""


def system_one(state, questions: dict) -> dict[str, dict]:
    """Ask ``questions`` about ``state``; return the answers keyed by question name.

    Rate-limit and overload responses and dropped connections are retried with
    backoff, honouring ``Retry-After``; any other failure raises
    ``TypeSafeError`` at once.
    """
    body = {
        "state": state,
        "model": os.environ.get("TYPESAFE_DEFAULT_MODEL") or _DEFAULT_MODEL,
        "questions": questions,
    }
    headers = {"Authorization": f"Bearer {os.environ.get('TYPESAFE_API_KEY', '')}"}
    backoff, retry_after = 1.0, None
    for attempt in range(_ATTEMPTS):
        if attempt:
            time.sleep(retry_after if retry_after is not None else backoff * random.uniform(0.8, 1.2))
            backoff *= 2
        try:
            response = requests.post(_URL, json=body, headers=headers, timeout=_TIMEOUT)
        except requests.RequestException as exc:
            failure, retry_after = type(exc).__name__, None
            if isinstance(exc, _TRANSIENT):
                continue
            break
        if response.status_code == 200:
            return _answers(response, questions)
        failure, retry_after = f"HTTP {response.status_code}", _retry_after(response)
        if response.status_code not in _RETRY_STATUSES:
            break
    raise TypeSafeError(failure)


def _retry_after(response) -> float | None:
    try:
        return min(max(0.0, float(response.headers.get("retry-after"))), _MAX_WAIT)
    except (TypeError, ValueError):
        return None


def _answers(response, questions: dict) -> dict[str, dict]:
    try:
        payload = response.json()
        answers = payload["answers"]
        if all(answers[q]["type"] == spec["type"] for q, spec in questions.items()):
            logger.debug("TypeSafe answered with %s", payload.get("model"))
            return answers
    except (ValueError, KeyError, TypeError):
        pass
    raise TypeSafeError("malformed response")


def _stance(answer: dict) -> str:
    choice = answer["choice"]
    if choice not in QUESTIONS["stance"]["criteria"] or answer["confidence"] < _STANCE_CONFIDENCE:
        return "unclear"
    return choice


def jev_screen(ticker: str):
    """A post screen for the social fetchers, or None without a TypeSafe key.

    The screen takes the post texts and returns one keep flag per post and a
    note line for the top of the source's block.
    """
    if not os.environ.get("TYPESAFE_API_KEY"):
        return None
    name = resolve_instrument_identity(ticker).get("company_name")
    instrument = f"{name} ({ticker})" if name else ticker

    def screen(posts: list[str]) -> tuple[list[bool], str]:
        try:
            answers = _ask_each(instrument, posts)
            keep = [a["about"]["noul"] >= _OFF_TOPIC_BELOW for a in answers]
            stances = [_stance(a["stance"]) for a, kept in zip(answers, keep, strict=True) if kept]
        except (KeyError, TypeError):
            return _unscreened(instrument, posts, "malformed response")
        except TypeSafeError as exc:
            return _unscreened(instrument, posts, str(exc))
        counts = ", ".join(f"{stances.count(s)} {s}" for s in ("bullish", "bearish", "neutral", "unclear"))
        return keep, (
            f"Screened by Jev: {len(stances)} of the {len(posts)} posts fetched are about "
            f"{instrument}; their stance on its stock: {counts}."
        )

    return screen


def _unscreened(instrument: str, posts: list[str], failure: str) -> tuple[list[bool], str]:
    logger.warning("Jev screening failed for %s: %s", instrument, failure)
    return [True] * len(posts), f"<Jev screening unavailable ({failure}); posts are unscreened>"


def _ask_each(instrument: str, posts: list[str]) -> list[dict]:
    """One request per post. The first failure raises at once: requests not yet
    sent are cancelled, and those in flight finish in the background unread."""
    answers: list = [None] * len(posts)
    pool = ThreadPoolExecutor(max_workers=_WORKERS)
    try:
        futures = {
            pool.submit(system_one, {"instrument": instrument, "post": post}, QUESTIONS): i
            for i, post in enumerate(posts)
        }
        for future in as_completed(futures):
            answers[futures[future]] = future.result()
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return answers
