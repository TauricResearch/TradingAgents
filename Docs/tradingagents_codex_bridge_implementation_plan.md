# TradingAgents × Codex 브리지 구현 설계서

## 1. 목표

TradingAgents가 요구하는 LLM 호출을 OpenAI API key 대신 **로컬 Codex app-server + ChatGPT/Codex 인증**으로 처리한다.  
핵심 목표는 다음과 같다.

1. TradingAgents의 **기존 LangGraph / ToolNode 구조를 유지**한다.
2. OpenAI 호환 프록시를 억지로 에뮬레이션하지 않고, **새 provider(`codex`)를 추가**한다.
3. ChatGPT Pro 사용자는 **Codex 로그인(`codex login` / `codex login --device-auth`) 또는 Codex의 managed auth cache(`~/.codex/auth.json`)**를 통해 인증한다.
4. `bind_tools()`가 필요한 analyst 노드와 plain `invoke()`만 필요한 debate / manager / trader 노드가 모두 동작해야 한다.
5. Codex의 자체 shell/web/tool 생태계에 의존하지 않고, TradingAgents가 이미 가진 도구 실행 루프를 그대로 사용한다.

---

## 2. 왜 이 방식이 최선인가

### 채택할 방식
**권장안:** `codex app-server`를 로컬에 띄우고, Python에서 stdio(JSONL)로 통신하는 **Custom LangChain ChatModel**을 만든다.

### 채택하지 않을 방식

#### A. OpenAI-compatible `/v1/responses` 프록시
비추천. TradingAgents는 현재 `openai` provider에서 `langchain_openai.ChatOpenAI`를 사용하고 native OpenAI일 때 `use_responses_api=True`를 켠다.  
즉 `/v1/responses`와 tool-calling semantics를 꽤 정확히 흉내 내야 한다. 구현 난도가 높고 유지보수 비용이 크다.

#### B. Codex dynamic tools 직접 사용
비추천. app-server의 `dynamicTools`와 `item/tool/call`은 **experimental** 이다.  
TradingAgents는 이미 `ToolNode`로 툴 실행을 잘 처리하므로, 여기까지 Codex에 넘길 이유가 없다.

#### C. Codex SDK 직접 내장
부분적으로 가능하지만 비권장. SDK는 TypeScript 중심이다. Python 프로젝트인 TradingAgents에선 app-server stdio 브리지가 더 단순하다.

### 설계 핵심
Codex는 **모델 추론만 담당**하고, 실제 툴 실행은 여전히 TradingAgents/LangGraph가 담당한다.  
따라서 Codex 쪽에는 tool schema를 설명하고, 응답은 **엄격한 JSON schema**로만 받는다.

- 툴이 필요하면: `{"mode":"tool_calls", ...}`
- 툴이 더 이상 필요 없으면: `{"mode":"final", ...}`

이렇게 하면 analyst 노드의 `bind_tools()` 요구사항을 만족시키면서도 Codex의 experimental dynamic tool API를 피할 수 있다.

---

## 3. 구현 아키텍처

## 3.1 새 provider 추가

### 수정 파일
- `tradingagents/llm_clients/factory.py`
- `tradingagents/default_config.py`
- `tradingagents/llm_clients/__init__.py`
- CLI/UI 관련 파일(선택 사항이 아니라 사실상 권장)

### 추가 파일
- `tradingagents/llm_clients/codex_client.py`
- `tradingagents/llm_clients/codex_chat_model.py`
- `tradingagents/llm_clients/codex_app_server.py`
- `tradingagents/llm_clients/codex_schema.py`
- `tradingagents/llm_clients/codex_message_codec.py`
- `tradingagents/llm_clients/codex_preflight.py`
- `tests/llm_clients/test_codex_chat_model.py`
- `tests/llm_clients/test_codex_app_server.py`
- `tests/integration/test_codex_provider_smoke.py`

---

## 3.2 런타임 구성

### TradingAgents 측
`TradingAgentsGraph.__init__()`는 deep/quick 두 개 LLM을 한 번 생성해 재사용한다.  
따라서 `CodexChatModel`도 **모델 인스턴스당 app-server 세션 1개**를 유지하는 것이 적절하다.

- quick_thinking_llm → Codex app-server session A
- deep_thinking_llm → Codex app-server session B

### 중요 원칙
- **세션은 재사용**
- **thread는 per-invoke 새로 생성**
- 이유: 여러 analyst / debate agent가 같은 LLM 인스턴스를 공유하므로 thread까지 재사용하면 문맥 오염이 발생한다.

