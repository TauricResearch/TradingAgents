# TradingAgents 일일 자동 리포트 설정 가이드

이 문서는 현재 저장소에 추가된 `self-hosted runner + Codex + GitHub Actions + GitHub Pages` 자동화 구성을 실제로 운영하는 방법을 처음부터 끝까지 정리한 문서입니다.

적용 대상:
- 저장소: `nornen0202/TradingAgents`
- 기본 티커: `GOOGL`, `NVDA`
- LLM 제공자: `codex`
- 모델: `gpt-5.4`
- analyst 구성: `market`, `social`, `news`, `fundamentals`
- 결과 언어: `Korean`

관련 파일:
- 설정 파일: [config/scheduled_analysis.toml](/C:/Projects/TradingAgents/config/scheduled_analysis.toml)
- 예시 설정: [config/scheduled_analysis.example.toml](/C:/Projects/TradingAgents/config/scheduled_analysis.example.toml)
- 실행 엔트리포인트: [tradingagents/scheduled/runner.py](/C:/Projects/TradingAgents/tradingagents/scheduled/runner.py)
- 정적 사이트 생성기: [tradingagents/scheduled/site.py](/C:/Projects/TradingAgents/tradingagents/scheduled/site.py)
- GitHub Actions 워크플로: [.github/workflows/daily-codex-analysis.yml](/C:/Projects/TradingAgents/.github/workflows/daily-codex-analysis.yml)

## 1. 지금 이미 준비된 것

이 저장소에는 다음이 이미 구현되어 있습니다.

- 비대화식 스케줄 실행기
  - 여러 티커를 순차 실행합니다.
  - `latest_available` 기준으로 최근 거래일을 자동 해석합니다.
  - 실패한 티커가 있어도 다른 티커를 계속 실행할 수 있습니다.
- 결과 아카이브
  - 각 실행마다 run manifest, final state, markdown report, graph log를 저장합니다.
- 웹 리포트 생성
  - GitHub Pages에 바로 올릴 수 있는 정적 HTML/CSS/JSON을 생성합니다.
- GitHub Actions 워크플로
  - 매일 `09:13 KST` 기준으로 실행되도록 cron이 잡혀 있습니다.
  - 수동 실행도 가능합니다.

## 2. 당신이 반드시 해야 하는 작업

이 부분은 제가 대신할 수 없습니다.

### 2-1. GitHub 저장소에 변경 반영

제가 로컬 저장소에는 구현을 끝냈지만, 원격 GitHub 저장소에 반영하려면 당신이 아래 둘 중 하나를 해야 합니다.

1. 직접 commit / push
2. 다음 턴에서 저에게 commit 메시지와 push/PR 작업까지 맡기기

### 2-2. self-hosted runner 준비

Codex 로그인 상태를 유지해야 하므로 GitHub-hosted runner가 아니라 self-hosted runner가 필요합니다.

권장:
- 항상 켜져 있거나, 최소한 스케줄 시간 전에 켜져 있는 Windows 머신 1대
- 이 저장소가 체크아웃된 경로 유지
- Python 3.13 사용
- `codex` 실행 가능

### 2-3. Codex 로그인

runner 머신에서 한 번 로그인해야 합니다.

PowerShell:

```powershell
where.exe codex
codex login
```

브라우저 기반 로그인이 어려우면:

```powershell
codex login --device-auth
```

확인:

```powershell
codex --version
```

참고:
- 이 환경에서는 `codex --version`이 WindowsApps alias 때문에 바로 실패했지만, TradingAgents preflight는 실제 Codex 바이너리를 자동 탐지해서 정상 통과했습니다.
- 즉 `codex` alias가 애매해도 TradingAgents 자체는 동작할 수 있습니다.
- 그래도 runner 머신에서는 가능하면 `where.exe codex`와 실제 `codex login`이 확실히 동작하도록 맞추는 편이 안전합니다.

### 2-4. GitHub Pages 설정

GitHub 저장소 설정에서 아래 작업이 필요합니다.

1. 저장소 `Settings`로 이동
2. 왼쪽 `Pages` 선택
3. `Build and deployment`의 `Source`를 `GitHub Actions`로 선택

이 단계는 GitHub UI 권한이 필요해서 당신이 해야 합니다.

### 2-5. self-hosted runner 등록

저장소 `Settings > Actions > Runners`에서 runner를 등록해야 합니다.

일반 순서:
1. 저장소 `Settings`
2. `Actions`
3. `Runners`
4. `New self-hosted runner`
5. Windows 선택
6. GitHub가 보여주는 등록 스크립트를 runner 머신에서 실행

runner label은 워크플로가 현재 아래를 요구합니다.

```yaml
runs-on: [self-hosted, Windows]
```

즉 `self-hosted`, `Windows` 라벨이 붙은 러너면 됩니다.

### 2-6. 선택이지만 강력 권장: 아카이브 경로 영속화

지금 기본 설정은 저장소 내부의 `./.runtime/tradingagents-archive`를 쓰게 되어 있습니다.
더 안정적인 운영을 원하면 GitHub repository variable에 아래 값을 넣는 것을 권장합니다.

- 이름: `TRADINGAGENTS_ARCHIVE_DIR`
- 예시 값: `D:\TradingAgentsData\archive`

이렇게 하면 저장소를 새로 checkout해도 이력 데이터가 유지됩니다.

저장소 변수 위치:
- `Settings > Secrets and variables > Actions > Variables`

## 3. 빠른 실행 순서

### 3-1. 로컬 확인

```powershell
Set-Location C:\Projects\TradingAgents
.\.venv-codex\Scripts\Activate.ps1
python -m pip install -e .
python -m tradingagents.scheduled --config config/scheduled_analysis.toml --label manual-local
```

