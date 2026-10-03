'use strict';

// Single-page front end over /api. No framework and no build step: the whole
// thing is served from the Python package, so a `pip install` is the install.

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const state = {
  config: null,
  portfolio: null,
  runs: [],
  selectedRun: null,
  stream: null,
  reportLabels: {},
  reportOrder: [],
};

async function api(path, options = {}) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch { /* a non-JSON error body: the status text stands */ }
    throw new Error(detail);
  }
  return res.status === 204 ? null : res.json();
}

function setStatus(el, text, kind = '') {
  el.textContent = text;
  el.className = `status ${kind}`;
  if (kind === 'ok') setTimeout(() => { if (el.textContent === text) el.textContent = ''; }, 4000);
}

// ─── Tabs ──────────────────────────────────────────────────────────────

$$('.tab').forEach((tab) => tab.addEventListener('click', () => {
  $$('.tab').forEach((t) => t.classList.toggle('active', t === tab));
  $$('.view').forEach((v) => v.classList.toggle('active', v.id === `view-${tab.dataset.view}`));
  if (tab.dataset.view === 'runs') refreshRuns();
  if (tab.dataset.view === 'history') loadHistory();
}));

// ─── Portfolio ─────────────────────────────────────────────────────────

function positionRow(position = { ticker: '', quantity: '', average_price: '' }) {
  const tr = document.createElement('tr');
  tr.innerHTML = `
    <td><input class="p-ticker" type="text" value="${position.ticker ?? ''}" placeholder="AAPL"></td>
    <td><input class="p-qty" type="number" step="any" value="${position.quantity ?? ''}"></td>
    <td><input class="p-avg" type="number" step="any" value="${position.average_price ?? ''}" placeholder="optional"></td>
    <td><button class="link remove">remove</button></td>`;
  tr.querySelector('.remove').addEventListener('click', () => tr.remove());
  return tr;
}

function renderPortfolio(book) {
  state.portfolio = book;
  const body = $('#positions tbody');
  body.textContent = '';
  (book?.positions ?? []).forEach((p) => body.appendChild(positionRow(p)));
  if (!body.children.length) body.appendChild(positionRow());
  $('#cash').value = book?.cash ?? '';
  $('#currency').value = book?.currency ?? '';
}

function readPortfolioForm() {
  const positions = Array.from($('#positions tbody').children).map((tr) => ({
    ticker: tr.querySelector('.p-ticker').value.trim().toUpperCase(),
    quantity: tr.querySelector('.p-qty').value,
    average_price: tr.querySelector('.p-avg').value,
  })).filter((p) => p.ticker && p.quantity !== '').map((p) => ({
    ticker: p.ticker,
    quantity: Number(p.quantity),
    average_price: p.average_price === '' ? null : Number(p.average_price),
  }));
  const cash = $('#cash').value;
  return {
    cash: cash === '' ? null : Number(cash),
    currency: $('#currency').value.trim() || null,
    positions,
  };
}

async function loadPortfolio() {
  const data = await api('/api/portfolio');
  renderPortfolio(data.portfolio);
  $('#portfolio-path').textContent = `Saved at ${data.path}`;
}

$('#add-row').addEventListener('click', () => $('#positions tbody').appendChild(positionRow()));

$('#save-portfolio').addEventListener('click', async () => {
  try {
    const data = await api('/api/portfolio', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(readPortfolioForm()),
    });
    renderPortfolio(data.portfolio);
    setStatus($('#portfolio-status'), 'Saved.', 'ok');
  } catch (err) {
    setStatus($('#portfolio-status'), err.message, 'err');
  }
});

$('#delete-portfolio').addEventListener('click', async () => {
  if (!confirm('Delete the saved book? Runs go back to advice not situated in a position.')) return;
  await api('/api/portfolio', { method: 'DELETE' });
  renderPortfolio(null);
  setStatus($('#portfolio-status'), 'Deleted.', 'ok');
});

