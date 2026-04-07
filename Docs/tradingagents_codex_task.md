# TradingAgents 개선 작업 지시서 (Codex용)

## 1) 목적

이 문서는 `nornen0202/TradingAgents` 저장소를 대상으로, 현재 구현을 **정확도·재현성·시장 확장성 관점에서 개선**하기 위한 작업 지시서다.

핵심 목표는 다음 4가지다.

1. **정합성 문제 수정**: 프롬프트/툴 시그니처 불일치, 설정값 미반영, 최종 시그널 파싱의 비결정성 제거.
2. **데이터 품질 개선**: `yfinance` 중심 뉴스 계층을 다원화하고, 소셜/공시/거시 데이터를 역할별로 분리.
3. **한국 시장 확장**: 미국 대형주 중심 구조를 KRX 종목에도 실효성 있게 확장.
4. **평가 가능성 확보**: 개선 전후를 비교할 수 있는 테스트와 평가 하네스 도입.

---

## 2) 현재 구조 요약

이 프로젝트는 대체로 다음 흐름으로 동작한다.

- Analyst Team: `market`, `social`, `news`, `fundamentals`
- Researcher Team: `bull`, `bear`, `research manager`
- Execution/Risk Team: `trader`, `aggressive/conservative/neutral risk`, `portfolio manager`
- 최종적으로 `SignalProcessor`가 텍스트형 최종 결정을 다시 파싱해 등급을 추출

구조 자체는 좋다. 하지만 현재 병목은 **에이전트 수가 아니라 데이터 계층의 얕음, 역할 중복, 결정 스키마 불일치**에 있다.

---

## 3) 현재 상태 진단 요약

### A. 기본 설정이 지나치게 `yfinance` 중심

- `default_config.py`에서 `core_stock_apis`, `technical_indicators`, `fundamental_data`, `news_data`가 모두 기본값 `yfinance`로 설정되어 있다.
- `max_debate_rounds`와 `max_risk_discuss_rounds` 기본값도 각각 `1`이다.

의미:

- 데이터 다양성이 좁다.
- 에이전트 토론이 사실상 1회 왕복 수준이라, 상호 반박/증거 대조가 충분히 이뤄지기 어렵다.

### B. Social agent의 역할과 실제 데이터가 맞지 않음

- `social_media_analyst.py`는 실제 툴로 `get_news` 하나만 사용한다.
- 프롬프트는 “social media posts”, “what people are saying”, “sentiment data of what people feel each day”를 요구하지만, 실제 툴은 소셜 데이터가 아니라 뉴스 데이터다.
- 더구나 프롬프트는 `get_news(query, start_date, end_date)`라고 설명하지만 실제 툴 시그니처는 `get_news(ticker, start_date, end_date)`이다.

의미:

- 현재 social agent는 사실상 **소셜 분석기**가 아니라 **회사 뉴스 재요약기**에 가깝다.
- 프롬프트-툴 계약이 깨져 있어 LLM이 잘못된 tool call을 시도할 위험이 있다.

### C. 뉴스 계층이 개선 여지는 있지만 여전히 제한적

- `yfinance_news.py`는 ticker 뉴스에 대해 `(20, 50, 100)` 개수로 점진 fetch를 시도하고, 필터링된 기사 수는 최대 `25`개로 제한한다.
- 이는 “20개 고정”보다는 낫지만, 여전히 기사 source diversity와 coverage는 제한적이다.
- 글로벌 뉴스는 고정된 영어 쿼리 목록으로 검색한다.
  - `"stock market economy"`
  - `"Federal Reserve interest rates"`
  - `"inflation economic outlook"`
  - `"global markets trading"`
- 글로벌 뉴스 경로는 미래 기사 차단은 하지만, 엄격한 lower-bound 필터링이나 지역/언어 다양성 측면이 약하다.

의미:

- 미국/영문 중심의 매크로 뉴스에는 어느 정도 맞지만,
- 한국 종목, 비영어권 이벤트, 지역 뉴스, 공시 중심 이벤트 대응에는 부족하다.

### D. 벤더 fallback 구조는 있지만 실질적 회복력은 약함

- `interface.py`는 comma-separated vendor chain을 허용한다.
- 하지만 실제 fallback은 `AlphaVantageRateLimitError`일 때만 작동한다.
- 빈 결과, 일반 예외, malformed payload, 품질 저하 상황에서는 다음 벤더로 자연스럽게 넘어가지 않는다.

의미:

- 추상화는 이미 존재하지만, **품질 회복력(resilience)** 은 충분하지 않다.

### E. 설정값 일부가 실제 실행에 반영되지 않음

- `Propagator`는 `max_recur_limit` 인자를 받도록 구현되어 있다.
- 그러나 `TradingAgentsGraph`는 `self.propagator = Propagator()`로 생성하여 config의 `max_recur_limit`를 넘기지 않는다.

의미:

- 사용자가 설정을 바꿔도 graph invocation recursion limit에 반영되지 않는다.

### F. 의사결정 스케일이 단계별로 일관되지 않음

현재 결정 스케일은 다음처럼 제각각이다.

- `research_manager.py`: **Buy / Sell / Hold**
- `trader.py`: `FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**`
- `portfolio_manager.py`: **Buy / Overweight / Hold / Underweight / Sell**
- `signal_processing.py`: 최종 텍스트를 다시 LLM에 넣어 **BUY / OVERWEIGHT / HOLD / UNDERWEIGHT / SELL** 중 하나를 추출

의미:

- agent 간 의미 손실이 발생한다.
- 마지막 단계가 deterministic parser가 아니라 LLM 재해석이라 재현성이 떨어진다.

### G. Memory/Reflection은 있으나 평가 루프와 느슨하게 연결됨

- `memory.py`는 BM25 기반 lexical retrieval만 사용한다.
- `reflect_and_remember()`는 존재하지만 자동 평가 루프와 강하게 연결되어 있지 않다.
- `trader.py`와 `portfolio_manager.py`는 `n_matches=2` 메모리만 참조한다.

의미:

- 과거 사례 회상이 문맥적으로 얕다.
- semantic similarity, regime metadata, outcome-conditioned reflection이 부족하다.

### H. Fundamentals agent의 도구 구성이 미완성

- `fundamentals_analyst.py`는 `get_insider_transactions`를 import하지만 tools 목록에 넣지 않는다.
- 프롬프트는 “past week” 중심인데, 펀더멘털은 본질적으로 주간 신호보다 분기/연간/가이던스/공시 이벤트와 더 잘 맞는다.

의미:

- 펀더멘털 agent가 본연의 강점을 충분히 활용하지 못하고 있다.

### I. 미국 종목에는 상대적으로 맞지만, 한국 종목은 실효성이 낮음

- upstream 계열은 exchange-qualified ticker 지원을 명시한다.
- Yahoo Finance에도 `005930.KS` 같은 한국 종목 페이지가 존재한다.
- 하지만 이 포크는 사용자 입력을 거의 그대로 `company_of_interest`에 넣고, 한국 종목명/숫자코드 → Yahoo/DART/거래소 심볼로 정규화하는 resolver가 없다.
- 또한 한국 전용 뉴스/공시/거시/수급 adapter가 없다.

의미:

- 미국 대형주는 “연구용/실험용”으로 꽤 쓸 만할 수 있다.
- 한국 종목은 현재 상태로는 **동작 가능**과 **효과적 수행 가능**을 구분해야 하며, 후자는 아직 부족하다.

---

## 4) 핵심 판단

### 결론 1: 문제의 본질은 “에이전트 수 부족”이 아니라 “독립적인 증거원 부족”이다

지금 구조는 여러 agent가 존재하지만, 실제로는 동일하거나 유사한 데이터(`yfinance` 뉴스 등)를 서로 다르게 요약하는 경우가 많다. 특히 social agent와 news agent의 독립성이 약하다.

### 결론 2: `yfinance`만으로 뉴스 계층을 운영하는 것은 부족하다

`yfinance`는 prototyping에는 좋지만, 아래가 부족하다.

- source diversity
- 언어/지역 다양성
- 소셜 감성 전용 신호
- 공시(event) 계층
- 한국 시장 로컬 정보
- point-in-time completeness

### 결론 3: 이 프로젝트는 “미국 상장 대형주” 쪽으로 더 최적화돼 있다

현재 글로벌 뉴스 검색 방식과 벤더 구성, 프롬프트 설계, ticker 정규화 부재를 종합하면 **US-optimized, KRX-compatible-but-not-KRX-specialized**라고 보는 것이 정확하다.

---

## 5) Codex가 구현해야 할 작업 범위

작업은 **P0 → P1 → P2 → P3** 순서로 진행하라.

---

## P0. 정합성 / 결정성 / 회귀 위험이 낮은 수정 (최우선)

### P0-1. `max_recur_limit` 실제 반영

#### 수정 대상
- `tradingagents/graph/trading_graph.py`
- `tradingagents/graph/propagation.py`

#### 작업 지시
- `TradingAgentsGraph.__init__()`에서 `Propagator(self.config["max_recur_limit"])` 형태로 생성하라.
- 필요하면 `Propagator` 생성자 type hint를 명시하라.
- 관련 회귀 테스트를 추가하라.

#### 수용 기준
- config에서 `max_recur_limit`를 바꾸면 graph invocation `config["recursion_limit"]`에 동일 값이 반영되어야 한다.

---

### P0-2. 프롬프트-툴 계약 불일치 수정

#### 수정 대상
- `tradingagents/agents/analysts/social_media_analyst.py`
- `tradingagents/agents/analysts/news_analyst.py`
- `tradingagents/agents/utils/news_data_tools.py`

#### 작업 지시
- 현재 social/news 프롬프트에서 `get_news(query, start_date, end_date)`라고 설명하는 부분을 실제 시그니처에 맞게 수정하라.
- 단기적으로는 `get_news(ticker, start_date, end_date)`를 정확히 반영하라.
- 추가로, 장기 확장용으로는 `get_company_news`, `get_macro_news`, `get_disclosures`, `get_social_sentiment` 같은 분리된 인터페이스로 발전시키기 쉽게 설계하라.

#### 수용 기준
- 프롬프트 설명과 tool signature가 일치해야 한다.
- social agent가 사용할 수 없는 capability(예: social media posts 수집)를 허위로 암시하지 않아야 한다.

---

### P0-3. 결정 스키마 통일 + 최종 파싱 deterministic화

#### 수정 대상
- `tradingagents/agents/managers/research_manager.py`
- `tradingagents/agents/trader/trader.py`
- `tradingagents/agents/managers/portfolio_manager.py`
- `tradingagents/graph/signal_processing.py`
- 신규: `tradingagents/schemas/decision.py` (또는 동등 파일)

#### 작업 지시
- 모든 최종/중간 의사결정 agent가 동일한 구조화 스키마를 출력하도록 바꾸라.
- 추천 스키마:

```json
{
  "rating": "BUY | OVERWEIGHT | HOLD | UNDERWEIGHT | SELL | NO_TRADE",
  "confidence": 0.0,
  "time_horizon": "short | medium | long",
  "entry_logic": "...",
  "exit_logic": "...",
  "position_sizing": "...",
  "risk_limits": "...",
  "catalysts": ["..."],
  "invalidators": ["..."]
}
```

- `research_manager`, `trader`, `portfolio_manager` 모두 이 스키마를 사용하게 하라.
- `signal_processing.py`는 더 이상 LLM 재호출로 등급을 추출하지 말고, 구조화 출력에서 `rating`만 deterministic하게 읽어 오게 하라.
- `NO_TRADE` 상태를 도입하라. 현재 구조는 Hold/Buy/Sell 쪽으로 과도하게 액션을 강제한다.

#### 수용 기준
- 최종 signal extraction에 추가 LLM 재호출이 없어야 한다.
- parsing failure 시 명시적 예외/검증 오류가 발생해야 하며, 조용히 잘못된 rating이 나오면 안 된다.

---

### P0-4. Fundamentals agent의 도구 누락 수정

#### 수정 대상
- `tradingagents/agents/analysts/fundamentals_analyst.py`
- 필요 시 `tradingagents/graph/trading_graph.py`

#### 작업 지시
- `get_insider_transactions`를 실제 tools 목록에 포함하라.
- 프롬프트를 “past week” 중심에서 “최근 공시/실적/가이던스/내부자거래/재무변화” 중심으로 재정렬하라.

#### 수용 기준
- fundamentals agent가 insider 거래를 실제로 조회할 수 있어야 한다.
- agent 프롬프트가 펀더멘털의 시간축과 맞아야 한다.

---

## P1. 뉴스/소셜/공시 계층의 실질적 강화 (정확도 향상 핵심)

### P1-1. 기본 뉴스 벤더를 `alpha_vantage,yfinance`로 전환

#### 수정 대상
- `tradingagents/default_config.py`

#### 작업 지시
- 아래 기본값으로 조정하라.

```python
"max_debate_rounds": 2,
"max_risk_discuss_rounds": 2,
"data_vendors": {
    "core_stock_apis": "yfinance",
    "technical_indicators": "yfinance",
    "fundamental_data": "yfinance",
    "news_data": "alpha_vantage,yfinance",
},
```

- tool-level override 예시도 주석으로 추가하라.
- 단, alpha_vantage API key가 없거나 rate limit에 걸리면 자연스럽게 fallback해야 한다.

#### 수용 기준
- default news path에서 `alpha_vantage`를 우선 시도하고 실패 시 `yfinance`로 내려가야 한다.

---

### P1-2. `route_to_vendor()`의 fallback을 일반화

#### 수정 대상
- `tradingagents/dataflows/interface.py`

