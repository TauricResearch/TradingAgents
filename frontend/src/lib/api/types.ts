/** Zod schemas mirroring the tested view models in
 * tradingagents/pro/dashboard/service.py — the API boundary is validated
 * so a drifted backend fails loudly here, not deep in a component.
 * `.passthrough()` where the backend may grow additive fields. */
import { z } from "zod";

export const OverviewSchema = z
  .object({
    status: z.string().optional(),
    symbol: z.string().optional(),
    as_of: z.string().optional(),
    last_close: z.number().nullable().optional(),
    n_bars: z.number().optional(),
    session: z.string().nullable().optional(),
    missing_feeds: z.array(z.string()).optional(),
    regime: z.string().nullable().optional(),
    run_id: z.string().optional(),
    started_at: z.string().optional(),
    execution_status: z.string().nullable().optional(),
    rejected_at: z.string().nullable().optional(),
  })
  .passthrough();
export type Overview = z.infer<typeof OverviewSchema>;

export const RunListItemSchema = z.object({
  run_id: z.string(),
  started_at: z.string(),
  symbol: z.string(),
  action: z.string().nullable(),
  rejected_at: z.string().nullable(),
  timeframe: z.string().nullable().optional(),
  // run provenance (R3.2): "loop" (schedule) or "operator" (run dialog)
  trigger: z.string().optional(),
});
export type RunListItem = z.infer<typeof RunListItemSchema>;
export const RunListSchema = z.array(RunListItemSchema);

const TakeProfitSchema = z.object({
  price: z.number(),
  size_fraction: z.number(),
});

const AgentVoteSchema = z.object({
  agent_id: z.string(),
  vote: z.string(),
  confidence: z.number(),
});

const EvidenceItemSchema = z
  .object({
    agent_id: z.string(),
    direction: z.string(),
    confidence: z.number(),
    claim: z.string(),
    data_refs: z
      .array(z.object({ name: z.string(), value: z.unknown() }).passthrough())
      .optional(),
    sources: z.array(z.unknown()).optional(),
  })
  .passthrough();
export type EvidenceItem = z.infer<typeof EvidenceItemSchema>;

const AnalogSchema = z
  .object({
    description: z.string(),
    similarity: z.number(),
    outcome: z.string(),
  })
  .passthrough();

export const RecommendationSchema = z
  .object({
    status: z.string().optional(), // "rejected" | "no recommendation"
    rejection: z
      .object({
        stage: z.string().nullable().optional(),
        // the gate's own words, e.g. "FOMC in 3.2h — new entries are
        // blocked…" (R4.3: name the event, not just the stage)
        reasons: z.array(z.string()).optional(),
      })
      .catchall(z.unknown())
      .nullable()
      .optional(),
    id: z.string().optional(),
    symbol: z.string().optional(),
    action: z.string().optional(),
    confidence: z.number().optional(),
    entry_price: z.number().nullable().optional(),
    stop_loss: z.number().nullable().optional(),
    take_profits: z.array(TakeProfitSchema).optional(),
    position_size: z
      .object({
        quantity: z.number(),
        notional: z.number().nullable().optional(),
        pct_of_equity: z.number().nullable().optional(),
      })
      .optional(),
    market_regime: z.string().optional(),
    risk_reward: z.number().nullable().optional(),
    vote_tally: z.record(z.number()).optional(),
    vote_breakdown: z.object({ votes: z.array(AgentVoteSchema) }).optional(),
    n_evidence: z.number().optional(),
    n_counterarguments: z.number().optional(),
    counterarguments: z.array(EvidenceItemSchema).optional(),
    evidence: z.array(EvidenceItemSchema).optional(),
    historical_analogs: z.array(AnalogSchema).optional(),
    invalidation: z.string().nullable().optional(),
    // empirical win probability from the system's own scored record
    p_win: z
      .object({
        p_win: z.number(),
        n: z.number(),
        basis: z.string(),
        median_hold_s: z.number().nullable().optional(),
      })
      .nullable()
      .optional(),
    created_at: z.string().optional(),
  })
  .passthrough();
export type Recommendation = z.infer<typeof RecommendationSchema>;

