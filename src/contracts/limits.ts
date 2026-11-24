// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The engineering bounds the modules share, in one place. User-facing limits (what a question or an agent
 * may use) are resolved from settings (config/limits.ts) and passed to their consumers; the bounds below
 * are engineering: defined once here, used where they apply, not set by users.
 *
 * A bound only one module's own work uses (how many questions the history keeps, how much of a table the
 * terminal shows) stays with that module, as do definitions of what is computed or shown (statistics
 * windows, the observation window, formats, layout).
 */
/** Requests to services: how long one may take. */
export const REQUEST_MS = {
  tauric: 30_000,
  polymarket: 10_000,
  /** Yahoo, every request including its cookie set-up and the answer's body. */
  yahoo: 30_000,
  /** The model server's model list, asked once for the context window. */
  modelProbe: 5_000,
  /** OpenAI's sign-in endpoints. */
  signIn: 30_000,
  /** The check for a newer release, made in the background. */
  updateCheck: 3_000,
  /** `tradingagents update`: reading the listing and downloading the release, and the new file's first start. */
  updateDownload: 600_000,
  updateStart: 30_000,
  /** A Bun runtime package downloaded to build a release. */
  runtimeDownload: 300_000,
} as const;

/** Bytes of one answer read from Tauric or Polymarket; a longer answer is the source being unavailable. */
export const ANSWER_BYTES = 16_777_216;

/** Model steps and their output. */
export const MODEL = {
  /** Waits before retrying a step that failed before anything of it arrived. */
  retryMs: [1_000, 2_000],
  /** Output a main agent or sub-agent step may write: reasoning comes first, and the answer must still fit. */
  stepOutputTokens: 32_768,
  /** Output assumed for a step whose spec sets no limit, when fitting it into the context window. */
  defaultOutputTokens: 8_192,
  /** Output the final answer step may write once a cap is reached. */
  finalOutputTokens: 16_384,
  /** Time the final answer step may take once a time limit is reached. */
  finalGraceMs: 120_000,
  /** The context window assumed when the server does not report one. */
  fallbackContextWindow: 32_768,
  /** A request the model sends nothing on for this long has stalled (any stream activity counts). */
  stallMs: 600_000,
} as const;

/** Tool calls. */
export const CALLS = {
  /** Calls of one step run at most this many at once, and a step may ask for at most so many. */
  atOnce: 4,
  perStep: 16,
  /** Data calls at once across a turn's runs, the main agent's and its sub-agents' together. */
  turnDataCalls: 6,
  /** Characters of a tool's result the model reads; tools write within the text budget. */
  resultChars: 12_000,
  /** Intraday bars one price_history page asks for: the most the source serves at once. */
  intradayBars: 100,
  /** Pages of 25 companies a sector screen reads at most: 500 companies, the largest sector. */
  screenPages: 20,
  textChars: 10_000,
  /** Characters of a brief to a sub-agent. */
  briefChars: 4_000,
  /** The most an agent's title (what its row shows) may hold. */
  agentTitleChars: 60,
  /** Recorded results one brief may hand on whole. */
  briefRecords: 8,
  /** How long the end of a turn waits for its sub-agents to stop once cancelled. */
  subagentsStopMs: 10_000,
  /** Markets of one event a prediction-market answer lists at most; results of one search page. */
  marketsPerEvent: 3,
  marketSearchPage: 20,
  /** Characters of one long field (a profile's description) shown, and kept free beside a filing's text. */
  longFieldChars: 1_500,
  sectionHeadroomChars: 1_500,
  /** Candidates named for an ambiguous symbol, and series offered for a name that is not certain. */
  symbolCandidates: 10,
  seriesCandidates: 5,
  /** Instruments a search names, and a currency pair's reference rates read at once (publication days). */
  instrumentMatches: 10,
  referenceRates: 100,
} as const;