#### 작업 지시
- 현재는 `AlphaVantageRateLimitError`에서만 fallback한다.
- 이를 다음 상황에서도 fallback 가능하게 개선하라.
  - vendor-specific 일반 예외
  - 빈 결과
  - `"No news found ..."` 류의 empty semantic result
  - malformed payload
- 단, **명백한 사용자 입력 오류**는 fallback 대상이 아니라 즉시 예외를 내는 것이 낫다.
- `should_fallback(result_or_exc)` 같은 헬퍼를 만들고 테스트 가능하게 작성하라.

#### 권장 로직

```python
if raises rate limit -> fallback
if raises transient/network/vendor-specific error -> fallback
if result is empty or semantically empty -> fallback
if result is valid non-empty -> return
if invalid user input / unsupported symbol format clearly identified -> raise
```

#### 수용 기준
- `alpha_vantage,yfinance` 구성이 실제 품질 회복력으로 작동해야 한다.
- “빈 문자열/빈 feed/No news found” 상황에서 다음 벤더로 넘어가야 한다.

---

### P1-3. 뉴스 계층을 역할별로 분리

#### 수정 대상
- `tradingagents/agents/utils/news_data_tools.py`
- `tradingagents/dataflows/interface.py`
- 신규 dataflow 파일들

#### 작업 지시
기존 `get_news`/`get_global_news`만으로 모든 역할을 처리하지 말고, 아래처럼 분리하라.

- `get_company_news(symbol, start_date, end_date)`
- `get_macro_news(curr_date, look_back_days=7, limit=10, region=None, language=None)`
- `get_disclosures(symbol, start_date, end_date)`
- `get_social_sentiment(symbol, start_date, end_date)`

단, 초기 단계에서는 backward compatibility를 위해 기존 `get_news()`를 남기되 내부적으로 `get_company_news()`의 thin wrapper로 두어라.

#### 수용 기준
- company news / macro news / disclosures / social sentiment가 개념적으로 분리되어야 한다.
- social agent가 더 이상 일반 뉴스 툴 하나에 과도하게 의존하지 않도록 구조를 만들라.

---

### P1-4. Social agent를 “실제 소셜” 또는 “명시적 뉴스 기반 sentiment”로 정직하게 재설계

#### 수정 대상
- `tradingagents/agents/analysts/social_media_analyst.py`
- 필요 시 파일명/클래스명 변경

#### 작업 지시
아래 두 옵션 중 하나를 택하되, 우선은 **옵션 A**를 추천한다.

#### 옵션 A (권장)
- 실제 social provider를 추가한다.
- 예: `Finnhub` 기반 sentiment 또는 다른 대체 데이터 제공자.
- provider가 미설정이면 agent는 “social provider unavailable, falling back to news-derived sentiment”를 명시해야 한다.

#### 옵션 B
- agent 이름을 `sentiment_analyst` 또는 `company_sentiment_analyst`로 바꾸고,
- 실제 capability를 “company news sentiment + public narrative analysis”로 축소 명시한다.

#### 수용 기준
- agent 이름/프롬프트/도구가 서로 모순되지 않아야 한다.
- unavailable capability를 허위로 묘사하면 안 된다.

---

### P1-5. 뉴스 표준 객체 도입

#### 수정 대상
- 신규: `tradingagents/dataflows/news_models.py` (또는 동등 파일)
- `yfinance_news.py`, `alpha_vantage_news.py`, 이후 추가 벤더들

#### 작업 지시
모든 뉴스/이벤트 source를 아래와 같은 공통 스키마로 정규화하라.

```python
@dataclass
class NewsItem:
    title: str
    source: str
    published_at: datetime | None
    language: str | None
    country: str | None
    symbols: list[str]
    topic_tags: list[str]
    sentiment: float | None
    relevance: float | None
    reliability: float | None
    url: str
    summary: str
    raw_vendor: str
```

- URL 또는 `(publisher, title, timestamp)` 기반 dedupe를 공통 처리하라.
- agent에는 raw article dump 전체가 아니라 **핵심 이벤트 목록 + evidence summary** 형태로 전달하라.

#### 수용 기준
- 서로 다른 벤더의 뉴스 결과를 하나의 공통 객체로 다룰 수 있어야 한다.
- dedupe와 evidence summarization이 일관되어야 한다.

---

## P2. 한국 시장 대응 (KRX 실효성 확보)

### P2-1. Instrument resolver 추가

#### 신규 파일
- `tradingagents/agents/utils/instrument_resolver.py`

#### 수정 대상
- `tradingagents/graph/propagation.py`
- `tradingagents/agents/utils/agent_utils.py`
- 필요 시 여러 tool wrapper

#### 작업 지시
입력값을 정규화하는 resolver를 추가하라.

지원 예시:

