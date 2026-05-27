import pytest


@pytest.mark.unit
def test_mock_embedder_shape():
    from tradingagents.sensing.embeddings import MockEmbedder
    e = MockEmbedder(dim=384)
    v = e.embed("hello world")
    assert len(v) == 384
    assert all(isinstance(x, float) for x in v)


@pytest.mark.unit
def test_mock_embedder_deterministic():
    from tradingagents.sensing.embeddings import MockEmbedder
    e = MockEmbedder(dim=384)
    assert e.embed("foo") == e.embed("foo")
    assert e.embed("foo") != e.embed("bar")


@pytest.mark.unit
def test_mock_embedder_l2_normalized():
    """Vectors must be unit-norm so cosine == dot product."""
    import math
    from tradingagents.sensing.embeddings import MockEmbedder
    v = MockEmbedder(dim=384).embed("x")
    norm = math.sqrt(sum(x * x for x in v))
    assert abs(norm - 1.0) < 1e-6


@pytest.mark.unit
def test_sentence_transformer_embedder_lazy_import(monkeypatch):
    """Constructor must not fail at import-time even if the model isn't downloaded."""
    from tradingagents.sensing.embeddings import SentenceTransformerEmbedder
    # Should construct without loading the model.
    emb = SentenceTransformerEmbedder("sentence-transformers/all-MiniLM-L6-v2")
    assert emb.dim == 384  # documented constant for that model
