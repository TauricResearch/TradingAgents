# TradingAgents: 멀티 에이전트 LLM 금융 트레이딩 프레임워크

영문 문서: [README.md](README.md)

## 개요

TradingAgents는 실제 트레이딩 조직의 협업 흐름을 반영한 멀티 에이전트 프레임워크입니다. 펀더멘털 분석가, 뉴스 분석가, 시장 분석가, 리서처, 트레이더, 리스크 관리 팀이 역할별로 나뉘어 시장을 분석하고, 토론을 거쳐 최종 매매 결정을 도출합니다.

이 프로젝트는 연구 목적입니다. 결과는 사용한 모델, 데이터 품질, 분석 기간, 프롬프트, 외부 환경에 따라 달라질 수 있으며 투자 자문 용도가 아닙니다.

## 팀 구성

### 애널리스트 팀
- 펀더멘털 분석가: 기업 재무 상태와 성과 지표를 평가합니다.
- 센티먼트 분석가: 소셜 미디어와 대중 심리를 분석합니다.
- 뉴스 분석가: 뉴스와 거시경제 이벤트의 영향을 해석합니다.
- 시장 분석가: 기술적 지표와 가격 흐름을 분석합니다.

### 리서처 팀
- 강세 관점과 약세 관점의 리서처가 애널리스트 보고서를 바탕으로 토론합니다.

### 트레이더
- 애널리스트와 리서처의 결과를 종합해 매매 타이밍과 비중을 판단합니다.

### 리스크 관리 및 포트폴리오 매니저
- 리스크를 평가하고 최종 거래 제안을 승인하거나 거절합니다.

## 설치

### 저장소 클론

```powershell
git clone https://github.com/TauricResearch/TradingAgents.git
Set-Location TradingAgents
```

### Windows PowerShell 빠른 시작

이 저장소에서 실제로 검증한 설치 절차입니다.

```powershell
Set-Location C:\Projects\TradingAgents
py -3.13 -m venv .venv-codex
.\.venv-codex\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e . --no-cache-dir
tradingagents --help
```

참고:
- 현재 환경에서는 `.venv-codex`를 기본 가상환경으로 사용하는 흐름을 검증했습니다.
- `tradingagents` 명령이 없으면 대개 패키지가 아직 가상환경에 설치되지 않은 상태입니다.

### Docker

```powershell
Copy-Item .env.example .env
notepad .env
docker compose run --rm tradingagents
```

Ollama 프로필:

```powershell
docker compose --profile ollama run --rm tradingagents-ollama
```

## API 및 인증

TradingAgents는 여러 LLM 제공자를 지원합니다.

### 일반 제공자용 환경 변수

```powershell
$env:OPENAI_API_KEY = "..."
$env:GOOGLE_API_KEY = "..."
$env:ANTHROPIC_API_KEY = "..."
$env:XAI_API_KEY = "..."
$env:OPENROUTER_API_KEY = "..."
$env:ALPHA_VANTAGE_API_KEY = "..."
```

### Codex 제공자

`codex` 제공자는 OpenAI API 키가 필요 없습니다. 대신 Codex CLI 로그인만 되어 있으면 됩니다.

```powershell
where.exe codex
codex --version
codex login
```

또는:

```powershell
codex login --device-auth
```

TradingAgents는 `codex app-server`와 stdio로 직접 통신하며, Codex가 관리하는 인증 정보를 사용합니다. 파일 기반 인증을 쓰는 경우 보통 `~/.codex/auth.json`이 사용될 수 있습니다.

권장 `~/.codex/config.toml`:

```toml
approval_policy = "never"
sandbox_mode = "read-only"
web_search = "disabled"
personality = "none"
cli_auth_credentials_store = "file"
```

중요한 점:
- TradingAgents는 자체 LangGraph `ToolNode`를 유지합니다.
- Codex dynamic tools는 사용하지 않습니다.
- 에이전트 간 컨텍스트 오염을 막기 위해 호출마다 새로운 ephemeral Codex thread를 사용합니다.
- 기본 Codex 작업 디렉터리는 `~/.codex/tradingagents-workspace`입니다.

VS Code 터미널에서 `codex`가 인식되지 않으면:
- `where.exe codex`로 경로를 확인합니다.
- VS Code 창을 다시 로드합니다.
- 필요하면 `where.exe codex`가 반환한 전체 경로로 `codex.exe`를 직접 실행합니다.

TradingAgents는 Windows에서 VS Code OpenAI 확장 설치 경로 같은 일반적인 위치의 `codex.exe`도 자동 탐지합니다. 자동 탐지를 덮어쓰고 싶다면:

```powershell
$env:CODEX_BINARY = "C:\full\path\to\codex.exe"
```

## CLI 실행

설치 후 인터랙티브 CLI 실행:

```powershell
Set-Location C:\Projects\TradingAgents
.\.venv-codex\Scripts\Activate.ps1
tradingagents
```

대안:

```powershell
Set-Location C:\Projects\TradingAgents
.\.venv-codex\Scripts\Activate.ps1
python -m cli.main
```

도움말 확인:

```powershell
Set-Location C:\Projects\TradingAgents
.\.venv-codex\Scripts\Activate.ps1
tradingagents --help
```

## Python 패키지로 사용

### 기본 예시

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())
_, decision = ta.propagate("NVDA", "2026-01-15")
print(decision)
```

### 설정 예시

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "codex"
config["quick_think_llm"] = "gpt-5.4-mini"
config["deep_think_llm"] = "gpt-5.4-mini"
config["max_debate_rounds"] = 1

ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("NVDA", "2026-01-15")
print(decision)
```

`llm_provider = "codex"`에서 추가로 조정할 수 있는 설정:
- `codex_binary`
- `codex_reasoning_effort`
- `codex_summary`
- `codex_personality`
- `codex_workspace_dir`
- `codex_request_timeout`
- `codex_max_retries`
- `codex_cleanup_threads`

## 이번 검증에서 확인한 항목

실제 Windows PowerShell 환경에서 다음 항목을 검증했습니다.

- `.venv-codex`에 패키지 설치
- `tradingagents --help` 실행
- 로그인된 Codex 계정으로 plain `llm.invoke(...)` 호출
- OpenAI 스타일 `list[dict]` 입력 경로
- `bind_tools()` 기반 tool-call 경로
- 최소 `TradingAgentsGraph(...).propagate(...)` smoke run으로 final decision 생성

최소 그래프 smoke run에서는 `FINAL_DECISION= HOLD`가 반환되는 것을 확인했습니다.

## 기여

버그 수정, 문서 개선, 기능 제안 등 모든 형태의 기여를 환영합니다.

## 인용

인용 정보는 [README.md](README.md)의 citation 섹션을 참고해 주세요.
