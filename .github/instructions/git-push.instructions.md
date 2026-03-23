---
description: "코드 변경 작업 완료 후 항상 git add, commit, push를 수행하도록 지시합니다."
---

# Git Push 자동 수행

코드 변경 작업을 완료한 후, 반드시 다음 단계를 순서대로 수행하세요:

1. **버전 업데이트** — `bot.py`의 `BOT_VERSION` 값을 변경 내용에 맞게 올린다
2. **git add** — GitKraken MCP 도구(`mcp_gitkraken_git_add_or_commit` action: add)로 스테이징
3. **git commit** — GitKraken MCP 도구(`mcp_gitkraken_git_add_or_commit` action: commit)로 커밋 (한국어 메시지)
4. **git push** — GitKraken MCP 도구(`mcp_gitkraken_git_push`)로 푸시

## 중요: 도구 사용 규칙

- **터미널 명령(`git add`, `git commit`, `git push`) 대신 반드시 MCP 또는 전용 도구를 사용한다.**
- GitKraken MCP 도구를 우선 사용하고, 사용 불가 시에만 터미널을 대안으로 사용한다.

## 버전 규칙 (semver)

- `bot.py` 상단의 `BOT_VERSION = "X.Y.Z"` 를 반드시 업데이트한다.
- **patch (+0.0.1)**: 버그 수정, 작은 변경, 리팩토링
- **minor (+0.1.0)**: 새 기능 추가, 기존 기능 개선
- **major (+1.0.0)**: 사용자가 명시적으로 요청한 경우에만
- 판단이 어려우면 patch를 올린다.

## 일반 규칙

- 커밋 메시지는 변경 내용을 명확하게 설명해야 합니다.
- 이미 커밋/푸시할 변경 사항이 없으면 건너뜁니다.
- 사용자가 명시적으로 "푸시하지 마" 또는 "커밋하지 마"라고 요청하면 이 규칙을 따르지 않습니다.