/** Fitting conversations into the context window. */
export const CONTEXT = {
  /** Characters per token when estimating a request before the model has measured one. */
  charsPerToken: 2,
  /**
   * Characters per token when counting what eliding saved from a measured request: as many as prose
   * takes, so the saving is never overstated.
   */
  savedCharsPerToken: 4,
  /** Tokens kept free beside the request and its output. */
  marginTokens: 2_048,
  /** A result shorter than this is not worth setting aside. */
  minElidedChars: 400,
  /** Compaction: the summary's output, the time it may take, and the characters of a call's arguments shown. */
  summaryTokens: 8_192,
  summaryMs: 120_000,
  argumentChars: 300,
  /** Characters kept free beside a compaction's transcript, and cut beyond a text's excess when shortening it. */
  transcriptSlackChars: 64,
  shortenSlackChars: 100,
  /** After the server says a request was too long, the share of the window the retry assumes. */
  retryWindowShare: 0.8,
} as const;

/** Memory: notes, recall and decisions. */
export const MEMORY = {
  noteChars: 300,
  /** A recorded decision's fields. */
  instrumentChars: 20,
  horizonChars: 60,
  thesisChars: 1_200,
  notesInContext: 40,
  notesContextChars: 4_000,
  recallSame: 5,
  recallOther: 3,
  recallChars: 6_000,
  settlementsPerRecall: 3,
  lessonTokens: 1_024,
  lessonMs: 60_000,
  /** Days after a decision that unreadable prices are retried before the observation is given up. */
  giveUpDays: 45,
  /** Days after the exit session that a gap in the prices is waited for before the settlement is given up. */
  gapPatienceDays: 30,
  appendWaitMs: 10_000,
  /** How often a held memory file is tried again while waiting for it. */
  appendPollMs: 50,
} as const;

/** Copying sessions to Tauric. */
export const SYNC = {
  /** Bytes sent in one append; a single line larger than this stops sync for the session. */
  chunkBytes: 1_000_000,
  retryMs: [2_000, 10_000, 60_000],
  drainMs: 10_000,
  /** After cancelling, how long a close waits for the work to stop before it lets go. */
  stopWaitMs: 5_000,
  /** Pages of 100 read to list the account's sessions; the newest of those are shown. */
  listedPages: 5,
} as const;

/** Recorded tool results (evidence) and how a session keeps them. */
export const EVIDENCE = {
  /** A record's payload above this many bytes of JSON stays on this computer: its record and preview sync. */
  recordBytes: 1_048_576,
  /** Payload bytes a session syncs; records past it stay on this computer too. */
  sessionBytes: 16 * 1_048_576,
  /** The longest line a record is written as: a payload that does not fit is split across lines. */
  lineBytes: SYNC.chunkBytes - 4_096,
  /** The preview kept with a record, from its rendered text. */
  previewChars: 600,
} as const;

/** ChatGPT sign-in. */
export const SIGN_IN = {
  /** Renew when the access token has less than this left (seconds). */
  refreshMarginSeconds: 300,
  /** After OpenAI could not renew, the wait before trying again (seconds). */
  retryAfterSeconds: 60,
  /** Time to wait for another process renewing the same sign-in. */
  lockWaitMs: 30_000,
  /** Time a person has to finish signing in in the browser. */
  browserMs: 600_000,
  /** The life assumed for an access token whose answer gives none, and the clock difference allowed (seconds). */
  assumedTokenSeconds: 3_600,
  clockLeewaySeconds: 5,
  /** How often the sign-in's lock is tried again while another process holds it. */
  lockPollMs: 100,
  /** Time the browser's last answer has to be written before the sign-in's connections are closed. */
  callbackCloseMs: 1_000,
} as const;

/**
 * Keys: the fewest characters a stored key has, and the fewest a secret has to be scrubbed from text
 * (lower, as a caller outside the settings may pass a shorter one).
 */
export const KEYS = { minChars: 8, scrubMinChars: 4 } as const;

/**
 * Evals: the judge's answer budget, and how much of a turn's tool results it reads: each result whole, as the
 * model read it (a figure it cannot see, it would call unsupported), all of them shared within a total that
 * holds a full analysis (about 150k tokens).
 */
export const EVALS = {
  judgeOutputTokens: 8_192,
  judgeResultChars: CALLS.resultChars,
  judgeResultsChars: 600_000,
} as const;

/** A skill's bundled file is read when it is text of at most this many bytes. */
export const SKILL_FILE_BYTES = 262_144;

/** Agent files: the steps an agent may take when its file says none, and the most it may say. */
export const AGENT_FILE_STEPS = { default: 15, max: 30 } as const;

