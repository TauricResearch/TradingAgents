import codecs
import locale
import os

import pytest

from pandas._config.localization import (
    can_set_locale,
    get_locales,
    set_locale,
)

from pandas.compat import ISMUSL

import pandas as pd

_all_locales = get_locales()
_current_locale = locale.setlocale(locale.LC_ALL)  # getlocale() is wrong, see GH#46595

# Don't run any of these tests if we have no locales.
pytestmark = pytest.mark.skipif(not _all_locales, reason="Need locales")

_skip_if_only_one_locale = pytest.mark.skipif(
    len(_all_locales) <= 1, reason="Need multiple locales for meaningful test"
)


def _get_current_locale(lc_var: int = locale.LC_ALL) -> str:
    # getlocale is not always compliant with setlocale, use setlocale. GH#46595
    return locale.setlocale(lc_var)


@pytest.mark.parametrize("lc_var", (locale.LC_ALL, locale.LC_CTYPE, locale.LC_TIME))
def test_can_set_current_locale(lc_var):
    # Can set the current locale
    before_locale = _get_current_locale(lc_var)
    assert can_set_locale(before_locale, lc_var=lc_var)
    after_locale = _get_current_locale(lc_var)
    assert before_locale == after_locale


@pytest.mark.parametrize("lc_var", (locale.LC_ALL, locale.LC_CTYPE, locale.LC_TIME))
def test_can_set_locale_valid_set(lc_var):
    # Can set the default locale.
    before_locale = _get_current_locale(lc_var)
    assert can_set_locale("", lc_var=lc_var)
    after_locale = _get_current_locale(lc_var)
    assert before_locale == after_locale


@pytest.mark.parametrize(
    "lc_var",
    (
        locale.LC_ALL,
        locale.LC_CTYPE,
        pytest.param(
            locale.LC_TIME,
            marks=pytest.mark.skipif(
                ISMUSL, reason="MUSL allows setting invalid LC_TIME."
            ),
        ),
    ),
)
def test_can_set_locale_invalid_set(lc_var):
    # Cannot set an invalid locale.
    before_locale = _get_current_locale(lc_var)
    assert not can_set_locale("non-existent_locale", lc_var=lc_var)
    after_locale = _get_current_locale(lc_var)
    assert before_locale == after_locale


@pytest.mark.parametrize(
    "lang,enc",
    [
        ("it_CH", "UTF-8"),
        ("en_US", "ascii"),
        ("zh_CN", "GB2312"),
        ("it_IT", "ISO-8859-1"),
    ],
)
@pytest.mark.parametrize("lc_var", (locale.LC_ALL, locale.LC_CTYPE, locale.LC_TIME))
def test_can_set_locale_no_leak(lang, enc, lc_var):
    # Test that can_set_locale does not leak even when returning False. See GH#46595
    before_locale = _get_current_locale(lc_var)
    can_set_locale((lang, enc), locale.LC_ALL)
    after_locale = _get_current_locale(lc_var)
    assert before_locale == after_locale


def test_can_set_locale_invalid_get(monkeypatch):
    # see GH#22129
    # In some cases, an invalid locale can be set,
    #  but a subsequent getlocale() raises a ValueError.

    def mock_get_locale():
        raise ValueError()

    with monkeypatch.context() as m:
        m.setattr(locale, "getlocale", mock_get_locale)
        assert not can_set_locale("")


def test_get_locales_at_least_one():
    # see GH#9744
    assert len(_all_locales) > 0


@_skip_if_only_one_locale
def test_get_locales_prefix():
    first_locale = _all_locales[0]
    assert len(get_locales(prefix=first_locale[:2])) > 0


@_skip_if_only_one_locale
@pytest.mark.parametrize(
    "lang,enc",
    [
        ("it_CH", "UTF-8"),
        ("en_US", "ascii"),
        ("zh_CN", "GB2312"),
        ("it_IT", "ISO-8859-1"),
    ],
)
def test_set_locale(lang, enc):
    before_locale = _get_current_locale()

    enc = codecs.lookup(enc).name
    new_locale = lang, enc

    if not can_set_locale(new_locale):
        msg = "unsupported locale setting"

        with pytest.raises(locale.Error, match=msg):
            with set_locale(new_locale):
                pass
    else:
        with set_locale(new_locale) as normalized_locale:
            new_lang, new_enc = normalized_locale.split(".")
            new_enc = codecs.lookup(enc).name

            normalized_locale = new_lang, new_enc
            assert normalized_locale == new_locale

    # Once we exit the "with" statement, locale should be back to what it was.
    after_locale = _get_current_locale()
    assert before_locale == after_locale


def test_encoding_detected():
    system_locale = os.environ.get("LC_ALL")
    system_encoding = system_locale.split(".")[-1] if system_locale else "utf-8"

    assert (
        codecs.lookup(pd.options.display.encoding).name
        == codecs.lookup(system_encoding).name
    )