실행 후 확인 경로:
- 아카이브: [config/scheduled_analysis.toml](/C:/Projects/TradingAgents/config/scheduled_analysis.toml)의 `archive_dir`
- 사이트: [site](/C:/Projects/TradingAgents/site)

### 3-2. GitHub Actions 수동 실행

1. GitHub 저장소의 `Actions` 탭 이동
2. `Daily Codex Analysis` 선택
3. `Run workflow` 클릭
4. 필요 시:
   - `tickers`: 예: `GOOGL,NVDA,MSFT`
   - `trade_date`: 예: `2026-04-04`
   - `site_only`: `true` 또는 `false`
5. 실행

입력 의미:
- `tickers`: 설정 파일의 티커를 일회성으로 덮어씁니다.
- `trade_date`: `latest_available` 대신 특정 날짜를 강제합니다.
- `site_only`: 새 분석 없이 기존 아카이브만 다시 Pages로 재배포합니다.

## 4. 매일 자동 실행 방식

현재 워크플로 cron:

```yaml
- cron: "13 0 * * *"
```

이 값은 UTC 기준이므로 한국 시간으로는 매일 `09:13`입니다.

왜 `09:00`이 아니라 `09:13`인가:
- GitHub 문서상 scheduled workflow는 부하가 높은 시각, 특히 정각 부근에서 지연되거나 드롭될 수 있습니다.
- 그래서 정각보다 몇 분 비켜서 잡는 편이 안전합니다.

## 5. 산출물 구조

예시 run 디렉터리:

```text
archive/
  latest-run.json
  runs/
    2026/
      20260405T080047_real-smoke/
        run.json
        tickers/
          GOOGL/
          NVDA/
        engine-results/
```

티커별 주요 파일:
- `analysis.json`: 실행 요약
- `final_state.json`: TradingAgents 최종 상태
- `report/complete_report.md`: 통합 마크다운 리포트
- `full_states_log_<date>.json`: graph 상태 로그
- 실패 시 `error.json`

사이트 구조:

```text
site/
  index.html
  feed.json
  runs/<run_id>/index.html
  runs/<run_id>/<ticker>.html
  downloads/<run_id>/<ticker>/*
```

## 6. 설정 변경 방법

기본 티커를 바꾸려면 [config/scheduled_analysis.toml](/C:/Projects/TradingAgents/config/scheduled_analysis.toml)에서 이 부분만 수정하면 됩니다.

```toml
[run]
tickers = ["GOOGL", "NVDA"]
```

연구 깊이를 올리려면:

```toml
max_debate_rounds = 3
max_risk_discuss_rounds = 3
```

주의:
- 값이 커질수록 실행 시간과 Codex 사용량이 늘어납니다.

## 7. 가장 추천하는 운영 형태

### 최소 운영

- runner 머신 1대
- `codex login` 1회
- GitHub Pages 공개 배포
- `GOOGL`, `NVDA` 일일 실행

### 안정 운영

- runner 머신 1대 고정
- `TRADINGAGENTS_ARCHIVE_DIR`를 저장소 밖 영속 경로로 지정
- Windows 부팅 시 runner 자동 시작
- 주 1회 정도 Actions 실행 기록 점검

## 8. 트러블슈팅

### `Missing config/scheduled_analysis.toml`

원인:
- 실제 설정 파일이 아직 저장소에 없음

해결:
- 현재는 이미 [config/scheduled_analysis.toml](/C:/Projects/TradingAgents/config/scheduled_analysis.toml)을 추가해 두었습니다.

### Codex 인증 오류

원인:
- runner 머신에서 로그인 안 됨

해결:

```powershell
codex login
```

또는:

```powershell
codex login --device-auth
```

### Pages가 비어 있음

확인 순서:
1. `Actions` 탭에서 `Daily Codex Analysis` 실행 성공 여부 확인
2. `Settings > Pages`에서 Source가 `GitHub Actions`인지 확인
3. workflow의 `deploy` job 성공 여부 확인

### 스케줄이 안 뜸

확인 순서:
1. workflow 파일이 default branch에 있는지 확인
2. 저장소에 최근 60일 내 활동이 있었는지 확인
3. cron이 UTC 기준임을 확인

## 9. 제가 이미 직접 검증한 것

이 저장소 로컬 환경에서 아래를 확인했습니다.

- `Codex preflight` 성공
- Codex 계정 읽기 성공
- 모델 목록에서 `gpt-5.4` 확인
- mock 기반 자동화 테스트 통과
- 실제 `SPY` 1티커 end-to-end 스모크 런 성공
  - 시작: `2026-04-05 08:00:47 +09:00`
  - 종료: `2026-04-05 08:06:24 +09:00`
  - 거래일 해석: `2026-04-02`
  - 최종 decision: `SELL`

## 10. 이번 요청 기준 정리

현재 상태에서 당신이 해야 하는 최소 작업은 아래입니다.

1. 변경사항을 원격 GitHub 저장소에 반영
2. self-hosted runner 등록
3. runner 머신에서 `codex login`
4. GitHub Pages Source를 `GitHub Actions`로 설정
5. 필요하면 `TRADINGAGENTS_ARCHIVE_DIR` repository variable 추가

그 외의 저장소 코드, 설정 파일, 워크플로, 문서는 지금 이 저장소에 이미 준비되어 있습니다.

## 참고 링크

- GitHub Actions `schedule` 이벤트: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
- GitHub Pages custom workflow: https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages
- GitHub Pages publishing source: https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site
- OpenAI Codex cloud/docs: https://developers.openai.com/codex/cloud
- OpenAI Codex app announcement: https://openai.com/index/introducing-the-codex-app/