// ─── CSV import ────────────────────────────────────────────────────────

const dropzone = $('#dropzone');
$('#browse').addEventListener('click', () => $('#csv-file').click());
$('#csv-file').addEventListener('change', (e) => e.target.files[0] && importCsv(e.target.files[0]));

['dragenter', 'dragover'].forEach((type) => dropzone.addEventListener(type, (e) => {
  e.preventDefault();
  dropzone.classList.add('over');
}));
['dragleave', 'drop'].forEach((type) => dropzone.addEventListener(type, (e) => {
  e.preventDefault();
  dropzone.classList.remove('over');
}));
dropzone.addEventListener('drop', (e) => {
  const file = e.dataTransfer.files[0];
  if (file) importCsv(file);
});

async function importCsv(file) {
  const report = $('#import-report');
  report.hidden = false;
  report.innerHTML = '<div class="note info">Reading…</div>';
  try {
    const text = await file.text();
    const data = await api('/api/portfolio/import', {
      method: 'POST',
      headers: { 'Content-Type': 'text/csv' },
      body: text,
    });
    // A preview, not a save: the parse fills the form and the user commits it,
    // so a misread column cannot quietly overwrite a book typed by hand.
    renderPortfolio(data.portfolio);
    const notes = [`<div class="note info"><strong>${data.portfolio.positions.length}</strong>
      position(s) read from <code>${file.name}</code>${data.portfolio.cash != null
        ? ` and cash of ${data.portfolio.cash.toLocaleString()}` : ''}.
      Check the book below, then <strong>Save book</strong> to keep it.</div>`];
    data.warnings.forEach((w) => notes.push(`<div class="note warn">${escapeHtml(w)}</div>`));
    if (data.skipped.length) {
      notes.push(`<div class="note warn"><strong>Skipped ${data.skipped.length} row(s):</strong><br>
        ${data.skipped.map(escapeHtml).join('<br>')}</div>`);
    }
    report.innerHTML = notes.join('');
  } catch (err) {
    report.innerHTML = `<div class="note err">${escapeHtml(err.message)}</div>`;
  }
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = String(text);
  return div.innerHTML;
}

// ─── Analyze ───────────────────────────────────────────────────────────

function fillModels() {
  const provider = $('#provider').value;
  const models = state.config.models[provider] ?? { quick: [], deep: [] };
  for (const [sel, mode, def] of [
    ['#deep-model', 'deep', state.config.defaults.deep_think_llm],
    ['#quick-model', 'quick', state.config.defaults.quick_think_llm],
  ]) {
    const node = $(sel);
    node.textContent = '';
    models[mode].filter((m) => m.value !== 'custom').forEach((m) => {
      node.appendChild(new Option(m.label, m.value));
    });
    if (!node.options.length) node.appendChild(new Option(def ?? '(set in config)', def ?? ''));
    if (Array.from(node.options).some((o) => o.value === def)) node.value = def;
  }
}

async function loadConfig() {
  const config = await api('/api/config');
  state.config = config;
  config.report_sections.forEach((s) => { state.reportLabels[s.key] = s.label; });
  state.reportOrder = config.report_sections.map((s) => s.key);

  const provider = $('#provider');
  config.providers.forEach((p) => provider.appendChild(new Option(p, p)));
  provider.value = config.defaults.llm_provider ?? config.providers[0];
  provider.addEventListener('change', fillModels);
  fillModels();

  $('#date').value = config.today;
  $('#date').max = config.today;
  $('#debate-rounds').value = config.defaults.max_debate_rounds ?? 1;
  $('#risk-rounds').value = config.defaults.max_risk_discuss_rounds ?? 1;

  const choices = $('#analyst-choices');
  config.analysts.forEach((a) => {
    const label = document.createElement('label');
    label.innerHTML = `<input type="checkbox" value="${a.value}" checked> ${a.label}`;
    choices.appendChild(label);
  });
}

