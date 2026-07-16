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
      .object({ stage: z.string().nullable().optional() })
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

export const BacktestSchema = z
  .object({
    status: z.string().optional(),
    report: z.record(z.number()).optional(),
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
      value: z.number(),
      unit: z.string().nullable(),
      as_of: z.string().nullable(),
      source: z.string().nullable(),
    }),
  ),
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