export const TimelineSchema = z.object({
  run_id: z.string(),
  node_sequence: z.array(z.string()),
  // per-node latency, parallel to node_sequence; absent/[] on runs
  // recorded before R9 (the pipeline board then omits latency)
  node_times: z
    .array(z.object({ node: z.string(), elapsed_s: z.number() }))
    .optional(),
  execution_status: z.string().nullable().optional(),
  entries: z.array(
    z
      .object({
        speaker: z.string(),
        stance: z.string().nullable(),
        confidence: z.number().nullable(),
        argument: z.string(),
        cited: z.array(z.string()),
      })
      .passthrough(),
  ),
  rejection: z
    .object({ stage: z.string().nullable().optional() })
    .catchall(z.unknown())
    .nullable(),
});
export type Timeline = z.infer<typeof TimelineSchema>;

export const EvidencePanelsSchema = z.record(z.array(EvidenceItemSchema));
export type EvidencePanels = z.infer<typeof EvidencePanelsSchema>;

export const StatusSchema = z
  .object({
    attached: z.boolean(),
    trading_halted: z.boolean().nullable(),
    kill_switch: z.object({ engaged: z.boolean(), reason: z.string() }).optional(),
    circuit_breaker: z.object({ tripped: z.boolean(), reason: z.string() }).optional(),
    open_positions: z
      .array(
        z.object({
          symbol: z.string(),
          quantity: z.number(),
          entry_price: z.number().nullable().optional(),
          mark_price: z.number().nullable().optional(),
          mark_source: z.enum(["live", "eod", "entry"]).optional(),
          unrealized_pnl: z.number().nullable().optional(),
          exposure_pct: z.number().nullable().optional(),
          stop_price: z.number().nullable().optional(),
        }),
      )
      .optional(),
    unrealized_total: z.number().nullable().optional(),
    equity: z.number().nullable().optional(),
    live_armed: z.boolean().optional(),
    arming: z
      .record(
        z.string(),
        z.object({
          pair: z.string(),
          tier: z.string(),
          label: z.string(),
          expires_at: z.string().optional(),
          expired: z.boolean().optional(),
        }),
      )
      .optional(),
  })
  .passthrough();
export type SystemStatus = z.infer<typeof StatusSchema>;

export const PriceAlertSchema = z
  .object({
    id: z.string(),
    symbol: z.string(),
    level: z.number(),
    direction: z.enum(["above", "below"]),
    note: z.string().optional(),
    created_at: z.string().optional(),
    triggered_at: z.string().nullable().optional(),
    active: z.boolean(),
  })
  .passthrough();
export const PriceAlertListSchema = z.array(PriceAlertSchema);
export type PriceAlert = z.infer<typeof PriceAlertSchema>;

export const RegimeSchema = z
  .object({
    symbols: z.record(
      z.string(),
      z.object({ regime: z.string().nullable() }),
    ),
    session: z.string().nullable().optional(),
    as_of: z.string(),
  })
  .passthrough();
export type RegimePayload = z.infer<typeof RegimeSchema>;

export const AlertSchema = z.object({
  time: z.string(),
  run_id: z.string(),
  severity: z.enum(["critical", "warning", "info"]),
  text: z.string(),
  // consecutive same-kind events coalesce server-side (×N)
  count: z.number().optional(),
});
export type Alert = z.infer<typeof AlertSchema>;
export const AlertFeedSchema = z.object({ alerts: z.array(AlertSchema) });

export const JournalSchema = z.object({
  entries: z.array(
    z
      .object({
        symbol: z.string(),
        action: z.string().nullable(),
        regime: z.string().nullable(),
        pnl: z.number(),
        won: z.boolean().nullable(),
        closed_at: z.string(),
        mode: z.string().optional(),
        commission: z.number().optional(),
        venue_order_id: z.string().optional(),
      })
      .passthrough(),
  ),
  total_pnl: z.number(),
  n_trades: z.number(),
  win_rate: z.number().nullable(),
  by_mode: z
    .record(
      z.string(),
      z.object({
        n_trades: z.number(),
        wins: z.number(),
        total_pnl: z.number(),
        win_rate: z.number().nullable(),
      }),
    )
    .optional(),
});
export type Journal = z.infer<typeof JournalSchema>;

export const ScannerSchema = z.object({
  rows: z.array(
    z
      .object({
        symbol: z.string(),
        timeframe: z.string(),
        regime: z.string(),
        trend_slope: z.number(),
        zscore: z.number(),
        realized_vol: z.number(),
        last_close: z.number(),
        score: z.number(),
      })
      .passthrough(),
  ),
  as_of: z.string(),
});
export type Scanner = z.infer<typeof ScannerSchema>;

