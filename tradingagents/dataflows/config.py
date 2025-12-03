from typing import Dict, Optional
from tradingagents.config import get_settings, update_settings

_config: Optional[Dict] = None
DATA_DIR: Optional[str] = None


def initialize_config():
    global _config, DATA_DIR
    if _config is None:
        settings = get_settings()
        _config = settings.to_dict()
        DATA_DIR = _config["data_dir"]


def set_config(config: Dict):
    global _config, DATA_DIR

    settings = get_settings()
    current_dict = settings.to_dict()
    current_dict.update(config)
    update_settings(**current_dict)

    _config = get_settings().to_dict()
    DATA_DIR = _config["data_dir"]


def get_config() -> Dict:
    global _config
    if _config is None:
        initialize_config()
    return _config.copy()


initialize_config()
