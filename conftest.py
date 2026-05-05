# Copyright 2026 herald.k, HongSoo Kim
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Project-level pytest config.

Loads `.env` (if present) before any test module is collected so that
secret-bearing tests (e.g., KRX_ID/KRX_PW for pykrx, OPENDART_API_KEY for
DART) can read credentials from a developer-local .env file. The .env file
is gitignored — see .env.example for the schema.
"""

from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass
