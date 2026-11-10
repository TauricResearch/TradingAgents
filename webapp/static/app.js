/* TradingAgents web console: form wiring, run polling and report display.
   Plain browser JavaScript, no framework and no external requests.
   Everything the model wrote is rendered as text, never as HTML. */

const els = {
  form: document.getElementById("run-form"),
  ticker: document.getElementById("ticker"),
  tickerHint: document.getElementById("ticker-hint"),
  date: document.getElementById("analysis-date"),
  assetType: document.getElementById("asset-type"),
  analysts: document.getElementById("analysts"),
  depth: document.getElementById("research-depth"),
  depthHint: document.getElementById("depth-hint"),
  language: document.getElementById("output-language"),
  provider: document.getElementById("llm-provider"),
  providerHint: document.getElementById("provider-hint"),
  backendUrlField: document.getElementById("backend-url-field"),
  backendUrl: document.getElementById("backend-url"),
  quickModel: document.getElementById("quick-model"),
  quickModelCustom: document.getElementById("quick-model-custom"),
  deepModel: document.getElementById("deep-model"),
  deepModelCustom: document.getElementById("deep-model-custom"),
  googleThinking: document.getElementById("google-thinking"),
  openaiEffort: document.getElementById("openai-effort"),
  anthropicEffort: document.getElementById("anthropic-effort"),
  checkpoint: document.getElementById("checkpoint"),
  saveReport: document.getElementById("save-report"),
  saveHtml: document.getElementById("save-html"),
  portfolio: document.getElementById("portfolio"),
  formError: document.getElementById("form-error"),
  start: document.getElementById("start"),
  cancel: document.getElementById("cancel"),
  serverState: document.getElementById("server-state"),
  appVersion: document.getElementById("app-version"),
  refreshOptions: document.getElementById("refresh-options"),

  runEmpty: document.getElementById("run-empty"),
  runView: document.getElementById("run-view"),
  runStatus: document.getElementById("run-status"),
  runElapsed: document.getElementById("run-elapsed"),
  runPhase: document.getElementById("run-phase"),
  agentsCount: document.getElementById("agents-count"),
  agentsBar: document.getElementById("agents-bar"),
  reportsCount: document.getElementById("reports-count"),
  reportsBar: document.getElementById("reports-bar"),
  runNote: document.getElementById("run-note"),
  runError: document.getElementById("run-error"),
  runStats: document.getElementById("run-stats"),
  agentsBody: document.getElementById("agents-body"),
  messageList: document.getElementById("message-list"),
  reportLinks: document.getElementById("report-links"),
  reportContent: document.getElementById("report-content"),
  runList: document.getElementById("run-list"),

  archiveList: document.getElementById("archive-list"),
  archiveEmpty: document.getElementById("archive-empty"),
  archiveView: document.getElementById("archive-view"),
  archiveTitleLine: document.getElementById("archive-title-line"),
  archiveMeta: document.getElementById("archive-meta"),
  archiveLinks: document.getElementById("archive-links"),
  archiveContent: document.getElementById("archive-content"),
  archiveDelete: document.getElementById("archive-delete"),
  archiveRerun: document.getElementById("archive-rerun"),
  archiveCompare: document.getElementById("archive-compare"),
  compareView: document.getElementById("compare-view"),
  compareTitle: document.getElementById("compare-title"),
  compareGrid: document.getElementById("compare-grid"),
  compareClose: document.getElementById("compare-close"),
  refreshArchive: document.getElementById("refresh-archive"),

  reportChart: document.getElementById("report-chart"),

  // Backtest panel
  backtestPanel: document.querySelector('[data-mode-panel="backtest"]'),
  backtestForm: document.getElementById("backtest-form"),
  btTickers: document.getElementById("bt-tickers"),
  btStart: document.getElementById("bt-start"),
  btEnd: document.getElementById("bt-end"),
  btEvery: document.getElementById("bt-every"),
  btAsset: document.getElementById("bt-asset"),
  btAnalysts: document.getElementById("bt-analysts"),
  btPortfolio: document.getElementById("bt-portfolio"),
  btError: document.getElementById("backtest-error"),
  btStartBtn: document.getElementById("bt-start-btn"),
  btCancel: document.getElementById("bt-cancel"),
  btView: document.getElementById("backtest-view"),
  btPhase: document.getElementById("backtest-phase"),
  btCellsCount: document.getElementById("bt-cells-count"),
  btCellsBar: document.getElementById("bt-cells-bar"),
  btNote: document.getElementById("backtest-note"),
  btErrorView: document.getElementById("backtest-error-view"),
  btSummary: document.getElementById("backtest-summary"),
  btFailures: document.getElementById("backtest-failures"),
  btStatus: document.getElementById("backtest-status"),
  btRefresh: document.getElementById("bt-refresh"),
  btList: document.getElementById("bt-list"),
  btListEmpty: document.getElementById("bt-list-empty"),

  // Decision log panel
  memoryPanel: document.querySelector('[data-mode-panel="memory"]'),
  memoryRefresh: document.getElementById("memory-refresh"),
  memoryPath: document.getElementById("memory-path"),
  memoryEmpty: document.getElementById("memory-empty"),
  memoryBody: document.getElementById("memory-body"),
  memoryDetail: document.getElementById("memory-detail"),
  memoryDetailTitle: document.getElementById("memory-detail-title"),
  memoryDecision: document.getElementById("memory-decision"),
  memoryReflection: document.getElementById("memory-reflection"),
  memoryReflectionSection: document.getElementById("memory-reflection-section"),
  memoryClose: document.getElementById("memory-close"),
  settleBtn: document.getElementById("settle-btn"),
  settleStatus: document.getElementById("settle-status"),
  settleResult: document.getElementById("settle-result"),
};

const state = {
  options: null,
  runId: null,
  polling: null,
  providers: new Map(),
  analystsByAsset: new Map(),
  lastMessageKey: "",
  lastAgentKey: "",
  archiveId: null,
  archiveReport: null,
  mode: "analyze",
  backtestId: null,
  backtestPolling: null,
  settlePolling: null,
  chartToken: 0,
};

const AGENT_TEAMS = [
  ["Analyst Team", ["Market Analyst", "Sentiment Analyst", "News Analyst", "Fundamentals Analyst"]],
  ["Research Team", ["Bull Researcher", "Bear Researcher", "Research Manager"]],
  ["Trading Team", ["Trader"]],
  ["Risk Management", ["Aggressive Analyst", "Neutral Analyst", "Conservative Analyst"]],
  ["Portfolio Management", ["Portfolio Manager"]],
];

