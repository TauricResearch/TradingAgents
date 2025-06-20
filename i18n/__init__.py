import importlib
from tradingagents.default_config import DEFAULT_CONFIG

def get_lang():
    lang_code = DEFAULT_CONFIG.get("language", "zh")
    try:
        lang_module = importlib.import_module(f"tradingagents.i18n.{lang_code}")
        return lang_module.LANG
    except Exception:
        # fallback to zh
        from .zh import LANG
        return LANG 