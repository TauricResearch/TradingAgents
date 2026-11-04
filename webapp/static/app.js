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
  refreshArchive: document.getElementById("refresh-archive"),
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

async function loadOptions() {
  els.serverState.textContent = "connecting";
  try {
    const data = await api("/api/options");
    state.options = data;
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
    await updateProviderUi();
    els.serverState.textContent = "local";
    els.serverState.className = "pill pill-completed";
    showFormError("");
  } catch (error) {
    els.serverState.textContent = "offline";
    els.serverState.className = "pill pill-failed";
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

  // Detach from whatever was being polled, so a request for a run that is
  // about to be replaced cannot report "lost the run" over this form's error.
  stopPolling();
  state.runId = null;

  els.start.disabled = true;
  els.start.textContent = "Starting…";
  try {
    const run = await api("/api/runs", { method: "POST", body: JSON.stringify(payload) });
    state.runId = run.id;
    state.lastMessageKey = "";
    state.lastAgentKey = "";
    els.runEmpty.hidden = true;
    els.runView.hidden = false;
    els.cancel.hidden = false;
    renderRun(run);
    startPolling();
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

function renderReport(run) {
  const links = [];
  if (run.report_available) {
    links.push(`<a href="/api/runs/${run.id}/report" target="_blank" rel="noopener">Open HTML report</a>`);
    links.push(`<a href="/api/runs/${run.id}/report.md" target="_blank" rel="noopener">Markdown</a>`);
  }
  els.reportLinks.innerHTML = links.join("");

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
      const left = document.createElement("span");
      left.className = "run-list-title";
      left.textContent = `${run.ticker} · ${run.analysis_date}`;
      const right = document.createElement("span");
      setPill(right, run.status);
      li.append(left, right);
      const open = () => {
        state.runId = run.id;
        state.lastMessageKey = "";
        state.lastAgentKey = "";
        els.runEmpty.hidden = true;
        els.runView.hidden = false;
        els.cancel.hidden = run.status !== "running";
        renderRun(run);
        if (run.status === "running") startPolling();
        else stopPolling();
      };
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
