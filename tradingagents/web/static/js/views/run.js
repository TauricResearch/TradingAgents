// Live run view: pipeline DAG over a split detail pane (report stream +
// stats + collapsible tool-call ticker).

import { el, clear, formatElapsed, decisionClass } from '../dom.js';
import { api } from '../api.js';
import { setMarkdown } from '../markdown.js';
import { SECTION_ORDER, SECTION_TITLES, TEAM_ORDER } from '../store.js';

const TEAM_AGENTS = {
  'Analyst Team': ['Market Analyst', 'Sentiment Analyst', 'News Analyst', 'Fundamentals Analyst'],
  'Research Team': ['Bull Researcher', 'Bear Researcher', 'Research Manager'],
  'Trading Team': ['Trader'],
  'Risk Management': ['Aggressive Analyst', 'Neutral Analyst', 'Conservative Analyst'],
  'Portfolio Management': ['Portfolio Manager'],
};

const STATE_LABEL = {
  running: 'RUNNING',
  done: 'DONE',
  failed: 'FAILED',
  cancelled: 'CANCELLED',
};

export function renderRun(container, store) {
  clear(container);
  const { live } = store.state;

  if (!live.runId) {
    container.append(
      el('div', { class: 'pagehead' }, [el('h2', {}, ['Runs'])]),
      el('div', { class: 'empty card' }, [
        'No run in this session yet. ',
        el('a', { href: '#/configure' }, ['Configure a new run →']),
      ]),
    );
    return () => {};
  }

  // -- header ------------------------------------------------------------
  const badge = el('span', { class: 'badge' });
  const cancelButton = el('button', { class: 'btn danger small', type: 'button' }, ['Stop run']);
  const cancelNote = el('small', { class: 'cancel-note', hidden: '' }, [
    'Stopping after the current agent finishes…',
  ]);
  cancelButton.addEventListener('click', async () => {
    cancelButton.disabled = true;
    cancelNote.hidden = false;
    try {
      await api.cancelRun(live.runId);
    } catch {
      cancelButton.disabled = false;
      cancelNote.hidden = true;
    }
  });

  const head = el('div', { class: 'pagehead' }, [
    el('h2', { class: 'mono' }, [live.ticker || '—']),
    el('p', {}, [`${live.date || ''}`]),
    badge,
    cancelButton,
    cancelNote,
  ]);

  const errorBox = el('div', { class: 'run-error card', hidden: '' });
  const decisionBanner = el('div', { class: 'decision-banner', hidden: '' });

  // -- pipeline DAG --------------------------------------------------------
  const agentNodes = new Map();
  const dag = el('div', { class: 'dag' });
  TEAM_ORDER.forEach((team, index) => {
    const stage = el('div', { class: 'stage' }, [el('h4', {}, [team])]);
    for (const agent of TEAM_AGENTS[team]) {
      const status = el('span', { class: 'st pend' });
      const node = el('div', { class: 'node pend-t' }, [status, agent]);
      agentNodes.set(agent, node);
      stage.append(node);
    }
    dag.append(stage);
    if (index < TEAM_ORDER.length - 1) dag.append(el('div', { class: 'edge' }));
  });

  // -- stats + ticker ------------------------------------------------------
  const statValues = {
    elapsed: el('b', {}, ['00:00']),
    llm_calls: el('b', {}, ['0']),
    tool_calls: el('b', {}, ['0']),
  };
  const stats = el('div', { class: 'stats' }, [
    el('div', { class: 'stat' }, [statValues.elapsed, el('span', {}, ['Elapsed'])]),
    el('div', { class: 'stat' }, [statValues.llm_calls, el('span', {}, ['LLM calls'])]),
    el('div', { class: 'stat' }, [statValues.tool_calls, el('span', {}, ['Tool calls'])]),
  ]);

  const tickerList = el('ol', { class: 'ticker-list' });
  const ticker = el('details', { class: 'ticker', open: '' }, [
    el('summary', {}, ['Tool calls']),
    tickerList,
  ]);

  // -- report stream -------------------------------------------------------
  const sectionBodies = new Map();
  const sectionWraps = new Map();
  const stream = el('div', { class: 'stream card-dark' }, [
    el('div', { class: 'stream-head' }, ['Report stream']),
  ]);
  for (const section of SECTION_ORDER) {
    const body = el('div', { class: 'report-body' }, ['Waiting…']);
    const wrap = el('section', { class: 'repsec queued' }, [
      el('h5', {}, [SECTION_TITLES[section]]),
      body,
    ]);
    sectionBodies.set(section, body);
    sectionWraps.set(section, wrap);
    stream.append(wrap);
  }

  container.append(
    head,
    errorBox,
    decisionBanner,
    el('div', { class: 'dagwrap card-dark' }, [dag]),
    el('div', { class: 'live-grid' }, [
      stream,
      el('div', { class: 'live-side' }, [stats, ticker]),
    ]),
  );

  // -- patchers ------------------------------------------------------------
  function patchHeader() {
    badge.textContent = STATE_LABEL[live.state] || '…';
    badge.className = `badge ${live.state || ''}`;
    head.querySelector('h2').textContent = live.ticker || '—';
    head.querySelector('p').textContent = live.date || '';
    const terminal = live.state && live.state !== 'running';
    cancelButton.hidden = terminal;
    if (terminal) cancelNote.hidden = true;
    if (live.state === 'done' && live.decision) {
      decisionBanner.hidden = false;
      decisionBanner.className = `decision-banner ${decisionClass(live.decision)}`;
      clear(decisionBanner);
      decisionBanner.append(
        el('span', { class: 'verdict' }, [live.decision]),
        el('span', { class: 'sub' }, [`${live.ticker} · ${live.date}`]),
      );
    }
    if (live.state === 'failed' && live.error) {
      errorBox.hidden = false;
      clear(errorBox);
      errorBox.append(
        el('b', {}, [`${live.error.exc_type || 'Error'}: `]),
        String(live.error.message || ''),
        el('pre', { class: 'tb' }, [(live.error.traceback_tail || []).join('\n')]),
      );
    }
  }

  function patchAgents() {
    for (const [agent, node] of agentNodes.entries()) {
      const info = live.agents[agent];
      const status = info ? info.status : 'pending';
      const dot = node.querySelector('.st');
      dot.className = `st ${status === 'done' ? 'done' : status === 'working' ? 'work' : 'pend'}`;
      node.className = `node${status === 'pending' ? ' pend-t' : ''}`;
    }
  }

  function patchSections() {
    for (const section of SECTION_ORDER) {
      const markdown = live.sections[section];
      const wrap = sectionWraps.get(section);
      if (markdown) {
        wrap.classList.remove('queued');
        setMarkdown(sectionBodies.get(section), markdown);
      }
    }
  }

  function patchStats() {
    statValues.elapsed.textContent = formatElapsed(live.stats.elapsed);
    statValues.llm_calls.textContent = String(live.stats.llm_calls);
    statValues.tool_calls.textContent = String(live.stats.tool_calls);
  }

  function patchTicker() {
    clear(tickerList);
    const recent = live.toolCalls.slice(-40).reverse();
    for (const call of recent) {
      tickerList.append(el('li', {}, [
        el('code', {}, [`${call.name}(${call.argsPreview || ''})`]),
      ]));
    }
  }

  function patchAll() {
    patchHeader();
    patchAgents();
    patchSections();
    patchStats();
    patchTicker();
  }
  patchAll();

  const unsubscribe = store.subscribe((event) => {
    if (event.type === 'live-reset') {
      patchAll();
      return;
    }
    if (event.type !== 'run-event') return;
    switch (event.eventType) {
      case 'agent_status':
        patchAgents();
        break;
      case 'report_section':
        patchSections();
        break;
      case 'stats':
        patchStats();
        break;
      case 'tool_call':
        patchTicker();
        break;
      default:
        patchAll();
    }
  });
  return unsubscribe;
}
