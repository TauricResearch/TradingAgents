// Reports view: master-detail — run history list on the left, article-style
// reading column on the right.

import { el, clear, decisionClass } from '../dom.js';
import { api } from '../api.js';
import { setMarkdown } from '../markdown.js';
import { SECTION_ORDER, SECTION_TITLES } from '../store.js';

export function renderReports(container, store) {
  clear(container);
  const list = el('div', { class: 'runlist card' }, [el('header', {}, ['Run history'])]);
  const reader = el('article', { class: 'reader card-dark' }, [
    el('div', { class: 'empty' }, ['Select a run to read its report.']),
  ]);

  async function refresh() {
    try {
      const payload = await api.runs();
      store.set('runs', payload.runs);
      renderList(payload.runs);
    } catch (error) {
      clear(list);
      list.append(el('header', {}, ['Run history']), el('div', { class: 'empty' }, [String(error.message)]));
    }
  }

  function renderList(runs) {
    clear(list);
    list.append(el('header', {}, ['Run history']));
    if (!runs.length) {
      list.append(el('div', { class: 'empty' }, ['No completed runs yet.']));
      return;
    }
    for (const run of runs) {
      const row = el('button', { class: 'runrow', type: 'button' }, [
        el('div', {}, [
          el('span', { class: 'tick mono' }, [run.ticker]),
          el('span', { class: 'date mono' }, [
            `${run.date}${run.source === 'cli' ? ' · cli' : ''}`,
          ]),
        ]),
        el('span', { class: `dec ${decisionClass(run.decision)}` }, [
          run.decision || (run.status === 'failed' ? 'FAILED' : '—'),
        ]),
      ]);
      row.addEventListener('click', () => {
        list.querySelectorAll('.runrow').forEach((r) => r.classList.remove('is-sel'));
        row.classList.add('is-sel');
        openReport(run);
      });
      list.append(row);
    }
  }

  async function openReport(run) {
    clear(reader);
    reader.append(el('div', { class: 'empty' }, ['Loading…']));
    let report;
    try {
      report = await api.report(run.ticker, run.date);
    } catch (error) {
      clear(reader);
      reader.append(el('div', { class: 'empty' }, [String(error.message)]));
      return;
    }
    store.set('report', report);
    clear(reader);

    const manifest = report.manifest || {};
    const decision = manifest.decision || run.decision;
    const meta = [];
    if (manifest.provider) meta.push(manifest.provider);
    if (manifest.deep_think_llm) meta.push(manifest.deep_think_llm);
    if (manifest.duration_seconds) meta.push(`${Math.round(manifest.duration_seconds)}s`);

    reader.append(el('div', { class: `banner ${decisionClass(decision)}` }, [
      el('span', { class: 'verdict' }, [decision || '—']),
      el('div', { class: 'sub' }, [
        el('b', {}, [`${report.ticker} · ${report.date}`]),
        el('span', {}, [meta.join(' · ')]),
      ]),
    ]));

    const body = el('div', { class: 'reader-body' });
    let rendered = 0;
    for (const section of SECTION_ORDER) {
      const markdown = report.sections[section];
      if (!markdown) continue;
      rendered += 1;
      const content = el('div', { class: 'report-body' });
      setMarkdown(content, markdown);
      body.append(el('section', { class: 'reader-sec' }, [
        el('h5', {}, [SECTION_TITLES[section]]),
        content,
      ]));
    }
    if (!rendered && report.complete_report) {
      const content = el('div', { class: 'report-body' });
      setMarkdown(content, report.complete_report);
      body.append(el('section', { class: 'reader-sec' }, [content]));
    }
    if (!rendered && !report.complete_report) {
      body.append(el('div', { class: 'empty' }, ['This run has no report files.']));
    }
    reader.append(body);
  }

  container.append(
    el('div', { class: 'pagehead' }, [
      el('h2', {}, ['Reports']),
      el('p', {}, ['Completed runs and final decisions']),
    ]),
    el('div', { class: 'reports-grid' }, [list, reader]),
  );
  refresh();
}
