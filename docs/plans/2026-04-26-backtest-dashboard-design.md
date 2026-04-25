# Backtest Engine + Performance Dashboard Design

**Date:** 2026-04-26
**Status:** Approved
**Scope:** TradingAgents에 백테스트 엔진, 실거래 성과 추적기, HTML 대시보드 통합

## 1. Architecture

외부 오케스트레이터 패턴: 기존 `TradingAgentsGraph`를 변경하지 않고, 신규 3개 모듈이 외부에서 호출.

```
tradingagents/
  ├── graph/          (기존 유지)
  ├── execution/      (기존 유지)
  ├── backtest/       (신규) — 백테스트 엔진 + 성과 계산
  │   ├── __init__.py
  │   ├── models.py        — TradeRecord, PerformanceMetrics, BacktestResult
  │   ├── engine.py        — BacktestEngine
  │   └── performance.py   — PerformanceCalculator
  ├── tracker/        (신규) — 실거래 성과 추적
  │   ├── __init__.py
  │   └── tracker.py       — TradeTracker
  └── dashboard/      (신규) — HTML 대시보드 생성
      ├── __init__.py
      └── builder.py       — DashboardBuilder
```

## 2. Data Models (backtest/models.py)

### TradeRecord
단일 거래 기록. 백테스트·모의투자·실투자 공용.
- ticker, trade_date, signal (BUY/SELL/HOLD)
- entry_price, exit_price, exit_date, quantity
- pnl, pnl_pct, source ("backtest"|"paper"|"real")
- analyst_reports (dict), debate_summary, risk_decision, persona

### PerformanceMetrics
기간 성과 지표.
- total_trades, win_rate, avg_return, cumulative_return
- sharpe_ratio, max_drawdown, max_drawdown_duration
- alpha, beta, profit_factor, avg_holding_days
- equity_curve [{date, equity, drawdown}]
- monthly_returns [{month, return_pct}]

### BacktestResult
백테스트 전체 결과.
- ticker, config_snapshot, start_date, end_date, benchmark
- trades (list[TradeRecord]), metrics (PerformanceMetrics)

## 3. Backtest Engine (backtest/engine.py)

`BacktestEngine.run(ticker, start_date, end_date, rebalance_freq, benchmark, initial_capital) → BacktestResult`

1. 리밸런싱 날짜 생성 (monthly/weekly/biweekly, 영업일 보정)
2. 각 날짜마다 `TradingAgentsGraph.propagate()` 호출
3. 시그널 추출 → 포지션 업데이트 → TradeRecord 생성
4. 선택적 Reflector 학습
5. PerformanceCalculator로 지표 계산
6. BacktestResult JSON 저장

비용 제어: skip_llm (캐시된 시그널 재사용), save_signals (시그널 캐시)
LLM 비결정성: n_runs 반복 실행 옵션

## 4. Performance Calculator (backtest/performance.py)

`PerformanceCalculator.calculate(trades, initial_capital, benchmark_ticker, start_date, end_date) → PerformanceMetrics`

- Sharpe: sqrt(252) * mean(daily_returns) / std(daily_returns)
- MDD: peak-to-trough + 지속 일수
- Alpha/Beta: CAPM 회귀
- Equity curve: 일별 자산 가치
- Monthly returns: 월별 집계

## 5. Trade Tracker (tracker/tracker.py)

`TradeTracker` — 실거래 결과 누적 기록.

- record_trade(): agent_state에서 메타데이터 추출 → TradeRecord → JSON append
- close_position(): 미청산 포지션 수동 청산
- get_trades(): 필터 조건 조회
- get_performance(): PerformanceCalculator 위임
- get_open_positions(): 미청산 목록

저장 구조:
```
results/
├── trades/{ticker}/trades.json
├── backtest/{ticker}_{period}.json
└── dashboard/performance.html
```

## 6. Dashboard (dashboard/builder.py)

자체 포함 HTML + Plotly.js CDN. 다크 테마.

레이아웃:
1. KPI 카드 4개 (누적수익률, Sharpe, MDD, 승률)
2. Equity Curve + Benchmark 비교 차트
3. Monthly Returns Heatmap
4. Win/Loss 분포 히스토그램 + 상세 지표 테이블
5. 거래 내역 (토론 요약 펼침 가능)
6. 백테스트 vs 실거래 비교 테이블
7. 설정 스냅샷

## 7. Constraints

- 기존 코드 변경 없음
- DB 의존성 없음 (JSON 파일 기반)
- 신규 필수 의존성: 없음 (pandas, plotly는 이미 사용 가능)
- 테스트: 각 모듈별 pytest
