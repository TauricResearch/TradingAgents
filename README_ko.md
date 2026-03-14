<p align="center">
  <img src="assets/TauricResearch.png" style="width: 60%; height: auto;">
</p>

<div align="center" style="line-height: 1;">
  <a href="https://arxiv.org/abs/2412.20138" target="_blank"><img alt="arXiv" src="https://img.shields.io/badge/arXiv-2412.20138-B31B1B?logo=arxiv"/></a>
  <a href="https://discord.com/invite/hk9PGKShPK" target="_blank"><img alt="Discord" src="https://img.shields.io/badge/Discord-TradingResearch-7289da?logo=discord&logoColor=white&color=7289da"/></a>
  <a href="./assets/wechat.png" target="_blank"><img alt="WeChat" src="https://img.shields.io/badge/WeChat-TauricResearch-brightgreen?logo=wechat&logoColor=white"/></a>
  <a href="https://x.com/TauricResearch" target="_blank"><img alt="X Follow" src="https://img.shields.io/badge/X-TauricResearch-white?logo=x&logoColor=white"/></a>
  <br>
  <a href="https://github.com/TauricResearch/" target="_blank"><img alt="Community" src="https://img.shields.io/badge/Join_GitHub_Community-TauricResearch-14C290?logo=discourse"/></a>
</div>

<div align="center">
  <a href="./README.md">English</a> |
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=de">Deutsch</a> |
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=es">Español</a> |
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=fr">français</a> |
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=ja">日本語</a> |
  <b>한국어</b> |
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=pt">Português</a> |
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=ru">Русский</a> |
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=zh">中文</a>
</div>

---

# TradingAgents: 멀티 에이전트 LLM 금융 트레이딩 프레임워크