const REPORT_TITLES = {
  market_report: "Market Analyst",
  sentiment_report: "Sentiment Analyst",
  news_report: "News Analyst",
  fundamentals_report: "Fundamentals Analyst",
  investment_plan: "Research Manager",
  trader_investment_plan: "Trader",
  final_trade_decision: "Portfolio Manager",
};

/* ---------------------------------------------------------------- helpers -- */

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const text = await response.text();
  const body = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const detail = body && body.detail ? body.detail : `request failed (${response.status})`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return body;
}

function option(value, label, selected = false) {
  const node = document.createElement("option");
  node.value = value;
  node.textContent = label;
  if (selected) node.selected = true;
  return node;
}

function setPill(node, status) {
  node.className = `pill pill-${
    ["running", "completed", "failed", "cancelled"].includes(status) ? status : "idle"
  }`;
  node.textContent = status;
}

function seconds(value) {
  if (value === null || value === undefined) return "";
  const whole = Math.floor(value);
  return `${String(Math.floor(whole / 60)).padStart(2, "0")}:${String(whole % 60).padStart(2, "0")}`;
}

function showFormError(message) {
  els.formError.textContent = message;
  els.formError.hidden = !message;
}

/* A provider needs a key when it has a key variable that is not set, and its
   credentials are not a sign-in. Local runtimes and generic endpoints are
   key-optional, so nothing is reported for them. */
function pNeedsKey(provider) {
  return Boolean(provider.api_key_env) && !provider.key_present &&
    !provider.signed_in && !provider.key_optional;
}

/* ------------------------------------------------------- options on load -- */

const FORM_MEMORY_KEY = "tradingagents-web-form";

/* The form answers worth offering again after a reload. Everything restored is
   re-checked against what the server offers, so a stale value cannot select a
   provider or model that no longer exists. */
const REMEMBERED = ["research_depth", "output_language", "llm_provider", "quick_think_llm",
  "deep_think_llm", "backend_url", "google_thinking_level", "openai_reasoning_effort",
  "anthropic_effort", "checkpoint", "save_report", "save_html", "portfolio"];

function saveFormMemory() {
  try {
    const memory = {};
    for (const key of REMEMBERED) {
      const node = els[key];
      if (!node) continue;
      memory[key] = node.type === "checkbox" ? node.checked : node.value;
    }
    localStorage.setItem(FORM_MEMORY_KEY, JSON.stringify(memory));
  } catch { /* storage may be unavailable; the defaults still work */ }
}

function loadFormMemory() {
  try {
    return JSON.parse(localStorage.getItem(FORM_MEMORY_KEY) || "{}");
  } catch {
    return {};
  }
}

function applyFormMemory() {
  const memory = loadFormMemory();
  if (memory.research_depth) {
    const depth = String(memory.research_depth);
    if ([...els.depth.options].some((o) => o.value === depth)) els.depth.value = depth;
  }
  if (memory.output_language) {
    const lang = [...els.language.options].some((o) => o.value === memory.output_language);
    if (lang) els.language.value = memory.output_language;
  }
  if (memory.llm_provider && state.providers.has(memory.llm_provider)) {
    els.provider.value = memory.llm_provider;
  }
  for (const key of ["google_thinking_level", "openai_reasoning_effort", "anthropic_effort"]) {
    if (memory[key]) els[key].value = memory[key];
  }
  for (const key of ["checkpoint", "save_report", "save_html"]) {
    if (typeof memory[key] === "boolean") els[key].checked = memory[key];
  }
  if (typeof memory.portfolio === "string") els.portfolio.value = memory.portfolio;
  els.saveHtml.disabled = !els.saveReport.checked;
  // Models are filled per provider; restore after the menus exist.
  restoreModels(memory);
  updateDepthHint();
}

function restoreModels(memory) {
  for (const [select, custom, key] of [
    [els.quickModel, els.quickModelCustom, "quick_think_llm"],
    [els.deepModel, els.deepModelCustom, "deep_think_llm"],
  ]) {
    const value = memory[key];
    if (!value) continue;
    const listed = [...select.options].some((o) => o.value === value);
    if (listed) {
      select.value = value;
      syncCustomVisibility(select, custom);
    } else if (value !== "custom") {
      // A model the catalog no longer lists is still offered, as a custom ID.
      select.hidden = true;
      custom.hidden = false;
      custom.value = value;
    }
  }
}

async function loadOptions() {
  els.serverState.textContent = "connecting";
  try {
    const data = await api("/api/options");
    state.options = data;
    els.appVersion.textContent = `v${data.version}`;
    els.appVersion.title = `TradingAgents ${data.version}, served by this process`;
    state.providers = new Map(data.providers.map((p) => [p.key, p]));

    els.date.value = data.defaults.today;
    els.date.max = data.defaults.today;

    els.depth.replaceChildren(
      ...data.depths.map((d) => option(String(d.value), `${d.label} (${d.value})`,
        d.value === data.defaults.research_depth))
    );
    updateDepthHint();

    els.language.replaceChildren(
      ...data.languages.map((l) => option(
        l.value,
        l.label,
        l.value === data.defaults.output_language
      ))
    );

    els.provider.replaceChildren(
      ...data.providers.map((p) => option(
        p.key,
        // Only say a key is missing when the provider actually needs one: a
        // local runtime, Bedrock and every signed-in plan have no key variable.
        `${p.label}${pNeedsKey(p) ? " · key not set" : ""}`,
        p.key === data.defaults.llm_provider
      ))
    );

    renderAnalysts(data.analysts, new Set(data.default_analysts));
    applyFormMemory();
    await updateProviderUi();
    els.serverState.textContent = "local";
    els.serverState.className = "pill pill-completed";
    showFormError("");
  } catch (error) {
    els.serverState.textContent = "offline";
    els.serverState.className = "pill pill-failed";
    els.appVersion.textContent = "v?";
    showFormError(`Could not load the options: ${error.message}`);
  }
}

function renderAnalysts(analysts, checked) {
  els.analysts.replaceChildren(
    ...analysts.map((analyst) => {
      const wrapper = document.createElement("label");
      wrapper.className = "check";
      wrapper.title = analyst.hint || "";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.value = analyst.key;
      input.checked = checked.has(analyst.key);
      const text = document.createElement("span");
      text.textContent = analyst.label;
      wrapper.append(input, text);
      return wrapper;
    })
  );
}