- `"AAPL"` → `AAPL`
- `"삼성전자"` → `005930.KS`
- `"005930"` → `005930.KS`
- `"NAVER"` → `035420.KS`
- `"035420"` → `035420.KS`
- 이미 suffix가 붙은 `005930.KS`, `241710.KQ` 등은 그대로 통과

추가 요구사항:

- Yahoo symbol / KRX short code / DART corp code를 함께 다룰 수 있는 구조를 고려하라.
- 최소한 내부적으로 아래를 분리해 보관 가능해야 한다.
  - `display_name`
  - `primary_symbol`
  - `exchange`
  - `country`
  - `dart_corp_code` (있으면)

#### 수용 기준
- `ta.propagate("삼성전자", "2026-01-15")` 같은 입력도 최소한 symbol 정규화 단계는 통과해야 한다.
- resolver 실패 시 명확한 오류 메시지를 제공하라.

---

### P2-2. 한국 전용 데이터 어댑터 추가

#### 신규 권장 파일
- `tradingagents/dataflows/opendart.py`
- `tradingagents/dataflows/naver_news.py`
- `tradingagents/dataflows/krx_open_api.py`
- `tradingagents/dataflows/ecos.py`

#### 작업 지시
한국 시장 대응을 위해 최소한 아래를 adapter 형태로 추가하라.

1. **OpenDART**
   - 공시 원문/회사개황/재무지표/주요 문서 접근
   - `get_disclosures()`와 fundamentals 계층에 연결

2. **Naver News Search API**
   - 한국어 회사 뉴스 검색
   - `get_company_news()`의 KRX 경로에 연결

3. **KRX Open API**
   - 일별 매매정보, 거래대금, 시장지표, 필요 시 공매도/수급 정보
   - market analysis 보강용

4. **ECOS (한국은행)**
   - 한국 거시 데이터
   - macro news / macro context 보강용

#### 구현 원칙
- API key / auth가 없으면 기능을 끄고 graceful fallback하라.
- 미국 종목 흐름은 기존처럼 동작해야 한다.
- 한국어 기사/공시는 원문 기반 사용을 우선하고, 영문은 보조 자료로만 다뤄라.

#### 수용 기준
- 한국 종목 분석 시 미국 매크로 영어 기사만 보는 상태를 벗어나야 한다.
- KRX 종목의 company news / disclosure / macro context가 분리되어 공급되어야 한다.

---

### P2-3. 시간대/거래소/통화 정규화

#### 수정 대상
- 시장/뉴스/리포트 생성 관련 유틸 전반

#### 작업 지시
- `US/Eastern`, `Asia/Seoul` 등 시장별 세션 타임존을 명시적으로 관리하라.
- 보고서/도구 요약에서 통화단위(`USD`, `KRW`)를 혼동하지 않게 하라.
- 장중/장후/장마감 상태와 이벤트 timestamp를 표준화하라.

#### 수용 기준
- KRX 종목 보고서에 미국 기준 시간 표현이 섞여 오해를 만들면 안 된다.
- 숫자와 통화가 명시적으로 표기되어야 한다.

---

## P3. 정확도 개선용 구조 업그레이드

### P3-1. Market agent를 “지표 선택형”에서 “레짐 인식 + 해석형”으로 전환

#### 수정 대상
- `tradingagents/agents/analysts/market_analyst.py`
- 필요 시 technical indicator tool 계층

#### 작업 지시
현재는 agent가 최대 8개 지표를 고르는 구조다. 이를 아래처럼 바꾸는 것을 목표로 하라.

1. 먼저 레짐 분류:
   - trending up / trending down / range-bound / high-volatility / event-driven
2. 레짐별 고정 feature bundle 계산
3. LLM은 feature를 “선택”하기보다 “해석”하게 함

추가 추천 feature:
- benchmark relative strength
- sector ETF 대비 상대 성과
- ATR / realized volatility
- gap + volume shock
- earnings-event proximity
- 거래대금/유동성 필터
- KRX의 경우 외국인/기관 수급, 공매도 가능 시그널

#### 수용 기준
- LLM이 tool parameter를 임의로 잘못 조합하는 위험이 줄어야 한다.
- 보고서가 narrative뿐 아니라 수치적 feature 기반으로 더 일관적이어야 한다.

---

### P3-2. Memory를 hybrid retrieval로 개선

#### 수정 대상
- `tradingagents/agents/utils/memory.py`

#### 작업 지시
현재 BM25만 사용한다. 이를 아래 중 하나로 개선하라.

- BM25 + embedding hybrid
- BM25 + regime tags + metadata filters
- outcome-aware memory (승률/드로우다운/보유기간/조건별 성과 메타 포함)

