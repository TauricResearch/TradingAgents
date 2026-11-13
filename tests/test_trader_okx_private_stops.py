"""Amending a pending stop in place (OKX's amend-algos), for an executor that never
leaves a position between two stops. The answers are the shapes OKX documents for the
endpoint ("Amend algo order", https://www.okx.com/docs-v5/en/); none of them has been
recorded from the exchange yet (#42). Nothing touches the network."""

import json

import pytest
import requests

from tests.test_trader_okx_private import T0, client
from trader import okx_private
from trader.okx_private import OKXPrivateError, StopOrder

AMEND = ("POST", "/api/v5/trade/amend-algos")
DONE = [{"algoId": "a1", "algoClOrdId": "stp1btc", "reqId": "", "sCode": "0", "sMsg": ""}]
STOP = StopOrder("a1", "stp1btc", "BTC-USDT-SWAP", "sell", 10.0, 79_000.0, True, T0)


def refusal(code, message):
    return {"code": "1", "msg": "All operations failed", "data": [
        {"algoId": "a1", "algoClOrdId": "stp1btc", "reqId": "", "sCode": code, "sMsg": message},
    ]}


def test_a_new_trigger_is_amended_as_a_market_stop_on_the_last_price_and_the_size_left_out():
    okx, session = client([(AMEND, DONE)])
    assert okx.amend_stop(STOP, 10, 81_000.5) is None
    assert json.loads(session.calls[0][2]) == {
        "instId": "BTC-USDT-SWAP", "algoId": "a1", "cxlOnFail": False,
        "newSlTriggerPx": "81000.5", "newSlOrdPx": "-1", "newSlTriggerPxType": "last",
    }


def test_a_new_size_is_amended_unsigned_and_the_trigger_left_out():
    okx, session = client([(AMEND, DONE), (AMEND, DONE)])
    okx.amend_stop(STOP, 20, 79_000.0)
    assert json.loads(session.calls[0][2]) == {
        "instId": "BTC-USDT-SWAP", "algoId": "a1", "cxlOnFail": False, "newSz": "20",
    }
    # A short's stop buys: the count comes signed like place_stop's, its size is sent.
    short = StopOrder("a2", "stp1eth", "ETH-USDT-SWAP", "buy", 9.99, 3_200.0, True, T0)
    okx.amend_stop(short, -5.5, 3_150.0)
    assert json.loads(session.calls[1][2]) == {
        "instId": "ETH-USDT-SWAP", "algoId": "a2", "cxlOnFail": False, "newSz": "5.5",
        "newSlTriggerPx": "3150", "newSlOrdPx": "-1", "newSlTriggerPxType": "last",
    }


def test_a_stop_that_already_is_as_asked_sends_no_request():
    okx, session = client()
    okx.amend_stop(STOP, 10, 79_000.0)
    assert session.calls == []


def test_the_stop_is_never_cancelled_when_the_amendment_fails():
    # cxlOnFail goes out as the JSON false, not left to OKX's default: a stop that
    # could not be amended must still be on the book.
    okx, session = client([(AMEND, DONE)])
    okx.amend_stop(STOP, 10, 81_000.0)
    assert '"cxlOnFail":false' in session.calls[0][2]


def test_a_refused_amendment_raises_its_item_code():
    okx, _ = client([
        (AMEND, refusal("51280", "SL trigger price cannot be higher than the last price.")),
        (AMEND, {"code": "51529", "data": [],
                 "msg": "Order modification unsuccessful. Stop order modification only applies"
                        " to Expiry Futures and Perpetual Futures."}),
    ])
    with pytest.raises(OKXPrivateError) as info:
        okx.amend_stop(STOP, 10, 81_000.0)
    assert info.value.code == "51280"
    assert str(info.value) == (
        "/api/v5/trade/amend-algos failed with code 51280:"
        " SL trigger price cannot be higher than the last price."
    )
    with pytest.raises(OKXPrivateError) as info:
        okx.amend_stop(STOP, 10, 81_000.0)
    assert info.value.code == "51529"


def test_an_amendment_whose_answer_was_lost_is_sent_again_and_the_error_is_the_second_answers(
    monkeypatch,
):
    # The transport resends a request that timed out. When the first one did go
    # through, the error the caller sees is whatever OKX makes of the second: it says
    # nothing about the stop on the book, which is why the executor reads it back.
    monkeypatch.setattr(okx_private.time, "sleep", lambda _: None)
    okx, session = client(
        [(AMEND, refusal("51527", "Order modification unsuccessful. The stop order does not exist."))],
        failures=[requests.Timeout("slow")],
    )
    with pytest.raises(OKXPrivateError) as info:
        okx.amend_stop(STOP, 10, 81_000.0)
    assert info.value.code == "51527"
    assert len(session.calls) == 2 and session.calls[0][2] == session.calls[1][2]