즉:
- app-server process: 재사용
- Codex thread: 매 호출마다 새로 생성 후 `thread/unsubscribe`

---

## 3.3 인증 전략

### 기본/권장
사용자가 먼저 로컬에서:

```bash
codex login
```

브라우저 callback이 막히거나 headless면:

```bash
codex login --device-auth
```

### headless / container / 원격 머신
- `cli_auth_credentials_store = "file"` 로 설정해서 `~/.codex/auth.json`을 사용
- 신뢰 가능한 머신에서 생성한 `auth.json`을 복사
- refresh는 직접 구현하지 말고 Codex가 하게 둔다
- `auth.json`은 절대 커밋 금지

### 고급 옵션: OAuth URL helper
원한다면 Python helper에서 app-server로 아래를 호출해 브라우저 login URL을 직접 받아 출력할 수 있다.

- `account/read`
- `account/login/start` with `type="chatgpt"`

하지만 **v1 구현은 이 helper 없이도 충분**하다. 실제 운영에서는 `codex login`이 더 단순하고 안정적이다.

---

## 3.4 보안 / 하드닝

Codex를 “코딩 에이전트”가 아니라 “모델 백엔드”로만 쓰기 위해 다음을 권장한다.

### `.codex/config.toml` 예시
```toml
model = "gpt-5.4"
model_reasoning_effort = "medium"
approval_policy = "never"
sandbox_mode = "read-only"
web_search = "disabled"
personality = "none"
log_dir = ".codex-log"
cli_auth_credentials_store = "file"
```

### 선택적 하드닝
```toml
[features]
apps = false
shell_tool = false
multi_agent = false
```

### 추가 권장
`cwd`를 프로젝트 루트가 아니라 **비어 있는 전용 workspace**로 준다.

예:
- `~/.cache/tradingagents/codex_workspace`
- 또는 repo 내 `./.tradingagents_codex_workspace`

이렇게 해야 Codex가 리포지토리를 뒤지거나 파일을 읽는 쪽으로 샐 가능성을 낮출 수 있다.

---

## 4. 메시지/툴 호출 설계

## 4.1 입력 정규화

`CodexChatModel`은 아래 입력을 모두 받아야 한다.

1. `str`
2. `list[BaseMessage]`
3. `list[dict(role=..., content=...)]`

이유:
- analyst 체인은 prompt pipeline 때문에 `BaseMessage` 시퀀스를 넘길 가능성이 높다
- trader / manager 쪽은 OpenAI-style dict list를 직접 `llm.invoke(messages)`로 넘긴다

### 내부 정규화 포맷 예시
```text
[SYSTEM]
...

[USER]
...

[ASSISTANT]
...

[ASSISTANT_TOOL_CALL]
name=get_news
args={"query":"AAPL",...}

[TOOL_RESULT]
name=get_news
call_id=call_xxx
content=...
```

---

## 4.2 bind_tools 처리

TradingAgents analyst 노드는 다음 패턴을 사용한다.

```python
chain = prompt | llm.bind_tools(tools)
result = chain.invoke(state["messages"])
```

따라서 `CodexChatModel.bind_tools()`는 반드시 구현해야 한다.

### 구현 방식
- LangChain tool 객체를 OpenAI-style tool schema로 변환
- 내부적으로 `self.bind(tools=formatted_tools, tool_choice=...)` 형태로 바인딩
- `_generate(..., tools=..., tool_choice=...)`에서 그 schema를 읽어 사용

### tool schema 변환
가능한 한 LangChain의 표준 helper(`convert_to_openai_tool` 계열)를 사용한다.  
각 tool에 대해 다음 정보를 확보한다.

- `name`
- `description`
- `parameters` JSON schema

---

## 4.3 output schema 설계

### plain invoke용
```json
{
  "type": "object",
  "properties": {
    "answer": { "type": "string" }
  },
  "required": ["answer"],
  "additionalProperties": false
}
```

### tool-capable invoke용
루트는 **final** 또는 **tool_calls** 중 하나가 되도록 강제한다.

