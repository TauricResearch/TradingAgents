"""기존 complete_report.md를 한국어로 번역하는 테스트 스크립트.

사용법:
    python translate_report.py                        # 최근 리포트 자동 선택
    python translate_report.py reports/SPY_.../complete_report.md
"""
import sys
import re
import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def translate_report_to_korean(report_content: str, llm) -> str:
    """cli/main.py의 translate_report_to_korean와 동일한 로직."""
    from langchain_core.messages import HumanMessage, SystemMessage

    system_prompt = (
        "당신은 금융 전문가이자 비전공자 교육 전문가입니다.\n"
        "영어 주식 트레이딩 분석 리포트를 한국어로 번역하고, "
        "금융·기술 전문 용어를 비전공자도 쉽게 이해할 수 있도록 설명을 추가해주세요.\n\n"
        "번역 지침:\n"
        "1. 자연스러운 한국어로 번역하세요.\n"
        "2. 처음 등장하는 전문 용어 뒤에 괄호로 쉬운 설명을 추가하세요.\n"
        "   예) 200 SMA(200일 단순이동평균: 200일간 종가 평균으로 장기 추세를 나타내는 기준선)\n"
        "   예) RSI(상대강도지수: 0~100 사이 값으로 과매수·과매도를 판단. 70 이상=과매수, 30 이하=과매도)\n"
        "   예) MACD(이동평균수렴확산: 단기·장기 이동평균의 차이로 추세 전환 시점을 포착하는 지표)\n"
        "   예) ATR(평균진폭: 주가의 하루 평균 변동 폭. 손절 위치 설정 등 리스크 관리에 활용)\n"
        "3. 복잡한 분석 개념은 일상적인 비유를 사용해 쉽게 설명하세요.\n"
        "4. 가격, 퍼센트 등 수치와 종목 코드는 그대로 유지하세요.\n"
        "5. 마크다운 형식(##, ###, -, * 등)을 그대로 유지하세요.\n"
        "6. 섹션 제목은 한국어로 번역하세요.\n"
        "7. 최종 투자 의견과 권고 사항을 명확히 전달하세요."
    )

    parts = re.split(r"(?=^## )", report_content, flags=re.MULTILINE)

    translated_parts = []
    total = sum(1 for p in parts if p.strip())
    done = 0

    for part in parts:
        if not part.strip():
            continue
        done += 1
        # 섹션 제목 미리보기
        first_line = part.strip().splitlines()[0][:60]
        print(f"  [{done}/{total}] 번역 중: {first_line} ...", flush=True)

        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"아래 내용을 한국어로 번역하고 전문 용어를 쉽게 설명해주세요:\n\n{part}"),
        ])
        translated_parts.append(response.content)

    return "\n\n".join(translated_parts)


def pick_report() -> Path:
    """번역할 리포트 파일 경로 결정."""
    if len(sys.argv) > 1:
        p = Path(sys.argv[1])
        if not p.exists():
            print(f"[오류] 파일을 찾을 수 없습니다: {p}")
            sys.exit(1)
        return p

    # reports/ 하위에서 최근 수정된 complete_report.md 자동 선택
    candidates = sorted(
        Path("reports").glob("*/complete_report.md"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        print("[오류] reports/ 폴더에 complete_report.md가 없습니다.")
        sys.exit(1)

    print("번역 가능한 리포트:")
    for i, c in enumerate(candidates):
        print(f"  {i+1}. {c}")

    if len(candidates) == 1:
        return candidates[0]

    choice = input(f"번역할 리포트 번호 선택 [1-{len(candidates)}] (기본=1): ").strip()
    idx = int(choice) - 1 if choice.isdigit() else 0
    return candidates[max(0, min(idx, len(candidates) - 1))]


def main():
    report_path = pick_report()
    print(f"\n대상 리포트: {report_path}")

    # 이미 번역본이 있으면 알림
    ko_path = report_path.parent / "complete_report_ko.md"
    if ko_path.exists():
        overwrite = input("번역본이 이미 존재합니다. 덮어쓰시겠습니까? [Y/n]: ").strip().upper()
        if overwrite == "N":
            print("취소되었습니다.")
            sys.exit(0)

    # LLM 생성 — API 키를 명시적으로 전달
    import os
    print("\nLLM 초기화 중...")

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")

    if anthropic_key:
        from langchain_anthropic import ChatAnthropic
        llm = ChatAnthropic(model="claude-sonnet-4-6", api_key=anthropic_key)
        print("  사용 모델: claude-sonnet-4-6 (Anthropic)")
    elif openai_key:
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(model="gpt-4o", api_key=openai_key)
        print("  사용 모델: gpt-4o (OpenAI)")
    else:
        print("[오류] ANTHROPIC_API_KEY 또는 OPENAI_API_KEY가 없습니다.")
        sys.exit(1)

    # 번역 실행
    report_content = report_path.read_text(encoding="utf-8")
    ticker = report_path.parent.name.split("_")[0].upper()
    print(f"\n번역 시작 (총 {len(report_content):,}자)...\n")

    korean_content = translate_report_to_korean(report_content, llm)

    # 저장
    ko_header = (
        f"# 트레이딩 분석 리포트: {ticker} (한국어)\n\n"
        f"> **안내**: 이 리포트는 영문 분석 결과를 AI가 한국어로 번역하고, "
        f"금융 전문 용어를 비전공자도 쉽게 이해할 수 있도록 설명을 추가한 버전입니다.\n\n"
        f"생성: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"---\n\n"
    )
    ko_path.write_text(ko_header + korean_content, encoding="utf-8")
    print(f"\n✓ 번역 완료: {ko_path.resolve()}")


if __name__ == "__main__":
    main()
