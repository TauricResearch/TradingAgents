// Read-only settings panel: key presence, paths, effective non-secret
// defaults. There is no settings editor in v1 — keys live in .env.

import { el, clear } from '../dom.js';

const STATUS_LABEL = {
  present: 'configured',
  missing: 'missing',
  'not-required': 'not required',
  optional: 'optional',
};

export function renderSettings(container, store) {
  clear(container);
  const { providers, config } = store.state;

  const keysTable = el('table', { class: 'kv' });
  for (const provider of providers) {
    keysTable.append(el('tr', {}, [
      el('td', {}, [provider.display]),
      el('td', { class: 'mono' }, [provider.key_env_var || '—']),
      el('td', { class: `key-${provider.key_status}` }, [
        STATUS_LABEL[provider.key_status] || provider.key_status,
      ]),
    ]));
  }

  const configTable = el('table', { class: 'kv' });
  for (const [key, value] of Object.entries(config)) {
    configTable.append(el('tr', {}, [
      el('td', { class: 'mono' }, [key]),
      el('td', { class: 'mono' }, [value === null ? '—' : String(value)]),
    ]));
  }

  container.append(
    el('div', { class: 'pagehead' }, [
      el('h2', {}, ['Settings']),
      el('p', {}, ['Read-only. Keys and overrides live in .env — restart the server after edits.']),
    ]),
    el('div', { class: 'card pad' }, [el('h3', {}, ['API keys']), keysTable]),
    el('div', { class: 'card pad' }, [el('h3', {}, ['Effective defaults']), configTable]),
  );
}