```json
{
  "oneOf": [
    {
      "type": "object",
      "properties": {
        "mode": { "const": "final" },
        "content": { "type": "string" },
        "tool_calls": {
          "type": "array",
          "maxItems": 0
        }
      },
      "required": ["mode", "content", "tool_calls"],
      "additionalProperties": false
    },
    {
      "type": "object",
      "properties": {
        "mode": { "const": "tool_calls" },
        "content": { "type": "string" },
        "tool_calls": {
          "type": "array",
          "minItems": 1,
          "items": {
            "oneOf": [
              {
                "type": "object",
                "properties": {
                  "name": { "const": "get_news" },
                  "arguments": { "...": "get_news parameters schema" }
                },
                "required": ["name", "arguments"],
                "additionalProperties": false
              }
            ]
          }
        }
      },
      "required": ["mode", "content", "tool_calls"],
      "additionalProperties": false
    }
  ]
}
```

### 중요한 포인트
`tool_calls.items.oneOf` 안에 **툴별 arguments schema**를 넣는다.  
그래야 Codex가 tool 이름과 인자를 아무렇게나 생성하지 못한다.

---

## 4.4 tool-call 정책

Codex에게 항상 다음 규칙을 준다.

1. 지금 당장 필요한 **다음 단계 툴 호출만** 요청할 것
2. speculative call 금지
3. tool result를 아직 보지 않은 상태에서 downstream tool을 미리 호출하지 말 것
4. 툴이 필요 없으면 final로 답할 것
5. 응답은 output schema에 맞는 JSON만 낼 것

### 왜 필요한가
예를 들어 market analyst는 `get_stock_data` 이후에 `get_indicators`가 자연스럽다.  
하지만 CSV 생성/캐시 같은 간접 의존성이 있으므로 한 번에 여러 단계를 추측 호출하게 두는 것보다 **최소 다음 호출만** 받는 편이 안전하다.

---

## 5. Codex app-server 통신 계층 설계

## 5.1 `CodexAppServerConnection`

책임:
- `codex app-server` subprocess 시작/종료
- `initialize` / `initialized`
- request/response correlation (`id`)
- stdout JSONL reader thread
- notifications 수집
- timeout / error propagation
- graceful shutdown

### 핵심 메서드
- `start()`
- `close()`
- `request(method, params, timeout)`
- `wait_for_turn_completion(thread_id, turn_id, timeout)`
- `read_account()`
- `read_models()`
- `read_rate_limits()`

### transport
- **stdio(JSONL)** 사용
- websocket transport는 실익이 적으므로 v1에서 제외

---

## 5.2 초기 handshake

시작 직후:
1. subprocess spawn: `codex app-server`
2. `initialize`
3. `initialized`
4. `account/read`
5. 필요 시 `model/list`

### `initialize` 예시
```json
{
  "method": "initialize",
  "id": 1,
  "params": {
    "clientInfo": {
      "name": "tradingagents_codex_bridge",
      "title": "TradingAgents Codex Bridge",
      "version": "0.1.0"
    }
  }
}
```

---

## 5.3 preflight 체크

`codex_preflight.py` 또는 helper 함수에서:

1. `codex` binary 존재 여부 확인
2. app-server 시작 가능 여부 확인
3. `account/read(refreshToken=false)` 실행
4. `account.type == "chatgpt"` 또는 `"apiKey"`인지 확인
5. 가능하면 `planType == "pro"` 확인
6. `model/list`에서 `deep_think_llm`, `quick_think_llm` 가용성 확인
7. `account/rateLimits/read` 가능하면 출력

### 실패 시 메시지 예시
- `Codex not installed. Install with npm i -g @openai/codex`
- `No ChatGPT/API auth found. Run codex login`
- `Requested model gpt-5.4-mini is not available under current Codex account`

---

## 6. LangChain 커스텀 모델 설계

## 6.1 `CodexChatModel`

상속:
- `langchain_core.language_models.chat_models.BaseChatModel`

필수 구현:
- `_generate(...)`
- `_llm_type`
- `bind_tools(...)`

권장 추가:
- `_identifying_params`
- `invoke(...)` 입력 정규화 보강
- 에러 래핑

### 내부 필드 예시
- `model`
- `reasoning_effort`
- `summary`
- `personality`
- `request_timeout`
- `max_retries`
- `server: CodexAppServerConnection`
- `workspace_dir`
- `cleanup_threads`
- `service_name`

---

## 6.2 `_generate()` 동작

### tools 없는 경우
1. 입력 messages 정규화
2. plain schema 생성 (`answer`)
3. thread/start
4. turn/start with `outputSchema`
5. 최종 agent message JSON 파싱
6. `AIMessage(content=answer)` 반환

### tools 있는 경우
1. 입력 messages 정규화
2. tool schema 생성
3. root oneOf output schema 생성
4. thread/start
5. turn/start with `outputSchema`
6. 최종 agent message JSON 파싱
7. `mode == "tool_calls"` 면:
   - 각 call에 `id = "call_" + uuid`
   - `AIMessage(content=content or "", tool_calls=[...])`
