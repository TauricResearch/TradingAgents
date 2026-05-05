"use strict";

const state = {
  currentRunId: null,
  currentRun: null,
  currentRunLoadMode: null,
  events: [],
  artifacts: [],
  decision: null,
  trace: null,
  selectedTraceNodeId: null,
  durationSamples: {},
  durationSampledRunIds: new Set(),
  priorRunMatches: [],
  priorLookupKey: null,
  priorLoadedRunId: null,
  priorLookupTimer: null,
  priorLookupSequence: 0,
  evaluations: [],
  polling: false,
  pollTimer: null,
  history: [],
  reports: [],
};

const el = {
  composerForm: document.getElementById("composer-form"),
  composerState: document.getElementById("composer-state"),
  tickerInput: document.getElementById("ticker-input"),
  tradeDateInput: document.getElementById("trade-date-input"),
  priorRunCard: document.getElementById("prior-run-card"),
  runIdInput: document.getElementById("run-id-input"),
  loadRunBtn: document.getElementById("load-run-btn"),
  pollToggleBtn: document.getElementById("poll-toggle-btn"),
  statusCard: document.getElementById("status-card"),
  eventsCard: document.getElementById("events-card"),
  decisionCard: document.getElementById("decision-card"),
  traceFlow: document.getElementById("trace-flow"),
  traceRuntime: document.getElementById("trace-runtime"),
  traceRuntimeText: document.getElementById("trace-runtime-text"),
  traceMiniLog: document.getElementById("trace-mini-log"),
  traceDetailTitle: document.getElementById("trace-detail-title"),
  traceDetailPayload: document.getElementById("trace-detail-payload"),
  evalModelInput: document.getElementById("eval-model-input"),
  runEvaluationBtn: document.getElementById("run-evaluation-btn"),
  evaluationState: document.getElementById("evaluation-state"),
  evaluationCard: document.getElementById("evaluation-card"),
  artifactsCard: document.getElementById("artifacts-card"),
  refreshReportsBtn: document.getElementById("refresh-reports-btn"),
  reportsCard: document.getElementById("reports-card"),
  historyCard: document.getElementById("history-card"),
  handoffPreview: document.getElementById("handoff-preview"),
  copyBtn: document.getElementById("copy-handoff-btn"),
  copyState: document.getElementById("copy-state"),
};

const HISTORY_KEY = "shadow_run_history_v1";
const DURATION_SAMPLES_KEY = "shadow_run_duration_samples_v1";
const TERMINAL_STATUSES = ["succeeded", "failed", "cancelled"];

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = String(value ?? "");
  return div.innerHTML;
}

async function fetchJson(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  let body = null;
  try {
    body = await response.json();
  } catch (_err) {
    body = null;
  }
  if (!response.ok) {
    const detail = body && body.detail ? String(body.detail) : `HTTP ${response.status}`;
    throw new Error(detail);
  }
  return body;
}

function setComposerState(text, cls = "muted") {
  el.composerState.className = `status-line ${cls}`;
  el.composerState.textContent = text;
}

function setCopyState(text, cls = "muted") {
  el.copyState.className = `status-line ${cls}`;
  el.copyState.textContent = text;
}

function setEvaluationState(text, cls = "muted") {
  el.evaluationState.className = `status-line ${cls}`;
  el.evaluationState.textContent = text;
}

function parseTimestamp(value) {
  const millis = Date.parse(value || "");
  return Number.isFinite(millis) ? millis : null;
}

function formatDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return "-";
  const rounded = Math.round(seconds);
  const minutes = Math.floor(rounded / 60);
  const rest = rounded % 60;
  if (minutes <= 0) return `${rest}s`;
  if (minutes < 60) return `${minutes}m ${String(rest).padStart(2, "0")}s`;
  const hours = Math.floor(minutes / 60);
  const minuteRest = minutes % 60;
  return `${hours}h ${String(minuteRest).padStart(2, "0")}m`;
}

function eventTime(eventType) {
  const event = state.events.find((evt) => evt.event_type === eventType);
  return event ? parseTimestamp(event.timestamp) : null;
}

function runSignature(run) {
  const analysts = (run && run.selected_analysts ? run.selected_analysts : []).slice().sort().join(",");
  return analysts || "unknown";
}

function loadModeLabel() {
  const labels = {
    queued: "new run",
    retrieved: "retrieved existing",
    loaded: "loaded by run id",
  };
  return labels[state.currentRunLoadMode] || "run";
}

function loadDurationSamples() {
  try {
    state.durationSamples = JSON.parse(localStorage.getItem(DURATION_SAMPLES_KEY) || "{}");
  } catch (_err) {
    state.durationSamples = {};
  }
}

