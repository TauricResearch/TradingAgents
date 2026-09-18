import builtins
import sys
import types

from tradingagents.dataflows import investboard


def test_register_is_a_no_op_without_the_companion_package(monkeypatch):
    real_import = builtins.__import__

    def refuse(name, *args, **kwargs):
        if name.startswith("tradingagents_investboard"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse)

    assert investboard.register() is False


def test_register_imports_the_companion_vendor_when_it_is_installed(monkeypatch):
    package = types.ModuleType("tradingagents_investboard")
    vendor = types.ModuleType("tradingagents_investboard.vendor")
    package.vendor = vendor
    monkeypatch.setitem(sys.modules, "tradingagents_investboard", package)
    monkeypatch.setitem(sys.modules, "tradingagents_investboard.vendor", vendor)

    assert investboard.register() is True


def test_the_default_vendor_choice_is_untouched():
    from tradingagents.default_config import DEFAULT_CONFIG

    assert "investboard" not in ",".join(DEFAULT_CONFIG["data_vendors"].values())