function runPayload() {
  return {
    trade_date: $('#date').value,
    analysts: $$('#analyst-choices input:checked').map((i) => i.value),
    llm_provider: $('#provider').value,
    deep_think_llm: $('#deep-model').value,
    quick_think_llm: $('#quick-model').value,
    max_debate_rounds: Number($('#debate-rounds').value),
    max_risk_discuss_rounds: Number($('#risk-rounds').value),
  };
}

function showRunsTab() {
  $('.tab[data-view="runs"]').click();
}

$('#run-one').addEventListener('click', async () => {
  const status = $('#analyze-status');
  try {
    const run = await api('/api/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...runPayload(),
        ticker: $('#ticker').value,
        use_portfolio: $('#use-portfolio').checked,
      }),
    });
    setStatus(status, `Queued ${run.ticker}.`, 'ok');
    await refreshRuns();
    selectRun(run.id);
    showRunsTab();
  } catch (err) {
    setStatus(status, err.message, 'err');
  }
});

$('#run-book').addEventListener('click', async () => {
  const status = $('#analyze-status');
  const count = state.portfolio?.positions?.length ?? 0;
  if (!count) {
    setStatus(status, 'No saved book with positions — import or enter one first.', 'err');
    return;
  }
  if (!confirm(`Queue ${count} analyses, one per holding? Each one calls your provider.`)) return;
  try {
    const data = await api('/api/runs/book', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(runPayload()),
    });
    const skipped = data.rejected.length ? `, ${data.rejected.length} skipped` : '';
    setStatus(status, `Queued ${data.runs.length} run(s)${skipped}.`, 'ok');
    await refreshRuns();
    selectRun(data.runs[0].id);
    showRunsTab();
  } catch (err) {
    setStatus(status, err.message, 'err');
  }
});

// ─── Runs ──────────────────────────────────────────────────────────────

async function refreshRuns() {
  const data = await api('/api/runs');
  state.runs = data.runs;
  const list = $('#run-list');
  list.textContent = '';
  if (!data.runs.length) {
    list.innerHTML = '<li class="hint">Nothing has run yet.</li>';
    return;
  }
  data.runs.forEach((run) => {
    const li = document.createElement('li');
    li.className = run.id === state.selectedRun ? 'selected' : '';
    li.innerHTML = `<span class="sym">${escapeHtml(run.ticker)}</span>
      <span class="pill ${run.status}">${run.rating ?? run.status}</span>
      <span class="when">${run.trade_date}</span>`;
    li.addEventListener('click', () => selectRun(run.id));
    list.appendChild(li);
  });
}

async function selectRun(runId) {
  state.selectedRun = runId;
  if (state.stream) { state.stream.close(); state.stream = null; }
  $$('#run-list li').forEach((li) => li.classList.remove('selected'));
  await refreshRuns();

  const run = await api(`/api/runs/${runId}`);
  renderRunHeader(run);
  $('#run-reports').textContent = '';
  $('#transcript').textContent = '';
  Object.entries(run.reports).forEach(([key, content]) => upsertReport(key, content));
  run.messages.forEach(appendMessage);

  // Replays from the first event, so a reload mid-run loses nothing.
  const stream = new EventSource(`/api/runs/${runId}/events`);
  state.stream = stream;
  const seen = new Set();
  stream.onmessage = (e) => {
    const event = JSON.parse(e.data);
    if (seen.has(event.seq)) return;
    seen.add(event.seq);
    handleEvent(runId, event);
  };
  stream.addEventListener('end', () => stream.close());
  stream.onerror = () => { /* EventSource reconnects on its own; the replay dedupes */ };
}

function handleEvent(runId, event) {
  if (runId !== state.selectedRun) return;
  if (event.kind === 'message') appendMessage(event);
  else if (event.kind === 'report') upsertReport(event.key, event.content);
  else if (event.kind === 'agent') markAgent(event.agent);
  else if (event.kind === 'stats') renderStats(event.stats);
  else if (event.kind === 'status') {
    api(`/api/runs/${runId}`).then((run) => { renderRunHeader(run); refreshRuns(); });
  }
}