export const PortfolioStatsSchema = z
  .object({
    equity_curve: z.array(z.number()),
    n_trades: z.number(),
    win_rate: z.number().nullable(),
    total_pnl: z.number(),
    expectancy: z.number(),
    profit_factor: z.number().nullable(),
    max_drawdown: z.number(),
    total_return: z.number(),
    starting_equity: z.number(),
    exposure: z
      .object({
        n_positions: z.number(),
        n_priced: z.number(),
        max_open_positions: z.number(),
        gross_exposure_pct: z.number().nullable(),
        net_exposure_pct: z.number().nullable(),
        long_exposure_pct: z.number().nullable(),
        short_exposure_pct: z.number().nullable(),
        largest_position_pct: z.number().nullable(),
      })
      .optional(),
  })
  .passthrough();
export type PortfolioStats = z.infer<typeof PortfolioStatsSchema>;

export const RiskBudgetSchema = z
  .object({
    attached: z.boolean(),
    daily_pnl: z.number().optional(),
    daily_loss_limit_pct: z.number().optional(),
    daily_loss_limit_usd: z.number().optional(),
    daily_loss_used_usd: z.number().optional(),
    daily_loss_used_pct_of_budget: z.number().nullable().optional(),
    consecutive_losses: z.number().optional(),
    consecutive_loss_limit: z.number().optional(),
    max_orders_per_day: z.number().nullable().optional(),
    orders_today: z.number().nullable().optional(),
    tripped: z.boolean().optional(),
    reason: z.string().optional(),
  })
  .passthrough();
export type RiskBudget = z.infer<typeof RiskBudgetSchema>;

export const BacktestReportSchema = z
  .object({
    total_return: z.number().optional(),
    max_drawdown: z.number().optional(),
    sharpe: z.number().optional(),
    sortino: z.number().optional(),
    win_rate: z.number().optional(),
    profit_factor: z.number().nullable().optional(),
    expectancy: z.number().optional(),
    n_trades: z.number().optional(),
    // R accounting (risk unit = qty × |entry − initial stop|)
    avg_r: z.number().optional(),
    avg_planned_rr: z.number().optional(),
    expectancy_r: z.number().optional(),
    win_rate_ex_scratch: z.number().optional(),
    scratches: z.number().optional(),
    exit_reasons: z.record(z.number()).nullable().optional(),
    // extended analytics (track T6)
    annualized_return: z.number().optional(),
    omega: z.number().optional(),
    ulcer_index: z.number().optional(),
    mar: z.number().optional(),
  })
  .passthrough();

export const BacktestSchema = z
  .object({
    status: z.string().optional(), // done | cancelled | interrupted
    report: BacktestReportSchema.optional(),
    final_equity: z.number().optional(),
    decisions: z.number().optional(),
    executed: z.number().optional(),
    rejections: z.record(z.number()).optional(),
    equity_curve: z.array(z.number()).optional(),
    n_trades: z.number().optional(),
    monte_carlo: z
      .object({
        final_equity_p5: z.number(),
        final_equity_p50: z.number(),
        final_equity_p95: z.number(),
        max_drawdown_p95: z.number(),
        prob_loss: z.number(),
      })
      .optional(),
  })
  .passthrough();
export type Backtest = z.infer<typeof BacktestSchema>;

/** One trade row — open (has mark_price/unrealized_pnl) or closed (has
 * exit_price/pnl/closed_at). Permissive so the same table renders both. */
export const BacktestTradeSchema = z
  .object({
    id: z.string(),
    symbol: z.string(),
    side: z.string(),
    quantity: z.number(),
    entry_price: z.number(),
    exit_price: z.number().optional(),
    mark_price: z.number().optional(),
    stop: z.number().optional(),
    pnl: z.number().optional(),
    unrealized_pnl: z.number().optional(),
    reason: z.string().optional(),
    opened_at: z.string().optional(),
    closed_at: z.string().optional(),
    initial_stop: z.number().nullable().optional(),
    r_multiple: z.number().nullable().optional(),
    planned_rr: z.number().nullable().optional(),
  })
  .passthrough();
export type BacktestTrade = z.infer<typeof BacktestTradeSchema>;

/** The result view of a run (metrics + metadata; bulk arrays live in the
 * per-run artifacts, fetched separately). */