function updateDepthHint() {
  const chosen = state.options.depths.find((d) => String(d.value) === els.depth.value);
  els.depthHint.textContent = chosen ? chosen.detail : "";
}

/* --------------------------------------------------------- provider/models -- */

function fillModels(select, custom, mode) {
  const provider = els.provider.value;
  const entries = (state.models && state.models[mode]) || [];
  select.replaceChildren(
    ...entries.map((m) => option(m.value, m.label, false))
  );
  const isCustom = entries.length === 0 || entries.every((m) => m.value === "custom");
  select.hidden = isCustom;
  custom.hidden = !isCustom;
  if (isCustom) custom.placeholder = mode === "quick" ? "quick model ID" : "deep model ID";
}

function syncCustomVisibility(select, custom) {
  if (select.hidden) return;
  custom.hidden = select.value !== "custom";
}

async function updateProviderUi() {
  const provider = els.provider.value;
  const info = state.providers.get(provider);
  if (!info) return;

  const status = [];
  if (info.signed_in) status.push("uses your signed-in plan");
  else if (info.api_key_env) {
    status.push(info.key_present
      ? `${info.api_key_env} is set`
      : `${info.api_key_env} is not set; exports from your shell or .env are read`);
  }
  if (info.key_optional) status.push("an API key is optional");
  els.providerHint.textContent = status.join(" · ");

  els.backendUrlField.hidden = !info.needs_url;
  if (info.needs_url) els.backendUrl.value = "";
  else els.backendUrl.value = info.default_url || "";

  try {
    state.models = await api(`/api/models/${encodeURIComponent(provider)}`);
  } catch (error) {
    state.models = { quick: [], deep: [] };
  }
  fillModels(els.quickModel, els.quickModelCustom, "quick");
  fillModels(els.deepModel, els.deepModelCustom, "deep");
  syncCustomVisibility(els.quickModel, els.quickModelCustom);
  syncCustomVisibility(els.deepModel, els.deepModelCustom);
}

/* ---------------------------------------------------------- ticker typing -- */

let detectTimer = null;
function scheduleDetect() {
  clearTimeout(detectTimer);
  detectTimer = setTimeout(detectTicker, 250);
}

async function detectTicker() {
  const value = els.ticker.value.trim();
  if (!value) {
    els.tickerHint.textContent = "Enter a ticker, e.g. SPY, 0700.HK, BTC-USD.";
    return;
  }
  try {
    const info = await api(`/api/detect?ticker=${encodeURIComponent(value)}`);
    if (!info.valid) {
      els.tickerHint.textContent = "Not a ticker symbol the run accepts.";
      return;
    }
    els.tickerHint.textContent = `${info.canonical} · ${info.asset_type}`;
    els.assetType.value = info.asset_type;
    applyAssetAnalysts(info.asset_type, info.available_analysts);
  } catch (error) {
    els.tickerHint.textContent = error.message;
  }
}

function applyAssetAnalysts(assetType, available) {
  if (!available) return;
  const allowed = new Set(available);
  for (const input of els.analysts.querySelectorAll("input[type=checkbox]")) {
    const ok = allowed.has(input.value);
    input.disabled = !ok;
    if (!ok) input.checked = false;
  }
  const anyChecked = [...els.analysts.querySelectorAll("input:checked")].length > 0;
  if (!anyChecked) {
    for (const input of els.analysts.querySelectorAll("input[type=checkbox]")) {
      if (!input.disabled) { input.checked = true; break; }
    }
  }
  if (assetType) els.assetType.value = assetType;
}

/* ------------------------------------------------------------- starting -- */

function collectPayload() {
  const analysts = [...els.analysts.querySelectorAll("input:checked")]
    .filter((input) => !input.disabled)
    .map((input) => input.value);

  let portfolio = null;
  const raw = els.portfolio.value.trim();
  if (raw) {
    try {
      portfolio = JSON.parse(raw);
    } catch (error) {
      throw new Error(`The portfolio is not valid JSON: ${error.message}`);
    }
  }

  if (!analysts.length) throw new Error("Select at least one analyst.");

  const quick = els.quickModel.hidden ? els.quickModelCustom.value.trim() : els.quickModel.value;
  const deep = els.deepModel.hidden ? els.deepModelCustom.value.trim() : els.deepModel.value;
  if (quick === "custom" || deep === "custom") {
    throw new Error("Type the model ID for the tier(s) set to Custom model ID.");
  }

  return {
    ticker: els.ticker.value.trim(),
    analysis_date: els.date.value,
    analysts,
    asset_type: els.assetType.value,
    research_depth: Number(els.depth.value),
    llm_provider: els.provider.value,
    backend_url: els.backendUrlField.hidden ? null : (els.backendUrl.value.trim() || null),
    quick_think_llm: quick || null,
    deep_think_llm: deep || null,
    output_language: els.language.value,
    google_thinking_level: els.googleThinking.value || null,
    openai_reasoning_effort: els.openaiEffort.value || null,
    anthropic_effort: els.anthropicEffort.value || null,
    checkpoint: els.checkpoint.checked ? true : null,
    save: els.saveReport.checked,
    html: els.saveHtml.checked,
    portfolio,
  };
}

async function startRun(event) {
  event.preventDefault();
  showFormError("");
  let payload;
  try {
    payload = collectPayload();
  } catch (error) {
    showFormError(error.message);
    return;
  }
  saveFormMemory();

  // Detach from whatever was being polled, so a request for a run that is
  // about to be replaced cannot report "lost the run" over this form's error.
  stopPolling();
  state.runId = null;

  els.start.disabled = true;
  els.start.textContent = "Starting…";
  try {
    const run = await api("/api/runs", { method: "POST", body: JSON.stringify(payload) });
    openRun(run);
    await refreshHistory();
  } catch (error) {
    showFormError(error.message);
  } finally {
    els.start.disabled = false;
    els.start.textContent = "Run analysis";
  }
}

async function cancelRun() {
  if (!state.runId) return;
  els.cancel.disabled = true;
  try {
    await api(`/api/runs/${state.runId}/cancel`, { method: "POST" });
  } catch (error) {
    showFormError(error.message);
  } finally {
    els.cancel.disabled = false;
  }
}

