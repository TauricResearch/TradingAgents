"""Serve the API on this machine only: python -m web.api, then http://127.0.0.1:8000/api."""

from __future__ import annotations

import uvicorn
from dotenv import find_dotenv, load_dotenv

from trader.settings import Settings
from web.api.app import create_app


def main() -> None:
    load_dotenv(find_dotenv(usecwd=True))
    uvicorn.run(create_app(Settings.from_env()), host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
