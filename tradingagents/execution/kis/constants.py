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

# KIS API base URLs
URLS = {
    "paper": "https://openapivts.koreainvestment.com:29443",
    "real": "https://openapi.koreainvestment.com:9443",
}

# Transaction IDs differ between paper and real trading
TR_IDS = {
    "paper": {
        "buy": "VTTC0802U",  # 모의투자 매수
        "sell": "VTTC0801U",  # 모의투자 매도
        "balance": "VTTC8434R",  # 모의투자 잔고조회
        "current_price": "FHKST01010100",  # 현재가 (동일)
        "order_status": "VTTC8001R",  # 모의투자 주문체결조회
    },
    "real": {
        "buy": "TTTC0802U",  # 실투자 매수
        "sell": "TTTC0801U",  # 실투자 매도
        "balance": "TTTC8434R",  # 실투자 잔고조회
        "current_price": "FHKST01010100",  # 현재가 (동일)
        "order_status": "TTTC8001R",  # 실투자 주문체결조회
    },
}

# Order type codes (KIS specific)
ORDER_TYPE_CODES = {
    "MARKET": "01",  # 시장가
    "LIMIT": "00",  # 지정가
}

# API paths
PATHS = {
    "token": "/oauth2/tokenP",
    "order": "/uapi/domestic-stock/v1/trading/order-cash",
    "balance": "/uapi/domestic-stock/v1/trading/inquire-balance",
    "current_price": "/uapi/domestic-stock/v1/quotations/inquire-price",
    "order_status": "/uapi/domestic-stock/v1/trading/inquire-daily-ccld",
}