/* -------------------------------------------------------------- polling -- */

function openRun(run) {
  /* One selected run at a time: the panel shows it, polling follows it. Other
     runs keep going server-side and stay in History to switch back to. */
  state.runId = run.id;
  state.lastMessageKey = "";
  state.lastAgentKey = "";
  els.runEmpty.hidden = true;
  els.runView.hidden = false;
  els.cancel.hidden = run.status !== "running";
  renderRun(run);
  if (run.status === "running") startPolling();
  else stopPolling();
}

function startPolling() {
  stopPolling();
  state.polling = setInterval(poll, 1200);
}

function stopPolling() {
  if (state.polling) clearInterval(state.polling);
  state.polling = null;
}

async function poll() {
  if (!state.runId) return;
  try {
    const run = await api(`/api/runs/${state.runId}`);
    renderRun(run);
    if (run.status !== "running") {
      stopPolling();
      els.cancel.hidden = true;
      await refreshHistory();
      // A finished run writes its report to disk, so the archive gained an entry.
      refreshArchive();
    }
  } catch (error) {
    stopPolling();
    showFormError(`Lost the run: ${error.message}`);
  }
}

/* ------------------------------------------------------------- rendering -- */

function renderRun(run) {
  setPill(els.runStatus, run.status);
  els.runElapsed.textContent = run.elapsed !== null ? seconds(run.elapsed) : "";
  els.runPhase.textContent = run.phase || "";

  const progress = run.progress || {};
  const agentsTotal = progress.agents_total || 0;
  const reportsTotal = progress.reports_total || 0;
  els.agentsCount.textContent = `${progress.agents_completed || 0}/${agentsTotal}`;
  els.reportsCount.textContent = `${progress.reports_completed || 0}/${reportsTotal}`;
  els.agentsBar.style.width = agentsTotal
    ? `${Math.round((100 * (progress.agents_completed || 0)) / agentsTotal)}%` : "0";
  els.reportsBar.style.width = reportsTotal
    ? `${Math.round((100 * (progress.reports_completed || 0)) / reportsTotal)}%` : "0";

  const note = run.note || "";
  els.runNote.textContent = note;
  els.runNote.hidden = !note;
  els.runError.textContent = run.error || "";
  els.runError.hidden = !run.error;

  renderStats(run);
  renderAgents(run.agent_status || {});
  renderMessages(run);
  renderReport(run);
}

function renderStats(run) {
  const stats = run.stats || {};
  const parts = [];
  const add = (label, value) => parts.push(`<span>${label} <b>${value}</b></span>`);
  if (stats.llm_calls !== undefined) add("LLM calls", stats.llm_calls);
  if (stats.tool_calls !== undefined) add("Tools", stats.tool_calls);
  if (stats.tokens_in || stats.tokens_out) {
    add("Tokens", `${stats.tokens_in}↑ ${stats.tokens_out}↓`);
  }
  if (run.rating) add("Rating", run.rating);
  if (run.wall_time_summary) add("Wall time", run.wall_time_summary.replace("Analyst wall time: ", ""));
  els.runStats.innerHTML = parts.join("");
}

function renderAgents(statuses) {
  const rows = [];
  for (const [team, agents] of AGENT_TEAMS) {
    const active = agents.filter((agent) => agent in statuses);
    active.forEach((agent, index) => {
      const status = statuses[agent] || "pending";
      rows.push(
        `<tr><td class="team">${index === 0 ? team : ""}</td>` +
        `<td>${agent}</td>` +
        `<td><span class="status status-${status}">${status.replace("_", " ")}</span></td></tr>`
      );
    });
  }
  const key = rows.join("|");
  if (key !== state.lastAgentKey) {
    state.lastAgentKey = key;
    els.agentsBody.innerHTML = rows.join("");
  }
}

function renderMessages(run) {
  const messages = (run.messages || []).slice().reverse();
  const tools = (run.tool_calls || []).slice().reverse();
  const items = [
    ...messages.map((m) => ({ time: m.time, type: m.type, content: m.content })),
    ...tools.map((t) => ({ time: t.time, type: "Tool", content: `${t.name}: ${t.args}` })),
  ].sort((a, b) => (a.time < b.time ? 1 : -1)).slice(0, 40);

  const key = items.map((i) => `${i.time}|${i.type}|${i.content}`).join("§");
  if (key === state.lastMessageKey) return;
  state.lastMessageKey = key;

  els.messageList.replaceChildren(...items.map((item) => {
    const li = document.createElement("li");
    const time = document.createElement("span");
    time.className = "time";
    time.textContent = item.time;
    const type = document.createElement("span");
    type.className = `type type-${item.type}`;
    type.textContent = item.type;
    const content = document.createElement("span");
    content.className = "content";
    const text = String(item.content || "");
    content.textContent = text.length > 400 ? `${text.slice(0, 397)}…` : text;
    li.append(time, type, content);
    return li;
  }));
}

function reportDownloadName(ticker, date) {
  return `${ticker}_${date}_report.md`;
}

function renderReport(run) {
  const links = [];
  if (run.report_available) {
    links.push(`<a href="/api/runs/${run.id}/report" target="_blank" rel="noopener">Open HTML report</a>`);
    links.push(`<a href="/api/runs/${run.id}/report.md" target="_blank" rel="noopener">Markdown</a>`);
    // A real download: the browser saves the file instead of opening a tab.
    links.push(`<a class="download" href="/api/runs/${run.id}/report.md?download=1" download="${reportDownloadName(run.ticker, run.analysis_date)}">⤓ Download markdown</a>`);
  }
  els.reportLinks.innerHTML = links.join("");
  loadChart(run.ticker, run.analysis_date);

  // The server renders each section from the same markdown into safe HTML
  // (raw HTML escaped, images off), so the report reads as formatted text here
  // exactly as it does in the terminal and in the saved page.
  const sections = run.report_sections || {};
  const rendered = run.report_sections_html || {};
  const blocks = Object.keys(REPORT_TITLES)
    .filter((key) => sections[key])
    .map((key) => {
      const section = document.createElement("div");
      section.className = "report-section";
      const title = document.createElement("h3");
      title.textContent = REPORT_TITLES[key];
      const body = document.createElement("div");
      body.className = "markdown";
      if (rendered[key]) {
        body.innerHTML = rendered[key];
      } else {
        const plain = document.createElement("pre");
        plain.textContent = Array.isArray(sections[key])
          ? sections[key].join("\n") : String(sections[key]);
        body.append(plain);
      }
      section.append(title, body);
      return section;
    });

  if (!blocks.length) {
    const waiting = document.createElement("p");
    waiting.className = "empty";
    waiting.textContent = "No report sections yet.";
    els.reportContent.replaceChildren(waiting);
  } else {
    els.reportContent.replaceChildren(...blocks);
  }
}

