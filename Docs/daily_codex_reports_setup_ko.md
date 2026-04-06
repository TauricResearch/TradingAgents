# TradingAgents 일일 Codex 리포트 운영 가이드

이 문서는 `self-hosted Windows runner + Codex + GitHub Actions + GitHub Pages` 조합으로 TradingAgents를 매일 자동 실행하고, 웹페이지에서 결과를 확인하는 운영 절차를 정리한 문서입니다.

기준 저장소:
- `https://github.com/nornen0202/TradingAgents`

기본 분석 설정:
- 티커: `GOOGL`, `NVDA`
- provider: `codex`
- model: `gpt-5.4`
- analyst: `market`, `social`, `news`, `fundamentals`
- 출력 언어: `Korean`

관련 파일:
- 설정 파일: [config/scheduled_analysis.toml](/C:/Projects/TradingAgents/config/scheduled_analysis.toml)
- 예시 설정: [config/scheduled_analysis.example.toml](/C:/Projects/TradingAgents/config/scheduled_analysis.example.toml)
- 스케줄 러너: [runner.py](/C:/Projects/TradingAgents/tradingagents/scheduled/runner.py)
- 정적 사이트 생성기: [site.py](/C:/Projects/TradingAgents/tradingagents/scheduled/site.py)
- GitHub Actions 워크플로: [daily-codex-analysis.yml](/C:/Projects/TradingAgents/.github/workflows/daily-codex-analysis.yml)

## 1. 현재 운영 상태

2026-04-07 기준 현재 상태는 아래와 같습니다.

- self-hosted Windows runner 등록 완료
- runner 이름: `desktop-gheeibb-codex`
- runner 상태: `online`
- GitHub Pages 소스: `GitHub Actions`
- Actions 변수 `TRADINGAGENTS_ARCHIVE_DIR` 설정 완료
- 변수 값: `C:\TradingAgentsData\archive`
- `GOOGL`, `NVDA` 설정 파일 작성 완료
- 실제 원격 GitHub Actions 실행 성공 검증 완료

검증된 성공 실행:
- run URL: `https://github.com/nornen0202/TradingAgents/actions/runs/24013668241`
- 상태: `success`
- 실행 시작: `2026-04-06 09:15:42 KST`
- 분석 완료: `2026-04-06 09:28:35 KST`
- Pages 배포 완료: `2026-04-06 09:28:47 KST`

검증된 결과:
- archive manifest: `C:\TradingAgentsData\archive\latest-run.json`
- Pages URL: `https://nornen0202.github.io/TradingAgents/`
- 이번 성공 실행 결과: `GOOGL = BUY`, `NVDA = SELL`
- trade date: 두 티커 모두 `2026-04-02`

중요:
- 현재 runner는 정상 동작 중입니다.
- 서비스 모드 전환은 아직 완료된 상태로 가정하지 않습니다.
- 지금도 PC가 켜져 있고 로그인된 상태라면 자동 실행은 가능합니다.

## 2. 전체 동작 구조

동작 흐름은 아래와 같습니다.

1. GitHub Actions가 매일 `09:13 KST`에 `daily-codex-analysis.yml`을 실행합니다.
2. self-hosted Windows runner가 잡을 받아 TradingAgents를 실행합니다.
3. Codex `gpt-5.4`로 4개 analyst 조합 분석을 수행합니다.
4. 결과를 `TRADINGAGENTS_ARCHIVE_DIR` 아래에 누적 저장합니다.
5. 정적 사이트를 생성합니다.
6. GitHub Pages로 배포합니다.

