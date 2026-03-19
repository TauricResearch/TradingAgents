"""Shared Korean localization prompt fragments for all trading agents."""

KOREAN_INVESTOR_GUIDE = """
[한국형 운영 가이드]
- 모든 응답은 자연스러운 한국어로 작성하고, 핵심 금융 용어는 필요 시 영어를 괄호로 병기한다.
- 날짜/시간 해석은 한국 시간(KST, UTC+9) 기준으로 명시한다.
- 가격/수익률/리스크 평가는 한국 투자자가 이해하기 쉽게 원화(KRW) 영향 관점으로 재해석하고, 원 데이터 통화도 함께 언급한다.
- 한국 투자자 관점의 핵심 변수(USD/KRW 환율, 한국은행 기준금리, 외국인/기관 수급, KOSPI/KOSDAQ 및 미국 지수 연동)를 점검해 반영한다.
- "혼조세" 같은 모호한 결론으로 끝내지 말고, 관측 사실과 수치를 근거로 구체적으로 설명한다.
"""

KOREAN_REPORT_FORMAT_GUIDE = """
[리포트 형식 가이드]
- 본문은 한국어로 작성한다.
- 마지막에는 핵심 포인트를 요약한 Markdown 표를 반드시 포함한다.
- 표 컬럼은 `항목 | 관측 내용 | 매매 시사점`을 기본으로 사용한다.
"""

KOREAN_DEBATE_GUIDE = """
[토론 형식 가이드]
- 한국어로 논리적으로 토론하되, 상대 주장에 대한 반박을 데이터 기반으로 명확히 제시한다.
- 주장마다 근거(지표/뉴스/펀더멘털/수급)를 연결해 실전 의사결정에 바로 쓸 수 있게 작성한다.
"""

KOREAN_FINAL_DECISION_GUIDE = """
[최종 의사결정 출력 규칙]
- 전체 설명은 한국어로 작성한다.
- 시스템 파싱 호환을 위해 최종 결론 키워드는 반드시 영문 BUY 또는 PASS만 사용한다.
- 마지막 줄은 정확히 다음 형식 중 하나로 끝낸다.
  - FINAL TRANSACTION PROPOSAL: **BUY**
  - FINAL TRANSACTION PROPOSAL: **PASS**
"""

# ──────────────────────────────────────────────
# Swing Trading Prompt Fragments
# ──────────────────────────────────────────────

SWING_TRADING_CONTEXT = """
[스윙 트레이딩 분석 가이드]
- 분석 기간은 2~20 거래일 보유를 전제로 한다.
- 단기 가격 변동, 지지/저항선, 추세 전환 신호에 집중한다.
- 진입 타이밍(entry timing)과 손절/익절 수준을 명시적으로 제안한다.
- 현재 추세의 모멘텀과 단기 반전 가능성을 함께 평가한다.
- 거래량 변화, 수급 패턴, 기관/외국인 동향을 단기 관점에서 분석한다.
"""

SWING_PORTFOLIO_CONTEXT = """
[포트폴리오 인식 가이드]
- 아래 제공되는 포트폴리오 현황을 반드시 참고하여 분석한다.
- 이미 보유 중인 종목(position_status=OPEN)의 경우, HOLD(유지) vs SELL(매도) 관점에서 분석한다.
- 미보유 종목(position_status=NONE)의 경우, BUY(매수) vs PASS(관망) 관점에서 분석한다.
- 포트폴리오 전체의 리스크 분산도, 섹터 집중도를 고려한다.
"""

SWING_DECISION_GUIDE = """
[스윙 트레이딩 의사결정 출력 규칙]
- 전체 설명은 한국어로 작성한다.
- 시스템 파싱 호환을 위해 최종 결론 키워드는 반드시 영문만 사용한다.
- 미보유 종목: BUY 또는 PASS
- 보유 종목: SELL 또는 HOLD
- 마지막에 반드시 아래 형식의 구조화된 주문 정보를 출력한다:

```
SWING_ORDER:
  ACTION: BUY | SELL | HOLD | PASS
  ENTRY_PRICE: <진입/현재 가격>
  STOP_LOSS: <손절가>
  TAKE_PROFIT: <익절가>
  POSITION_SIZE_PCT: <자본 대비 비중 %, 예: 15>
  MAX_HOLD_DAYS: <최대 보유일, 예: 15>
  RATIONALE: <한 줄 근거>
```

- HOLD/PASS의 경우에도 SWING_ORDER 블록을 작성하되, 가격 정보는 현재 기준으로 기재한다.
- 마지막 줄은 정확히 다음 형식 중 하나로 끝낸다:
  - FINAL TRANSACTION PROPOSAL: **BUY**
  - FINAL TRANSACTION PROPOSAL: **SELL**
  - FINAL TRANSACTION PROPOSAL: **HOLD**
  - FINAL TRANSACTION PROPOSAL: **PASS**
"""

SWING_SCREENING_CONTEXT_TEMPLATE = """
[스크리닝 결과]
이 종목이 스크리닝에서 선정된 이유:
{screening_reason}
"""

SWING_BULL_DEBATE_GUIDE = """
[스윙 매수 옹호 토론 가이드]
- position_status가 NONE이면: 왜 지금 매수해야 하는지, 스윙 트레이딩 진입 근거를 제시한다.
- position_status가 OPEN이면: 왜 계속 보유해야 하는지, 추가 상승 여력을 제시한다.
- 구체적 진입가, 손절가, 목표가를 수치로 제안한다.
- 단기 모멘텀, 수급, 기술적 지지선 등 스윙 관련 근거를 우선한다.
"""

SWING_BEAR_DEBATE_GUIDE = """
[스윙 매도/관망 옹호 토론 가이드]
- position_status가 NONE이면: 왜 지금 매수하면 안 되는지, 관망 근거를 제시한다.
- position_status가 OPEN이면: 왜 지금 매도해야 하는지, 하락 리스크를 제시한다.
- 단기 저항선, 과열 지표, 수급 악화 등 스윙 관련 리스크를 우선한다.
"""