8. `mode == "final"` 면:
   - `AIMessage(content=content, tool_calls=[])`

### 종료 처리
- `thread/unsubscribe`
- reader queue cleanup
- 필요 시 thread archive는 선택 옵션

---

## 6.3 app-server 호출 파라미터

### thread/start
```json
{
  "method": "thread/start",
  "params": {
    "model": "gpt-5.4",
    "cwd": "/abs/path/to/.tradingagents_codex_workspace",
    "approvalPolicy": "never",
    "serviceName": "tradingagents_codex_bridge"
  }
}
```

### turn/start
```json
{
  "method": "turn/start",
  "params": {
    "threadId": "...",
    "input": [
      { "type": "text", "text": "<serialized prompt>" }
    ],
    "model": "gpt-5.4",
    "effort": "medium",
    "summary": "concise",
    "personality": "none",
    "sandboxPolicy": {
      "type": "readOnly",
      "access": { "type": "fullAccess" }
    },
    "outputSchema": { ... }
  }
}
```

---

## 6.4 프롬프트 래퍼 템플릿

### plain invoke wrapper
```text
You are the language model backend for a LangGraph-based financial multi-agent system.

Rules:
1. Answer only from the provided conversation transcript.
2. Do not inspect files.
3. Do not run commands.
4. Do not use web search.
5. Return ONLY JSON that matches the provided schema.

Conversation transcript:
<...serialized messages...>
```

### tool-capable wrapper
```text
You are the language model backend for a LangGraph-based financial multi-agent system.

You may either:
- request the next necessary tool call(s), or
- provide the final assistant response.

Hard rules:
1. Use only the allowed tools listed below.
2. Arguments must conform exactly to the JSON schema for that tool.
3. Request only the next required tool call batch.
4. Do not speculate past missing tool results.
5. Do not inspect files.
6. Do not run commands.
7. Do not use web search.
8. Return ONLY JSON that matches the provided schema.

Allowed tools:
<tool schemas pretty-printed>

Conversation transcript:
<...serialized messages...>
```

### 안정화 팁
- tool schema를 pretty JSON으로 포함
- 1~2개의 few-shot example을 포함할 수 있음
- 단, prompt를 너무 길게 만들어 토큰 낭비하지 않도록 주의

---

## 7. TradingAgents 코드 변경 체크리스트

## 7.1 `default_config.py`
추가 권장 key:

```python
"llm_provider": "openai",
"codex_binary": "codex",
"codex_reasoning_effort": "medium",
"codex_summary": "concise",
"codex_personality": "none",
"codex_workspace_dir": os.getenv("TRADINGAGENTS_CODEX_WORKSPACE", "./.tradingagents_codex_workspace"),
"codex_request_timeout": 120,
"codex_max_retries": 2,
"codex_cleanup_threads": True,
```

호환성 위해:
- `openai_reasoning_effort`가 설정돼 있고 `codex_reasoning_effort`가 비어 있으면 fallback 하도록 해도 좋다.

---

## 7.2 `factory.py`
대략:

```python
if provider_lower == "codex":
    return CodexClient(model, base_url, **kwargs)
```

---

## 7.3 `codex_client.py`
책임:
- `BaseLLMClient` 구현
- kwargs를 `CodexChatModel` 생성자에 전달
- `validate_model()`에서 preflight/model list 확인

---

## 7.4 CLI / UI
반드시 추가할 항목:
- provider 목록에 `codex`
- backend_url 입력은 codex일 때 숨기거나 무시
- advanced options:
  - `codex_reasoning_effort`
  - `codex_summary`
  - `codex_personality`
  - `codex_workspace_dir`

---

## 7.5 README / docs
반드시 문서화:
1. ChatGPT Pro/Codex auth와 API key의 차이
2. `codex login`
3. headless auth cache 사용법
4. `.codex/config.toml` 예시
5. provider 선택 방법
6. known limitations

---

## 8. 테스트 전략

## 8.1 단위 테스트

### `test_codex_message_codec.py`
- `str` 입력 정규화
- `BaseMessage` 시퀀스 정규화
- dict message 시퀀스 정규화
- `ToolMessage` 직렬화

### `test_codex_schema.py`
- plain schema 생성
- tool oneOf schema 생성
- tool args const / required / additionalProperties 검증

