# TradingAgents 일일 Codex 리포트 운영 가이드

이 문서는 `self-hosted Windows runner + Codex + GitHub Actions + GitHub Pages` 조합으로 TradingAgents를 매일 자동 실행하고, 웹페이지에서 결과를 확인하는 전체 절차를 정리한 문서입니다.

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

## 1. 현재 완료된 상태

2026-04-06 기준으로 아래 항목은 이미 완료되었습니다.

- self-hosted Windows runner 설치 및 저장소 등록 완료
- runner 이름: `desktop-gheeibb-codex`
- runner 현재 상태: `online`
- GitHub Pages 소스: `GitHub Actions`로 설정 완료
- Actions 변수 `TRADINGAGENTS_ARCHIVE_DIR` 설정 완료
- 값: `C:\TradingAgentsData\archive`
- `GOOGL`, `NVDA`용 설정 파일 작성 완료
- 실제 원격 GitHub Actions 실행 성공 완료

검증된 원격 실행:
- run URL: `https://github.com/nornen0202/TradingAgents/actions/runs/24013668241`
- 상태: `success`
- 실행 시작: `2026-04-06 09:15:42 KST`
- 분석 단계 완료: `2026-04-06 09:28:35 KST`
- Pages 배포 완료: `2026-04-06 09:28:47 KST`

검증된 산출물:
- archive manifest: `C:\TradingAgentsData\archive\latest-run.json`
- Pages URL: `https://nornen0202.github.io/TradingAgents/`

이번 성공 실행 결과:
- `GOOGL`: `BUY`
- `NVDA`: `SELL`
- trade date: 두 티커 모두 `2026-04-02`

## 2. 가장 중요한 개념 3가지

### 2-1. runner token은 무엇인가

runner token은 self-hosted runner를 GitHub 저장소에 등록할 때 한 번 쓰는 짧은 수명의 등록 토큰입니다.

중요:
- 영구 토큰이 아닙니다.
- 보통 1시간 안쪽의 짧은 만료 시간을 가집니다.
- runner를 새로 등록하거나 다시 등록할 때마다 새로 발급받으면 됩니다.

### 2-2. `codex login`은 어디에서 해야 하나

`codex login`은 GitHub가 아니라, 실제로 workflow를 실행할 self-hosted runner 머신에서 해야 합니다.

즉 이 구성에서는:
- 이 로컬 Windows PC에서 로그인해야 합니다.
- GitHub-hosted runner에서는 이 로그인 상태를 유지할 수 없습니다.

### 2-3. `TRADINGAGENTS_ARCHIVE_DIR`는 어떤 경로여야 하나

이 변수는 GitHub 저장소 경로나 GitHub Pages URL이 아니라, self-hosted runner가 돌아가는 로컬 PC의 절대 경로여야 합니다.

올바른 예:
- `C:\TradingAgentsData\archive`
- `D:\TradingAgents\archive`

권장하지 않는 예:
- 저장소 체크아웃 폴더 내부 임시 경로
- GitHub URL
- 상대 경로

이유:
- runner는 매 실행마다 저장소를 다시 checkout할 수 있습니다.
- archive는 저장소 밖의 고정 경로에 있어야 이전 실행 이력이 계속 누적됩니다.

## 3. 관리자 PowerShell에서 새 runner token 발급받는 방법

관리자 PowerShell이 꼭 필요한 것은 아닙니다. 토큰 발급 자체는 GitHub UI 또는 `gh` CLI로 하면 됩니다.

### 방법 A. GitHub 웹 UI에서 발급