추가 요구사항:
- `n_matches`를 고정 상수처럼 쓰지 말고 configurable하게 하라.
- reflection outcome과 연결해 past memory quality를 점진적으로 높여라.

#### 수용 기준
- lexical overlap이 낮아도 유사한 시장상황을 더 잘 회수해야 한다.

---

### P3-3. Reflection을 실제 평가 루프에 연결

#### 수정 대상
- `TradingAgentsGraph.reflect_and_remember()` 호출 경로
- backtest/evaluation 스크립트 신규 추가

#### 작업 지시
- walk-forward evaluation 또는 backtest 루프에서 `returns_losses` 결과가 나오면 자동으로 reflection을 호출하도록 연결하라.
- reflection 이전/이후의 memory 변화가 재현 가능하게 저장되도록 하라.

#### 수용 기준
- reflection이 수동 실험용 기능이 아니라 평가 파이프라인 일부가 되어야 한다.

---

## 6) 추천 외부 데이터 소스 설계

### 미국/글로벌 우선 스택

#### 기본 조합
- `Alpha Vantage NEWS_SENTIMENT` → 1차
- `yfinance` → fallback

#### 옵션
- `Finnhub` → social/sentiment/대체데이터 보강
- `NewsAPI` → source diversity 보강
- `GDELT` → 글로벌/다국어 이벤트 coverage 보강
- `SEC EDGAR` → 미국 공시 계층

### 한국 우선 스택

- `OpenDART` → 공시/재무/원문 문서
- `Naver News Search API` → 한국어 뉴스
- `BIGKinds` → 국내 뉴스 다양성/아카이브
- `KRX Open API` → 거래/시장 데이터
- `ECOS` → 한국 거시 통계

### 주의

- Finnhub company news는 북미 기업 전용 제약이 있으므로 KRX 회사뉴스의 메인 소스로 쓰지 말 것.
- DART 영문 공시는 법적 효력이 없는 자발적 번역일 수 있으므로, 한국 종목 분석의 1차 근거는 한국어 원문 공시를 우선할 것.

---

## 7) 파일별 상세 수정 지시

### 7.1 `tradingagents/default_config.py`

#### 해야 할 일
- `news_data` 기본값: `"alpha_vantage,yfinance"`
- `max_debate_rounds`: `2`
- `max_risk_discuss_rounds`: `2`
- 향후 확장을 위한 선택적 설정 추가
  - `social_data`
  - `market_country`
  - `timezone`
  - `enable_no_trade`
  - `vendor_timeout`
  - `empty_result_fallback`

#### 주의
- 기존 사용자 config override와 충돌하지 않도록 backward compatible하게 작성

---

### 7.2 `tradingagents/graph/trading_graph.py`

#### 해야 할 일
- `Propagator(self.config["max_recur_limit"])` 적용
- tool node 구성 재검토
  - social 전용 툴 추가 시 여기서 연결
  - disclosures 분리 시 news/fundamentals 중 적절한 agent에 연결
- `process_signal()` 경로를 구조화 스키마 기반으로 변경

---

### 7.3 `tradingagents/graph/propagation.py`

#### 해야 할 일
- 초기 state 생성 전에 instrument resolver를 호출하도록 설계
- `company_of_interest`에 raw input만 넣지 말고 정규화된 symbol/context를 보관 가능하게 개선

예시:

```python
{
  "input_instrument": "삼성전자",
  "company_of_interest": "005930.KS",
  "instrument_profile": {
    "display_name": "삼성전자",
    "primary_symbol": "005930.KS",
    "country": "KR",
    "exchange": "KRX"
  }
}
```

---

### 7.4 `tradingagents/graph/signal_processing.py`

#### 해야 할 일
- LLM 기반 문자열 추출 제거
- `pydantic` 또는 stdlib validation으로 rating deterministic extraction
- invalid schema에 대한 명시적 예외 처리

---

### 7.5 `tradingagents/agents/utils/news_data_tools.py`

#### 해야 할 일
- 기존 `get_news()`는 유지하되 thin wrapper로 축소
- 아래 인터페이스 추가
  - `get_company_news`
  - `get_macro_news`
  - `get_disclosures`
  - `get_social_sentiment`
- 툴 docstring을 실제 capability에 맞게 다시 작성

---

### 7.6 `tradingagents/dataflows/interface.py`

#### 해야 할 일
- fallback generalization
- 신규 tool→category 매핑 추가
- vendor chain 검증 강화
- empty result fallback 로직 추가
- vendor-specific adapter를 공통 normalize layer에 연결

---

### 7.7 `tradingagents/dataflows/yfinance_news.py`