사용자가 보는 위치:
- 웹: [https://nornen0202.github.io/TradingAgents/](https://nornen0202.github.io/TradingAgents/)
- 로컬 archive: `C:\TradingAgentsData\archive`

## 3. 가장 중요한 개념 3가지

### 3-1. runner token

runner token은 self-hosted runner를 GitHub 저장소에 등록할 때 쓰는 짧은 수명 토큰입니다.

중요:
- 영구 토큰이 아닙니다.
- 보통 1시간 내외로 만료됩니다.
- runner를 새로 등록하거나 재등록할 때만 사용합니다.

### 3-2. Codex 로그인 위치

`codex login`은 GitHub가 아니라 실제 self-hosted runner가 돌아가는 로컬 Windows PC에서 해야 합니다.

즉 이 구성에서는:
- 이 로컬 PC에서 로그인해야 합니다.
- GitHub-hosted runner에서는 이 로그인 상태를 유지할 수 없습니다.

### 3-3. `TRADINGAGENTS_ARCHIVE_DIR`

이 변수는 GitHub 경로나 저장소 경로가 아니라, self-hosted runner가 실행되는 로컬 PC의 절대 경로여야 합니다.

권장 예:
- `C:\TradingAgentsData\archive`
- `D:\TradingAgents\archive`

권장하지 않는 예:
- `C:\Projects\TradingAgents`
- GitHub URL
- 상대 경로

이유:
- 결과 이력을 저장소 checkout 폴더와 분리해야 안전합니다.
- archive는 저장소 밖의 영속 경로에 있어야 이전 실행 이력이 누적됩니다.

## 4. runner token 발급 방법

### 방법 A. GitHub 웹 UI

1. 저장소 [TradingAgents](https://github.com/nornen0202/TradingAgents)로 이동
2. `Settings`
3. `Actions`
4. `Runners`
5. `New self-hosted runner`
6. `Windows` 선택
7. 화면에 표시되는 명령의 `--token` 값을 사용

### 방법 B. GitHub CLI

등록용 token:

```powershell
gh auth status
gh api -X POST repos/nornen0202/TradingAgents/actions/runners/registration-token
```

삭제용 token:

```powershell
gh api -X POST repos/nornen0202/TradingAgents/actions/runners/remove-token
```

중요:
- `registration token`과 `remove token`은 서로 다릅니다.
- `.\config.cmd remove`에는 `remove token`이 필요합니다.
- `.\config.cmd --token ...` 등록에는 `registration token`이 필요합니다.

## 5. Codex 로그인 방법

먼저 확인:

```powershell
where.exe codex
codex --help
```

이 PC에서 확인된 실제 Codex 바이너리:

```powershell
C:\Users\JY\.vscode\extensions\openai.chatgpt-26.325.31654-win32-x64\bin\windows-x86_64\codex.exe
```

브라우저 로그인:

```powershell
codex login
```

또는 실제 경로 직접 실행:

```powershell
& 'C:\Users\JY\.vscode\extensions\openai.chatgpt-26.325.31654-win32-x64\bin\windows-x86_64\codex.exe' login
```

디바이스 인증:

```powershell
codex login --device-auth
```

상태 확인:

```powershell
codex login status
```

현재 이 PC에서 실제 확인된 상태:

```text
Logged in using ChatGPT
```

## 6. 서비스 모드 이해

### 서비스 모드가 의미하는 것

서비스 모드로 전환하면:
- Windows에 로그인하지 않아도 runner가 자동 시작될 수 있습니다.
- 로그아웃 상태에서도 GitHub Actions 잡을 받을 수 있습니다.

### 서비스 모드로도 안 되는 것

서비스 모드여도 아래 상태에서는 동작하지 않습니다.

- PC 전원이 꺼져 있음
- 절전 또는 최대 절전 상태
- 네트워크 끊김

즉 핵심은:
- 서비스 모드 = 로그아웃 상태 대응
- 전원 꺼짐 대응은 아님

### Codex 로그인 유지 여부

보통 같은 PC, 같은 사용자 환경이라면 Codex 로그인은 유지됩니다.

다만 아래 경우에는 재로그인이 필요할 수 있습니다.

- 인증 만료
- Codex 앱/CLI 업데이트 후 인증 재요구
- runner를 다른 사용자 계정으로 실행
- 인증 파일 삭제

## 7. 서비스 모드 전환 절차

현재 질문 흐름상 아직 서비스 모드 전환은 완료하지 않은 상태를 기준으로 설명합니다.

### 7-1. 기존 등록 제거

PowerShell:

```powershell
gh api -X POST repos/nornen0202/TradingAgents/actions/runners/remove-token
Set-Location C:\actions-runner
.\config.cmd remove
```

프롬프트가 뜨면:
- 방금 받은 `remove token` 값을 입력합니다.

주의:
- `registration token`을 넣으면 안 됩니다.

### 7-2. 서비스 모드 재등록

관리자 PowerShell:

```powershell
gh api -X POST repos/nornen0202/TradingAgents/actions/runners/registration-token
Set-Location C:\actions-runner
.\config.cmd --unattended --url https://github.com/nornen0202/TradingAgents --token <REGISTRATION_TOKEN> --name desktop-gheeibb-codex --work _work --replace --labels codex --runasservice
```

### 7-3. 확인

확인 항목:
- GitHub `Settings > Actions > Runners`에서 `online`
- `services.msc`에서 runner 서비스 확인
- `gh api repos/nornen0202/TradingAgents/actions/runners`

## 8. 운영 체크리스트

### 매일 자동 실행 전제 조건

- PC 전원이 켜져 있음
- 인터넷 연결 정상
- runner가 `online`
- `codex login status`가 정상
- `TRADINGAGENTS_ARCHIVE_DIR` 경로 존재

### 수동 점검 체크리스트

```powershell
gh auth status
gh variable list --repo nornen0202/TradingAgents
gh run list --repo nornen0202/TradingAgents --workflow daily-codex-analysis.yml --limit 5
gh api repos/nornen0202/TradingAgents/actions/runners
codex login status
Test-Path C:\TradingAgentsData\archive
```

### 수동 실행 체크리스트

1. 저장소 `Actions`
2. `Daily Codex Analysis`
3. `Run workflow`
4. 필요시 입력:
   - `tickers`: `GOOGL,NVDA`
   - `trade_date`: `2026-04-02`
   - `site_only`: `false`

## 9. 최근 질의응답 정리

### Q. `registration token`의 `expires_at`은 서비스 모드 만료 시간인가

A. 아닙니다.

- `expires_at`은 토큰 만료 시각입니다.
- 서비스 모드 자체의 만료 시각이 아닙니다.
- 만료 전에 등록만 완료하면 이후 서비스는 계속 동작합니다.

### Q. 서비스 모드로 바꾸면 PC를 꺼도 동작하나

A. 아닙니다.

- 서비스 모드는 로그아웃 상태 대응입니다.
- PC 전원이 꺼져 있으면 동작하지 않습니다.

### Q. 서비스 모드로 바꾸면 Codex 로그인은 유지되나

A. 보통 유지됩니다.

- 같은 PC와 같은 사용자 기준이면 대체로 유지됩니다.
- 다만 인증 만료나 사용자 계정 변경 시 재로그인이 필요할 수 있습니다.

### Q. `.\config.cmd remove`에서 무엇을 입력해야 하나

A. `remove token`을 입력해야 합니다.

명령:

```powershell
gh api -X POST repos/nornen0202/TradingAgents/actions/runners/remove-token
```

중요:
- `registration token`이 아닙니다.
- `remove token`과 `registration token`은 별개입니다.

### Q. `TRADINGAGENTS_ARCHIVE_DIR`는 프로젝트 경로인가

A. 아니고, 이 로컬 PC의 영속 archive 폴더 경로입니다.

현재 설정값:

```text
C:\TradingAgentsData\archive
```

## 10. 티커 변경 방법

수정 파일:
- [config/scheduled_analysis.toml](/C:/Projects/TradingAgents/config/scheduled_analysis.toml)

예시:

```toml
[run]
tickers = ["GOOGL", "NVDA"]
```

다른 티커로 바꾸려면:

```toml
[run]
tickers = ["AAPL", "MSFT", "TSLA"]
```

일회성 테스트는 GitHub Actions 수동 실행에서 `tickers` 입력칸으로 덮어쓸 수 있습니다.

## 11. 장애 대응 순서

문제가 생기면 아래 순서로 확인합니다.

1. runner 온라인 여부 확인
2. Codex 로그인 상태 확인
3. archive 경로 존재 여부 확인
4. 최근 Actions run 로그 확인
5. GitHub Pages 최신 페이지 반영 확인

자주 발생하는 원인:
- runner 오프라인
- Windows 로그아웃 또는 전원 꺼짐
- Codex 로그인 만료
- archive 경로 권한 문제
- workflow 수정 후 미푸시

## 12. 실제 검증 완료 항목

이번 작업에서 직접 검증한 항목:

- GitHub CLI 인증 정상
- self-hosted runner 온라인 확인
- Codex 로그인 상태 확인
- Actions 변수 설정 확인
- GitHub Pages 설정 확인
- 원격 workflow dispatch 성공
- `GOOGL`, `NVDA` 분석 성공
- Pages artifact 업로드 성공
- GitHub Pages 배포 성공
- 실제 Pages URL HTTP 200 확인

성공 링크:
- [GitHub Actions run](https://github.com/nornen0202/TradingAgents/actions/runs/24013668241)
- [GitHub Pages](https://nornen0202.github.io/TradingAgents/)

## 13. 지금 꼭 해야 하는 일

즉시 사용 기준으로는 추가 필수 작업이 없습니다.

다만 아래 상황이면 추가 작업이 필요합니다.

- 로그아웃 상태에서도 항상 돌리고 싶다
  - 관리자 PowerShell에서 서비스 모드 전환 필요
- 티커를 바꾸고 싶다
  - [config/scheduled_analysis.toml](/C:/Projects/TradingAgents/config/scheduled_analysis.toml) 수정
- 다른 PC로 runner를 옮기고 싶다
  - 그 PC에서 다시 `codex login`과 runner 등록 필요

## 14. 자주 쓰는 명령

```powershell
gh auth status
gh variable list --repo nornen0202/TradingAgents
gh run list --repo nornen0202/TradingAgents --workflow daily-codex-analysis.yml --limit 5
gh api repos/nornen0202/TradingAgents/actions/runners
codex login status
```

실제 Codex 바이너리 직접 실행:

```powershell
& 'C:\Users\JY\.vscode\extensions\openai.chatgpt-26.325.31654-win32-x64\bin\windows-x86_64\codex.exe' login status
```