/** The check for a newer release: at most once a day, with a bounded answer. */
export const UPDATES = {
  checkEveryMs: 86_400_000,
  /** The latest release's description. */
  answerBytes: 1_048_576,
  /** The most `tradingagents update` downloads: the executable, and SHA256SUMS. */
  executableBytes: 536_870_912,
  sumsBytes: 65_536,
} as const;

/** The interactive app: how long a stopping turn has before a further Ctrl+C leaves without it. */
export const APP = {
  leaveGraceMs: 2_000,
  /** How long after a setup step ends a paste is dropped: the rest of one that began with its Enter. */
  pasteQuietMs: 250,
  /** How often the spinner moves (and running rows' times are redrawn). */
  spinnerMs: 80,
  /** The most one clipboard write through the terminal (OSC 52) carries, encoded, as terminals cap it. */
  clipboardTerminalBytes: 100_000,
  /** How long the platform's clipboard tool has to take the text. */
  clipboardToolMs: 2_000,
} as const;

/** Sessions: how many are listed, and the turns of a resumed one shown again. */
export const SESSIONS = {
  listed: 50,
  replayTurns: 20,
  /** Bytes read of a session file to list it without reading it all. */
  headBytes: 8_192,
} as const;

// User-facing limits ---------------------------------------------------------------------------

/**
 * What a question and its agents may use. Nothing but the step guards is set by default: a question
 * runs until it is answered or the person stops it. Settings (config.json `limits`, then `--limit`
 * flags) override field by field.
 */
export type Limits = {
  /** The whole question: the main agent's steps, and the turn's tokens and time (sub-agents included). */
  question: { steps: number; tokens?: number; timeMs?: number };
  /** Per agent, by name: its steps (its file's by default), tokens and time. */
  agents: Record<string, { steps?: number; tokens?: number; timeMs?: number }>;
  /** Sub-agent runs one question may start; unlimited unless set. */
  subagentsPerQuestion?: number;
  /** Output one request may write, and the final answer after a cap: guards against a model that loops. */
  output: { stepTokens: number; finalTokens: number };
  /** How long a model request may send nothing before it counts as stalled. */
  modelStallMs: number;
};

export const DEFAULT_LIMITS: Limits = {
  question: { steps: 30 },
  agents: {},
  output: { stepTokens: MODEL.stepOutputTokens, finalTokens: MODEL.finalOutputTokens },
  modelStallMs: MODEL.stallMs,
};

/** An agent's name, as agent files write it. */
export const AGENT_NAME_PATTERN = /^[a-z][a-z0-9_-]{1,39}$/;

/** Of a question's time limit, what is kept for its final answer: the grace period, or a quarter of it. */
export function questionReserve(limits: Limits): number {
  return Math.floor(Math.min(MODEL.finalGraceMs, (limits.question.timeMs ?? 0) / 4));
}

/** Sector screens: a fiscal year this far from the sector's usual end is marked; years of lengths further apart are not compared. */
export const SCREEN = { offCalendarDays: 183, lengthDays: 30 } as const;

/** Portfolio tools: the most holdings one call takes, and how far weights may sum from 1 before a note says so. */
export const PORTFOLIO = {
  holdings: 20,
  weightSumTolerance: 1e-9,
  /** A portfolio variance at or below this fraction of its holdings' own (weighted) variances is 0. */
  varianceTolerance: 1e-12,
  /** Efficient-frontier points one optimization gives at most. */
  frontierPoints: 10,
} as const;

/**
 * The portfolio optimizer's iterations: an active-set solve stops when no held weight's multiplier is
 * wrong by more than the tolerance (relative), or at its cap; risk parity stops when no weight moves by
 * more than the tolerance; a one-dimensional search (golden section, bisection, doubling) takes at most
 * a fixed number of steps. The frontier's high end is reached when its return is within the end
 * tolerance of the spread of mean returns. Risk parity's shares of variance are equal within the share
 * tolerance.
 */
export const OPTIMIZER = {
  activeSetIterations: 1_000,
  riskParitySweeps: 10_000,
  tolerance: 1e-13,
  searchSteps: 60,
  endTolerance: 1e-10,
  shareTolerance: 1e-8,
} as const;

/**
 * The indicators tool: indicators one call computes and the longest period it takes; per line, the
 * crossings of each kind and the last values its result lists (the rest is in its data).
 */
export const INDICATORS = { perCall: 6, maxPeriod: 250, events: 10, tail: 10 } as const;