function renderRunHeader(run) {
  const elapsed = run.started_at
    ? Math.round(((run.finished_at ?? Date.now() / 1000) - run.started_at))
    : 0;
  const parts = [
    `<div><span class="rating ${run.rating ?? ''}">${run.rating ?? '—'}</span>
      <strong style="margin-left:10px">${escapeHtml(run.ticker)}</strong>
      <span class="pill ${run.status}">${run.status}</span></div>`,
    `<div class="meta">${run.trade_date} · ${run.analysts.join(', ')} ·
      ${run.with_portfolio ? 'against your book' : 'no portfolio context'} ·
      ${elapsed}s<span id="run-stats"></span></div>`,
  ];
  if (run.needs_review) {
    parts.push(`<div class="note warn">No rating could be read from the final decision, so
      this run is recorded for review rather than as a position. Read the decision and judge
      it yourself, or run it again.</div>`);
  }
  if (run.error) parts.push(`<div class="note err">${escapeHtml(run.error)}</div>`);
  if (run.report_path) parts.push(`<div class="meta">Report tree: <code>${escapeHtml(run.report_path)}</code></div>`);
  if (run.status === 'queued' || run.status === 'running') {
    parts.push('<button id="cancel-run" class="danger" style="margin-top:10px">Stop this run</button>');
  }
  $('#run-header').innerHTML = parts.join('');
  const cancel = $('#cancel-run');
  if (cancel) {
    cancel.addEventListener('click', async () => {
      await api(`/api/runs/${run.id}/cancel`, { method: 'POST' });
      refreshRuns();
    });
  }
  renderAgents(run);
}

function renderAgents(run) {
  const names = [...run.analysts, 'bull', 'bear', 'aggressive', 'conservative', 'neutral'];
  // A status event re-renders the header, so the finished agents are read back
  // from the run rather than left in the DOM, where the re-render would lose them.
  const done = new Set(run.agents_done ?? state.agentsDone ?? []);
  state.agentsDone = [...done];
  $('#agent-track').innerHTML = names
    .map((n) => `<span class="chip${done.has(n) ? ' completed' : ''}" data-agent="${n}">${n}</span>`)
    .join('');
}

function markAgent(agent) {
  state.agentsDone = [...new Set([...(state.agentsDone ?? []), agent])];
  const chip = document.querySelector(`.chip[data-agent="${agent}"]`);
  if (chip) chip.classList.add('completed');
}

function renderStats(stats) {
  const node = $('#run-stats');
  if (node && stats) {
    node.textContent = ` · ${stats.llm_calls} LLM calls · ` +
      `${(stats.tokens_in + stats.tokens_out).toLocaleString()} tokens`;
  }
}

function upsertReport(key, content) {
  const label = state.reportLabels[key] ?? key.replace(/_/g, ' ');
  let node = document.querySelector(`details.report[data-key="${key}"]`);
  if (!node) {
    node = document.createElement('details');
    node.className = 'report';
    node.dataset.key = key;
    // The decision is the thing being looked for, so it opens itself.
    if (key === 'final_trade_decision') node.open = true;
    node.innerHTML = `<summary>${escapeHtml(label)}</summary><div class="report-body"></div>`;
    insertInPipelineOrder(node, key);
  }
  node.querySelector('.report-body').innerHTML = renderMarkdown(content);
}

function insertInPipelineOrder(node, key) {
  const container = $('#run-reports');
  const rank = state.reportOrder.indexOf(key);
  const after = Array.from(container.children).find((child) => {
    const other = state.reportOrder.indexOf(child.dataset.key);
    return other > rank;
  });
  container.insertBefore(node, after ?? null);
}

