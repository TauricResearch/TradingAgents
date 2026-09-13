"""Devin Bridge — local OpenAI Chat Completions sidecar backed by the Devin CLI.

This package implements a local HTTP server that translates OpenAI Chat
Completions requests into fresh ``devin -p`` invocations using the
authenticated Devin CLI. It is a separate sidecar — NOT part of the
TradingAgents package. TradingAgents points its existing ``openai_compatible``
provider at this server's loopback URL.

Run with::

    python -m devin_bridge
    python -m devin_bridge --help
"""

__version__ = "0.1.0"