1. 저장소 [TradingAgents](https://github.com/nornen0202/TradingAgents)로 이동
2. `Settings`
3. `Actions`
4. `Runners`
5. `New self-hosted runner`
6. 운영체제 `Windows` 선택
7. 화면에 표시되는 `config.cmd --token ...` 명령의 토큰 부분을 사용

설명:
- 이 방법이 가장 직관적입니다.
- 토큰은 화면에 잠깐 보이는 등록용 토큰입니다.
- 만료되면 다시 같은 화면에서 새로 받으면 됩니다.

### 방법 B. GitHub CLI로 발급

PowerShell:

```powershell
gh auth status
gh api -X POST repos/nornen0202/TradingAgents/actions/runners/registration-token
```

응답 예시는 아래와 비슷합니다.

```json
{
  "token": "XXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
  "expires_at": "2026-04-06T00:49:20Z"
}
```

이 세션에서 실제 검증한 결과:
- 토큰 발급 API 호출 성공
- 토큰 길이 확인 완료
- 만료 시각 응답 확인 완료

### 언제 새 token이 필요한가

아래 경우 새 token이 필요합니다.

- runner를 처음 등록할 때
- `config.cmd remove` 후 다시 등록할 때
- 이름이나 labels를 바꿔서 재등록할 때
- 서비스 모드로 새로 등록할 때

## 4. runner 머신에서 `codex login` 또는 `codex login --device-auth` 하는 방법

### 4-1. 먼저 확인할 것

PowerShell에서 아래를 확인합니다.

```powershell
where.exe codex
codex --help
```

만약 `codex` alias가 애매하게 잡히거나 바로 실행이 안 되면, 실제 바이너리를 직접 실행하면 됩니다.

이 PC에서 확인된 실제 Codex 바이너리:

```powershell
C:\Users\JY\.vscode\extensions\openai.chatgpt-26.325.31654-win32-x64\bin\windows-x86_64\codex.exe
```

### 4-2. 브라우저 로그인 방식

PowerShell:

```powershell
codex login
```

또는 실제 경로 직접 실행:

```powershell
& 'C:\Users\JY\.vscode\extensions\openai.chatgpt-26.325.31654-win32-x64\bin\windows-x86_64\codex.exe' login
```

동작:
- 브라우저 인증 창이 열리거나
- 브라우저 인증 링크가 표시됩니다.
- ChatGPT/OpenAI 계정으로 로그인하면 됩니다.

### 4-3. 디바이스 인증 방식

브라우저 팝업이 어려우면 아래를 사용합니다.

```powershell
codex login --device-auth
```

또는:

```powershell
& 'C:\Users\JY\.vscode\extensions\openai.chatgpt-26.325.31654-win32-x64\bin\windows-x86_64\codex.exe' login --device-auth
```

동작:
- 터미널에 코드와 인증 URL이 나옵니다.
- 브라우저에서 해당 URL을 열고 코드를 입력해 인증합니다.

### 4-4. 로그인 확인

```powershell
codex login status
```

또는:

```powershell
& 'C:\Users\JY\.vscode\extensions\openai.chatgpt-26.325.31654-win32-x64\bin\windows-x86_64\codex.exe' login status
```

이 세션에서 실제 확인된 상태:

```text
Logged in using ChatGPT
```

즉 현재 이 runner 머신은 Codex 로그인 상태가 이미 유효합니다.

## 5. `TRADINGAGENTS_ARCHIVE_DIR`에 어떤 경로를 넣어야 하나

질문에 대한 짧은 답:

네. 이 self-hosted runner가 돌아가는 로컬 PC 기준의 절대 경로를 넣는 것이 맞습니다.

다만 정확히는:
- "프로젝트 경로"를 넣는 것이 아니라
- "프로젝트 바깥의 영속 보관 폴더"를 넣는 것이 더 좋습니다.

### 왜 프로젝트 경로 자체는 권장하지 않나

예를 들어 아래 경로는 권장하지 않습니다.

```text
C:\Projects\TradingAgents
```

이유:
- 저장소 작업 폴더와 결과 보관 폴더가 섞입니다.
- checkout/clean 동작과 결과 보존이 충돌할 수 있습니다.
- 리포트 이력 관리가 지저분해집니다.

### 권장 경로

이 세션에서 이미 설정해둔 값:

```text
C:\TradingAgentsData\archive
```

이 경로가 좋은 이유:
- 저장소 바깥 경로입니다.
- runner가 같은 PC에서 실행되므로 항상 접근 가능합니다.
- 실행 이력이 계속 누적됩니다.

### 현재 설정 상태 확인 방법

```powershell
gh variable list --repo nornen0202/TradingAgents
```

현재 실제 설정값:

```text
TRADINGAGENTS_ARCHIVE_DIR    C:\TradingAgentsData\archive
```

## 6. self-hosted runner 등록 방법

### 현재 상태

이미 이 PC에서 등록 완료되어 있습니다.

- runner name: `desktop-gheeibb-codex`
- labels: `self-hosted`, `Windows`, `X64`, `codex`

현재 워크플로의 대상:

```yaml
runs-on: [self-hosted, Windows]
```

### 새로 등록해야 할 때 전체 절차

PowerShell:

```powershell
mkdir C:\actions-runner
Set-Location C:\actions-runner
Invoke-WebRequest -Uri https://github.com/actions/runner/releases/download/v2.333.1/actions-runner-win-x64-2.333.1.zip -OutFile actions-runner-win-x64-2.333.1.zip
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::ExtractToDirectory("$PWD/actions-runner-win-x64-2.333.1.zip", "$PWD")
```

그 다음 GitHub에서 받은 token으로 등록:

```powershell
.\config.cmd --url https://github.com/nornen0202/TradingAgents --token <NEW_TOKEN>
```

실행:

```powershell
.\run.cmd
```

## 7. 관리자 권한이 필요한 경우와 아닌 경우

### 관리자 권한이 없어도 되는 것

- runner token 발급
- `config.cmd`로 일반 runner 등록
- `run.cmd`로 foreground 실행
- `codex login`
- GitHub Actions 실행

### 관리자 권한이 필요한 것

- Windows 서비스로 runner 등록
- 시스템 전체 실행 정책 변경

현재 상태:
- 일반 runner 등록은 완료
- 로그인 시 자동 시작되도록 작업 스케줄러 등록 완료
- 따라서 "사용자가 로그인된 상태"에서는 정상 동작

주의:
- PC가 꺼져 있거나
- Windows에 로그인되어 있지 않으면
- 현재 구성에서는 runner가 잡을 받지 못할 수 있습니다.

## 8. 진짜 항상 돌게 하려면

현재도 자동화는 동작합니다. 다만 가장 안정적인 운영을 원하면 나중에 관리자 PowerShell에서 서비스 모드로 전환하는 것이 좋습니다.

서비스 모드 재등록 예시:

```powershell
Set-Location C:\actions-runner
.\config.cmd remove
.\config.cmd --unattended --url https://github.com/nornen0202/TradingAgents --token <NEW_TOKEN> --name desktop-gheeibb-codex --work _work --replace --labels codex --runasservice
```

설명:
- 이 방식은 로그아웃 상태에서도 계속 동작하게 만드는 방향입니다.
- 새 token이 필요합니다.

## 9. GitHub Pages 설정 확인 방법

웹 UI:

1. 저장소 `Settings`
2. `Pages`
3. `Build and deployment`
4. `Source = GitHub Actions`

현재 실제 확인 상태:
- Pages URL: `https://nornen0202.github.io/TradingAgents/`
- build type: `workflow`
- 공개 상태: `public`

## 10. 수동 실행 방법

### 로컬에서 바로 실행

PowerShell:

```powershell
Set-Location C:\Projects\TradingAgents
python -m pip install -e .
python -m tradingagents.scheduled --config config/scheduled_analysis.toml --label manual-local
```

### GitHub Actions에서 수동 실행

1. 저장소 `Actions`
2. `Daily Codex Analysis`
3. `Run workflow`
4. 필요하면 입력값 지정

입력값 예시:
- `tickers`: `GOOGL,NVDA`
- `trade_date`: `2026-04-02`
- `site_only`: `false`

## 11. 매일 자동 실행 방식

현재 cron:

```yaml
- cron: "13 0 * * *"
```

이 의미:
- UTC 기준 `00:13`
- 한국 시간 기준 매일 `09:13`

즉 지금은 매일 오전 9시 13분에 자동 실행되도록 설정되어 있습니다.

## 12. 결과는 어디서 보나

### 웹페이지

- [https://nornen0202.github.io/TradingAgents/](https://nornen0202.github.io/TradingAgents/)

### 로컬 archive

- `C:\TradingAgentsData\archive\latest-run.json`
- `C:\TradingAgentsData\archive\runs\...`

### runner 작업 폴더에서 생성된 site

- `C:\actions-runner\_work\TradingAgents\TradingAgents\site\index.html`

## 13. 이번에 실제로 검증한 항목

이번 세션에서 아래를 직접 검증했습니다.

- `gh` 인증 상태 정상
- self-hosted runner 온라인 상태 확인
- Codex 로그인 상태 확인
- `TRADINGAGENTS_ARCHIVE_DIR` 변수 설정 확인
- GitHub Pages 설정 확인
- 원격 workflow dispatch 실행 성공
- `GOOGL`, `NVDA` 실제 분석 성공
- Pages artifact 업로드 성공
- GitHub Pages 배포 성공
- 실제 Pages URL HTTP 200 응답 확인
- 실제 Pages HTML에 최신 run ID 노출 확인

실제 성공 run:
- [GitHub Actions run](https://github.com/nornen0202/TradingAgents/actions/runs/24013668241)
- [GitHub Pages](https://nornen0202.github.io/TradingAgents/)

## 14. 당신이 지금 꼭 해야 하는 일

즉시 사용 기준으로는 추가 필수 작업이 없습니다.

이미 완료된 것:
- 설정 파일 작성
- runner 등록
- Codex 로그인 확인
- Actions 변수 설정
- Pages 설정
- 원격 실실행 검증

다만 아래 상황이면 당신이 직접 해야 합니다.

- 로그아웃 상태에서도 항상 돌게 만들고 싶다
  - 관리자 PowerShell로 서비스 등록 필요
- 티커를 바꾸고 싶다
  - [scheduled_analysis.toml](/C:/Projects/TradingAgents/config/scheduled_analysis.toml) 수정 필요
- 다른 PC로 runner를 옮기고 싶다
  - 그 PC에서 다시 `codex login`과 runner 등록 필요

## 15. 자주 쓰는 확인 명령

```powershell
gh auth status
gh variable list --repo nornen0202/TradingAgents
gh run list --repo nornen0202/TradingAgents --workflow daily-codex-analysis.yml --limit 5
gh run view 24013668241 --repo nornen0202/TradingAgents
codex login status
```

실제 Codex 바이너리 직접 확인이 필요하면:

```powershell
& 'C:\Users\JY\.vscode\extensions\openai.chatgpt-26.325.31654-win32-x64\bin\windows-x86_64\codex.exe' login status
```