// A deliberately small markdown subset: the agents write headings, bold, lists
// and tables, and nothing here needs links or images. Everything is escaped
// first and the transforms run over escaped text, so a report cannot inject
// markup no matter what a model or a news headline puts in it.
function renderMarkdown(text) {
  const rows = [];
  let inTable = false;

  const flushTable = () => {
    if (!rows.length) return '';
    const cells = (line, tag) => '<tr>' + line.split('|').slice(1, -1)
      .map((c) => `<${tag}>${inline(c.trim())}</${tag}>`).join('') + '</tr>';
    const head = cells(rows[0], 'th');
    const body = rows.slice(2).map((r) => cells(r, 'td')).join('');
    rows.length = 0;
    return `<table class="md"><thead>${head}</thead><tbody>${body}</tbody></table>`;
  };

  const inline = (s) => s
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*]+)\*/g, '$1<em>$2</em>')
    .replace(/`([^`]+)`/g, '<code>$1</code>');

  const out = [];
  for (const raw of escapeHtml(text).split('\n')) {
    const line = raw.trimEnd();
    const isRow = /^\s*\|.*\|\s*$/.test(line);
    if (isRow) { inTable = true; rows.push(line.trim()); continue; }
    if (inTable) { out.push(flushTable()); inTable = false; }

    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      const level = Math.min(heading[1].length + 2, 6);
      out.push(`<h${level}>${inline(heading[2])}</h${level}>`);
    } else if (/^\s*[-*]\s+/.test(line)) {
      out.push(`<li>${inline(line.replace(/^\s*[-*]\s+/, ''))}</li>`);
    } else if (!line) {
      out.push('');
    } else {
      out.push(`<p>${inline(line)}</p>`);
    }
  }
  if (inTable) out.push(flushTable());

  // Consecutive list items become one list, so they indent as a group.
  return out.join('\n').replace(/((?:<li>.*?<\/li>\n?)+)/g, '<ul>$1</ul>');
}

function appendMessage(message) {
  const node = document.createElement('div');
  node.innerHTML = `<span class="who">${escapeHtml(message.type)}</span> ${escapeHtml(
    message.content.length > 500 ? `${message.content.slice(0, 500)}…` : message.content)}`;
  const box = $('#transcript');
  const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 40;
  box.appendChild(node);
  if (atBottom) box.scrollTop = box.scrollHeight;
}

// ─── History ───────────────────────────────────────────────────────────

async function loadHistory() {
  const data = await api('/api/history');
  const body = $('#history-table tbody');
  body.textContent = '';
  if (!data.entries.length) {
    body.innerHTML = '<tr><td colspan="6" class="hint">No decisions recorded yet.</td></tr>';
    return;
  }
  data.entries.forEach((e) => {
    const tr = document.createElement('tr');
    const alphaClass = e.alpha?.startsWith('-') ? 'alpha-neg' : e.alpha ? 'alpha-pos' : '';
    tr.innerHTML = `<td>${escapeHtml(e.date ?? '')}</td>
      <td class="sym">${escapeHtml(e.ticker ?? '')}</td>
      <td>${escapeHtml(e.rating ?? '')}</td>
      <td>${escapeHtml(e.raw ?? '—')}</td>
      <td class="${alphaClass}">${escapeHtml(e.alpha ?? '—')}</td>
      <td>${e.pending ? '<span class="pending">pending</span>' : escapeHtml(e.resolved ?? 'settled')}</td>`;
    body.appendChild(tr);
  });
}

// ─── Boot ──────────────────────────────────────────────────────────────

(async function start() {
  await loadConfig();
  await loadPortfolio();
  await refreshRuns();
  // A queued run only starts when the worker reaches it, and a finished one
  // changes the list, so the list refreshes on a timer while runs are open.
  setInterval(() => {
    if (state.runs.some((r) => r.status === 'queued' || r.status === 'running')) refreshRuns();
  }, 5000);
})();