### `test_codex_chat_model.py`
mock app-server 응답으로:
- plain final answer
- tool_calls answer
- malformed JSON retry
- timeout
- unsupported model error

### `test_codex_app_server.py`
- initialize handshake
- request/response correlation
- notification draining
- turn completed / failed 처리

---

## 8.2 통합 테스트

### smoke
- provider=`codex`
- analyst=`news` 한 개만 선택
- ticker=`AAPL`
- research depth=1
- 최종 리포트 파일 생성 확인

### tool loop
- market analyst만 실행
- 첫 응답이 `get_stock_data` tool call
- tool result 후 다음 응답이 `get_indicators` 또는 final

### multi-agent
- `market + news`
- graph 전체 완주
- `final_trade_decision` 비어 있지 않음

### auth preflight
- 로그인 안 된 환경 → 친절한 실패
- 로그인 된 환경 → account/read 성공

---

## 8.3 운영 검증
실제 실행 전 아래 순서 권장:

```bash
codex login
python -m tradingagents.llm_clients.codex_preflight
python main.py
```

또는 CLI/UI에서 provider를 `codex`로 선택.

---

## 9. 장애 대응

## 9.1 malformed JSON
대응:
- 1회 재시도
- 재시도 prompt:
  - “Your previous output was invalid JSON. Return valid JSON matching the schema only.”
- 그래도 실패하면 예외 raise

## 9.2 app-server 시작 실패
대응:
- binary path 재확인
- `codex --version` 확인
- PATH 문제면 `codex_binary` 절대경로 사용

## 9.3 로그인/권한 문제
대응:
- `codex login`
- headless면 `codex login --device-auth`
- `cli_auth_credentials_store="file"` 설정
- `~/.codex/auth.json` 존재 여부 확인

## 9.4 rate limit
대응:
- `account/rateLimits/read` 노출
- 재시도(backoff)
- 긴 배치 작업은 serialized run
- 필요 시 Codex credits 사용 고려

## 9.5 thread log 과다 생성
대응:
- `thread/unsubscribe` 기본 수행
- `.codex-log` 별도 디렉터리 사용
- 오래된 로그 cleanup script 추가

---

## 10. 권장 구현 순서

### Phase 1
- provider 추가
- app-server connection 추가
- plain invoke만 먼저 연결
- preflight 추가

### Phase 2
- `bind_tools()` + tool schema oneOf 구현
- analyst nodes smoke test

### Phase 3
- CLI/UI 옵션 추가
- README/docs 작성
- 통합 테스트 보강

### Phase 4
- malformed JSON retry
- rate limit/backoff
- log cleanup / diagnostics

---

## 11. 최종 권장안 요약

### 가장 좋은 구현 방식
**TradingAgents에 `codex` provider를 새로 추가하고, 내부에서 `codex app-server`와 stdio(JSONL)로 통신하는 LangChain 커스텀 ChatModel을 구현한다.**  
tool calling은 Codex dynamicTools를 쓰지 말고, **outputSchema + JSON oneOf** 방식으로 모델 응답을 `final` 또는 `tool_calls` 형태로 강제한다.

### 이 방식의 장점
- OpenAI API key 불필요
- ChatGPT Pro / Codex 로그인 재사용 가능
- TradingAgents의 기존 ToolNode / graph 구조 유지
- Python 프로젝트에 자연스럽게 통합 가능
- dynamicTools 실험 API 의존 최소화
- 추후 유지보수 포인트가 명확함

### 반드시 지켜야 할 운영 원칙
- 직접 OAuth refresh 구현 금지
- `auth.json`은 비밀 취급
- `codex login` 또는 device-auth 우선
- one auth cache per trusted runner / serialized workflow
- Codex를 모델 백엔드로만 쓰고 shell/web 기능은 최대한 비활성화

---

## 12. 최소 수용 기준(Acceptance Criteria)

아래가 모두 충족되면 구현 성공으로 간주한다.

1. `llm_provider="codex"` 설정으로 TradingAgents가 실행된다.
2. API key 없이 `codex login` 상태에서 동작한다.
3. analyst 노드가 `bind_tools()`를 통해 tool call을 생성하고 ToolNode가 이를 실행한다.
4. manager/trader/risk nodes가 plain `invoke()`로 정상 응답한다.
5. `AAPL` 또는 `SPY`에 대해 최소 1개 analyst + 전체 graph smoke run이 성공한다.
6. malformed JSON, auth missing, binary missing, model missing에 대한 에러 메시지가 명확하다.
7. README와 preflight가 포함된다.