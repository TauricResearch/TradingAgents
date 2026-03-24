import json
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.json"


def load_config() -> dict:
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as config_file:
            config = json.load(config_file)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Config file not found: {CONFIG_PATH}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in config file: {CONFIG_PATH}") from exc
    except OSError as exc:
        raise RuntimeError(f"Unable to read config file: {CONFIG_PATH}") from exc
    if not isinstance(config, dict):
        raise RuntimeError(f"Invalid config format in file: {CONFIG_PATH}")
    return config


def get_config_section(config: dict, key: str, expected_type: type) -> Any:
    value = config.get(key)
    if not isinstance(value, expected_type):
        raise RuntimeError(f"Invalid or missing '{key}' in config file: {CONFIG_PATH}")
    return value


def get_base_urls_map(config: dict) -> dict[str, str]:
    base_urls = get_config_section(config, "BASE_URLS", list)
    mapped_urls: dict[str, str] = {}
    for item in base_urls:
        if (
            isinstance(item, list)
            and len(item) == 2
            and isinstance(item[0], str)
            and isinstance(item[1], str)
        ):
            mapped_urls[item[0].lower()] = item[1]
    return mapped_urls
