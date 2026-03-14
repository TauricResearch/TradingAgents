# Copyright 2026 herald.k, HongSoo Kim
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from .base_broker import BaseBroker
from .engine import ExecutionEngine
from .models import OrderRequest, OrderResult, PortfolioSnapshot


def create_broker(config: dict) -> BaseBroker:
    """Factory function to create a broker instance from config.

    Args:
        config: Full application config dict containing broker settings.

    Returns:
        A BaseBroker implementation for the configured provider.
    """
    provider = config.get("broker", {}).get("provider", "kis")

    if provider == "kis":
        from .kis.broker import KISBroker

        return KISBroker(config)

    raise ValueError(f"Unsupported broker provider: {provider}")
