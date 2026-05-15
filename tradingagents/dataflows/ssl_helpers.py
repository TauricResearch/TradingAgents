"""Shared SSL context for outbound HTTP requests.

macOS ships Python *without* linking the system certificate store into
``ssl.create_default_context()``.  The well-known symptom is::

    SSL: CERTIFICATE_VERIFY_FAILED — unable to get local issuer certificate

The ``certifi`` package (a transitive dependency of ``requests``, which is
already in the project requirements) bundles Mozilla's root CA bundle.
Building the default context with ``cafile=certifi.where()`` fixes the
problem on every platform without requiring the user to manually run
``/Applications/Python 3.x/Install Certificates.command``.
"""

from __future__ import annotations

import logging
import ssl
from functools import lru_cache

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def default_ssl_context() -> ssl.SSLContext:
    """Return a cached SSL context with proper CA certificates.

    Tries ``certifi`` first (works everywhere, including macOS).
    Falls back to the platform default (works on most Linux distros).
    """
    try:
        import certifi  # noqa: WPS433 — optional runtime import

        ctx = ssl.create_default_context(cafile=certifi.where())
        logger.debug("SSL context built with certifi CA bundle")
        return ctx
    except ImportError:
        logger.debug("certifi not installed; using platform default SSL context")
        return ssl.create_default_context()