function saveDurationSamples() {
  localStorage.setItem(DURATION_SAMPLES_KEY, JSON.stringify(state.durationSamples));
}

function recordDurationSample() {
  if (!state.currentRun || !TERMINAL_STATUSES.includes(state.currentRun.status)) return;
  if (state.durationSampledRunIds.has(state.currentRun.run_id)) return;
  const started = eventTime("running");
  const ended =
    eventTime("succeeded") || eventTime("failed") || eventTime("cancelled") || parseTimestamp(state.currentRun.updated_at);
  if (!started || !ended || ended <= started) return;
  state.durationSampledRunIds.add(state.currentRun.run_id);
  const signature = runSignature(state.currentRun);
  const sampleSeconds = Math.round((ended - started) / 1000);
  const samples = (state.durationSamples[signature] || []).filter((value) => Number.isFinite(value));
  state.durationSamples[signature] = [sampleSeconds, ...samples].slice(0, 12);
  saveDurationSamples();
}

function averageDurationForCurrentRun() {
  const samples = state.durationSamples[runSignature(state.currentRun)] || [];
  if (!samples.length) return null;
  return samples.reduce((sum, value) => sum + value, 0) / samples.length;
}

function activeRunElapsedSeconds() {
  const started = eventTime("running") || parseTimestamp(state.currentRun && state.currentRun.created_at);
  if (!started) return null;
  return Math.max(0, (Date.now() - started) / 1000);
}

function etaText() {
  if (!state.currentRun) return "No active run.";
  if (TERMINAL_STATUSES.includes(state.currentRun.status)) {
    const started = eventTime("running");
    const ended =
      eventTime("succeeded") || eventTime("failed") || eventTime("cancelled") || parseTimestamp(state.currentRun.updated_at);
    if (started && ended && ended > started) return `completed in ${formatDuration((ended - started) / 1000)}`;
    return "complete";
  }
  const elapsed = activeRunElapsedSeconds();
  const average = averageDurationForCurrentRun();
  if (!Number.isFinite(elapsed)) return "ETA learning: no start timestamp.";
  if (!Number.isFinite(average)) return `elapsed ${formatDuration(elapsed)}; ETA learning from completed runs.`;
  const remaining = Math.max(0, average - elapsed);
  return `elapsed ${formatDuration(elapsed)}; ETA ${formatDuration(remaining)} based on ${state.durationSamples[runSignature(state.currentRun)].length} similar run(s).`;
}

function renderTraceRuntime() {
  const run = state.currentRun;
  if (!run) {
    el.traceRuntime.className = "trace-runtime muted";
    el.traceRuntimeText.textContent = "No active run.";
    return;
  }
  const active = !TERMINAL_STATUSES.includes(run.status);
  el.traceRuntime.className = `trace-runtime ${active ? "active" : run.status === "failed" ? "error" : "muted"}`;
  el.traceRuntimeText.textContent = `${loadModeLabel()} · ${run.status} · ${etaText()}`;
}

function renderTraceMiniLog() {
  if (!state.currentRunId) {
    el.traceMiniLog.className = "trace-mini-log-body muted";
    el.traceMiniLog.textContent = "No events.";
    return;
  }
  const events = state.events.slice().sort((a, b) => b.sequence - a.sequence).slice(0, 8);
  if (!events.length) {
    el.traceMiniLog.className = "trace-mini-log-body muted";
    el.traceMiniLog.textContent = "No timeline events yet.";
    return;
  }
  el.traceMiniLog.className = "trace-mini-log-body";
  el.traceMiniLog.innerHTML = events
    .map((evt) => {
      const ts = parseTimestamp(evt.timestamp);
      const age = ts ? `${formatDuration((Date.now() - ts) / 1000)} ago` : "-";
      const payload = evt.payload || {};
      const note =
        evt.event_type === "stage_progress"
          ? `${payload.stage || "stage"} ${payload.status || ""}`.trim()
          : payload.error || payload.worker_id || (payload.result && payload.result.decision) || "";
      return `
        <div class="trace-mini-log-row">
          <span class="trace-mini-log-seq">#${escapeHtml(evt.sequence)}</span>
          <span class="trace-mini-log-event">${escapeHtml(evt.event_type)}${note ? ` · ${escapeHtml(note)}` : ""}</span>
          <span class="trace-mini-log-age">${escapeHtml(age)}</span>
        </div>
      `;
    })
    .join("");
}

