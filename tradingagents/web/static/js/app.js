// App shell: sidebar nav + hash router + boot sequence.

import { el, clear, formatElapsed } from './dom.js';
import { api } from './api.js';
import { createStore } from './store.js';
import { connectRunEvents } from './sse.js';
import { renderConfigure } from './views/configure.js';
import { renderRun } from './views/run.js';
import { renderReports } from './views/reports.js';
import { renderSettings } from './views/settings.js';

const store = createStore();

const ROUTES = {
  '#/configure': { title: 'New Run', render: renderConfigure },
  '#/run': { title: 'Runs', render: renderRun },
  '#/reports': { title: 'Reports', render: renderReports },
  '#/settings': { title: 'Settings', render: renderSettings },
};

let teardown = null;
let main = null;

function navigate(hash) {
  if (location.hash === hash) route();
  else location.hash = hash;
}

function route() {
  const hash = ROUTES[location.hash] ? location.hash : '#/configure';
  document.querySelectorAll('.navitem').forEach((item) => {
    item.classList.toggle('is-on', item.dataset.route === hash);
  });
  if (teardown) {
    teardown();
    teardown = null;
  }
  const result = ROUTES[hash].render(main, store, navigate);
  if (typeof result === 'function') teardown = result;
}

function buildShell() {
  const root = document.getElementById('app');
  main = el('main', { class: 'main' });

  const nav = el('nav', { class: 'nav', 'aria-label': 'Primary' });
  for (const [hash, def] of Object.entries(ROUTES)) {
    nav.append(el('a', {
      class: 'navitem', href: hash, dataset: { route: hash },
    }, [def.title]));
  }

  const pin = el('a', { class: 'pin', href: '#/run', hidden: '' });

  root.append(
    el('div', { class: 'shell' }, [
      el('aside', { class: 'side' }, [
        el('div', { class: 'brand' }, ['TradingAgents ', el('em', {}, ['local'])]),
        nav,
        el('div', { class: 'pinlabel' }, ['Active run']),
        pin,
        el('div', { class: 'sidefoot' }, ['single user · localhost only']),
      ]),
      main,
    ]),
  );

  store.subscribe(() => patchPin(pin));
  patchPin(pin);
}

function patchPin(pin) {
  const { live } = store.state;
  if (!live.runId) {
    pin.hidden = true;
    return;
  }
  pin.hidden = false;
  clear(pin);
  const running = live.state === 'running';
  const done = Object.values(live.agents).filter((a) => a.status === 'done').length;
  const total = Object.keys(live.agents).length;
  pin.append(
    el('span', { class: 'pin-top' }, [
      el('i', { class: `livedot${running ? '' : ' off'}` }),
      el('span', { class: 'mono' }, [live.ticker || '…']),
      el('small', {}, [live.date || '']),
    ]),
    el('span', { class: 'pin-stage' }, [
      running
        ? `${done}/${total || '…'} agents done`
        : (live.state || '').toUpperCase(),
    ]),
    el('span', { class: 'pin-meta mono' }, [formatElapsed(live.stats.elapsed)]),
  );
}

async function boot() {
  buildShell();
  window.addEventListener('hashchange', route);

  try {
    const [providersPayload, configPayload, runsPayload] = await Promise.all([
      api.providers(), api.config(), api.runs(),
    ]);
    store.set('providers', providersPayload.providers);
    store.set('config', configPayload.config);
    store.set('lastUsed', configPayload.last_used || {});
    store.set('runs', runsPayload.runs);

    const active = runsPayload.active_run;
    if (active && active.run_id) {
      store.set('activeRun', active);
      store.resetLive(active.run_id);
      // Full replay from id 0 — reducers are idempotent.
      connectRunEvents(active.run_id, (type, data) => store.applyRunEvent(type, data));
      if (!location.hash) {
        location.hash = '#/run';
      }
    }
  } catch (error) {
    main.append(el('div', { class: 'card pad form-error' }, [
      `Could not reach the server: ${error.message}`,
    ]));
  }
  route();
}

boot();