export const BacktestRunViewSchema = BacktestSchema.extend({
  provider: z.string().optional(),
  symbol: z.string().optional(),
  timeframe: z.string().optional(),
  duration: z.string().optional(),
  window: z.array(z.string()).nullable().optional(),
  window_truncated: z.boolean().optional(),
  trades: z.array(BacktestTradeSchema).optional(),
  est_cost_usd: z.number().optional(),
  llm_calls: z.number().optional(),
  bars: z.number().optional(),
  indicator_mode: z.string().optional(),
  initial_equity: z.number().optional(),
  risk_per_trade_pct: z.number().optional(),
  max_position_pct: z.number().optional(),
  strategy_id: z.string().optional(),
  strategy_params: z.record(z.unknown()).optional(),
  artifacts: z.array(z.string()).optional(),
});

/** Strategy discovery (GET /api/backtest/strategies) — drives the run
 * controls' strategy picker + dynamic parameter inputs (track T1). */
export const BacktestStrategyParamSchema = z.object({
  name: z.string(),
  kind: z.enum(["float", "int", "categorical"]),
  low: z.number().nullable().optional(),
  high: z.number().nullable().optional(),
  step: z.number().nullable().optional(),
  choices: z.array(z.union([z.string(), z.number()])).default([]),
  default: z.union([z.string(), z.number()]).nullable().optional(),
});
export type BacktestStrategyParam = z.infer<typeof BacktestStrategyParamSchema>;
export const BacktestStrategySchema = z.object({
  id: z.string(),
  description: z.string().default(""),
  params: z.array(BacktestStrategyParamSchema).default([]),
});
export type BacktestStrategy = z.infer<typeof BacktestStrategySchema>;
export const BacktestStrategiesSchema = z.object({
  strategies: z.array(BacktestStrategySchema),
});
export type BacktestRunView = z.infer<typeof BacktestRunViewSchema>;

/** equity artifact rows: [iso_time, equity] — every decision, nothing dropped */
export const BacktestEquityArtifactSchema = z.array(
  z.tuple([z.string(), z.number()]),
);
export const BacktestTradesArtifactSchema = z.array(BacktestTradeSchema);

/** In-flight (or last) job snapshot from GET /api/backtest/job. */
export const BacktestJobSchema = z
  .object({
    status: z.string(),
    job_id: z.string().optional(),
    params: z.record(z.unknown()).optional(),
    progress: z.record(z.unknown()).optional(),
    open_trades: z.array(BacktestTradeSchema).optional(),
    closed_trades: z.array(BacktestTradeSchema).optional(),
    closed_total: z.number().optional(),
    error: z.string().nullable().optional(),
    result: BacktestRunViewSchema.nullable().optional(),
    started_at: z.string().optional(),
  })
  .passthrough();
export type BacktestJob = z.infer<typeof BacktestJobSchema>;

export const BacktestRunListItemSchema = z
  .object({
    id: z.string(),
    created_at: z.string().nullable().optional(),
    symbol: z.string().nullable().optional(),
    timeframe: z.string().nullable().optional(),
    duration: z.string().nullable().optional(),
    provider: z.string().nullable().optional(),
    status: z.string().nullable().optional(),
    n_trades: z.number().nullable().optional(),
    final_equity: z.number().nullable().optional(),
    total_return: z.number().nullable().optional(),
    win_rate: z.number().nullable().optional(),
    window: z.array(z.string()).nullable().optional(),
    decisions: z.number().nullable().optional(),
    indicator_mode: z.string().nullable().optional(),
  })
  .passthrough();
export type BacktestRunListItem = z.infer<typeof BacktestRunListItemSchema>;
export const BacktestRunsSchema = z.object({
  runs: z.array(BacktestRunListItemSchema),
});

export const BacktestRunSchema = z
  .object({
    id: z.string(),
    created_at: z.string().optional(),
    params: z.record(z.unknown()).optional(),
    view: BacktestRunViewSchema,
  })
  .passthrough();
export type BacktestRun = z.infer<typeof BacktestRunSchema>;

/** Parameter optimization (track T3): a grid sweep whose selected "best"
 * always ships with the overfitting guards (deflated Sharpe + PBO) and a
 * plain-language verdict, so a config that only looks good because it won a
 * many-trial search is visibly flagged, never silently promoted. */