/* ------------------------------------------------------------ price chart -- */

/* The chart is drawn as inline SVG from the closes the server fetched through
   the same vendor path the agents use — no external requests, no library. */
async function loadChart(ticker, analysisDate) {
  const token = ++state.chartToken;
  if (!ticker || !analysisDate) {
    els.reportChart.hidden = true;
    return;
  }
  try {
    const data = await api(`/api/chart/${encodeURIComponent(ticker)}?date=${encodeURIComponent(analysisDate)}`);
    if (token !== state.chartToken) return;  // a slower load must not overwrite a newer run
    drawChart(data);
  } catch {
    // A chart the server cannot price is not a failed report: show nothing.
    if (token === state.chartToken) els.reportChart.hidden = true;
  }
}

function drawChart(data) {
  const closes = data.closes || [];
  if (closes.length < 2) {
    els.reportChart.hidden = true;
    return;
  }
  const width = 640, height = 120, pad = 6;
  const values = closes.map((c) => c.close);
  const min = Math.min(...values), max = Math.max(...values);
  const span = max - min || 1;
  const x = (i) => pad + (i * (width - 2 * pad)) / (closes.length - 1);
  const y = (v) => pad + (1 - (v - min) / span) * (height - 2 * pad);
  const line = closes.map((c, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(c.close).toFixed(1)}`).join("");

  // The analysis date's bar, so the chart reads against the day the run priced.
  const markIndex = closes.findIndex((c) => c.date >= data.analysis_date);
  const mark = markIndex > 0 ? closes[markIndex] : null;

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("class", "chart");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", `Daily closes for ${data.ticker} around ${data.analysis_date}`);

  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", line);
  path.setAttribute("class", "chart-line");
  svg.append(path);

  if (mark) {
    const marker = document.createElementNS("http://www.w3.org/2000/svg", "line");
    marker.setAttribute("x1", x(markIndex)); marker.setAttribute("x2", x(markIndex));
    marker.setAttribute("y1", pad); marker.setAttribute("y2", height - pad);
    marker.setAttribute("class", "chart-mark");
    svg.append(marker);
  }

  const caption = document.createElement("p");
  caption.className = "chart-caption mono subtle";
  caption.textContent = `${data.ticker} closes · ${closes[0].date} → ${closes[closes.length - 1].date}`
    + (mark ? ` · analysis date ${mark.date}: ${mark.close}` : "");

  els.reportChart.replaceChildren(svg, caption);
  els.reportChart.hidden = false;
}

async function refreshHistory() {
  try {
    const data = await api("/api/runs");
    if (!data.runs.length) {
      els.runList.replaceChildren();
      return;
    }
    els.runList.replaceChildren(...data.runs.map((run) => {
      const li = document.createElement("li");
      li.tabIndex = 0;
      li.classList.toggle("is-active", run.id === state.runId);
      const left = document.createElement("span");
      left.className = "run-list-title";
      left.textContent = `${run.ticker} · ${run.analysis_date}`;
      const right = document.createElement("span");
      right.className = "run-list-meta";
      setPill(right, run.status);
      li.append(left, right);
      const open = () => openRun(run);
      li.addEventListener("click", open);
      li.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); open(); }
      });
      return li;
    }));
  } catch (error) {
    /* history is a convenience: its failure must not disturb the run view */
  }
}

/* --------------------------------------------------------------- archive -- */

function archiveLabel(report) {
  const parts = [report.ticker];
  if (report.analysis_date) parts.push(report.analysis_date);
  return parts.join(" · ");
}

async function openArchiveReport(report) {
  state.archiveId = report.id;
  state.archiveReport = report;
  for (const li of els.archiveList.querySelectorAll("li")) {
    li.classList.toggle("is-active", li.dataset.id === report.id);
  }
  els.archiveView.hidden = false;
  els.archiveTitleLine.textContent = archiveLabel(report);
  els.archiveMeta.textContent = [
    report.rating ? `rating ${report.rating}` : null,
    report.source === "run" ? "unfinished run, kept as written" : null,
  ].filter(Boolean).join(" · ");

  // Only a finished report has a consolidated page and markdown file on disk.
  const links = [];
  if (report.has_html) {
    links.push(`<a href="/api/archive/${report.id}/report" target="_blank" rel="noopener">Open HTML report</a>`);
  }
  if (report.source === "report") {
    links.push(`<a href="/api/archive/${report.id}/report.md" target="_blank" rel="noopener">Markdown</a>`);
    // A real download: the browser saves the file instead of opening a tab.
    links.push(`<a class="download" href="/api/archive/${report.id}/report.md?download=1" download="${reportDownloadName(report.ticker, report.analysis_date)}">⤓ Download markdown</a>`);
  }
  els.archiveLinks.innerHTML = links.join("");

  const placeholder = document.createElement("p");
  placeholder.className = "empty";
  placeholder.textContent = "Loading…";
  els.archiveContent.replaceChildren(placeholder);

  try {
    const data = await api(`/api/archive/${encodeURI(report.id)}/sections`);
    if (state.archiveId !== report.id) return;  // a slower load must not overwrite a newer pick
    const blocks = data.sections.map((section) => {
      const wrapper = document.createElement("div");
      wrapper.className = "report-section";
      const title = document.createElement("h3");
      title.textContent = section.title;
      const body = document.createElement("div");
      body.className = "markdown";
      // The server escaped raw HTML and turned images off, so this is safe
      // to insert, exactly like a live run's sections.
      body.innerHTML = section.html;
      wrapper.append(title, body);
      return wrapper;
    });
    if (!blocks.length) {
      const empty = document.createElement("p");
      empty.className = "empty";
      empty.textContent = "This report has no readable sections.";
      els.archiveContent.replaceChildren(empty);
    } else {
      els.archiveContent.replaceChildren(...blocks);
    }
  } catch (error) {
    const failed = document.createElement("div");
    failed.className = "alert alert-error";
    failed.textContent = `This report could not be read: ${error.message}`;
    els.archiveContent.replaceChildren(failed);
  }
}

async function deleteArchiveReport() {
  const report = state.archiveReport;
  if (!report) return;
  const label = archiveLabel(report);
  // Deleting is permanent and removes files from disk, so it is asked about
  // plainly and the answer is not assumed.
  const yes = window.confirm(
    `Delete the saved report for ${label}?\n\n` +
    "This permanently removes the report files from disk and cannot be undone."
  );
  if (!yes) return;

  els.archiveDelete.disabled = true;
  els.archiveDelete.textContent = "Deleting…";
  try {
    await api(`/api/archive/${encodeURI(report.id)}?confirm=true`, { method: "DELETE" });
    state.archiveReport = null;
    state.archiveId = null;
    els.archiveView.hidden = true;
    await refreshArchive();
  } catch (error) {
    window.alert(`The report could not be deleted: ${error.message}`);
  } finally {
    els.archiveDelete.disabled = false;
    els.archiveDelete.textContent = "Delete report";
  }
}

/* ------------------------------------------------- re-run from an archive -- */

async function rerunFromArchive() {
  const report = state.archiveReport;
  if (!report) return;
  els.archiveRerun.disabled = true;
  try {
    const settings = await api(`/api/archive/${encodeURI(report.id)}/rerun`);
    setMode("analyze");
    els.ticker.value = settings.ticker || "";
    if (settings.analysis_date) els.date.value = settings.analysis_date;
    if (settings.analysts && settings.analysts.length) {
      for (const input of els.analysts.querySelectorAll("input[type=checkbox]")) {
        input.checked = settings.analysts.includes(input.value);
      }
    }
    if (settings.research_depth) {
      const depth = String(settings.research_depth);
      if ([...els.depth.options].some((o) => o.value === depth)) els.depth.value = depth;
      updateDepthHint();
    }
    // The header names models as text; offer them as custom IDs to confirm or change.
    for (const [select, custom, value] of [
      [els.quickModel, els.quickModelCustom, settings.quick_think_llm],
      [els.deepModel, els.deepModelCustom, settings.deep_think_llm],
    ]) {
      if (!value) continue;
      const listed = [...select.options].some((o) => o.value === value);
      if (listed) { select.value = value; select.hidden = false; custom.hidden = true; }
      else { select.hidden = true; custom.hidden = false; custom.value = value; }
    }
    scheduleDetect();
    els.ticker.focus();
    showFormError("");
  } catch (error) {
    window.alert(`The report's settings could not be read: ${error.message}`);
  } finally {
    els.archiveRerun.disabled = false;
  }
}

