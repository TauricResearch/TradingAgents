// Configure ("New Run") view: per-run form mirroring the CLI selections.

import { el, clear } from '../dom.js';
import { api } from '../api.js';
import { connectRunEvents } from '../sse.js';

const ANALYSTS = [
  ['market', 'Market'],
  ['social', 'Sentiment'],
  ['news', 'News'],
  ['fundamentals', 'Fundamentals'],
];

const DEPTHS = [
  [1, 'Shallow'],
  [3, 'Medium'],
  [5, 'Deep'],
];

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

// Server accepts exactly 1 | 3 | 5; env overrides can put other values in the
// effective config, so clamp to the nearest preset.
function nearestDepth(value) {
  const n = Number(value) || 1;
  return DEPTHS.reduce((best, [v]) => (Math.abs(v - n) < Math.abs(best - n) ? v : best), 1);
}

export function renderConfigure(container, store, navigate) {
  const { providers, lastUsed, config } = store.state;
  clear(container);

  const defaults = {
    ticker: lastUsed.ticker || '',
    date: todayISO(),
    asset_type: lastUsed.asset_type || 'stock',
    analysts: lastUsed.analysts || ['market', 'social', 'news', 'fundamentals'],
    research_depth: nearestDepth(lastUsed.research_depth || config.max_debate_rounds || 1),
    provider: lastUsed.provider || config.llm_provider || 'openai',
    deep_think_llm: lastUsed.deep_think_llm || config.deep_think_llm || '',
    quick_think_llm: lastUsed.quick_think_llm || config.quick_think_llm || '',
    google_thinking_level: lastUsed.google_thinking_level || '',
    openai_reasoning_effort: lastUsed.openai_reasoning_effort || '',
    anthropic_effort: lastUsed.anthropic_effort || '',
    checkpoint_enabled: lastUsed.checkpoint_enabled ?? null,
  };

  const form = { ...defaults, analysts: [...defaults.analysts] };
  const errorBox = el('div', { class: 'form-error', hidden: '' });
  const keyNote = el('div', { class: 'key-note' });

  const tickerInput = el('input', {
    class: 'input mono', value: form.ticker, placeholder: 'NVDA',
    'aria-label': 'Ticker symbol', maxlength: '32',
    oninput: (e) => { form.ticker = e.target.value.toUpperCase(); },
  });
  const dateInput = el('input', {
    class: 'input mono', type: 'date', value: form.date,
    'aria-label': 'Trade date',
    oninput: (e) => { form.date = e.target.value; },
  });

  function segment(options, selected, onPick) {
    const wrap = el('div', { class: 'seg', role: 'group' });
    for (const [value, label] of options) {
      const button = el('button', {
        type: 'button',
        class: `seg-item${String(value) === String(selected) ? ' on' : ''}`,
        onclick: () => {
          onPick(value);
          wrap.querySelectorAll('.seg-item').forEach((b) => b.classList.remove('on'));
          button.classList.add('on');
        },
      }, [label]);
      wrap.append(button);
    }
    return wrap;
  }

  const analystChips = el('div', { class: 'chips' });
  for (const [key, label] of ANALYSTS) {
    const chip = el('button', {
      type: 'button',
      class: `chip${form.analysts.includes(key) ? ' on' : ''}`,
      onclick: () => {
        const idx = form.analysts.indexOf(key);
        if (idx >= 0) form.analysts.splice(idx, 1);
        else form.analysts.push(key);
        chip.classList.toggle('on');
      },
    }, [label]);
    analystChips.append(chip);
  }

  const providerSelect = el('select', {
    class: 'input', 'aria-label': 'LLM provider',
    onchange: (e) => {
      form.provider = e.target.value;
      syncProvider();
    },
  });
  for (const provider of providers) {
    providerSelect.append(el('option', {
      value: provider.key,
      ...(provider.key === form.provider ? { selected: '' } : {}),
    }, [provider.display]));
  }

  const deepSelect = el('select', { class: 'input mono', 'aria-label': 'Deep-think model' });
  const quickSelect = el('select', { class: 'input mono', 'aria-label': 'Quick-think model' });
  const deepCustom = el('input', {
    class: 'input mono', placeholder: 'custom model id', hidden: '',
    'aria-label': 'Custom deep-think model id',
  });
  const quickCustom = el('input', {
    class: 'input mono', placeholder: 'custom model id', hidden: '',
    'aria-label': 'Custom quick-think model id',
  });
  const backendField = el('div', { class: 'field wide', hidden: '' }, [
    el('label', { class: 'lab' }, ['Backend URL (write-only, never shown again)']),
    el('input', {
      class: 'input mono', placeholder: 'http://localhost:8000/v1',
      'aria-label': 'OpenAI-compatible base URL', id: 'backend-url',
    }),
  ]);

  function fillModels(select, custom, options, preferred) {
    clear(select);
    for (const option of options) {
      select.append(el('option', {
        value: option.value,
        ...(option.value === preferred ? { selected: '' } : {}),
      }, [option.label]));
    }
    if (!options.length) {
      select.append(el('option', { value: 'custom' }, ['Custom model ID']));
    }
    const sync = () => {
      custom.hidden = select.value !== 'custom';
    };
    select.onchange = sync;
    sync();
  }

  function currentProvider() {
    return providers.find((p) => p.key === form.provider) || null;
  }

  function syncProvider() {
    const provider = currentProvider();
    if (!provider) return;
    fillModels(deepSelect, deepCustom, provider.models.deep || [], form.deep_think_llm);
    fillModels(quickSelect, quickCustom, provider.models.quick || [], form.quick_think_llm);
    backendField.hidden = !provider.needs_backend_url;
    clear(keyNote);
    if (provider.key_status === 'missing') {
      keyNote.append(el('span', { class: 'key-missing' }, [
        `API key missing: add ${provider.key_env_var} to .env and restart the server.`,
      ]));
    } else if (provider.key_status === 'present') {
      keyNote.append(el('span', { class: 'key-ok' }, [`${provider.key_env_var} configured`]));
    } else if (provider.key_status === 'optional') {
      keyNote.append(el('span', { class: 'key-opt' }, [
        `${provider.key_env_var} optional (set it in .env for keyed endpoints)`,
      ]));
    } else {
      keyNote.append(el('span', { class: 'key-opt' }, ['No API key required']));
    }
  }

  function advancedSelect(label, values, current, onChange) {
    const select = el('select', { class: 'input', 'aria-label': label, onchange: (e) => onChange(e.target.value) });
    select.append(el('option', { value: '' }, ['provider default']));
    for (const value of values) {
      select.append(el('option', {
        value, ...(value === current ? { selected: '' } : {}),
      }, [value]));
    }
    return el('div', { class: 'field' }, [el('label', { class: 'lab' }, [label]), select]);
  }

  const checkpointSelect = el('select', { class: 'input', 'aria-label': 'Checkpoint resume' });
  for (const [value, label] of [['', 'server default'], ['true', 'enabled'], ['false', 'disabled']]) {
    checkpointSelect.append(el('option', {
      value,
      ...(String(form.checkpoint_enabled ?? '') === value ? { selected: '' } : {}),
    }, [label]));
  }

  const startButton = el('button', { class: 'btn primary', type: 'submit' }, ['Start Run']);

  async function submit(event) {
    event.preventDefault();
    errorBox.hidden = true;
    const provider = currentProvider();
    const body = {
      ticker: form.ticker.trim().toUpperCase(),
      date: form.date,
      asset_type: form.asset_type,
      analysts: ANALYSTS.map(([k]) => k).filter((k) => form.analysts.includes(k)),
      research_depth: Number(form.research_depth),
      provider: form.provider,
      deep_think_llm: deepSelect.value === 'custom' ? deepCustom.value.trim() : deepSelect.value,
      quick_think_llm: quickSelect.value === 'custom' ? quickCustom.value.trim() : quickSelect.value,
    };
    if (provider && provider.needs_backend_url) {
      const url = backendField.querySelector('input').value.trim();
      if (url) body.backend_url = url;
    }
    const advanced = {
      google_thinking_level: form.google_thinking_level,
      openai_reasoning_effort: form.openai_reasoning_effort,
      anthropic_effort: form.anthropic_effort,
    };
    for (const [key, value] of Object.entries(advanced)) {
      if (value) body[key] = value;
    }
    if (checkpointSelect.value) body.checkpoint_enabled = checkpointSelect.value === 'true';

    startButton.disabled = true;
    try {
      const run = await api.startRun(body);
      store.set('activeRun', run);
      store.resetLive(run.run_id);
      connectRunEvents(run.run_id, (type, data) => store.applyRunEvent(type, data));
      navigate('#/run');
    } catch (error) {
      errorBox.hidden = false;
      clear(errorBox);
      if (error.status === 409 && error.body && error.body.active_run_id) {
        errorBox.append('A run is already active. ', el('a', { href: '#/run' }, ['Open it →']));
      } else {
        errorBox.append(String(error.message));
      }
    } finally {
      startButton.disabled = false;
    }
  }

  const formEl = el('form', { class: 'card form-grid', onsubmit: submit }, [
    el('div', { class: 'field' }, [el('label', { class: 'lab' }, ['Ticker']), tickerInput]),
    el('div', { class: 'field' }, [el('label', { class: 'lab' }, ['Trade date']), dateInput]),
    el('div', { class: 'field' }, [
      el('label', { class: 'lab' }, ['Asset type']),
      segment([['stock', 'Stock'], ['crypto', 'Crypto']], form.asset_type,
        (v) => { form.asset_type = v; }),
    ]),
    el('div', { class: 'field' }, [
      el('label', { class: 'lab' }, ['Research depth']),
      segment(DEPTHS, form.research_depth, (v) => { form.research_depth = v; }),
    ]),
    el('div', { class: 'field wide' }, [el('label', { class: 'lab' }, ['Analysts']), analystChips]),
    el('div', { class: 'field wide' }, [
      el('label', { class: 'lab' }, ['LLM provider']), providerSelect, keyNote,
    ]),
    el('div', { class: 'field' }, [
      el('label', { class: 'lab' }, ['Deep-think model']), deepSelect, deepCustom,
    ]),
    el('div', { class: 'field' }, [
      el('label', { class: 'lab' }, ['Quick-think model']), quickSelect, quickCustom,
    ]),
    backendField,
    el('details', { class: 'field wide advanced' }, [
      el('summary', {}, ['Advanced']),
      el('div', { class: 'advanced-grid' }, [
        advancedSelect('Google thinking level', ['high', 'minimal'],
          form.google_thinking_level, (v) => { form.google_thinking_level = v; }),
        advancedSelect('OpenAI reasoning effort', ['low', 'medium', 'high'],
          form.openai_reasoning_effort, (v) => { form.openai_reasoning_effort = v; }),
        advancedSelect('Anthropic effort', ['low', 'medium', 'high'],
          form.anthropic_effort, (v) => { form.anthropic_effort = v; }),
        el('div', { class: 'field' }, [el('label', { class: 'lab' }, ['Checkpoint resume']), checkpointSelect]),
      ]),
    ]),
    el('div', { class: 'form-foot wide' }, [
      startButton,
      el('small', {}, ['Runs locally · API keys are read from .env']),
    ]),
    errorBox,
  ]);

  container.append(
    el('div', { class: 'pagehead' }, [
      el('h2', {}, ['New Run']),
      el('p', {}, ['Configure and launch an analysis pipeline']),
    ]),
    formEl,
  );
  syncProvider();
}