function renderStatus() {
  if (!state.currentRun) {
    el.statusCard.className = "box muted";
    el.statusCard.textContent = "No run loaded.";
    return;
  }
  const run = state.currentRun;
  const statusClass = run.status === "failed" ? "error" : run.status === "succeeded" ? "ok" : "muted";
  el.statusCard.className = `box ${statusClass}`;
  el.statusCard.innerHTML = `
    <div><strong>Status:</strong> ${escapeHtml(run.status)}</div>
    <div><strong>Loaded as:</strong> ${escapeHtml(loadModeLabel())}</div>
    <div><strong>Run ID:</strong> <span class="mono">${escapeHtml(run.run_id)}</span></div>
    <div><strong>Ticker:</strong> ${escapeHtml(run.ticker)} | <strong>Date:</strong> ${escapeHtml(run.trade_date)}</div>
    <div><strong>Analysts:</strong> ${escapeHtml((run.selected_analysts || []).join(", "))}</div>
    <div><strong>Provider/Model:</strong> ${escapeHtml(run.provider || "-")} / ${escapeHtml(run.model_name || "-")}</div>
    <div><strong>Updated:</strong> ${escapeHtml(run.updated_at)}</div>
    ${run.error_message ? `<div class="error"><strong>Error:</strong> ${escapeHtml(run.error_message)}</div>` : ""}
  `;
}

function renderEvents() {
  if (!state.currentRunId) {
    el.eventsCard.className = "box muted";
    el.eventsCard.textContent = "No events yet.";
    return;
  }
  if (!state.events.length) {
    el.eventsCard.className = "box muted";
    el.eventsCard.textContent = "No timeline events available.";
    return;
  }
  el.eventsCard.className = "box";
  el.eventsCard.innerHTML = state.events
    .slice()
    .sort((a, b) => a.sequence - b.sequence)
    .map(
      (evt) => `
      <div class="event">
        <div><strong>#${escapeHtml(evt.sequence)}</strong> ${escapeHtml(evt.event_type)}</div>
        <div class="muted">${escapeHtml(evt.timestamp)}</div>
        <pre>${escapeHtml(JSON.stringify(evt.payload || {}, null, 2))}</pre>
      </div>
    `
    )
    .join("");
}

function renderDecision() {
  if (!state.currentRunId) {
    el.decisionCard.className = "box muted";
    el.decisionCard.textContent = "No decision loaded.";
    return;
  }
  const d = state.decision;
  if (!d || (!d.final_rating && !d.final_decision_markdown)) {
    el.decisionCard.className = "box muted";
    el.decisionCard.textContent = "Decision not available yet.";
    return;
  }
  const qualityClass =
    d.quality_status === "failed" ? "error" : d.quality_status === "passed" ? "ok" : "muted";
  const recommendationClass =
    d.recommendation_status === "invalid" ? "error" : d.recommendation_status === "valid" ? "ok" : "muted";
  const findings = (d.quality_findings || [])
    .map(
      (finding) => `
      <div class="event">
        <div><strong>${escapeHtml(finding.severity || "-")}</strong> ${escapeHtml(finding.code || "-")}</div>
        <div>${escapeHtml(finding.message || "")}</div>
        ${finding.evidence ? `<div class="mono">${escapeHtml(finding.evidence)}</div>` : ""}
      </div>
    `
    )
    .join("");
  const audit = d.recommendation_audit || {};
  const sourceSummary = d.source_summary || {};
  const directions = audit.directions || {};
  const citedSourceIds = sourceSummary.cited_source_ids || [];
  el.decisionCard.className = "box";
  el.decisionCard.innerHTML = `
    <div><strong>Final Rating:</strong> ${escapeHtml(d.final_rating || "-")}</div>
    <div><strong>Markdown Report:</strong> <a href="/v1/shadow-runs/${encodeURIComponent(state.currentRunId)}/report.md" target="_blank" rel="noreferrer">open report.md</a></div>
    <div class="${recommendationClass}"><strong>Recommendation Status:</strong> ${escapeHtml(d.recommendation_status || "not assessed")}${
      d.invalidated_by_quality_gate ? ` (original: ${escapeHtml(d.original_final_rating || "-")})` : ""
    }</div>
    <div><strong>Provider:</strong> ${escapeHtml(d.provider || "-")}</div>
    <div><strong>Deep/Quick Model:</strong> ${escapeHtml(d.deep_model || "-")} / ${escapeHtml(d.quick_model || "-")}</div>
    <div class="${qualityClass}"><strong>Quality:</strong> ${escapeHtml(d.quality_status || "not assessed")}</div>
    ${
      d.recommendation_audit
        ? `<div><strong>Recommendation Chain:</strong> ${escapeHtml(audit.alignment_status || "-")}</div>
           <div class="mono">research=${escapeHtml(audit.research_manager_rating || "-")} (${escapeHtml(directions.research_manager || "-")}) | trader=${escapeHtml(audit.trader_action || "-")} (${escapeHtml(directions.trader || "-")}) | final=${escapeHtml(audit.final_rating || "-")} (${escapeHtml(directions.portfolio_manager || "-")})</div>
           <div><strong>Reports:</strong> ${escapeHtml(audit.intermediate_report_count ?? "-")} | <strong>Source refs:</strong> ${escapeHtml(audit.explicit_source_reference ? "yes" : "no")} | <strong>Source IDs cited:</strong> ${escapeHtml(citedSourceIds.length)} | <strong>Raw tool outputs:</strong> ${escapeHtml(sourceSummary.raw_tool_output_count ?? "-")}</div>
           <div><strong>Scorecard:</strong> ${escapeHtml(audit.scorecard_suggested_rating || "-")} (${escapeHtml(audit.scorecard_suggested_direction || "-")}) | <strong>PM vs scorecard:</strong> ${escapeHtml(audit.rating_vs_scorecard || "-")}</div>`
        : ""
    }
    <div><strong>State Log:</strong> <span class="mono">${escapeHtml(d.state_log_dir || "-")}</span></div>
    <div><strong>Memory Log:</strong> <span class="mono">${escapeHtml(d.memory_log_path || "-")}</span></div>
    ${findings ? `<hr /><div><strong>Quality Findings</strong></div>${findings}` : ""}
    <hr />
    <pre>${escapeHtml(d.final_decision_markdown || "")}</pre>
  `;
}