/* ------------------------------------------------------- compare reports -- */

async function openCompare() {
  const report = state.archiveReport;
  if (!report) return;
  // Only reports of the same ticker make a comparison worth reading.
  const candidates = (await api("/api/archive")).reports
    .filter((r) => r.ticker === report.ticker && r.id !== report.id);
  if (!candidates.length) {
    window.alert(`No other saved report for ${report.ticker} to compare with.`);
    return;
  }
  const options = candidates
    .map((r) => `${archiveLabel(r)} [${r.id}]`)
    .join("\n");
  const pick = window.prompt(
    `Compare ${archiveLabel(report)} with which report of ${report.ticker}?\n\n${options}\n\n` +
    "Paste the id in brackets:",
  );
  if (!pick) return;
  const match = candidates.find((r) => pick.trim() === r.id || pick.includes(`[${r.id}]`));
  if (!match) {
    window.alert("That id does not name a listed report.");
    return;
  }
  await renderCompare(report, match);
}

async function renderCompare(left, right) {
  els.archiveView.hidden = true;
  els.compareView.hidden = false;
  els.compareTitle.textContent = `${archiveLabel(left)}  ↔  ${archiveLabel(right)}`;
  const placeholder = document.createElement("p");
  placeholder.className = "empty";
  placeholder.textContent = "Loading…";
  els.compareGrid.replaceChildren(placeholder);
  try {
    const data = await api(`/api/archive/compare?left=${encodeURI(left.id)}&right=${encodeURI(right.id)}`);
    const blocks = data.sections.map((section) => {
      const row = document.createElement("div");
      row.className = "compare-row";
      const title = document.createElement("h3");
      title.textContent = section.title;
      row.append(title);
      for (const [side, html] of [["left", section.left_html], ["right", section.right_html]]) {
        const cell = document.createElement("div");
        cell.className = `compare-cell compare-${side} markdown`;
        if (html) cell.innerHTML = html;  // server-rendered safe HTML, as the report panel
        else {
          const empty = document.createElement("p");
          empty.className = "empty";
          empty.textContent = "Not in this report.";
          cell.append(empty);
        }
        row.append(cell);
      }
      return row;
    });
    els.compareGrid.replaceChildren(...blocks);
  } catch (error) {
    const failed = document.createElement("div");
    failed.className = "alert alert-error";
    failed.textContent = `The reports could not be compared: ${error.message}`;
    els.compareGrid.replaceChildren(failed);
  }
}

async function refreshArchive() {
  try {
    const data = await api("/api/archive");
    els.archiveList.replaceChildren();
    els.archiveEmpty.hidden = data.reports.length > 0;
    // A report removed elsewhere (or just deleted here) must not stay open on
    // screen showing content that no longer exists.
    if (state.archiveId && !data.reports.some((r) => r.id === state.archiveId)) {
      state.archiveId = null;
      state.archiveReport = null;
      els.archiveView.hidden = true;
    }
    if (!data.reports.length) {
      els.archiveView.hidden = true;
      return;
    }
    els.archiveList.replaceChildren(...data.reports.map((report) => {
      const li = document.createElement("li");
      li.tabIndex = 0;
      li.dataset.id = report.id;

      const left = document.createElement("span");
      left.className = "run-list-title";
      left.textContent = archiveLabel(report);

      const right = document.createElement("span");
      right.className = "run-list-meta";
      if (report.rating) {
        const rating = document.createElement("span");
        rating.className = "pill pill-idle";
        rating.textContent = report.rating;
        right.append(rating);
      }
      const count = document.createElement("span");
      count.className = "run-list-date";
      count.textContent = `${report.section_titles.length} section${report.section_titles.length === 1 ? "" : "s"}`;
      right.append(count);

      li.append(left, right);
      const open = () => { openArchiveReport(report); };
      li.addEventListener("click", open);
      li.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); open(); }
      });
      return li;
    }));
  } catch (error) {
    /* the archive is a convenience: its failure must not disturb the run view */
  }
}