export const OptimizationTrialSchema = z.object({
  params: z.record(z.union([z.string(), z.number()])),
  objective: z.number(),
});
export type OptimizationTrial = z.infer<typeof OptimizationTrialSchema>;

export const OptimizationViewSchema = z
  .object({
    strategy_id: z.string(),
    symbol: z.string(),
    timeframe: z.string(),
    duration: z.string(),
    objective: z.string(),
    n_trials: z.number(),
    param_grid: z.record(z.array(z.union([z.string(), z.number()]))),
    best_params: z.record(z.union([z.string(), z.number()])),
    best_objective: z.number(),
    deflated_sharpe: z.number().nullable().optional(),
    pbo: z.number().nullable().optional(),
    verdict: z.string(),
    guard_note: z.string().default(""),
    window: z.array(z.string()).nullable().optional(),
    window_truncated: z.boolean().optional(),
    trials: z.array(OptimizationTrialSchema).default([]),
  })
  .passthrough();
export type OptimizationView = z.infer<typeof OptimizationViewSchema>;

export const OptimizationSchema = z
  .object({
    id: z.string(),
    created_at: z.string().optional(),
    type: z.string().optional(),
    status: z.string().optional(),
    params: z.record(z.unknown()).optional(),
    view: OptimizationViewSchema,
  })
  .passthrough();
export type Optimization = z.infer<typeof OptimizationSchema>;

export const OptimizationListItemSchema = z
  .object({
    id: z.string(),
    created_at: z.string().nullable().optional(),
    type: z.string().nullable().optional(),
    symbol: z.string().nullable().optional(),
    timeframe: z.string().nullable().optional(),
    duration: z.string().nullable().optional(),
    strategy_id: z.string().nullable().optional(),
    objective: z.string().nullable().optional(),
    n_trials: z.number().nullable().optional(),
    status: z.string().nullable().optional(),
    best_objective: z.number().nullable().optional(),
    deflated_sharpe: z.number().nullable().optional(),
    pbo: z.number().nullable().optional(),
  })
  .passthrough();
export type OptimizationListItem = z.infer<typeof OptimizationListItemSchema>;
export const OptimizationsSchema = z.object({
  optimizations: z.array(OptimizationListItemSchema),
});

export const MemorySchema = z.object({
  counts: z.record(z.number()),
  recent_lessons: z.array(z.object({ kind: z.string(), text: z.string() })),
});
export type MemoryInsights = z.infer<typeof MemorySchema>;

export const AgentPerfSchema = z.record(
  z.object({
    votes: z.number(),
    avg_confidence: z.number(),
    scored: z.number(),
    hit_rate: z.number().nullable(),
  }),
);
export type AgentPerf = z.infer<typeof AgentPerfSchema>;

export const SymbolSpecSchema = z.object({
  tradeable: z.boolean().optional(),
  symbol: z.string(),
  vendor_symbol: z.string(),
  source: z.string(),
  timeframes: z.array(z.string()),
  live: z.boolean(),
});
export type SymbolSpec = z.infer<typeof SymbolSpecSchema>;
export const SymbolsSchema = z.array(SymbolSpecSchema);

export const BarSchema = z.object({
  time: z.number(),
  open: z.number(),
  high: z.number(),
  low: z.number(),
  close: z.number(),
  volume: z.number(),
});
export type Bar = z.infer<typeof BarSchema>;
export const BarsSchema = z.array(BarSchema);

/** AI decision history for the chart (chart Phase 1). Times are epoch
 * seconds, UNSNAPPED — the chart snaps them to its own bar array. */
export const ChartAnnotationsSchema = z.object({
  symbol: z.string(),
  cadence_seconds: z.number(),
  runs: z.array(
    z.object({
      run_id: z.string(),
      time: z.number().nullable(),
      action: z.string().nullable(),
      rejected_at: z.string().nullable(),
      rejected_reason: z.string().nullable().optional(),
      confidence: z.number().nullable(),
      market_regime: z.string().nullable(),
      geometry: z
        .object({
          entry: z.number(),
          stop: z.number().nullable(),
          invalidation: z.number().nullable(),
          take_profits: z.array(
            z.object({ price: z.number(), size_fraction: z.number() }),
          ),
          direction: z.enum(["long", "short"]),
        })
        .nullable(),
      span: z
        .object({
          from: z.number().nullable(),
          to: z.number().nullable(),
          reason: z.string(),
        })
        .nullable(),
    }),
  ),
  fills: z.array(
    z.object({
      run_id: z.string().nullable(),
      link: z.string(),
      entry_time: z.number().nullable(),
      entry_price: z.number().nullable(),
      closed_time: z.number().nullable(),
      fill_price: z.number().nullable(),
      pnl: z.number(),
      won: z.boolean().nullable(),
      mode: z.string(),
    }),
  ),
});
export type ChartAnnotations = z.infer<typeof ChartAnnotationsSchema>;