function renderArtifacts() {
  if (!state.currentRunId) {
    el.artifactsCard.className = "box muted";
    el.artifactsCard.textContent = "No artifacts loaded.";
    return;
  }
  if (!state.artifacts.length) {
    el.artifactsCard.className = "box muted";
    el.artifactsCard.textContent = "No artifacts available yet.";
    return;
  }
  el.artifactsCard.className = "box";
  el.artifactsCard.innerHTML = state.artifacts
    .map(
      (a) => `
      <div class="artifact">
        <div><strong>${escapeHtml(a.kind)}</strong> (${escapeHtml(a.content_type)})</div>
        <div class="mono">${escapeHtml(a.uri)}</div>
        <div class="muted">${escapeHtml(a.bytes)} bytes | sha256 ${escapeHtml(a.sha256 || "-")}</div>
      </div>
    `
    )
    .join("");
}

function renderPriorRunLookup() {
  const ticker = el.tickerInput.value.trim().toUpperCase();
  const tradeDate = el.tradeDateInput.value.trim();
  if (!ticker || !tradeDate) {
    el.priorRunCard.className = "box muted";
    el.priorRunCard.textContent = "Enter ticker and trade date to check for a prior run.";
    return;
  }
  if (!state.priorRunMatches.length) {
    el.priorRunCard.className = "box muted";
    el.priorRunCard.textContent = `No prior run found for ${ticker} on ${tradeDate}.`;
    return;
  }
  el.priorRunCard.className = "box ok";
  el.priorRunCard.innerHTML = `
    <div><strong>Prior run surfaced:</strong> ${escapeHtml(ticker)} ${escapeHtml(tradeDate)}</div>
    <table class="data-table compact">
      <thead>
        <tr>
          <th>Run ID</th>
          <th>Status</th>
          <th>Analysts</th>
          <th>Updated</th>
        </tr>
      </thead>
      <tbody>
        ${state.priorRunMatches
          .map(
            (run) => `
          <tr>
            <td><button type="button" data-run-id="${escapeHtml(run.run_id)}">${escapeHtml(run.run_id)}</button></td>
            <td>${escapeHtml(run.status)}</td>
            <td>${escapeHtml((run.selected_analysts || []).join(", "))}</td>
            <td>${escapeHtml(run.updated_at)}</td>
          </tr>
        `
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function composerLookupKey() {
  const ticker = el.tickerInput.value.trim().toUpperCase();
  const tradeDate = el.tradeDateInput.value.trim();
  return ticker && tradeDate ? `${ticker}|${tradeDate}` : null;
}

function clearLoadedPriorRunIfComposerChanged() {
  if (!state.priorLoadedRunId || state.currentRunId !== state.priorLoadedRunId) return;
  stopPolling();
  state.currentRunId = null;
  state.currentRun = null;
  state.currentRunLoadMode = null;
  state.events = [];
  state.artifacts = [];
  state.decision = null;
  state.trace = null;
  state.selectedTraceNodeId = null;
  state.evaluations = [];
  el.runIdInput.value = "";
  renderStatus();
  renderEvents();
  renderDecision();
  renderTrace();
  renderEvaluations();
  renderArtifacts();
  renderHandoffPayload();
  setComposerState("Prior run cleared after ticker/date changed.", "muted");
}

function clearPriorRunLookupForComposerChange() {
  const nextKey = composerLookupKey();
  if (nextKey === state.priorLookupKey) return;
  state.priorLookupSequence += 1;
  state.priorLookupKey = nextKey;
  state.priorRunMatches = [];
  clearLoadedPriorRunIfComposerChanged();
  state.priorLoadedRunId = null;
  renderPriorRunLookup();
}

async function loadRunById(runId, { mode = "loaded", source = "manual" } = {}) {
  el.runIdInput.value = runId;
  state.currentRunId = runId;
  state.currentRunLoadMode = mode;
  state.priorLoadedRunId = source === "prior_lookup" ? runId : null;
  setComposerState(`Loading ${runId}...`, "muted");
  try {
    await refreshAll(runId);
    const prefix = source === "prior_lookup" ? "Surfaced prior run" : "Loaded";
    setComposerState(`${prefix} ${runId}`, mode === "retrieved" ? "muted" : "ok");
  } catch (err) {
    setComposerState(`Load failed: ${err.message}`, "error");
  }
}

async function lookupPriorRunForComposer({ autoLoad = true } = {}) {
  const ticker = el.tickerInput.value.trim().toUpperCase();
  const tradeDate = el.tradeDateInput.value.trim();
  const lookupKey = composerLookupKey();
  state.priorRunMatches = [];
  if (!ticker || !tradeDate) {
    state.priorLookupKey = lookupKey;
    renderPriorRunLookup();
    return;
  }
  state.priorLookupKey = lookupKey;
  const sequence = ++state.priorLookupSequence;
  el.priorRunCard.className = "box muted";
  el.priorRunCard.textContent = `Checking for prior ${ticker} run on ${tradeDate}...`;
  try {
    const query = new URLSearchParams({
      ticker,
      date_from: tradeDate,
      date_to: tradeDate,
      limit: "10",
      offset: "0",
    });
    const payload = await fetchJson(`/v1/shadow-runs?${query.toString()}`);
    if (sequence !== state.priorLookupSequence) return;
    state.priorRunMatches = payload.runs || [];
    renderPriorRunLookup();
    if (autoLoad && state.priorRunMatches.length) {
      const newestRun = state.priorRunMatches[0];
      if (newestRun.run_id && newestRun.run_id !== state.currentRunId) {
        await loadRunById(newestRun.run_id, { mode: "retrieved", source: "prior_lookup" });
      }
    }
  } catch (err) {
    if (sequence !== state.priorLookupSequence) return;
    el.priorRunCard.className = "box error";
    el.priorRunCard.textContent = `Prior run lookup failed: ${err.message}`;
  }
}

function schedulePriorRunLookup() {
  if (state.priorLookupTimer) {
    clearTimeout(state.priorLookupTimer);
  }
  clearPriorRunLookupForComposerChange();
  state.priorLookupTimer = setTimeout(() => {
    lookupPriorRunForComposer().catch((err) => {
      el.priorRunCard.className = "box error";
      el.priorRunCard.textContent = `Prior run lookup failed: ${err.message}`;
    });
  }, 300);
}

function renderReports() {
  if (!state.reports.length) {
    el.reportsCard.className = "box muted";
    el.reportsCard.textContent = "No generated reports yet.";
    return;
  }
  el.reportsCard.className = "box";
  el.reportsCard.innerHTML = `
    <table class="data-table">
      <thead>
        <tr>
          <th>Ticker</th>
          <th>Trade Date</th>
          <th>Run ID</th>
          <th>Size</th>
          <th>Updated</th>
          <th>Report</th>
        </tr>
      </thead>
      <tbody>
        ${state.reports
          .map(
            (report) => `
          <tr>
            <td>${escapeHtml(report.ticker)}</td>
            <td>${escapeHtml(report.trade_date)}</td>
            <td><button type="button" data-run-id="${escapeHtml(report.run_id)}">${escapeHtml(report.run_id)}</button></td>
            <td>${escapeHtml(report.bytes)} bytes</td>
            <td>${escapeHtml(report.updated_at)}</td>
            <td><a href="${escapeHtml(report.report_url)}" target="_blank" rel="noreferrer">open .md</a></td>
          </tr>
        `
          )
          .join("")}
      </tbody>
    </table>
  `;
}

async function refreshReports() {
  const payload = await fetchJson("/v1/reports?limit=100");
  state.reports = payload.reports || [];
  renderReports();
}

function renderEvaluations() {
  if (!state.currentRunId) {
    el.evaluationCard.className = "box muted";
    el.evaluationCard.textContent = "No run loaded.";
    return;
  }
  if (!state.evaluations.length) {
    el.evaluationCard.className = "box muted";
    el.evaluationCard.textContent = "No evaluations available.";
    return;
  }
  const latest = state.evaluations[0];
  const result = latest.result || {};
  const labelClass =
    result.label === "accept" || result.label === "accept_with_notes"
      ? "ok"
      : result.label
        ? "error"
        : "muted";
  const scores = (latest.scores || [])
    .map(
      (score) => `
      <div class="event">
        <div><strong>${escapeHtml(score.dimension)}</strong>: ${escapeHtml(score.score)} / 100</div>
        <div class="muted">${escapeHtml(score.basis)} | confidence ${escapeHtml(score.confidence)} | pass ${escapeHtml(score.pass_fail ? "yes" : "no")}</div>
        <div>${escapeHtml(score.rationale || "")}</div>
      </div>
    `
    )
    .join("");
  const annotations = (latest.annotations || [])
    .map(
      (annotation) => `
      <div class="event">
        <div><strong>${escapeHtml(annotation.label)}</strong> ${escapeHtml(annotation.severity)}</div>
        <div>${escapeHtml(annotation.notes || "")}</div>
      </div>
    `
    )
    .join("");
  el.evaluationCard.className = "box";
  el.evaluationCard.innerHTML = `
    <div class="${labelClass}"><strong>Label:</strong> ${escapeHtml(result.label || "-")}</div>
    <div><strong>Overall:</strong> ${escapeHtml(result.overall_score ?? "-")} | <strong>Status:</strong> ${escapeHtml(latest.status)}</div>
    <div><strong>Evaluator:</strong> ${escapeHtml(latest.evaluator_type)} / ${escapeHtml(latest.evaluator_model || "-")}</div>
    <div><strong>Rubric:</strong> ${escapeHtml(latest.rubric_name || "-")} ${escapeHtml(latest.rubric_version || "")}</div>
    <div><strong>Human review:</strong> ${escapeHtml(result.needs_human_review ? "required" : "not required")}</div>
    <div><strong>Unsupported markers:</strong> ${escapeHtml((result.unsupported_claim_markers || []).join(", ") || "-")}</div>
    <hr />
    <div><strong>Scores</strong></div>
    ${scores || '<div class="muted">No score rows.</div>'}
    ${annotations ? `<hr /><div><strong>Queue Annotations</strong></div>${annotations}` : ""}
  `;
}

function renderTrace() {
  if (!state.currentRunId) {
    el.traceFlow.className = "trace-flow muted";
    el.traceFlow.textContent = "No run loaded.";
    el.traceDetailTitle.textContent = "Select a trace stage";
    el.traceDetailPayload.textContent = "";
    renderTraceRuntime();
    renderTraceMiniLog();
    return;
  }
  const trace = state.trace;
  const nodes = trace && Array.isArray(trace.nodes) ? trace.nodes : [];
  const edges = trace && Array.isArray(trace.edges) ? trace.edges : [];
  if (!nodes.length) {
    el.traceFlow.className = "trace-flow muted";
    el.traceFlow.textContent = "No trace available.";
    el.traceDetailTitle.textContent = "Select a trace stage";
    el.traceDetailPayload.textContent = "";
    renderTraceRuntime();
    renderTraceMiniLog();
    return;
  }
  el.traceFlow.className = "trace-flow";
  const edgeBySource = new Map(edges.map((edge) => [edge.from_node, edge]));
  el.traceFlow.innerHTML = nodes
    .map((node) => {
      const edge = edgeBySource.get(node.node_id);
      return `
        <button type="button" class="trace-node ${node.node_id === state.selectedTraceNodeId ? "selected" : ""}" data-trace-node-id="${escapeHtml(node.node_id)}">
          <span class="trace-node-title">${escapeHtml(node.label)}</span>
          <span class="trace-node-status">${escapeHtml(node.status)}</span>
          <span class="trace-node-kind">${escapeHtml(node.kind)}</span>
          <span class="trace-node-summary">${escapeHtml(node.summary)}</span>
        </button>
        ${edge ? `<div class="trace-edge">${escapeHtml(edge.label)}</div>` : ""}
      `;
    })
    .join("");
  const selected = nodes.find((node) => node.node_id === state.selectedTraceNodeId) || nodes[0];
  state.selectedTraceNodeId = selected.node_id;
  el.traceDetailTitle.textContent = `${selected.label} · ${selected.status}`;
  el.traceDetailPayload.textContent = JSON.stringify(
    {
      node_id: selected.node_id,
      kind: selected.kind,
      summary: selected.summary,
      metrics: selected.metrics || {},
      payload: selected.payload || {},
    },
    null,
    2
  );
  renderTraceRuntime();
  renderTraceMiniLog();
}

function loadHistory() {
  try {
    state.history = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
  } catch (_err) {
    state.history = [];
  }
}

function saveHistory() {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(state.history.slice(0, 30)));
}

function addHistory(run) {
  if (!run || !run.run_id) return;
  state.history = [
    {
      run_id: run.run_id,
      ticker: run.ticker,
      trade_date: run.trade_date,
      status: run.status,
      updated_at: run.updated_at,
    },
    ...state.history.filter((item) => item.run_id !== run.run_id),
  ].slice(0, 30);
  saveHistory();
  renderHistory();
}

function renderHistory() {
  if (!state.history.length) {
    el.historyCard.className = "box muted";
    el.historyCard.textContent = "No local history yet.";
    return;
  }
  el.historyCard.className = "box";
  el.historyCard.innerHTML = state.history
    .map(
      (item) => `
      <div class="history-item">
        <div><strong>${escapeHtml(item.ticker || "-")}</strong> ${escapeHtml(item.trade_date || "-")}</div>
        <div class="muted">${escapeHtml(item.status || "-")} | ${escapeHtml(item.updated_at || "-")}</div>
        <button type="button" data-run-id="${escapeHtml(item.run_id)}">Load ${escapeHtml(item.run_id)}</button>
      </div>
    `
    )
    .join("");
}

function renderHandoffPayload() {
  const payload = {
    run: state.currentRun || null,
    load_mode: state.currentRunLoadMode || null,
    decision: state.decision || null,
    trace: state.trace || null,
    evaluations: state.evaluations || [],
    artifacts: state.artifacts || [],
    events: state.events || [],
    generated_at: new Date().toISOString(),
  };
  el.handoffPreview.value = JSON.stringify(payload, null, 2);
}

async function refreshAll(runId) {
  const [run, events, decision, artifacts, trace, evaluations] = await Promise.all([
    fetchJson(`/v1/shadow-runs/${encodeURIComponent(runId)}`),
    fetchJson(`/v1/shadow-runs/${encodeURIComponent(runId)}/events`),
    fetchJson(`/v1/shadow-runs/${encodeURIComponent(runId)}/decision`),
    fetchJson(`/v1/shadow-runs/${encodeURIComponent(runId)}/artifacts`),
    fetchJson(`/v1/shadow-runs/${encodeURIComponent(runId)}/trace`),
    fetchJson(`/v1/evaluations?shadow_run_id=${encodeURIComponent(runId)}`),
  ]);
  state.currentRun = run;
  state.events = events.events || [];
  state.decision = decision || null;
  state.artifacts = artifacts.artifacts || [];
  state.trace = trace || null;
  if (!state.selectedTraceNodeId || !(trace.nodes || []).some((node) => node.node_id === state.selectedTraceNodeId)) {
    state.selectedTraceNodeId = trace.nodes && trace.nodes.length ? trace.nodes[0].node_id : null;
  }
  state.evaluations = evaluations.evaluations || [];
  recordDurationSample();
  addHistory(run);
  renderStatus();
  renderEvents();
  renderDecision();
  renderTrace();
  renderEvaluations();
  renderArtifacts();
  await refreshReports();
  renderPriorRunLookup();
  renderHandoffPayload();
}

function stopPolling() {
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
  }
  state.pollTimer = null;
  state.polling = false;
  el.pollToggleBtn.textContent = "Start Poll";
}

function startPolling() {
  if (!state.currentRunId) {
    setComposerState("Load a run ID before polling.", "error");
    return;
  }
  if (state.polling) return;
  state.polling = true;
  el.pollToggleBtn.textContent = "Stop Poll";
  state.pollTimer = setInterval(async () => {
    try {
      await refreshAll(state.currentRunId);
      if (state.currentRun && TERMINAL_STATUSES.includes(state.currentRun.status)) {
        stopPolling();
      }
    } catch (err) {
      stopPolling();
      setComposerState(`Polling stopped: ${err.message}`, "error");
    }
  }, 3000);
}

el.composerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(el.composerForm);
  const analysts = formData.getAll("selected_analysts").map(String);
  if (!analysts.length) {
    setComposerState("Select at least one analyst.", "error");
    return;
  }
  const payload = {
    ticker: String(formData.get("ticker") || "").trim(),
    trade_date: String(formData.get("trade_date") || "").trim(),
    selected_analysts: analysts,
  };
  const provider = String(formData.get("provider") || "").trim();
  const model = String(formData.get("model") || "").trim();
  if (provider) payload.provider = provider;
  if (model) payload.model = model;

  setComposerState("Queueing run...", "muted");
  try {
    const created = await fetchJson("/v1/shadow-runs", { method: "POST", body: JSON.stringify(payload) });
    state.currentRunId = created.run_id;
    state.currentRunLoadMode = created.reused_existing ? "retrieved" : "queued";
    el.runIdInput.value = created.run_id;
    const actionText = created.reused_existing ? "Retrieved existing run" : "Queued new run";
    setComposerState(`${actionText} ${created.run_id}`, created.reused_existing ? "muted" : "ok");
    await refreshAll(state.currentRunId);
    stopPolling();
    if (!created.reused_existing || (state.currentRun && !TERMINAL_STATUSES.includes(state.currentRun.status))) {
      startPolling();
    }
  } catch (err) {
    setComposerState(`Queue failed: ${err.message}`, "error");
  }
});

el.runEvaluationBtn.addEventListener("click", async () => {
  if (!state.currentRunId) {
    setEvaluationState("Load a run before evaluating.", "error");
    return;
  }
  const model = el.evalModelInput.value.trim();
  const payload = { evaluator_type: model ? "llm" : "system" };
  if (model) payload.evaluator_model = model;
  setEvaluationState("Creating evaluation...", "muted");
  try {
    await fetchJson(`/v1/evaluations/shadow-runs/${encodeURIComponent(state.currentRunId)}`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    await refreshAll(state.currentRunId);
    setEvaluationState("Evaluation complete.", "ok");
  } catch (err) {
    setEvaluationState(`Evaluation failed: ${err.message}`, "error");
  }
});

el.traceFlow.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  const button = target.closest("[data-trace-node-id]");
  if (!(button instanceof HTMLElement)) return;
  state.selectedTraceNodeId = button.getAttribute("data-trace-node-id");
  renderTrace();
});

el.tickerInput.addEventListener("input", schedulePriorRunLookup);
el.tradeDateInput.addEventListener("input", schedulePriorRunLookup);
el.tradeDateInput.addEventListener("change", schedulePriorRunLookup);

el.loadRunBtn.addEventListener("click", async () => {
  const runId = el.runIdInput.value.trim();
  if (!runId) {
    setComposerState("Enter a run ID.", "error");
    return;
  }
  await loadRunById(runId);
});

el.pollToggleBtn.addEventListener("click", async () => {
  if (state.polling) {
    stopPolling();
    setComposerState("Polling stopped.", "muted");
    return;
  }
  try {
    await refreshAll(state.currentRunId);
    startPolling();
    setComposerState("Polling started.", "ok");
  } catch (err) {
    setComposerState(`Cannot start polling: ${err.message}`, "error");
  }
});

el.copyBtn.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(el.handoffPreview.value);
    setCopyState("Payload copied.", "ok");
  } catch (_err) {
    setCopyState("Clipboard write failed.", "error");
  }
});

el.refreshReportsBtn.addEventListener("click", async () => {
  try {
    await refreshReports();
  } catch (err) {
    el.reportsCard.className = "box error";
    el.reportsCard.textContent = `Failed to load reports: ${err.message}`;
  }
});

el.reportsCard.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  const runId = target.getAttribute("data-run-id");
  if (!runId) return;
  await loadRunById(runId);
});

el.priorRunCard.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  const runId = target.getAttribute("data-run-id");
  if (!runId) return;
  await loadRunById(runId, { mode: "retrieved", source: "prior_lookup" });
});

el.historyCard.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  const runId = target.getAttribute("data-run-id");
  if (!runId) return;
  await loadRunById(runId);
});

function init() {
  loadHistory();
  loadDurationSamples();
  renderStatus();
  renderEvents();
  renderDecision();
  renderTrace();
  renderEvaluations();
  renderArtifacts();
  renderReports();
  renderPriorRunLookup();
  renderHistory();
  renderHandoffPayload();
  refreshReports().catch(() => {
    renderReports();
  });
  setComposerState("Ready.");
}

init();
