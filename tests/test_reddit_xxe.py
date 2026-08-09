"""Tests for XXE hardening in the Reddit Atom parser (issue #1206).

The RSS path parses Reddit-supplied XML with ElementTree; a malicious or
compromised feed could smuggle an external entity (XXE) that reads local
files or hits internal hosts. The parser must not resolve external
entities, and must degrade to an empty result rather than raising on a
feed that references one.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tradingagents.dataflows import reddit

# A feed that declares an external entity pointing at a local file and
# references it inside the title. If the parser resolved entities, the
# title would leak file contents; if it errors on the undefined entity,
# the fetch must still return [] (graceful degradation), not raise.
_XXE_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE feed [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>leak: &xxe;</title>
    <published>2026-05-20T14:30:00+00:00</published>
    <content type="html">&lt;p&gt;body&lt;/p&gt;</content>
  </entry>
</feed>
"""


def _resp(data: bytes):
    class _Resp:
        def __enter__(self_inner):
            return self_inner

        def __exit__(self_inner, *a):
            return False

        def read(self_inner):
            return data
    return _Resp()


@pytest.mark.unit
class TestXxeHardening:
    def test_external_entity_not_resolved(self):
        """A feed with an external entity must not leak file contents."""
        with patch.object(reddit, "urlopen", return_value=_resp(_XXE_ATOM.encode("utf-8"))):
            posts = reddit._fetch_subreddit_rss("NVDA", "stocks", limit=5, timeout=5.0)
        assert isinstance(posts, list)
        # If any post survived, its title must not contain file contents.
        for post in posts:
            assert "root:" not in post["title"]
            assert "/bin/bash" not in post["title"]

    def test_xxe_feed_degrades_gracefully(self):
        """The fetcher must return [] (or benign posts), never raise, on an XXE feed."""
        with patch.object(reddit, "urlopen", return_value=_resp(_XXE_ATOM.encode("utf-8"))):
            posts = reddit._fetch_subreddit_rss("NVDA", "stocks", limit=5, timeout=5.0)
        # Graceful: either no posts at all, or posts whose title is not the
        # resolved entity value.
        assert isinstance(posts, list)
        for post in posts:
            assert "leak:" not in post["title"]

    def test_normal_feed_still_parses(self):
        """Hardening must not break the happy path."""
        atom = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>NVDA earnings</title>
    <published>2026-05-20T14:30:00+00:00</published>
    <content type="html">&lt;p&gt;Great quarter&lt;/p&gt;</content>
  </entry>
</feed>
"""
        with patch.object(reddit, "urlopen", return_value=_resp(atom.encode("utf-8"))):
            posts = reddit._fetch_subreddit_rss("NVDA", "stocks", limit=5, timeout=5.0)
        assert len(posts) == 1
        assert posts[0]["title"] == "NVDA earnings"
