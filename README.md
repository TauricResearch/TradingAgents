<p align="center">
  <img src="assets/TauricResearch.png" style="width: 60%; height: auto;">
</p>

---

# TradingAgents: Discord 기반 멀티 에이전트 자동매매 봇

> TradingAgents 프레임워크에 Discord 봇, 한국투자증권 Open API, KR/US 워치리스트 전략을 결합한 자동매매 프로젝트입니다.

---

## 목차

- [한눈에 보기](#한눈에-보기)
- [전략 개요](#전략-개요)
- [에이전트 아키텍처](#에이전트-아키텍처)
- [설치](#설치)
- [환경 설정](#환경-설정)
- [사용법](#사용법)
- [KIS API 연동](#kis-api-연동)
- [LLM과 데이터 소스](#llm과-데이터-소스)
- [프로젝트 구조](#프로젝트-구조)
- [운영 메모](#운영-메모)
- [Citation](#citation)

---

## 한눈에 보기

- Discord 슬래시 명령 11개로 분석, 잔고조회, 수동 주문, 스코어링, 손익 조회를 제공합니다.
- 한국(KR)과 미국(US) 모두 워치리스트 기반 스코어링 뒤 상위 후보만 AI 분석합니다.
- 자동매매는 `룰 기반 후보 선정 -> 상위 N개 AI 분석 -> BUY 종목만 균등매수 -> 오후 점검 -> 손절/익절 감시` 흐름으로 동작합니다.
- 자동매수 예산은 `기준 자금(anchor) × 비율`로 계산할 수 있어, 예를 들어 `50%` 설정 시 절반씩 회전 투자할 수 있습니다.
- 분석 보고서는 Markdown 파일로 저장되며, 필요하면 Discord에도 자동 업로드합니다.
- 매매 이력과 실현손익은 SQLite로 누적 관리합니다.

---

## 전략 개요

### 전체 흐름

```text
워치리스트/랭킹 후보 수집
-> 룰 기반 점수 계산
-> 상위 후보만 TradingAgentsGraph AI 분석
-> BUY 종목만 균등분할 매수
-> 오후 매도 점검
-> 손절/익절 모니터링
```

### 시장별 자동매매 흐름

| 시장 | 후보 풀 | 자동 매수 | 오후 점검 | 장중 감시 |
|------|---------|-----------|-----------|-----------|
| KR | `KR_WATCHLIST` 우선, 비어 있으면 시총/거래량 랭킹 fallback | `AUTO_BUY_TIME` (기본 `09:30` KST), 예산 `AUTO_BUY_BUDGET_RATIO` 적용 | `AUTO_SELL_TIME` (기본 `15:20` KST) | `MONITOR_INTERVAL_MIN` 간격 |
| US | `US_WATCHLIST` 우선, 비어 있으면 시총/거래량 랭킹 fallback | `US_AUTO_BUY_TIME` (기본 `09:35` ET), 예산 `US_AUTO_BUY_BUDGET_RATIO` 적용 | `US_AUTO_SELL_TIME` (기본 `15:50` ET) | `MONITOR_INTERVAL_MIN` 간격 |

### 현재 스코어링 규칙

KR/US 공통 골격은 같습니다.

- 워치리스트 기본 점수: `+30`
- 등락률 `0~2%`: `+25`
- 등락률 `2~5%`: `+15`
- 시가총액 랭크 진입: `+10`
- 거래량 랭크 진입: `+5`
- 필터: 등락률 `> 8%` 또는 `< -5%`면 제외

추가 메모:

- KR은 KIS 현재가와 yfinance 전일 종가를 함께 써서 점수를 계산합니다.
- US는 yfinance 가격 이력을 기본으로 쓰고, KIS 미국 현재가가 가능하면 현재가를 보정합니다.
- 랭킹 보너스는 응답이 있을 때만 붙습니다.
- 현재 코드 기준으로 미국 시총/거래량 랭킹은 모의투자에서 비활성 처리되어, 실전 환경에서만 반영됩니다.

### 오후 매도 정책

- 워치리스트에 포함된 종목은 강제 청산하지 않고 스윙 보유합니다.
- 워치리스트 밖 보유 종목만 오후 점검 시 시장가 매도합니다.
- 손절/익절 조건은 워치리스트 여부와 관계없이 계속 감시합니다.

### 손절/익절 규칙

- 손절: `STOP_LOSS_PCT` 이하
- 익절: `TAKE_PROFIT_PCT` 이상
- 감시 주기: `MONITOR_INTERVAL_MIN` 분

---

## 에이전트 아키텍처

TradingAgentsGraph는 아래 구조로 동작합니다.

### 1. 애널리스트 팀

- 시장 애널리스트: 기술적 지표와 차트 흐름 분석
- 소셜 미디어 애널리스트: 투자 심리와 센티먼트 분석
- 뉴스 애널리스트: 뉴스와 이벤트 리스크 분석
- 펀더멘털 애널리스트: 재무와 사업 체력 분석

### 2. 리서치 팀

- 강세 리서처
- 약세 리서처
- 리서치 매니저

### 3. 트레이딩/리스크 팀

- 트레이더
- 공격적 리스크 매니저
- 보수적 리스크 매니저
- 중립적 리스크 매니저

### 4. 최종 의사결정

- 포트폴리오 매니저가 `BUY / SELL / HOLD`를 확정합니다.

---

## 설치

### 1. 레포지토리 클론

```bash
git clone https://github.com/TauricResearch/TradingAgents.git
cd TradingAgents
```

### 2. 가상환경

```bash
python -m venv .venv
source .venv/bin/activate
```

Windows는 아래를 사용하세요.

```bash
.venv\Scripts\activate
```

### 3. 의존성 설치

Discord 봇을 바로 실행하려면 아래 조합이 가장 안전합니다.

```bash
pip install -r requirements.txt python-dotenv
pip install -e .
```

### 4. 환경변수 파일 준비

```bash
cp .env.example .env
```

---

## 환경 설정

기본 템플릿은 [`.env.example`](/home/devuser/projects/TradingAgents2/.env.example)에 있습니다.

```env
# LLM Providers
OPENAI_API_KEY=
GOOGLE_API_KEY=
ANTHROPIC_API_KEY=
XAI_API_KEY=
OPENROUTER_API_KEY=

# Discord
DISCORD_BOT_TOKEN=
# DISCORD_CHANNEL_IDS=123456789012345678,987654321098765432

# KIS
KIS_APP_KEY=
KIS_APP_SECRET=
KIS_ACCOUNT_NO=12345678-01
KIS_VIRTUAL=true
KIS_MAX_ORDER_AMOUNT=1000000
KR_WATCHLIST=005930,000660,005380,005490,035420,105560,069500,114800,226490,229200

# US
ENABLE_US_TRADING=false
US_MAX_ORDER_AMOUNT=5000
US_EXCHANGE_SEARCH_ORDER=NASD,NYSE,AMEX
US_WATCHLIST=AAPL,MSFT,NVDA,AMZN,GOOGL,META,TSLA,AMD,AVGO,QQQ,SPY

# Schedule
DAY_TRADE_PICKS=5
AUTO_BUY_BUDGET_RATIO=1.0
AUTO_BUY_TIME=09:30
AUTO_SELL_TIME=15:20
US_DAY_TRADE_PICKS=5
US_AUTO_BUY_BUDGET_RATIO=1.0
US_AUTO_BUY_TIME=09:35
US_AUTO_SELL_TIME=15:50

# Risk / reports
STOP_LOSS_PCT=-5.0
TAKE_PROFIT_PCT=10.0
MONITOR_INTERVAL_MIN=30
REPORTS_DIR=reports
AUTO_REPORT_UPLOAD=true

# Optional bot model overrides
DEEP_THINK_LLM=gemini-3-flash-preview
QUICK_THINK_LLM=gemini-3-flash-preview
MAX_DEBATE_ROUNDS=1
```

### 설정 메모

- `DISCORD_CHANNEL_IDS`를 비워두면 수동 명령은 모든 채널에서 사용할 수 있습니다.
- 자동매매 스케줄은 `DISCORD_CHANNEL_IDS`가 설정된 경우에만 실제로 동작합니다.
- 미국 수동/자동 주문은 `ENABLE_US_TRADING=true`가 아니면 막힙니다.
- `KIS_VIRTUAL=true`면 모의투자, `false`면 실전투자입니다.
- `AUTO_BUY_BUDGET_RATIO=0.5`처럼 설정하면 KR 자동매수는 기준 자금의 50%만 사용합니다. `50%` 형식도 가능합니다.
- `US_AUTO_BUY_BUDGET_RATIO`를 비워두면 미국 자동매수도 같은 비율을 사용합니다.
- 기준 자금(anchor)은 시장별로 저장되는 자동매수 기준 예수금이며, 더 큰 예수금을 확인하면 자동으로 상향 갱신됩니다.
- Discord 봇은 모델명만 환경변수로 덮어쓰고, 기본 provider는 [`tradingagents/default_config.py`](/home/devuser/projects/TradingAgents2/tradingagents/default_config.py) 설정을 따릅니다.

### KIS 앱키 발급

1. [한국투자증권 API 포털](https://apiportal.koreainvestment.com)에 로그인합니다.
2. 앱키를 발급합니다.
3. 모의투자와 실전투자는 앱키가 다릅니다.
4. 계좌번호는 `12345678-01` 형식으로 입력합니다.

### Discord 봇 토큰 발급

1. [Discord Developer Portal](https://discord.com/developers/applications)에서 애플리케이션을 만듭니다.
2. `Bot` 탭에서 토큰을 발급합니다.
3. OAuth2에서 `bot`, `applications.commands` 스코프를 추가해 서버에 초대합니다.

---

## 사용법

### Discord 봇 실행

```bash
python bot.py
```

정상 실행 시 봇은 아래 정보를 콘솔에 출력합니다.

- 동기화된 슬래시 명령 수
- KR/US 자동매매 시각
- 손절/익절 기준
- 허용 채널 여부
- 모의/실전 모드

### 슬래시 명령어

현재 등록되는 명령은 11개입니다.

| 명령 | 설명 |
|------|------|
| `/분석 <티커> [날짜]` | 단일 종목 멀티 에이전트 AI 분석, 보고서 파일 첨부 |
| `/대형주 [날짜]` | KR 스코어링 TOP5를 순차 분석하고 BUY 종목에 버튼 제공 |
| `/잔고` | KRW/USD 계좌 요약과 보유 종목 조회 |
| `/매수 <티커> [수량]` | 시장별 수동 예산 상한 기준 매수 확인 버튼 표시 |
| `/매도 <티커> [수량]` | 보유 수량 기준 매도 확인 버튼 표시 |
| `/상태` | 오늘 자동매매 실행 상태 조회 |
| `/봇정보` | 스케줄, 설정, 계좌 요약, 오늘 이력을 한 번에 조회 |
| `/스코어링 [시장] [count] [exclude_held]` | 실시간 후보 점수 조회 |
| `/스코어규칙 [시장]` | 현재 코드 기준 스코어링 규칙 조회 |
| `/수익` | 누적 실현손익, 승률, 종목별 요약 조회 |
| `/수익초기화 [통화]` | 손익 집계 기준 시점 초기화 |

### 수동 주문 동작 방식

- `/매수`는 수량을 생략하면 `KIS_MAX_ORDER_AMOUNT` 또는 `US_MAX_ORDER_AMOUNT` 기준으로 자동 수량을 계산합니다.
- `/매도`는 수량을 생략하면 전량 매도로 동작합니다.
- 장이 닫혀 있으면 매수 버튼을 띄우지 않습니다.
- 매수 확인 버튼은 5분, 매도 확인 버튼은 2분 뒤 만료됩니다.

### 자동매매 스케줄

자동매매는 허용 채널이 있을 때만 실행됩니다.

#### KR 자동매수

1. 워치리스트 점수 계산
2. 보유 종목 제외
3. 상위 `DAY_TRADE_PICKS`만 AI 분석
4. BUY 종목만 `기준 자금(anchor) × AUTO_BUY_BUDGET_RATIO` 예산 안에서 균등분할 매수
5. 장 시작 전 분석이 끝나면 개장까지 대기 후 주문

#### KR 오후 점검

1. 보유 종목 조회
2. `KR_WATCHLIST` 밖 종목만 시장가 매도
3. 워치리스트 종목은 유지
4. 결과를 Discord와 손익 DB에 반영

#### US 자동매매

- `ENABLE_US_TRADING=true`일 때만 실행됩니다.
- KR과 동일한 흐름으로 동작하되 시간대만 ET 기준이며, 예산은 `US_AUTO_BUY_BUDGET_RATIO`를 따릅니다.
- 오후 점검도 `US_WATCHLIST` 밖 종목만 정리합니다.

#### 손절/익절 모니터링

- KR/US 보유 종목 전체를 감시합니다.
- 손절 또는 익절 조건에 도달하면 확인 없이 자동 매도합니다.

### 분석 보고서

- 보고서는 `REPORTS_DIR` 아래 Markdown 파일로 저장됩니다.
- `AUTO_REPORT_UPLOAD=true`면 자동매매 중 생성된 보고서도 Discord로 업로드합니다.

### Python에서 직접 사용

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["deep_think_llm"] = "gemini-3-flash-preview"
config["quick_think_llm"] = "gemini-3-flash-preview"

ta = TradingAgentsGraph(debug=True, config=config)
final_state, decision = ta.propagate("AAPL", "2026-03-18")
print(decision)
```

### CLI 사용

```bash
python -m cli.main
```

또는 설치 후:

```bash
tradingagents
```

---

## KIS API 연동

핵심 구현은 [`kis_client.py`](/home/devuser/projects/TradingAgents2/kis_client.py)에 있습니다.

### 현재 실제로 쓰는 API

| 기능 | 엔드포인트 | 비고 |
|------|------------|------|
| OAuth 토큰 | `POST /oauth2/tokenP` | 실전/모의 공통 |
| KR 잔고 조회 | `GET /uapi/domestic-stock/v1/trading/inquire-balance` | KRW 요약 포함 |
| US 잔고 조회 | `GET /uapi/overseas-stock/v1/trading/inquire-balance` | 거래소별 합산 |
| KR 현재가 | `GET /uapi/domestic-stock/v1/quotations/inquire-price` | 국내 6자리 코드 |
| US 현재가 | `GET /uapi/overseas-price/v1/quotations/price` | 거래소 탐색 포함 |
| KR 주문 | `POST /uapi/domestic-stock/v1/trading/order-cash` | 시장가 매수/매도 |
| US 주문 | `POST /uapi/overseas-stock/v1/trading/order` | 시장가 매수/매도 |
| KR 시총 랭킹 | `GET /uapi/domestic-stock/v1/ranking/market-cap` | 스코어링 보너스 |
| KR 거래량 랭킹 | `GET /uapi/domestic-stock/v1/quotations/volume-rank` | 스코어링 보너스 |
| US 시총 랭킹 | `GET /uapi/overseas-stock/v1/ranking/market-cap` | 실전에서만 사용 |
| US 거래량 랭킹 | `GET /uapi/overseas-stock/v1/ranking/trade-vol` | 실전에서만 사용 |

### 코드에 남아 있는 KR 보조 랭킹 유틸리티

현재 기본 전략은 사용하지 않지만, 아래 API 래퍼도 구현돼 있습니다.

- 체결강도 순위: `get_volume_power()`
- 등락률 순위: `get_fluctuation_rank()`
- 대량체결 순위: `get_bulk_trans()`

### 중요한 운영 차이

- KR 워치리스트가 비어 있으면 시총 랭킹, 그다음 거래량 랭킹으로 후보를 보완합니다.
- US 워치리스트가 비어 있어도 같은 순서로 fallback 합니다.
- 미국 시총/거래량 랭킹은 현재 코드에서 모의투자 시 빈 결과를 반환하도록 되어 있습니다.

---

## LLM과 데이터 소스

### 프레임워크가 지원하는 LLM 제공자

- OpenAI
- Google
- Anthropic
- xAI
- OpenRouter
- Ollama

### 현재 Discord 봇 기본값

- provider 기본값: [`tradingagents/default_config.py`](/home/devuser/projects/TradingAgents2/tradingagents/default_config.py)
- 봇 환경변수로 덮는 값: `DEEP_THINK_LLM`, `QUICK_THINK_LLM`, `MAX_DEBATE_ROUNDS`
- 데이터 수집: yfinance
- 주문/잔고/랭킹: KIS Open API

---

## 프로젝트 구조

```text
TradingAgents/
├── bot.py
├── kis_client.py
├── trade_history.py
├── main.py
├── README.md
├── .env.example
├── requirements.txt
├── pyproject.toml
├── reports/
├── data/
├── cli/
└── tradingagents/
    ├── agents/
    ├── dataflows/
    ├── graph/
    ├── llm_clients/
    └── default_config.py
```

주요 파일:

- [`bot.py`](/home/devuser/projects/TradingAgents2/bot.py): Discord 봇, 명령어, 자동매매 스케줄
- [`kis_client.py`](/home/devuser/projects/TradingAgents2/kis_client.py): KIS REST API 래퍼
- [`trade_history.py`](/home/devuser/projects/TradingAgents2/trade_history.py): SQLite 기반 매매/손익 기록
- [`tradingagents/graph/trading_graph.py`](/home/devuser/projects/TradingAgents2/tradingagents/graph/trading_graph.py): 멀티 에이전트 분석 그래프

---

## 운영 메모

- 수동 주문은 예산 상한을 넘기면 차단됩니다.
- 자동매매는 `daily_state` 기록으로 중복 실행을 막습니다.
- 보고서는 저장 실패 시에도 Discord 전송을 가능한 형태로 fallback 합니다.
- 분석은 `asyncio.Lock`으로 직렬화되어 동시에 여러 건이 돌지 않습니다.
- 모의투자에서는 실전과 일부 API 응답 차이가 있을 수 있습니다.

> 이 프로젝트는 연구/자동화 실험용입니다. 실제 주문 전에는 반드시 모의투자로 충분히 검증하세요.

---

## Citation

```bibtex
@misc{xiao2025tradingagentsmultiagentsllmfinancial,
      title={TradingAgents: Multi-Agents LLM Financial Trading Framework},
      author={Yijia Xiao and Edward Sun and Di Luo and Wei Wang},
      year={2025},
      eprint={2412.20138},
      archivePrefix={arXiv},
      primaryClass={q-fin.TR},
      url={https://arxiv.org/abs/2412.20138},
}
```
