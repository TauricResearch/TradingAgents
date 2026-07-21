// Hand-rolled pub/sub store. The run-event reducer is idempotent (it mutates
// `live` in place, but replaying any event prefix always converges to the
// same state, so a full SSE replay on a fresh page load is safe).

export const SECTION_ORDER = [
  'market_report',
  'sentiment_report',
  'news_report',
  'fundamentals_report',
  'investment_plan',
  'trader_investment_plan',
  'final_trade_decision',
];

export const SECTION_TITLES = {
  market_report: 'Market Analysis',
  sentiment_report: 'Social Sentiment',
  news_report: 'News Analysis',
  fundamentals_report: 'Fundamentals Analysis',
  investment_plan: 'Research Team Decision',
  trader_investment_plan: 'Trading Team Plan',
  final_trade_decision: 'Portfolio Management Decision',
};

export const TEAM_ORDER = [
  'Analyst Team',
  'Research Team',
  'Trading Team',
  'Risk Management',
  'Portfolio Management',
];

export function emptyLiveRun() {
  return {
    runId: null,
    state: null, // running | done | failed | cancelled
    ticker: null,
    date: null,
    startedAt: null,
    decision: null,
    error: null,
    agents: {}, // name -> {team, status}
    sections: {}, // section key -> markdown
    toolCalls: [], // {name, argsPreview}
    messages: [], // {agent, preview}
    stats: { elapsed: 0, llm_calls: 0, tool_calls: 0 },
  };
}

const MAX_FEED_ITEMS = 200;

// Pure reducer for one SSE event; mutates and returns `live`.
export function reduceRunEvent(live, type, data) {
  switch (type) {
    case 'run_status':
      live.runId = data.run_id ?? live.runId;
      live.state = data.state ?? live.state;
      live.ticker = data.ticker ?? live.ticker;
      live.date = data.date ?? live.date;
      live.startedAt = data.started_at ?? live.startedAt;
      break;
    case 'agent_status':
      live.agents[data.agent] = { team: data.team, status: data.status };
      break;
    case 'report_section':
      live.sections[data.section] = data.markdown;
      break;
    case 'tool_call':
      live.toolCalls.push({ name: data.name, argsPreview: data.args_preview });
      if (live.toolCalls.length > MAX_FEED_ITEMS) live.toolCalls.shift();
      break;
    case 'message':
      live.messages.push({ agent: data.agent, preview: data.preview });
      if (live.messages.length > MAX_FEED_ITEMS) live.messages.shift();
      break;
    case 'stats':
      live.stats = {
        elapsed: data.elapsed ?? live.stats.elapsed,
        llm_calls: data.llm_calls ?? live.stats.llm_calls,
        tool_calls: data.tool_calls ?? live.stats.tool_calls,
      };
      break;
    case 'done':
      live.state = 'done';
      live.decision = data.result ? data.result.decision : null;
      break;
    case 'error':
      live.state = 'failed';
      live.error = data;
      break;
    case 'cancelled':
      live.state = 'cancelled';
      break;
    default:
      break;
  }
  return live;
}

export function createStore() {
  const state = {
    providers: [],
    config: {},
    lastUsed: {},
    runs: [],
    activeRun: null,
    live: emptyLiveRun(),
    report: null, // {ticker, date, sections, complete_report, manifest}
  };
  const listeners = new Set();

  function notify(event) {
    listeners.forEach((fn) => fn(event, state));
  }

  return {
    state,
    subscribe(fn) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
    set(key, value) {
      state[key] = value;
      notify({ type: 'set', key });
    },
    resetLive(runId) {
      state.live = emptyLiveRun();
      state.live.runId = runId;
      notify({ type: 'live-reset' });
    },
    applyRunEvent(type, data) {
      reduceRunEvent(state.live, type, data);
      notify({ type: 'run-event', eventType: type, data });
    },
  };
}