/* --------------------------------------------------------------- wiring -- */

/* ---------------------------------------------------------- mode switching -- */

function setMode(mode) {
  state.mode = mode;
  for (const tab of document.querySelectorAll(".mode-tab")) {
    const active = tab.dataset.mode === mode;
    tab.classList.toggle("is-active", active);
    tab.setAttribute("aria-selected", String(active));
  }
  for (const panel of document.querySelectorAll("[data-mode-panel]")) {
    panel.hidden = panel.dataset.modePanel !== mode;
  }
  if (mode === "backtest") refreshBacktests();
  if (mode === "memory") refreshMemory();
}

for (const tab of document.querySelectorAll(".mode-tab")) {
  tab.addEventListener("click", () => setMode(tab.dataset.mode));
}

/* ------------------------------------------------------------- backtest -- */

function showBacktestError(message) {
  els.btError.textContent = message;
  els.btError.hidden = !message;
}

function renderBacktest(sweep) {
  setPill(els.btStatus, sweep.status);
  els.btPhase.textContent = sweep.phase || "";
  const total = sweep.cells_total || 0;
  const done = sweep.cells_run || 0;
  els.btCellsCount.textContent = `${done}/${total}` + (sweep.skipped ? ` · ${sweep.skipped} skipped` : "");
  els.btCellsBar.style.width = total ? `${Math.round((100 * done) / total)}%` : "0";

  els.btNote.textContent = sweep.note || "";
  els.btNote.hidden = !sweep.note;
  els.btErrorView.textContent = sweep.error || "";
  els.btErrorView.hidden = !sweep.error;

  const summary = sweep.summary;
  if (summary) {
    const parts = [];
    parts.push(`<span>Resolved <b>${summary.resolved}</b></span>`);
    parts.push(`<span>Pending <b>${summary.pending}</b></span>`);
    if (summary.unscored) parts.push(`<span>Unscored <b>${summary.unscored}</b></span>`);
    for (const row of summary.by_rating || []) {
      const hit = row.hit_rate === null || row.hit_rate === undefined
        ? "no direction" : `${Math.round(row.hit_rate * 100)}% hit`;
      parts.push(`<span>${row.rating} <b>n=${row.count}</b> · ${hit} · alpha ${(row.mean_alpha * 100).toFixed(1)}%</span>`);
    }
    if (summary.holding) parts.push(`<span>Window <b>${summary.holding}</b></span>`);
    els.btSummary.innerHTML = parts.join("");
    els.btSummary.hidden = false;
  } else {
    els.btSummary.hidden = true;
  }

  const failures = [...(sweep.failures || []), ...(sweep.settlement_failures || [])];
  if (failures.length) {
    const list = document.createElement("ul");
    for (const failure of failures.slice(0, 20)) {
      const li = document.createElement("li");
      li.textContent = failure.date
        ? `${failure.ticker} ${failure.date}: ${failure.reason}`
        : `${failure.ticker}: ${failure.reason}`;
      list.append(li);
    }
    els.btFailures.replaceChildren(list);
    els.btFailures.hidden = false;
  } else {
    els.btFailures.hidden = true;
  }

  els.btCancel.hidden = sweep.status !== "running";
}

function startBacktestPolling() {
  stopBacktestPolling();
  state.backtestPolling = setInterval(async () => {
    if (!state.backtestId) return stopBacktestPolling();
    try {
      const sweep = await api(`/api/backtests/${state.backtestId}`);
      renderBacktest(sweep);
      if (sweep.status !== "running") {
        stopBacktestPolling();
        refreshBacktests();
      }
    } catch {
      stopBacktestPolling();
    }
  }, 1500);
}

function stopBacktestPolling() {
  if (state.backtestPolling) clearInterval(state.backtestPolling);
  state.backtestPolling = null;
}

async function refreshBacktests() {
  try {
    const data = await api("/api/backtests");
    els.btListEmpty.hidden = data.backtests.length > 0;
    els.btList.replaceChildren(...data.backtests.map((sweep) => {
      const li = document.createElement("li");
      li.tabIndex = 0;
      li.classList.toggle("is-active", sweep.id === state.backtestId);
      const left = document.createElement("span");
      left.className = "run-list-title";
      left.textContent = `${sweep.tickers.join(", ")} · ${sweep.dates[0] || "?"} → ${sweep.dates[sweep.dates.length - 1] || "?"}`;
      const right = document.createElement("span");
      right.className = "run-list-meta";
      setPill(right, sweep.status);
      li.append(left, right);
      const open = () => {
        state.backtestId = sweep.id;
        els.btView.hidden = false;
        renderBacktest(sweep);
        if (sweep.status === "running") startBacktestPolling();
        else stopBacktestPolling();
      };
      li.addEventListener("click", open);
      li.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); open(); }
      });
      return li;
    }));
  } catch { /* the list is a convenience */ }
}

els.backtestForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  showBacktestError("");
  let portfolio = null;
  const raw = els.btPortfolio.value.trim();
  if (raw) {
    try { portfolio = JSON.parse(raw); }
    catch (error) { showBacktestError(`The portfolio is not valid JSON: ${error.message}`); return; }
  }
  const tickers = els.btTickers.value.split(",").map((t) => t.trim()).filter(Boolean);
  if (!tickers.length) { showBacktestError("Give at least one ticker."); return; }
  const analysts = els.btAnalysts.value.split(",").map((a) => a.trim()).filter(Boolean);
  els.btStartBtn.disabled = true;
  els.btStartBtn.textContent = "Starting…";
  try {
    const sweep = await api("/api/backtests", {
      method: "POST",
      body: JSON.stringify({
        tickers,
        start_date: els.btStart.value,
        end_date: els.btEnd.value,
        every_n_days: Math.max(1, Number(els.btEvery.value) || 7),
        analysts,
        asset_type: els.btAsset.value,
        portfolio,
      }),
    });
    state.backtestId = sweep.id;
    els.btView.hidden = false;
    renderBacktest(sweep);
    startBacktestPolling();
    refreshBacktests();
  } catch (error) {
    showBacktestError(error.message);
  } finally {
    els.btStartBtn.disabled = false;
    els.btStartBtn.textContent = "Run backtest";
  }
});