export const IndicatorSeriesSchema = z.record(
  z.object({
    params: z.record(z.unknown()),
    series: z.record(z.array(z.object({ time: z.number(), value: z.number() }))),
  }),
);
export type IndicatorSeries = z.infer<typeof IndicatorSeriesSchema>;

export const IntelSchema = z.object({
  as_of: z.string(),
  session: z.string(),
  metrics: z.array(
    z.object({
      name: z.string(),
      // data dictionary (trader review): human label + series note
      label: z.string().nullable().optional(),
      note: z.string().nullable().optional(),
      value: z.number(),
      unit: z.string().nullable(),
      as_of: z.string().nullable(),
      source: z.string().nullable(),
    }),
  ),
  headlines: z
    .array(
      z.object({
        symbol: z.string(),
        headline: z.string(),
        source: z.string(),
        published_at: z.string().nullable(),
        url: z.string().nullable(),
      }),
    )
    .optional(),
  missing_feeds: z.array(z.string()),
  unsubscribed_feeds: z.array(z.object({ name: z.string(), provider: z.string() })),
});
export type Intel = z.infer<typeof IntelSchema>;

const CalendarReleaseSchema = z.object({
  date: z.string(),
  release: z.string(),
  release_id: z.number().nullable().optional(),
  major: z.boolean().optional(),
  // agency publication time when fixed (BLS/BEA 08:30 ET, FOMC 14:00 ET);
  // honest nulls when unknown — the UI never guesses a time
  time_et: z.string().nullable().optional(),
  ts_utc: z.string().nullable().optional(),
});
export const VolumeProfileSchema = z.object({
  levels: z.array(z.object({ price: z.number(), volume: z.number() })),
  poc: z.number().nullable(),
  value_area_low: z.number().nullable(),
  value_area_high: z.number().nullable(),
  total_volume: z.number(),
});
export type VolumeProfile = z.infer<typeof VolumeProfileSchema>;

export const CalendarSchema = z.object({
  releases: z.array(CalendarReleaseSchema),
  next_major: CalendarReleaseSchema.extend({
    at: z.string(),
    seconds_until: z.number(),
  })
    .nullable()
    .optional(),
  missing_feeds: z.array(z.string()),
  as_of: z.string(),
});
export type Calendar = z.infer<typeof CalendarSchema>;
export type CalendarRelease = z.infer<typeof CalendarReleaseSchema>;

export const NotificationSchema = z.object({
  id: z.string(),
  severity: z.string(),
  event: z.string(),
  text: z.string(),
  time: z.string(),
  read: z.boolean(),
});
export type Notification = z.infer<typeof NotificationSchema>;
export const NotificationsSchema = z.object({
  notifications: z.array(NotificationSchema),
  unread: z.number(),
});

export const SavedViewSchema = z.object({
  name: z.string(),
  path: z.string(),
});
export type SavedView = z.infer<typeof SavedViewSchema>;

export const PrefsSchema = z.object({
  theme: z.string(),
  operator_label: z.string().optional(),
  default_symbol: z.string(),
  layouts: z.record(z.unknown()),
  views: z.array(SavedViewSchema).default([]),
  muted_events: z.array(z.string()).default([]),
  version: z.number(),
}).passthrough(); // round-trips must preserve fields this client predates
export type Prefs = z.infer<typeof PrefsSchema>;

export const CorrelationsSchema = z.object({
  window: z.number(),
  used_days: z.number(),
  symbols: z.array(z.string()),
  matrix: z.record(z.record(z.number())),
  missing: z.array(z.string()),
  as_of: z.string(),
});
export type Correlations = z.infer<typeof CorrelationsSchema>;

export const WatchlistSchema = z.object({
  name: z.string(),
  symbols: z.array(z.string()),
});
export type Watchlist = z.infer<typeof WatchlistSchema>;
export const WatchlistsSchema = z.array(WatchlistSchema);
