"""``get_scrubbed``: the vendor key must not survive into an error.

FRED and Alpha Vantage authenticate with a query parameter, so requests quotes
the key back in the text of HTTP, connection and timeout errors, and in the
``request`` and ``response`` it attaches (#1324). These pin every route by
which the value could reach a log or a traceback.

No network: ``requests.get`` is replaced throughout.
"""
import unittest
from unittest import mock

import pytest
import requests

from tradingagents.dataflows.utils import get_scrubbed

# A fabricated value in the shape of a FRED key. Never paste a real one into a
# fixture — a test file is exactly the kind of file that gets read and copied.
_KEY = "deadbeefdeadbeefdeadbeefdeadbeef"

# The shape requests produces when the host cannot be resolved: the full URL,
# key included.
_LEAK = (
    "HTTPSConnectionPool(host='api.stlouisfed.org', port=443): Max retries "
    f"exceeded with url: /fred/series?series_id=DGS10&api_key={_KEY}"
    "&file_type=json (Caused by NameResolutionError(...))"
)


def _response(status_code=200):
    response = mock.Mock(spec=requests.Response)
    response.status_code = status_code
    response.raise_for_status.side_effect = (
        None if status_code < 400 else requests.HTTPError(_LEAK)
    )
    return response


def _call(**kwargs):
    kwargs.setdefault("params", {"api_key": _KEY})
    kwargs.setdefault("timeout", 5)
    kwargs.setdefault("secret", _KEY)
    return get_scrubbed("https://api.stlouisfed.org/fred/series", **kwargs)


@pytest.mark.unit
class GetScrubbedSuccessTests(unittest.TestCase):
    def test_returns_the_response(self):
        response = _response()
        with mock.patch.object(requests, "get", return_value=response):
            self.assertIs(_call(), response)

    def test_a_passthrough_status_is_returned_not_raised(self):
        # FRED answers an unknown series with 400 and a JSON error body the
        # caller renders itself, so that status must come back intact.
        response = _response(400)
        with mock.patch.object(requests, "get", return_value=response):
            self.assertIs(_call(passthrough=(400,)), response)
        response.raise_for_status.assert_not_called()

    def test_a_status_outside_passthrough_still_raises(self):
        response = _response(500)
        with mock.patch.object(requests, "get", return_value=response), \
                self.assertRaises(requests.HTTPError):
            _call(passthrough=(400,))


@pytest.mark.unit
class GetScrubbedMaskingTests(unittest.TestCase):
    def test_the_key_is_replaced_in_the_message(self):
        with mock.patch.object(requests, "get", side_effect=requests.ConnectionError(_LEAK)), \
                self.assertRaises(requests.ConnectionError) as ctx:
            _call()
        self.assertNotIn(_KEY, str(ctx.exception))
        self.assertIn("api_key=***", str(ctx.exception))

    def test_the_rest_of_the_message_survives(self):
        # A masked error still has to be diagnosable: host, path and the other
        # parameters are what separate a DNS failure from a bad series ID.
        with mock.patch.object(requests, "get", side_effect=requests.ConnectionError(_LEAK)), \
                self.assertRaises(requests.ConnectionError) as ctx:
            _call()
        message = str(ctx.exception)
        self.assertIn("api.stlouisfed.org", message)
        self.assertIn("series_id=DGS10", message)
        self.assertIn("NameResolutionError", message)

    def test_the_exception_type_is_preserved(self):
        # The routing layer reacts by type, so masking must not flatten a
        # timeout into a generic error.
        for kind in (requests.ConnectionError, requests.Timeout, requests.HTTPError):
            with self.subTest(kind=kind.__name__):
                with mock.patch.object(requests, "get", side_effect=kind(_LEAK)), \
                        self.assertRaises(kind):
                    _call()

    def test_a_raised_status_is_masked_too(self):
        # The key reaches the error by a second route here: raise_for_status
        # builds its own message from the request URL.
        with mock.patch.object(requests, "get", return_value=_response(500)), \
                self.assertRaises(requests.HTTPError) as ctx:
            _call()
        self.assertNotIn(_KEY, str(ctx.exception))

    def test_no_secret_leaves_the_error_untouched(self):
        original = requests.ConnectionError("plain failure")
        with mock.patch.object(requests, "get", side_effect=original), \
                self.assertRaises(requests.ConnectionError) as ctx:
            _call(secret="")
        self.assertIs(ctx.exception, original)


@pytest.mark.unit
class GetScrubbedAttachmentTests(unittest.TestCase):
    """The message is only one of three ways the URL travels with an error."""

    def test_the_response_is_not_carried_over(self):
        # exc.response.url holds the unmasked URL, so a masked message alone
        # would still leave the key one attribute away.
        leaky = requests.HTTPError(_LEAK)
        leaky.response = mock.Mock(url=f"https://x.invalid/?api_key={_KEY}")
        with mock.patch.object(requests, "get", side_effect=leaky), \
                self.assertRaises(requests.HTTPError) as ctx:
            _call()
        self.assertIsNone(ctx.exception.response)

    def test_the_request_is_not_carried_over(self):
        leaky = requests.ConnectionError(_LEAK)
        leaky.request = mock.Mock(url=f"https://x.invalid/?api_key={_KEY}")
        with mock.patch.object(requests, "get", side_effect=leaky), \
                self.assertRaises(requests.ConnectionError) as ctx:
            _call()
        self.assertIsNone(ctx.exception.request)

    def test_the_original_is_not_chained(self):
        # Raising inside the except block would attach the unmasked original as
        # __context__, and a printed traceback would reprint the key below the
        # masked line. This is why the helper raises after the block.
        with mock.patch.object(requests, "get", side_effect=requests.ConnectionError(_LEAK)):
            try:
                _call()
            except requests.ConnectionError as exc:
                self.assertIsNone(exc.__cause__)
                self.assertIsNone(exc.__context__)


if __name__ == "__main__":
    unittest.main()