els.btCancel.addEventListener("click", async () => {
  if (!state.backtestId) return;
  els.btCancel.disabled = true;
  try {
    await api(`/api/backtests/${state.backtestId}/cancel`, { method: "POST" });
  } catch (error) {
    showBacktestError(error.message);
  } finally {
    els.btCancel.disabled = false;
  }
});

els.btRefresh.addEventListener("click", refreshBacktests);

/* ---------------------------------------------------------- decision log -- */

function renderMemory(data) {
  els.memoryPath.textContent = data.path || "";
  const entries = data.entries || [];
  els.memoryEmpty.hidden = entries.length > 0;
  els.memoryBody.replaceChildren(...entries.map((entry) => {
    const tr = document.createElement("tr");
    tr.tabIndex = 0;
    const cells = [
      entry.date, entry.ticker, entry.rating,
      entry.pending ? "—" : (entry.raw || "—"),
      entry.pending ? "—" : (entry.alpha || "—"),
      entry.holding || "—",
      entry.pending ? "pending" : "settled",
    ];
    cells.forEach((value, index) => {
      const td = document.createElement("td");
      td.textContent = value;
      if (index === 6) td.className = entry.pending ? "memory-pending" : "memory-settled";
      tr.append(td);
    });
    const open = () => openMemoryEntry(entry);
    tr.addEventListener("click", open);
    tr.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); open(); }
    });
    return tr;
  }));
}

function openMemoryEntry(entry) {
  els.memoryDetail.hidden = false;
  els.memoryDetailTitle.textContent = `${entry.ticker} · ${entry.date} · ${entry.rating}`;
  els.memoryDecision.innerHTML = "";
  els.memoryReflection.innerHTML = "";
  // The server renders the same markdown the reports use, so the detail reads
  // as formatted text; here the log's own text is shown as written.
  const decision = document.createElement("pre");
  decision.textContent = entry.decision || "(no decision text)";
  els.memoryDecision.append(decision);
  if (entry.reflection) {
    const reflection = document.createElement("pre");
    reflection.textContent = entry.reflection;
    els.memoryReflection.append(reflection);
    els.memoryReflectionSection.hidden = false;
  } else {
    els.memoryReflectionSection.hidden = true;
  }
  els.memoryDetail.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function refreshMemory() {
  try {
    renderMemory(await api("/api/memory"));
  } catch { /* the log is a convenience */ }
  pollSettleStatus();
}

function pollSettleStatus() {
  clearInterval(state.settlePolling);
  state.settlePolling = setInterval(async () => {
    try {
      const status = await api("/api/memory/settle/status");
      setPill(els.settleStatus, status.status === "running" ? "running" : "idle");
      els.settleStatus.textContent = status.status;
      if (status.status !== "running") {
        clearInterval(state.settlePolling);
        els.settleBtn.disabled = false;
        if (status.status === "completed") {
          const settled = status.settled || [];
          const failed = status.failed || [];
          els.settleResult.className = "alert alert-warn";
          els.settleResult.textContent = settled.length || failed.length
            ? `Settled ${settled.length} decision${settled.length === 1 ? "" : "s"}`
              + (failed.length ? `, ${failed.length} could not be settled` : "") + "."
            : "Nothing to settle: no pending decision's window has traded yet.";
          els.settleResult.hidden = false;
          refreshMemory();
        } else if (status.status === "failed") {
          els.settleResult.className = "alert alert-error";
          els.settleResult.textContent = `Settlement failed: ${status.error || "unknown error"}`;
          els.settleResult.hidden = false;
        }
      }
    } catch { clearInterval(state.settlePolling); }
  }, 1500);
}

els.settleBtn.addEventListener("click", async () => {
  els.settleBtn.disabled = true;
  els.settleResult.hidden = true;
  try {
    await api("/api/memory/settle", { method: "POST" });
    setPill(els.settleStatus, "running");
    els.settleStatus.textContent = "running";
    pollSettleStatus();
  } catch (error) {
    els.settleBtn.disabled = false;
    els.settleResult.className = "alert alert-error";
    els.settleResult.textContent = error.message;
    els.settleResult.hidden = false;
  }
});

els.memoryRefresh.addEventListener("click", refreshMemory);
els.memoryClose.addEventListener("click", () => { els.memoryDetail.hidden = true; });

els.form.addEventListener("submit", startRun);
els.cancel.addEventListener("click", cancelRun);
els.refreshOptions.addEventListener("click", loadOptions);
els.ticker.addEventListener("input", scheduleDetect);
els.assetType.addEventListener("change", () => {
  const asset = els.assetType.value;
  const available = state.options
    ? state.options.analysts.map((a) => a.key).filter((key) => asset !== "crypto" || key !== "fundamentals")
    : null;
  applyAssetAnalysts(asset, available);
});
els.depth.addEventListener("change", updateDepthHint);
els.provider.addEventListener("change", updateProviderUi);
els.quickModel.addEventListener("change", () => syncCustomVisibility(els.quickModel, els.quickModelCustom));
els.deepModel.addEventListener("change", () => syncCustomVisibility(els.deepModel, els.deepModelCustom));
els.saveReport.addEventListener("change", () => {
  els.saveHtml.disabled = !els.saveReport.checked;
});
els.refreshArchive.addEventListener("click", refreshArchive);
els.archiveDelete.addEventListener("click", deleteArchiveReport);
els.archiveRerun.addEventListener("click", rerunFromArchive);
els.archiveCompare.addEventListener("click", openCompare);
els.compareClose.addEventListener("click", () => {
  els.compareView.hidden = true;
  if (state.archiveId) els.archiveView.hidden = false;
});

// The form answers are remembered as they change, not only on submit, so a
// reload mid-thought keeps what was chosen.
for (const key of REMEMBERED) {
  const node = els[key];
  if (!node) continue;
  node.addEventListener(node.type === "checkbox" ? "change" : "change", saveFormMemory);
}

for (const tab of document.querySelectorAll(".tab")) {
  tab.addEventListener("click", () => {
    for (const other of document.querySelectorAll(".tab")) {
      const active = other === tab;
      other.classList.toggle("is-active", active);
      other.setAttribute("aria-selected", String(active));
    }
    for (const panel of document.querySelectorAll(".tab-body")) {
      panel.hidden = panel.dataset.panel !== tab.dataset.tab;
    }
  });
}

loadOptions();
scheduleDetect();
refreshHistory();
refreshArchive();
refreshBacktests();
setMode("analyze");