#### 해야 할 일
- 현 구조의 장점(점진 fetch / dedupe)은 유지
- global news 검색 쿼리를 고정 영어 4개에서 확장 가능하도록 분리
- lower-bound filtering 및 region/language filtering 가능성 추가
- `NewsItem` 표준화 계층에 맞게 결과 반환 구조 정리

#### 추가 개선 포인트
- 현재 global query는 미국 거시 편향이 강하므로 지역별 query preset 지원
  - `US`
  - `KR`
  - `GLOBAL`

---

### 7.8 `tradingagents/dataflows/alpha_vantage_news.py`

#### 해야 할 일
- `NEWS_SENTIMENT` 결과를 `NewsItem`으로 정규화
- ticker/company news와 macro news를 일관된 형태로 내보내기
- rate limit/empty result 시 fallback-friendly 예외 또는 상태 반환

---

### 7.9 `tradingagents/agents/analysts/social_media_analyst.py`

#### 해야 할 일
- agent 이름/프롬프트/툴 세트를 capability와 일치시키기
- 실제 소셜 provider 없으면 “news-derived sentiment analyst”로 안전하게 축소
- social provider가 있으면 그때만 social-specific prompt 활성화

---

### 7.10 `tradingagents/agents/analysts/news_analyst.py`

#### 해야 할 일
- `company news`, `macro news`, `disclosures`를 분리된 evidence block으로 사용
- 단순 장문 요약보다 아래 형식을 권장
  - 핵심 이벤트 3~5개
  - event type
  - source
  - why it matters
  - bullish / bearish implication
  - confidence

---

### 7.11 `tradingagents/agents/analysts/fundamentals_analyst.py`

#### 해야 할 일
- insider transactions 포함
- “past week” 중심 문구 수정
- 공시/실적/가이던스/내부자거래/재무 구조 변화 중심 재구성
- KRX면 OpenDART 우선, 미국이면 기존/SEC 경로 우선하는 훅 설계

---

### 7.12 `tradingagents/agents/analysts/market_analyst.py`

#### 해야 할 일
- 지표 선택형 설계를 단계적으로 regime-driven 설계로 전환
- KRX 전용 feature 확장 가능성을 남길 것

---

### 7.13 `tradingagents/agents/trader/trader.py`

#### 해야 할 일
- `BUY/HOLD/SELL` 텍스트 강제를 제거
- 구조화 출력 사용
- 진입 조건 / 청산 조건 / 포지션 크기 / time horizon 포함
- `NO_TRADE` 허용

---

### 7.14 `tradingagents/agents/managers/research_manager.py`

#### 해야 할 일
- Hold 억제(action bias) 문구를 완화
- evidence arbitration 중심으로 프롬프트 재작성
- 각 주장별 근거와 무효화 조건을 명시하게 유도

---

### 7.15 `tradingagents/agents/managers/portfolio_manager.py`

#### 해야 할 일
- 최종 결정의 구조화 스키마 사용
- 리스크 한도, 포지션 사이징, invalidator, catalyst 포함
- memory 참조 방식을 hybrid retrieval로 연결 가능하게 준비

---

## 8) 평가/테스트 지시

### 필수 단위 테스트

아래 테스트를 추가하라.

1. **config propagation test**
   - `max_recur_limit`가 실제 graph args에 반영되는지

2. **prompt-tool consistency test**
   - social/news agent 프롬프트가 실제 tool signature와 모순되지 않는지

3. **vendor fallback test**
   - rate limit
   - generic exception
   - empty result
   - malformed payload
   각각에서 다음 vendor로 fallback되는지

4. **structured decision parsing test**
   - valid schema에서 deterministic하게 rating을 읽는지
   - invalid schema에서 예외가 나는지

5. **instrument resolver test**
   - `AAPL`
   - `005930.KS`
   - `005930`
   - `삼성전자`
   - `NAVER`
   - `035420`

6. **news normalization test**
   - yfinance/alpha_vantage 결과가 공통 `NewsItem`으로 정규화되는지

7. **social agent degrade-gracefully test**
   - 소셜 provider 미설정 시 fallback messaging이 정직하게 나오는지

### 권장 평가 하네스

신규 스크립트를 추가하라.

- `scripts/eval_walk_forward.py`
- 또는 `tradingagents/eval/walk_forward.py`

평가 메트릭 예시:

- hit rate
- forward return by rating bucket
- turnover
- max drawdown
- benchmark excess return
- abstain(NO_TRADE) frequency
- US vs KR split metrics

---

## 9) 구현 원칙

### 반드시 지킬 것

