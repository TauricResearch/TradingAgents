# TradingAgents 프로젝트 가이드라인

## 프로젝트 개요

멀티 에이전트 LLM 데이 트레이딩 프레임워크. LangGraph 기반 5단계 파이프라인(분석→토론→트레이딩→리스크→포트폴리오)으로 주식 매매 의사결정을 수행한다. Discord 봇 + 한국투자증권 API 연동으로 실제 자동매매를 지원한다.

## 빌드 및 실행

```bash
pip install -e .                  # 개발 설치
tradingagents analyze             # CLI 대화형 분석
python bot.py                     # Discord 봇 (자동 데이트레이딩)
python main.py                    # 직접 분석 예제
docker-compose up                 # 컨테이너 배포
```

- Python 3.10+ 필수
- `.env` 파일에 API 키 설정 필요 (LLM, Discord, KIS)

## 아키텍처

### 핵심 디렉터리

| 디렉터리 | 역할 |
|----------|------|
| `tradingagents/agents/` | 에이전트 팀 (analysts, researchers, trader, risk_mgmt, managers) |
| `tradingagents/dataflows/` | 데이터 벤더 추상화 (yfinance/AlphaVantage) |
| `tradingagents/graph/` | LangGraph 오케스트레이션, 상태 관리 |
| `tradingagents/llm_clients/` | LLM 프로바이더 팩토리 (openai, anthropic, google 등) |
| `cli/` | Typer 기반 대화형 CLI |

### 진입점

| 파일 | 용도 |
|------|------|
| `bot.py` | Discord 봇 (슬래시 커맨드 + 자동 스케줄) |
| `main.py` | Python 직접 사용 예제 |
| `kis_client.py` | 한국투자증권 REST API 클라이언트 |
| `trade_history.py` | SQLite 거래 기록 관리 |

### 5단계 파이프라인

1. **애널리스트** (병렬): 시장/소셜/뉴스/펀더멘털 → 각 리포트
2. **리서치 토론**: 강세 vs 약세 연구원 → 리서치 매니저 중재
3. **트레이더**: 리포트 + BM25 메모리 기반 투자 계획 수립
4. **리스크 토론**: 공격/중립/보수 → 리스크 심판
5. **포트폴리오 매니저**: 최종 BUY/HOLD/SELL 결정

## 코드 컨벤션

### 에이전트 패턴

- 에이전트 생성: `create_*` 팩토리 함수 (예: `create_market_analyst(llm)`)
- 그래프 노드: `node_func(state) → updated_state` 형태
- 도구: LangChain 도구 바인딩, 벤더 추상화 레이어로 라우팅
- 상태: `AgentState` TypedDict로 단계 간 데이터 전달

### 설정 관리

- `tradingagents/default_config.py`의 `DEFAULT_CONFIG` dict를 복사하여 사용
- LLM 프로바이더, 토론 라운드, 데이터 벤더 등 중앙 관리
- 환경변수: `.env` 파일 참조 (API 키, 스케줄, 한도 등)

### LLM 클라이언트

- `create_llm_client(provider, model, **kwargs)` 팩토리로 생성
- 지원: openai, anthropic, google, xai, ollama, openrouter
- Google: `thinking_level`, OpenAI: `reasoning_effort` 파라미터

### 데이터 벤더

- `dataflows/interface.py`에서 도구별 벤더 라우팅
- 기본: yfinance (무료), 대안: AlphaVantage (유료)
- 벤더 실패 시 자동 폴백

## 주의사항

- KIS API는 `KIS_VIRTUAL=true`로 모의투자 먼저 테스트
- `bot.py`의 자동매매 스케줄(09:30/15:20 KST)은 실제 주문 실행 — 신중하게 수정
- 커밋 메시지는 한국어로 간결하게 작성
- Docker 배포 시 `data/`, `results/`, `reports/` 볼륨 마운트 필수