## 소식
- [2026-03] **KIS 증권사 연동** — 한국투자증권 API를 통한 실시간 매매 실행. 모의투자와 실투자를 모두 지원하며 다중 안전장치 내장.
- [2026-03] **투자 페르소나 시스템** — 워런 버핏, 레이 달리오, 피터 린치 스타일로 트레이딩. 페르소나별 전략이 트레이더, 리서치 매니저, 리스크 매니저 에이전트에 주입됩니다.
- [2026-02] **TradingAgents v0.2.0** 출시 — 멀티 프로바이더 LLM 지원 (GPT-5.x, Gemini 3.x, Claude 4.x, Grok 4.x) 및 시스템 아키텍처 개선.
- [2026-01] **Trading-R1** [기술 보고서](https://arxiv.org/abs/2509.11420) 공개, [터미널](https://github.com/TauricResearch/Trading-R1) 출시 예정.

<div align="center">
<a href="https://www.star-history.com/#TauricResearch/TradingAgents&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=TauricResearch/TradingAgents&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=TauricResearch/TradingAgents&type=Date" />
   <img alt="TradingAgents Star History" src="https://api.star-history.com/svg?repos=TauricResearch/TradingAgents&type=Date" style="width: 80%; height: auto;" />
 </picture>
</a>
</div>

> 🎉 **TradingAgents**가 공식 출시되었습니다! 많은 관심과 문의에 감사드립니다.
>
> 프레임워크를 완전 오픈소스로 공개합니다. 함께 멋진 프로젝트를 만들어 갑시다!

<div align="center">

🚀 [프레임워크 소개](#tradingagents-프레임워크) | ⚡ [설치 및 CLI](#설치-및-cli) | 🎬 [데모](https://www.youtube.com/watch?v=90gr5lwjIho) | 📦 [패키지 사용법](#tradingagents-패키지) | 🎭 [투자 페르소나](#투자-페르소나) | 📈 [증권사 연동](#증권사-연동-kis) | 🤝 [기여하기](#기여하기) | 📄 [인용](#인용)

</div>

## TradingAgents 프레임워크

TradingAgents는 실제 트레이딩 회사의 운영 구조를 모방한 멀티 에이전트 트레이딩 프레임워크입니다. 펀더멘털 애널리스트, 센티멘트 전문가, 테크니컬 애널리스트, 트레이더, 리스크 관리팀 등 전문화된 LLM 기반 에이전트를 배치하여 시장 상황을 협력적으로 분석하고 투자 결정을 내립니다. 또한 에이전트들은 최적의 전략을 도출하기 위해 동적인 토론을 수행합니다.

<p align="center">
  <img src="assets/schema.png" style="width: 100%; height: auto;">
</p>

> TradingAgents 프레임워크는 연구 목적으로 설계되었습니다. 트레이딩 성과는 사용하는 LLM 모델, 모델 온도 설정, 트레이딩 기간, 데이터 품질 등 다양한 요인에 따라 달라질 수 있습니다. [이 프레임워크는 금융, 투자 또는 트레이딩 조언을 제공하지 않습니다.](https://tauric.ai/disclaimer/)

프레임워크는 복잡한 트레이딩 작업을 전문화된 역할로 분해합니다. 이를 통해 시장 분석과 의사결정에 대한 견고하고 확장 가능한 접근 방식을 제공합니다.

### 애널리스트 팀
- **펀더멘털 애널리스트**: 기업 재무제표와 성과 지표를 평가하여 내재 가치와 잠재적 위험 요소를 식별합니다. 한국 상장 기업의 경우 [OpenDART](https://opendart.fss.or.kr/) 데이터(공시 재무제표 및 규제 공시)를 추가로 활용합니다.
- **센티멘트 애널리스트**: 소셜 미디어와 대중 여론을 분석하여 단기 시장 분위기를 파악합니다.
- **뉴스 애널리스트**: 글로벌 뉴스와 거시경제 지표를 모니터링하여 이벤트가 시장에 미치는 영향을 해석합니다.
- **테크니컬 애널리스트**: MACD, RSI 등 기술 지표를 활용하여 매매 패턴을 감지하고 가격 변동을 예측합니다.

<p align="center">
  <img src="assets/analyst.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

### 리서처 팀
- 강세(Bull)와 약세(Bear) 리서처로 구성되어 애널리스트 팀의 분석을 비판적으로 평가합니다. 구조화된 토론을 통해 잠재적 수익과 내재된 리스크 사이의 균형을 잡습니다.

<p align="center">
  <img src="assets/researcher.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

### 트레이더 에이전트
- 애널리스트와 리서처의 보고서를 종합하여 정보에 기반한 매매 결정을 내립니다. 종합적인 시장 인사이트를 바탕으로 매매 시점과 규모를 결정합니다.

<p align="center">
  <img src="assets/trader.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

### 리스크 관리 및 포트폴리오 매니저
- 시장 변동성, 유동성 등 리스크 요소를 지속적으로 평가합니다. 리스크 관리팀이 매매 전략을 평가하고 조정하여 포트폴리오 매니저에게 평가 보고서를 제공합니다.
- 포트폴리오 매니저가 거래 제안을 승인/거부합니다. 승인되면 주문이 거래소로 전달되어 실행됩니다.

<p align="center">
  <img src="assets/risk.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

## 설치 및 CLI

### 설치

TradingAgents 클론:
```bash
git clone https://github.com/TauricResearch/TradingAgents.git
cd TradingAgents
```

가상 환경 생성:
```bash
conda create -n tradingagents python=3.13
conda activate tradingagents
```

의존성 설치:
```bash
pip install -r requirements.txt
```

### 필수 API 키

TradingAgents는 여러 LLM 프로바이더를 지원합니다. 사용하는 프로바이더의 API 키를 설정하세요:

```bash
# LLM 프로바이더 (사용하는 것만 설정)
export OPENAI_API_KEY=...          # OpenAI (GPT)
export GOOGLE_API_KEY=...          # Google (Gemini)
export ANTHROPIC_API_KEY=...       # Anthropic (Claude)
export XAI_API_KEY=...             # xAI (Grok)
export OPENROUTER_API_KEY=...      # OpenRouter

# 데이터 프로바이더
export ALPHA_VANTAGE_API_KEY=...   # Alpha Vantage (yfinance 대안)
export OPENDART_API_KEY=...        # OpenDART (한국 DART 공시)

# KIS 증권사 (한국투자증권) — 매매 실행 시에만 필요
export KIS_APP_KEY=...             # KIS Open API 앱 키
export KIS_APP_SECRET=...          # KIS Open API 앱 시크릿
export KIS_ACCOUNT_NO=...          # 계좌번호 (형식: XXXXXXXX-XX)
```

로컬 모델의 경우, 설정에서 `llm_provider: "ollama"`로 구성하세요.

또는 `.env.example`을 `.env`로 복사하여 키를 입력할 수 있습니다:
```bash
cp .env.example .env
```

### CLI 사용법

CLI를 직접 실행할 수 있습니다:
```bash
python -m cli.main
```
CLI는 9단계 대화형 설정을 안내합니다: 종목 코드, 날짜, 애널리스트 선택, LLM 프로바이더 및 모델, 리서치 깊이, 투자 페르소나, 증권사 실행 모드.

<p align="center">
  <img src="assets/cli/cli_init.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

결과가 로드되는 동안 에이전트의 진행 상황을 실시간으로 추적할 수 있는 인터페이스가 표시됩니다.

<p align="center">
  <img src="assets/cli/cli_news.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

<p align="center">
  <img src="assets/cli/cli_transaction.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

## TradingAgents 패키지

### 구현 세부사항

TradingAgents는 유연성과 모듈성을 위해 LangGraph로 구축되었습니다. 프레임워크는 OpenAI, Google, Anthropic, xAI, OpenRouter, Ollama 등 다양한 LLM 프로바이더를 지원합니다.

### Python 사용법

코드에서 TradingAgents를 사용하려면 `tradingagents` 모듈을 임포트하고 `TradingAgentsGraph()` 객체를 초기화합니다. `.propagate()` 함수가 매매 결정을 반환합니다. `main.py`를 실행하거나 아래 예제를 참고하세요:

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())

# 순전파 실행
_, decision = ta.propagate("NVDA", "2026-01-15")
print(decision)
```

LLM, 토론 라운드, 페르소나 등 기본 설정을 원하는 대로 조정할 수 있습니다:

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openai"        # openai, google, anthropic, xai, openrouter, ollama
config["deep_think_llm"] = "gpt-5.2"     # 복잡한 추론용 모델
config["quick_think_llm"] = "gpt-5-mini" # 빠른 분석용 모델
config["max_debate_rounds"] = 2

# 투자 페르소나 적용 (선택사항)
config["persona"] = "warren_buffett"     # None, "warren_buffett", "ray_dalio", "peter_lynch"

ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("NVDA", "2026-01-15")
print(decision)
```

KIS 증권사를 통한 실시간 매매 실행을 활성화하려면:

```python
config["broker"] = {
    "enabled": True,
    "provider": "kis",
    "mode": "paper",                 # "paper" (모의투자) 또는 "real" (실투자)
    "default_position_pct": 0.05,    # 거래당 포트폴리오의 5%
}

ta = TradingAgentsGraph(debug=True, config=config)
final_state, decision = ta.propagate("005930", "2026-03-15")
print(decision)
print(final_state.get("execution_result", ""))  # 주문 실행 결과
```

모든 설정 옵션은 `tradingagents/default_config.py`를 참고하세요.

### 한국 시장 지원 (OpenDART)

TradingAgents는 [OpenDART API](https://opendart.fss.or.kr/)를 통해 한국 상장 기업을 지원합니다. 한국의 DART(전자공시시스템)에서 공식 재무제표와 규제 공시를 제공합니다.

한국 시장 지원을 활성화하려면:

1. [OpenDART](https://opendart.fss.or.kr/)에서 API 키를 발급받습니다
2. 환경 변수를 설정합니다:
   ```bash
   export OPENDART_API_KEY=your_api_key_here
   ```
3. 6자리 한국 종목 코드를 사용합니다 (예: 삼성전자 `005930`):
   ```python
   _, decision = ta.propagate("005930", "2026-03-08")
   ```

펀더멘털 애널리스트가 한국 종목 분석 시 `get_dart_financials`와 `get_dart_disclosures` 도구를 자동으로 사용하여 다음을 조회합니다:
- **재무제표**: 분기/연간 DART 공시의 매출, 영업이익, 순이익, 영업이익률(OPM)
- **공시**: 최근 30일간의 규제 공시, 실적 보고, 기업 활동

### 투자 페르소나

TradingAgents는 트레이더, 리서치 매니저, 리스크 매니저의 의사결정 방식을 결정하는 투자 페르소나를 지원합니다. 애널리스트는 객관성을 유지하며 페르소나의 영향을 받지 않습니다.

| 페르소나 | 전략 | 핵심 원칙 |
|---------|------|----------|
| **워런 버핏** | 가치 투자 | 장기 보유, 안전마진, 내재 가치, 경제적 해자 분석 |
| **레이 달리오** | 체계적 매크로 | 분산 ETF 배분, 리밸런싱, 거시경제 기반 체계적 의사결정 |
| **피터 린치** | 성장 투자 | PEG 비율 중시, 아는 것에 투자, 합리적 가격의 성장주 |

```python
config["persona"] = "warren_buffett"  # 또는 "ray_dalio", "peter_lynch", None (기본값)
```

CLI 모드에서는 대화형 위저드의 8단계에서 페르소나를 선택할 수 있습니다.

커스텀 페르소나를 추가하려면 `tradingagents/agents/personas.py`의 `PERSONAS` 딕셔너리에 `"trader"`, `"research_manager"`, `"risk_manager"` 역할에 대한 프롬프트 조각을 추가하세요.

### 증권사 연동 (KIS)

TradingAgents는 [한국투자증권](https://apiportal.koreainvestment.com/) REST API를 통해 실제 매매를 실행할 수 있습니다. 활성화하면 리스크 판사(Risk Judge) 이후에 실행 노드(Executor)가 그래프에 추가되어, 최종 매매 결정에 따라 자동으로 주문을 실행합니다.

#### 설정

1. [KIS Developers](https://apiportal.koreainvestment.com/)에서 KIS Open API 계정을 등록합니다
2. 앱을 생성하여 APP_KEY와 APP_SECRET를 발급받습니다
3. 환경 변수를 설정합니다:
   ```bash
   export KIS_APP_KEY=your_app_key
   export KIS_APP_SECRET=your_app_secret
   export KIS_ACCOUNT_NO=12345678-01    # 형식: XXXXXXXX-XX
   ```

#### 매매 모드

| 모드 | 설명 | 용도 |
|------|------|------|
| **모의투자** (`"paper"`) | KIS 가상 매매 서버를 통한 시뮬레이션 | 테스트, 개발, 전략 검증 |
| **실투자** (`"real"`) | 실제 자금으로 라이브 매매 | 운영 환경 (명시적 동의 필요) |

#### 안전장치

실행 엔진에 다중 보호 레이어가 내장되어 있습니다:

| 안전장치 | 기본값 | 설명 |
|---------|--------|------|
| 모의투자 기본 | `mode: "paper"` | 실투자는 명시적 동의 필요 |
| 이중 확인 | `require_confirmation: True` | CLI에서 실투자 활성화 전 2회 확인 |
| 포지션 한도 | `max_position_pct: 10%` | 단일 종목 최대 포트폴리오 비중 |
| 주문 금액 한도 | `max_order_amount: 500만원` | 1회 주문 최대 금액 |
| 일일 손실 한도 | `daily_loss_limit: -50만원` | 일일 손실 초과 시 매매 중단 |
| 장중 제한 | `enforce_market_hours: True` | KRX 장 시간(09:00-15:30) 외 주문 차단 |

#### 설정

```python
config["broker"] = {
    "enabled": True,
    "provider": "kis",
    "mode": "paper",                     # "paper" 또는 "real"
    "default_order_type": "market",      # "market" 또는 "limit"
    "default_position_pct": 0.05,        # 거래당 포트폴리오의 5%
    "safety": {
        "max_position_pct": 0.10,
        "max_order_amount": 5_000_000,
        "daily_loss_limit": -500_000,
        "enforce_market_hours": True,
        "require_confirmation": True,
    },
}
```

#### 아키텍처

증권사 시스템은 추상 `BaseBroker` 인터페이스를 사용하여, 향후 다른 한국 증권사(키움, 이베스트 등)로 확장 가능합니다:

```
ExecutionEngine (안전장치 + 오케스트레이션)
  └── BaseBroker (추상 인터페이스)
        └── KISBroker (KIS REST API 구현체)
              └── KISClient (HTTP 클라이언트 + 토큰 관리 + 레이트 리밋)
```

증권사가 활성화되면, 트레이더 에이전트가 포트폴리오 컨텍스트(보유 종목, 예수금, 미실현 손익)를 전달받아 더 정보에 기반한 의사결정을 내립니다.

### 전체 설정 옵션

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `llm_provider` | `"openai"` | LLM 프로바이더: openai, google, anthropic, xai, openrouter, ollama |
| `deep_think_llm` | `"gpt-5.2"` | 복잡한 추론용 모델 |
| `quick_think_llm` | `"gpt-5-mini"` | 빠른 분석용 모델 |
| `backend_url` | `"https://api.openai.com/v1"` | API 엔드포인트 URL |
| `max_debate_rounds` | `1` | 강세/약세 토론 라운드 수 |
| `max_risk_discuss_rounds` | `1` | 리스크 관리 토론 라운드 수 |
| `data_vendors` | `{"core_stock_apis": "yfinance", ...}` | 카테고리별 데이터 벤더 선택 |
| `persona` | `None` | 투자 페르소나 |
| `broker.enabled` | `False` | 매매 실행 활성화 |
| `broker.mode` | `"paper"` | 모의투자 또는 실투자 |
| `google_thinking_level` | `None` | Gemini 사고 설정: "high", "minimal" |
| `openai_reasoning_effort` | `None` | OpenAI 추론 노력도: "low", "medium", "high" |

## 기여하기

커뮤니티의 기여를 환영합니다! 버그 수정, 문서 개선, 새로운 기능 제안 등 여러분의 참여가 프로젝트를 더 나은 방향으로 이끕니다. 이 연구 분야에 관심이 있으시다면 오픈소스 금융 AI 연구 커뮤니티 [Tauric Research](https://tauric.ai/)에 참여해 주세요.

## 인용

*TradingAgents*가 도움이 되셨다면 아래와 같이 인용해 주세요 :)

```
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