- **기존 공개 API를 불필요하게 깨지 말 것**
- 새 vendor/API key가 없어도 기존 경로로 graceful fallback할 것
- unavailable capability를 프롬프트에서 허위로 주장하지 말 것
- 최종 decision은 자유형 텍스트가 아니라 구조화 결과를 우선할 것
- 한국 종목은 영문 보조 자료보다 한국어 원문 공시/뉴스를 우선할 것

### 피해야 할 것

- social agent가 계속 `get_news` 하나만 쓰면서 “social media”를 분석한다고 말하는 상태 유지
- `signal_processing.py`에서 LLM을 한 번 더 호출하는 비결정적 추출 유지
- fallback 체인이 있어 보이지만 실제로는 rate limit 외에는 동작하지 않는 상태 유지
- KRX 지원을 “티커 suffix만 붙으면 된다” 수준으로 과대평가

---

## 10) 단계별 커밋 권장 순서

### Commit 1 — Correctness & determinism
- recursion limit 반영
- prompt-tool mismatch 수정
- structured decision schema 도입
- signal_processing deterministic화
- fundamentals tool 누락 보완

### Commit 2 — Vendor resilience
- default config 조정
- fallback generalization
- news normalization layer 도입

### Commit 3 — Social / disclosure separation
- company news / macro news / disclosures / social sentiment 인터페이스 분리
- social agent 정직한 capability 재정의

### Commit 4 — KRX support
- instrument resolver
- OpenDART / Naver / KRX / ECOS adapter 뼈대
- timezone/currency normalization

### Commit 5 — Evaluation
- unit tests 확장
- walk-forward evaluation 스크립트 추가

---

## 11) 완료 조건 (Definition of Done)

다음 조건을 만족하면 1차 완료로 본다.

1. `max_recur_limit`가 실제로 반영된다.
2. social/news 프롬프트와 툴 시그니처가 일치한다.
3. 뉴스 벤더가 `alpha_vantage,yfinance` 조합에서 실제 fallback한다.
4. 최종 rating 추출이 구조화/결정적으로 수행된다.
5. `NO_TRADE` 상태가 지원된다.
6. fundamentals agent가 insider transactions를 실제로 쓴다.
7. KRX symbol normalization이 최소 수준으로 동작한다.
8. 한국 종목에서 공시/한국어 뉴스/거시 확장 지점을 남긴다.
9. 관련 단위 테스트가 모두 통과한다.

---

## 12) 참고 메모 (설계 판단 이유)

- 현재 구조는 연구 프레임워크로는 매력적이지만, 실제 정확도는 agent 숫자보다 **데이터 source 독립성**과 **결정 스키마 일관성**에 더 크게 좌우된다.
- 따라서 이번 패치의 우선순위는 “agent 추가”가 아니라 아래다.
  1. 데이터 역할 분리
  2. fallback/정규화
  3. 구조화 출력
  4. KRX 대응
  5. 평가 루프

---

## 13) 외부 참고 링크 (구현 시 참고)

### Repo / 코드
- https://github.com/nornen0202/TradingAgents
- https://github.com/TauricResearch/TradingAgents/releases

### 미국/글로벌 데이터
- Alpha Vantage docs: https://www.alphavantage.co/documentation/
- Finnhub company news docs: https://finnhub.io/docs/api/company-news
- NewsAPI docs: https://newsapi.org/docs
- GDELT project: https://www.gdeltproject.org/
- GDELT DOC 2.0: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/

### 한국 데이터
- OpenDART intro: https://engopendart.fss.or.kr/intro/main.do
- English DART disclaimer: https://englishdart.fss.or.kr/
- Naver News Search API: https://developers.naver.com/docs/serviceapi/search/news/news.md
- KRX Open API: https://openapi.krx.co.kr/
- ECOS Open API: https://ecos.bok.or.kr/api/
- BIGKinds: https://bigkinds.or.kr/

---

## 14) Codex에 바로 붙여 넣을 실행 요약

아래 요약을 작업 prompt 첫머리에 붙여 넣어도 된다.

> `nornen0202/TradingAgents`를 분석한 결과, 정확도 병목은 agent 수보다 데이터 계층, 역할 분리, 결정 스키마, KRX 대응성 부족에 있습니다. 우선순위는 (1) recursion/config 반영과 prompt-tool mismatch 수정, (2) final decision의 구조화 및 deterministic parsing, (3) news vendor를 alpha_vantage,yfinance로 바꾸고 fallback을 일반화, (4) company/macro/disclosure/social 인터페이스 분리, (5) instrument resolver와 KRX/OpenDART/Naver/ECOS 확장 포인트 추가, (6) 테스트 및 walk-forward evaluation 추가입니다. 기존 public API는 최대한 유지하고, provider key가 없을 때는 graceful fallback이 되게 해주세요.`

