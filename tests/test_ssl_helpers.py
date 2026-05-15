"""Tests for the shared SSL context helper."""

import ssl

import pytest

from tradingagents.dataflows.ssl_helpers import default_ssl_context


class TestDefaultSslContext:
    """default_ssl_context() returns a usable SSLContext."""

    def test_returns_ssl_context(self) -> None:
        ctx = default_ssl_context()
        assert isinstance(ctx, ssl.SSLContext)

    def test_cached_singleton(self) -> None:
        ctx1 = default_ssl_context()
        ctx2 = default_ssl_context()
        assert ctx1 is ctx2

    def test_verify_mode_is_cert_required(self) -> None:
        ctx = default_ssl_context()
        assert ctx.verify_mode == ssl.CERT_REQUIRED

    def test_has_ca_certs_loaded(self) -> None:
        ctx = default_ssl_context()
        stats = ctx.cert_store_stats()
        assert stats["x509_ca"] > 0, "expected at least one CA cert loaded"
