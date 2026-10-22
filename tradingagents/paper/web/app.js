/* Koral Equities research desk. No brokerage, simulated ledger only. */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const money = (x, decimals = 2) => new Intl.NumberFormat('en-GB', {style:'currency',currency:'GBP',minimumFractionDigits:decimals,maximumFractionDigits:decimals}).format(Number(x) || 0);
  const signedMoney = (x) => `${Number(x) > 0 ? '+' : Number(x) < 0 ? '−' : ''}${money(Math.abs(Number(x) || 0))}`;
  const percentage = (x, n = 2) => `${(Number(x) || 0).toFixed(n)}%`;
  const number = (x, digits = 2) => (Number(x) || 0).toLocaleString('en-GB',{minimumFractionDigits:digits,maximumFractionDigits:digits});
  const escapeHtml = (x) => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const dateText = (x) => x ? String(x).slice(0,10) : '—';
  const byId = (id, value) => {const element = $(id); if(element) element.textContent = value;};
  let state = null;
  let period = 'ALL';
  let activeTab = 'positions';
  let wasRunning = false;
  let toastTimer = null;
  let currentScanId = null;
  let acknowledgedScanId = null;
  try { acknowledgedScanId = sessionStorage.getItem('koral-equities-acknowledged-scan'); } catch (_) { /* Private browsing may restrict storage. */ }

  const icon = (name) => `<svg aria-hidden="true"><use href="#i-${name}"></use></svg>`;
  function dismissToast() {
    clearTimeout(toastTimer);
    $('toast').classList.remove('visible');
  }
  function notify(message, error = false) {
    const node = $('toast');
    // An error requiring acknowledgement must not be overwritten by a routine refresh.
    if (!error && node.classList.contains('error') && node.classList.contains('visible')) return;
    byId('toast-message', message);
    node.classList.toggle('error', error);
    node.classList.add('visible');
    $('toast-ok').hidden = !error;
    clearTimeout(toastTimer);
    // Errors remain until OK is pressed; routine success notices may disappear.
    if (!error) toastTimer = setTimeout(() => node.classList.remove('visible'), 5400);
  }
  function acknowledgeScan() {
    if (currentScanId) {
      acknowledgedScanId = currentScanId;
      try { sessionStorage.setItem('koral-equities-acknowledged-scan', currentScanId); } catch (_) { /* Memory still tracks acknowledgement for this page. */ }
    }
    $('scan-progress').classList.remove('active', 'scan-failed');
    $('ack-scan').hidden = true;
  }
  function scanFailureHint(log) {
    if (log.includes('OPENAI_API_KEY') && log.includes('openai')) {
      return 'AI access is configured for the OpenAI API. If you signed in with ChatGPT, save TRADINGAGENTS_LLM_PROVIDER=chatgpt in your project .env file and restart the dashboard. Never paste API keys here.';
    }
    return '';
  }
  function clock() {
    const d = new Date();
    const now = new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',hour:'2-digit',minute:'2-digit',hour12:false}).format(d);
    $('market-clock').innerHTML = `<span class="tiny-dot"></span><span>NEW YORK · ${escapeHtml(now)} ET</span>`;
  }
  function renderMetrics(data) {
    const a = data.account;
    byId('equity-value', money(a.equity_gbp));
    byId('equity-sub', a.last_session ? `Last priced: ${dateText(a.last_session)}` : `Simulated account since ${dateText(a.started)}`);
    byId('return-value', signedMoney(a.return_gbp));
    byId('return-percent', `${a.return_pct >= 0 ? '+' : ''}${percentage(a.return_pct)}`);
    $('return-percent').className = 'delta ' + (a.return_pct > 0 ? 'delta-pos' : a.return_pct < 0 ? 'delta-neg' : 'delta-flat');
    byId('cash-value', money(a.cash_gbp));
    byId('cash-share', a.equity_gbp > 0 ? `${percentage(100 * a.cash_gbp / a.equity_gbp,0)} of equity` : 'GBP cash');
    const wins = data.closed.filter(t => Number(t.pnl_gbp) > 0).length;
    byId('win-value', data.closed.length ? percentage(100 * wins / data.closed.length,1) : '—');
    byId('win-count', data.closed.length ? `${wins} wins / ${data.closed.length} closed` : 'No closed trades');
    byId('risk-value', percentage(a.risk_per_trade_pct,1));
    byId('drawdown-value', percentage(a.drawdown_pct));
    byId('positions-value', `${a.positions_count} / ${a.max_positions}`);
    byId('orders-value', String(a.pending_count));
    $('risk-status').innerHTML = `<span class="tiny-dot" style="background:${a.halted ? '#d7855b' : '#58b18a'}"></span> ${a.halted ? 'HALTED' : 'Operational'}`;
    $('risk-status').style.color = a.halted ? '#b16b47' : '#208254';
    byId('mandate-single', percentage(a.risk_per_trade_pct,1));
    byId('mandate-aggregate', percentage(a.max_combined_risk_pct,1));
    byId('mandate-alloc', percentage(a.max_name_pct,1));
    byId('mandate-halt', percentage(a.max_drawdown_pct,1));
    byId('asof-label', a.last_session ? `As of ${dateText(a.last_session)} · EOD` : 'Awaiting first session');
    byId('footer-sync', a.last_session ? `LAST SESSION ${dateText(a.last_session)}` : 'AWAITING FIRST PAPER SESSION');
    const scanButton = $('scan-btn');
    scanButton.title = a.analysis_available ? 'Launch an AI research cycle on completed data' : `Paper trading first becomes available at 17:30 New York time after ${a.started}`;
    scanButton.disabled = !a.analysis_available;
    document.querySelector('.mode-name').innerHTML = `<span class="live-dot"></span> ${a.halted ? 'RISK HALT · PAPER' : 'PAPER ENVIRONMENT'}`;
    document.querySelector('.mode-sub').textContent = a.halted ? 'New positions disabled by drawdown guard' : '100% simulated · No broker connected';
  }
  function equityChart(data) {
    let rows = [...data.history].filter(p => p.date && Number.isFinite(Number(p.equity_gbp)) && Number.isFinite(Number(p.spy_benchmark_gbp)))
      .sort((a,b)=>a.date.localeCompare(b.date));
    if(period !== 'ALL' && rows.length) {
      const last = new Date(rows[rows.length - 1].date + 'T12:00:00Z');
      const days = period === '30D' ? 30 : 90;
      const cutoff = new Date(last.valueOf() - (days - 1) * 86400000);
      rows = rows.filter(row => new Date(row.date + 'T12:00:00Z') >= cutoff);
    }
    const element = $('chart-container');
    byId('chart-range', rows.length ? `${dateText(rows[0].date)} — ${dateText(rows[rows.length - 1].date)}` : 'NO SESSIONS PROCESSED');
    if(!rows.length) {
      element.innerHTML = '<div class="chart-empty"><span class="chart-empty-symbol">◌</span><strong>Performance begins here.</strong><p>After the first completed market session, every paper portfolio mark will appear here. No simulated profit is invented.</p></div>';
      return;
    }
    const w = 880, h = 330, left=72, right=18, top=18, bottom=39, plotW=w-left-right, plotH=h-top-bottom;
    const values = rows.flatMap(row => [Number(row.equity_gbp), Number(row.spy_benchmark_gbp)]);
    let lo = Math.min(...values), hi = Math.max(...values);
    const padding = Math.max(60, (hi-lo)*.14, hi*.006);
    lo-=padding; hi+=padding;
    const x = (i) => left + (rows.length === 1 ? plotW/2 : i*plotW/(rows.length-1));
    const y = (v) => top + plotH*(hi-v)/(hi-lo);
    const line = (key) => rows.map((row,i)=>`${i===0?'M':'L'}${x(i).toFixed(1)} ${y(Number(row[key])).toFixed(1)}`).join(' ');
    const portfolioLine = line('equity_gbp'), benchLine=line('spy_benchmark_gbp');
    const bottomY = top+plotH;
    const fillPath = `${portfolioLine} L ${x(rows.length-1).toFixed(1)} ${bottomY} L ${x(0).toFixed(1)} ${bottomY} Z`;
    const ticks = Array.from({length:5},(_,i)=>lo+(hi-lo)*i/4).reverse();
    const grid = ticks.map(t=>`<line x1="${left}" x2="${w-right}" y1="${y(t)}" y2="${y(t)}" stroke="#eef2ee" stroke-width="1"/><text x="${left-12}" y="${y(t)+4}" fill="#a0ada3" font-size="11" text-anchor="end" font-family="ui-monospace,monospace">${escapeHtml('£'+Math.round(t).toLocaleString('en-GB'))}</text>`).join('');
    const startDate = rows[0].date, endDate=rows[rows.length-1].date;
    element.innerHTML = `
      <svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="Paper equity and SPY price benchmark since first session">
        <defs><linearGradient id="equityTint" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#1d9e68" stop-opacity=".16"/><stop offset="100%" stop-color="#1d9e68" stop-opacity="0"/></linearGradient></defs>
        ${grid}
        <path d="${fillPath}" fill="url(#equityTint)"/>
        <path d="${benchLine}" fill="none" stroke="#b5c1ba" stroke-width="2" stroke-dasharray="6 6" vector-effect="non-scaling-stroke"/>
        <path d="${portfolioLine}" fill="none" stroke="#168757" stroke-width="3" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>
        <circle cx="${x(rows.length-1)}" cy="${y(Number(rows[rows.length-1].equity_gbp))}" r="5" fill="#168757" stroke="#fff" stroke-width="3" vector-effect="non-scaling-stroke"/>
        <text x="${left}" y="${h-11}" font-size="11" fill="#9eaaa1" text-anchor="start">${escapeHtml(startDate)}</text>
        <text x="${w-right}" y="${h-11}" font-size="11" fill="#9eaaa1" text-anchor="end">${escapeHtml(endDate)}</text>
        <line id="chart-hoverline" x1="0" x2="0" y1="${top}" y2="${bottomY}" stroke="#9ac3a9" stroke-dasharray="3 5" opacity="0"/>
        <rect id="chart-interaction" x="${left}" y="${top}" width="${plotW}" height="${plotH}" fill="transparent" style="cursor:crosshair"/>
      </svg>`;
    const svg = element.querySelector('svg');
    const hoverline = svg.querySelector('#chart-hoverline');
    const rect = svg.querySelector('#chart-interaction');
    const tooltip = document.createElement('div');tooltip.className='chart-tooltip';tooltip.style.display='none';element.appendChild(tooltip);
    rect.addEventListener('mousemove',(event)=>{
      const bounds=rect.getBoundingClientRect();
      const ratio=Math.max(0,Math.min(1,(event.clientX-bounds.left)/bounds.width));
      const i=Math.max(0,Math.min(rows.length-1,Math.round(ratio*(rows.length-1))));
      const row=rows[i];
      const pointX=x(i);
      hoverline.setAttribute('x1',String(pointX));hoverline.setAttribute('x2',String(pointX));hoverline.setAttribute('opacity','1');
      tooltip.innerHTML=`<b>${escapeHtml(row.date)}</b><br>Portfolio&nbsp; ${escapeHtml(money(row.equity_gbp))}<br>SPY&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; ${escapeHtml(money(row.spy_benchmark_gbp))}`;
      tooltip.style.display='block';
      tooltip.style.left=`${Math.min(bounds.width+10,Math.max(100,event.clientX-element.getBoundingClientRect().left))}px`;
      tooltip.style.top=`${Math.max(61,event.clientY-element.getBoundingClientRect().top)}px`;
    });
    rect.addEventListener('mouseleave',()=>{tooltip.style.display='none';hoverline.setAttribute('opacity','0')});
  }
  const eventTypes = {
    BUY_FILLED:['BUY FILLED','success','↗'],SELL_FILLED:['SELL FILLED','success','↙'],
    ORDER_QUEUED:['ORDER QUEUED','neutral','+'],ORDER_REJECTED:['ORDER REJECTED','failure','!'],
    AGENT_RATING:['AI DECISION','neutral','◈'],AGENT_ERROR:['MODEL ERROR','failure','!'],
    DRAWDOWN_HALT:['RISK HALT','failure','!'],IGNORED_DUPLICATE:['DUPLICATE IGNORED','warning','·'],
    V1_UNSTRUCTURED_ENTRY_BLOCKED:['RESEARCH ONLY','warning','!'],
    SESSION_MARK:['MARK TO MARKET','neutral','◌'],NO_ORDER:['NO TRADE','neutral','–']
  };
  function renderActivity(data) {
    const events = data.events.filter(e=>!['NO_ORDER','SESSION_MARK'].includes(e.type)).slice(0,22);
    byId('event-count', `${data.events.length}${data.events.length>=100?'+':''} RECENT EVENTS`);
    const list=$('activity-list');
    if(!events.length) {list.innerHTML=`<div class="list-empty">${icon('terminal')}<strong>No activity recorded yet</strong><p>AI decisions and simulated fills appear here after the first eligible scan.</p></div>`;return;}
    list.innerHTML=events.map(e=>{
      const [title,kind,mark]=eventTypes[e.type] || [String(e.type || 'EVENT').replaceAll('_',' '),'neutral','·'];
      const detail=[e.ticker,e.rating,e.shares!=null?`${e.shares} shares`:null,e.reason,e.pnl_gbp!=null?signedMoney(e.pnl_gbp):null].filter(x=>x!==undefined&&x!==null&&String(x).length).join(' · ');
      return `<div class="activity-row"><span class="activity-symbol ${kind}">${escapeHtml(mark)}</span><div class="activity-row-content"><b>${escapeHtml(title)}</b><span>${escapeHtml(detail||'Portfolio ledger event')}</span></div><span class="activity-date">${escapeHtml(dateText(e.date))}</span></div>`;
    }).join('');
  }
  function renderRatings(data) {
    const ratings=new Map(data.ratings.map(r=>[r.ticker,r]));
    byId('ratings-count', `${data.ratings.length} RATINGS`);
    const list=$('ratings-list');
    list.innerHTML=data.watchlist.map(ticker=>{
      const decision=ratings.get(ticker),label=decision?.rating||'AWAITING';
      const css=label.toLowerCase().replace(/[^a-z]/g,'');
      return `<div class="rating-row"><div class="rating-label"><div class="ticker-mark">${escapeHtml(ticker.slice(0,2))}</div><div><strong>${escapeHtml(ticker)}</strong><small>${decision ? 'Analysed ' + escapeHtml(dateText(decision.date)) : 'No AI analysis recorded'}</small></div></div><span class="rating-pill ${css}">${escapeHtml(label)}</span></div>`;
    }).join('');
  }
  const tabs = {
    positions: {
      headers:['SYMBOL','SHARES','ENTRY (USD)','MARK (USD)','STOP (USD)','VALUE (GBP)','UNREALISED (GBP)'],
      fields:(p)=>[p.ticker,p.shares,number(p.entry_usd),number(p.mark_usd),number(p.stop_usd),money(p.value_gbp),signedMoney(p.unrealized_gbp)],
      empty:'No open paper positions yet', detail:'When an AI buy is accepted, the next-session paper fill appears here.'
    },
    orders: {
      headers:['ORDER','SYMBOL','SIDE','CREATED','RATING','INITIAL STOP (USD)'],
      fields:(p)=>[p.id,p.ticker,p.side,p.created,p.rating,p.stop_usd == null ? '—' : number(p.stop_usd)],
      empty:'No orders waiting', detail:'Accepted AI signals queue for the next trading session, never the same close.'
    },
    closed: {
      headers:['SYMBOL','SHARES','ENTRY','EXIT','REASON','P&L (GBP)','RETURN'],
      fields:(p)=>[p.ticker,p.shares,p.entry_date,p.exit_date,p.reason,signedMoney(p.pnl_gbp),percentage(100*Number(p.return_fraction))],
      empty:'No closed trades yet', detail:'Completed paper trades will build your full, auditable journal.'
    }
  };
  function portfolioTable(data) {
    const spec=tabs[activeTab],rows=activeTab==='positions'?data.positions:activeTab==='orders'?data.orders:[...data.closed].reverse();
    $('export-link').href=activeTab==='closed'?'/api/export/closed':'/api/export/positions';
    $('export-link').style.display=activeTab==='orders'?'none':'inline-flex';
    const target=$('portfolio-table');
    if(!rows.length){target.innerHTML=`<div class="table-empty">${icon('briefcase')}<strong>${escapeHtml(spec.empty)}</strong><span>${escapeHtml(spec.detail)}</span></div>`;return;}
    target.innerHTML=`<table class="data-table"><thead><tr>${spec.headers.map(h=>`<th scope="col">${escapeHtml(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${spec.fields(row).map((cell,i)=>{const pnlColumn=(activeTab==='positions'&&i===6)||(activeTab==='closed'&&i===5);const raw=activeTab==='positions'?row.unrealized_gbp:row.pnl_gbp;const cls=pnlColumn?(Number(raw)>0?'positive':Number(raw)<0?'negative':''):i===0?'strong':'';return `<td><span class="${cls}">${escapeHtml(cell)}</span></td>`}).join('')}</tr>`).join('')}</tbody></table>`;
  }
  function renderReports(data) {
    const element=$('report-links');
    byId('journal-description',data.reports.length ? `${data.reports.length} saved AI reports · open each report in a new browser tab.` : 'Saved analyst reports appear after a completed AI scan.');
    if(!data.reports.length) {element.innerHTML='<span class="muted">No reports yet</span>';return;}
    element.innerHTML=data.reports.slice(0,5).map(r=>{
      const url=String(r.url||'');
      if(!url.startsWith('/reports/')||!url.endsWith('/complete_report.html'))return '';
      return `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(r.name)} ↗</a>`;
    }).join('');
  }
  function render(data) {
    state = data;
    renderMetrics(data);
    equityChart(data);
    renderActivity(data);
    renderRatings(data);
    portfolioTable(data);
    renderReports(data);
  }
  async function refresh(silent=false) {
    try {
      const response=await fetch('/api/state',{cache:'no-store'});
      const body=await response.json();
      if(!response.ok) throw new Error(body.error||'Unable to read the paper ledger');
      render(body);
      if(!silent) notify('Paper portfolio refreshed');
    } catch(err) {if(!silent) notify(err.message,true);else console.warn('Dashboard refresh:',err.message);}
  }
  async function updateScan() {
    try {
      const response=await fetch('/api/scan-status',{cache:'no-store'});
      if (!response.ok) throw new Error('Scan status HTTP ' + response.status);
      const data=await response.json();
      const progress=$('scan-progress');
      currentScanId = data.started_at || null;
      const dismissed = Boolean(currentScanId && currentScanId === acknowledgedScanId);
      const finished = Boolean(data.finished);
      const failed = finished && data.returncode !== 0;
      const showReport = finished && !dismissed;
      const text = data.log || (data.running ? 'Loading agents…' : 'No scan log was recorded.');
      progress.classList.toggle('active', Boolean(data.running || showReport));
      progress.classList.toggle('scan-failed', Boolean(failed && showReport));
      $('ack-scan').hidden = !showReport;
      byId('scan-progress-log', text);
      const hint=failed ? scanFailureHint(text) : '';
      byId('scan-progress-guide',hint);
      $('scan-progress-guide').hidden=!Boolean(hint) || dismissed;
      if (data.running) {
        byId('scan-progress-status','AGENTS ANALYSING');
        byId('scan-progress-description','TradingAgents is reviewing your stocks. The dashboard will update when finished.');
        $('scan-btn').disabled=true;
        wasRunning=true;
      } else {
        if(state) $('scan-btn').disabled=!state.account.analysis_available;
        if (showReport) {
          byId('scan-progress-status',failed ? 'SCAN ERROR' : 'SCAN COMPLETE');
          byId('scan-progress-description',failed ?
            'The scan stopped. The complete log stays here until you press OK.' :
            'The research cycle finished. Review the log, then press OK.');
        }
        if (wasRunning && finished) {
          wasRunning=false;
          await refresh(true);
          if (!failed) notify('AI research cycle complete. Paper ledger updated.');
        }
      }
    } catch(e){
      console.warn('Scan status unavailable',e);
      notify('Unable to read the scan status. Check that Koral Equities is still running.',true);
    }
  }
  async function beginScan(event) {
    event.preventDefault();
    const input=$('scan-tickers').value.trim();
    const tickers=input.toUpperCase().split(/[\s,]+/).filter(Boolean);
    if(!tickers.length||tickers.length>25||new Set(tickers).size!==tickers.length||tickers.some(t=>! /^[A-Z0-9.\-]{1,16}$/.test(t))){notify('Enter 1–25 unique valid stock tickers',true);return;}
    $('confirm-scan').disabled=true;
    try {
      const response=await fetch('/api/scan',{method:'POST',headers:{'Content-Type':'application/json','X-Koral-Action':'scan'},body:JSON.stringify({tickers})});
      const result=await response.json();
      if(!response.ok)throw new Error(result.error||'Unable to start scan');
      $('scan-dialog').close();
      wasRunning=true;
      notify('Paper research started. No real trades will be placed.');
      await updateScan();
    }catch(err){notify(err.message,true)}finally{$('confirm-scan').disabled=false;}
  }

  /* Independent market discovery: no paper orders, position changes or signals. */
  let discoveryWasRunning = false;
  let discoveryAcknowledged = null;
  let discoveryCurrentId = null;
  try { discoveryAcknowledged = sessionStorage.getItem('koral-discovery-ack'); }
  catch (_) { /* Storage may be blocked in private windows. */ }
  const moneyUS = (value) => {
    const amount = Number(value);
    if (!Number.isFinite(amount) || value === null || value === undefined) return '—';
    if (amount >= 1e9) return '$' + (amount / 1e9).toFixed(2) + 'B';
    if (amount >= 1e6) return '$' + (amount / 1e6).toFixed(0) + 'M';
    return '$' + Math.round(amount).toLocaleString('en-US');
  };
  const percentUS = (value) =>
    value == null || !Number.isFinite(Number(value)) ? '—' :
    (100 * Number(value)).toFixed(1) + '%';

  async function refreshDiscovery() {
    try {
      const response = await fetch('/api/discovery/state', {cache:'no-store'});
      if (!response.ok) throw new Error('Discovery snapshot unavailable');
      const view = await response.json();
      const candidates = Array.isArray(view.candidates) ? view.candidates : [];
      const reports = new Map((view.ai_reports || []).map(report => [report.ticker, report]));
      byId('discovery-coverage', view.universe_scanned != null ?
        Number(view.universe_scanned).toLocaleString('en-GB') + ' / ' +
        Number(view.universe_total).toLocaleString('en-GB') : '—');
      byId('discovery-count', view.candidates ? String(candidates.length) : '—');
      byId('discovery-analysed',
        String((view.ai_reports || []).filter(report => report.status === 'completed').length));
      byId('discovery-date', view.generated_at_utc ?
        String(view.generated_at_utc).slice(0, 10) : '—');
      byId('discovery-asof', view.generated_at_utc ?
        (view.sampled_not_exhaustive ? 'SAMPLED · ' : '') + 'SNAPSHOT ' +
        String(view.generated_at_utc).slice(0, 16).replace('T', ' ') + ' UTC' :
        'No scan recorded');
      const place = $('discovery-results');
      if (!place) return;
      if (!candidates.length) {
        place.innerHTML = '<div class="discovery-empty">' +
          (view.generated_at_utc ?
          'No stocks passed this particular sample. Try another or a larger universe. This does not prove no opportunities exist.' :
          'No companies shortlisted yet. Select a scan depth and choose <strong>Discover stocks</strong>.') +
          '</div>';
        return;
      }
      place.innerHTML = candidates.map((company) => {
        const diligence = company.valuation_v2 || null;
        const hurdle = diligence?.ten_x?.annualised_shareholder_return_hurdle_pct;
        const method = diligence?.valuation_method || 'Older snapshot — rerun Discovery for V2';
        const filings = diligence?.source?.primary_filing_lookup;
        const filingNote = filings?.status === 'AVAILABLE' ?
          'SEC metadata linked; numbers not reconciled' : 'Primary filing verification unavailable';
        const firstGap = diligence?.required_primary_evidence?.[0] || 'Audit company filings and assumptions';
        const firstRisk = diligence?.risk_flags?.[0] || '';
        const secUrl = filings?.filings?.[0]?.url || '';
        const secValid = /^https:\/\/www\.sec\.gov\/Archives\/edgar\/data\/[0-9]+\/[0-9]+\/[A-Za-z0-9._-]+$/.test(secUrl);
        const secLink = secValid ?
          ' · <a href="' + escapeHtml(secUrl) + '" target="_blank" rel="noopener noreferrer">SEC filing ↗</a>' : '';
        const report = reports.get(company.ticker);
        const reportValid=report?.report_url && /^\/discovery\/reports\/[0-9]{8}T[0-9]{6}Z\/[A-Z0-9.-]+\/complete_report\.html$/.test(report.report_url);
        const memoValid=report?.memo_url && /^\/discovery\/reports\/[0-9]{8}T[0-9]{6}Z\/[A-Z0-9.-]+\/compounder_memo\.md$/.test(report.memo_url);
        const reportLink = reportValid ?
          '<a href="' + escapeHtml(report.report_url) +
          '" target="_blank" rel="noopener noreferrer">AI committee ↗</a>' :
          (report?.status === 'failed' ? 'AI research unavailable' : 'No AI report yet');
        const memoLink = memoValid ?
          ' · <a href="' + escapeHtml(report.memo_url) +
          '" target="_blank" rel="noopener noreferrer">Five-year thesis ↗</a>' : '';
        return '<article class="discovery-candidate">' +
          '<div class="discovery-name"><div><strong>' + escapeHtml(company.ticker) + '</strong>' +
          '<small>' + escapeHtml(company.company || 'Listed company') + '</small></div>' +
          '<span class="discovery-rank">SCORE ' + escapeHtml(company.research_score) + '</span></div>' +
          '<div class="discovery-metrics">' +
          '<div><span>MARKET CAP</span><b>' + escapeHtml(moneyUS(company.market_cap_usd)) + '</b></div>' +
          '<div><span>VENDOR SALES GROWTH</span><b>' + escapeHtml(percentUS(company.revenue_growth_vendor)) + '</b></div>' +
          '<div><span>CASH FLOW</span><b>' + escapeHtml(moneyUS(company.free_cash_flow_usd)) + '</b></div></div>' +
           '<div class="discovery-scenario"><span class="scenario-label">FIVE-YEAR 10× HURDLE · NOT A FORECAST</span>' +
           '<strong>' + escapeHtml(hurdle == null ? '—' : hurdle + '% PER YEAR') + '</strong></div>' +
           '<div class="discovery-underwriting">' +
           '<div><b>APPROPRIATE VALUATION METHOD</b><span>' + escapeHtml(method) + '</span></div>' +
           '<div><b>TENFOLD THESIS</b><span>' + escapeHtml(diligence?.rating || 'OLDER SCAN — RERUN') + '</span></div>' +
           '<div><b>REGULATORY SOURCES</b><span>' + escapeHtml(filingNote) + secLink + '</span></div>' +
           '<div><b>REQUIRED DILIGENCE</b><span>' + escapeHtml(firstGap) + '</span></div>' +
           (firstRisk ? '<div><b>RISK FLAG</b><span>' + escapeHtml(firstRisk) + '</span></div>' : '') +
           '</div>' +
          '<div class="discovery-ai-result"><span>' + escapeHtml(company.sector || 'Sector unverified') +
          (report?.rating ? ' · ' + escapeHtml(report.rating) : ' · Research only') +
          '</span><span>' + reportLink + memoLink + '</span></div>' +
          '</article>';
      }).join('');
    } catch(error) {
      console.warn('Discovery snapshot:', error);
    }
  }

  async function updateDiscoveryStatus() {
    try {
      const response = await fetch('/api/discovery/status', {cache:'no-store'});
      if (!response.ok) throw new Error('Discovery status unavailable');
      const data = await response.json();
      const panel = $('discovery-progress');
      discoveryCurrentId = data.started_at || null;
      const acknowledged = Boolean(discoveryCurrentId && discoveryCurrentId === discoveryAcknowledged);
      const showing = Boolean(data.running || (data.finished && !acknowledged));
      panel.hidden = !showing;
      panel.classList.toggle('failed', Boolean(data.finished && data.returncode !== 0 && !acknowledged));
      $('discovery-dismiss').hidden = Boolean(data.running) || !showing;
      byId('discovery-log', data.log || (data.running ? 'Research starting…' : 'No scan log recorded'));
      byId('discovery-stage', data.running ? 'DISCOVERY IN PROGRESS' :
        data.returncode === 0 ? 'DISCOVERY FINISHED — REVIEW RESULTS' : 'DISCOVERY ERROR — REVIEW LOG');
      $('discover-btn').disabled = Boolean(data.running);
      if (data.running) discoveryWasRunning = true;
      if (discoveryWasRunning && data.finished) {
        discoveryWasRunning = false;
        await refreshDiscovery();
        if (data.returncode !== 0) notify('Discovery stopped. Check the persistent log.', true);
      }
    } catch(error) {
      console.warn('Discovery status:', error);
      notify('Discovery status unavailable. Check the local Koral Equities server.', true);
    }
  }

  async function beginDiscovery() {
    const max_symbols = Number($('discovery-size').value);
    const ai = Number($('discovery-ai').value);
    if (![200, 350, 800, 1500].includes(max_symbols) || ![0, 1, 2, 3].includes(ai)) {
      notify('Choose a supported discovery configuration.', true);
      return;
    }
    $('discover-btn').disabled = true;
    try {
      const response = await fetch('/api/discovery/start', {
        method:'POST',
        headers:{'Content-Type':'application/json', 'X-Koral-Action':'discovery'},
        body:JSON.stringify({max_symbols, ai})
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Discovery failed to start');
      discoveryAcknowledged = null;
      discoveryWasRunning = true;
      notify('Independent stock discovery started. No trades will be placed.');
      await updateDiscoveryStatus();
    } catch(error) {
      notify('Discovery could not start: ' + error.message, true);
      $('discover-btn').disabled = false;
    }
  }

  async function refreshAutopilot() {
    try {
      const response = await fetch('/api/v3/state', {cache:'no-store'});
      if (!response.ok) throw new Error('V3 ledger unavailable');
      const v = await response.json();
      if (v.status !== 'paper_ready') {
        byId('v3-mode', v.status === 'not_initialized' ? 'NOT INITIALISED' : 'NEEDS REVIEW');
        byId('v3-state-description', v.status === 'not_initialized' ?
          'V3 uses a separate £10,000 GBP simulated account. Initialise it once using the dedicated command-line tool; the old portfolio is unchanged.' :
          'V3 state could not be verified; do not activate automatic entries.');
        return;
      }
      byId('v3-mode',v.halted ? 'RISK HALT' : v.paused ? 'PAUSED' :
        v.enabled ? 'PAPER AUTONOMY ENABLED' : 'PAPER AUTONOMY DISABLED');
      byId('v3-equity',money(v.equity_gbp));
      byId('v3-benchmark',v.performance?.spy_benchmark_gbp != null ? money(v.performance.spy_benchmark_gbp) : '—');
      byId('v3-exposure',(v.positions?.length ?? 0) + ' / ' + (v.queued ?? 0));
      byId('v3-scheduler',v.scheduler_heartbeat_recent ? 'PULSE RECENT' : 'NOT RUNNING / STALE');
      byId('v3-state-description','Last verified session: '+escapeHtml(v.last_session || 'none')+
           ' · Watchlist: '+(v.watchlist || []).map(escapeHtml).join(', ') +
           ' · AI receipts: '+(v.receipts_count || 0)+
           ' · Closed trades: '+(v.performance?.closed_trades || 0)+
           '. All prices and fills are simulated.');
      const intents = $('v3-intents');
      if (intents) {
        intents.replaceChildren();
        const rows = (v.intents || []).slice(-8);
        if (!rows.length) {intents.textContent = 'No active or historical V3 intents.';}
        else for (const item of rows) {
          const div = document.createElement('div');
          div.textContent = item.ticker+' · '+item.status+' · '+item.confirmations+' confirmation(s)';
          intents.appendChild(div);
        }
      }
      const log = $('v3-audit');
      if (log) {
        log.replaceChildren();
        for (const event of (v.recent_audit || []).slice().reverse()) {
          const div = document.createElement('div');
          div.textContent = String(event.utc || '').slice(0,16).replace('T',' ')+' UTC · '+event.kind;
          log.appendChild(div);
        }
        if (!log.childNodes.length) log.textContent = 'No V3 events.';
      }
    } catch (error) {
      byId('v3-mode','UNAVAILABLE');
      byId('v3-scheduler','OFFLINE');
      console.warn('V3 read-only status:',error);
    }
  }

  function init() {
    clock();setInterval(clock,30000);
    $('refresh-btn').addEventListener('click',()=>refresh());
    $('discover-btn').addEventListener('click', beginDiscovery);
    $('discovery-dismiss').addEventListener('click', () => {
      discoveryAcknowledged = discoveryCurrentId;
      try { sessionStorage.setItem('koral-discovery-ack', discoveryCurrentId || ''); }
      catch (_) { /* Dismissed for current session anyway. */ }
      $('discovery-progress').hidden = true;
    });
    $('discovery-copy').addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText($('discovery-log').textContent);
        notify('Discovery log copied.');
      } catch (_) {
        notify('Select the discovery log and press Ctrl+C to copy.', true);
      }
    });

    $('scan-btn').addEventListener('click',()=>$('scan-dialog').showModal());
    $('close-dialog').addEventListener('click',()=>$('scan-dialog').close());
    $('cancel-scan').addEventListener('click',()=>$('scan-dialog').close());
    $('scan-form').addEventListener('submit',beginScan);
    $('ack-scan').addEventListener('click',acknowledgeScan);
    $('toast-ok').addEventListener('click',dismissToast);
    $('copy-scan-log').addEventListener('click',async()=>{
      try {
        await navigator.clipboard.writeText($('scan-progress-log').textContent);
        notify('Scan log copied.');
      } catch (_) {
        notify('Could not copy automatically. Select the log text and press Ctrl+C.',true);
      }
    });
    document.querySelectorAll('[data-period]').forEach(button=>button.addEventListener('click',()=>{
      period=button.dataset.period;
      document.querySelectorAll('[data-period]').forEach(b=>b.classList.toggle('selected',b===button));
      if(state)equityChart(state);
    }));
    document.querySelectorAll('[data-tab]').forEach(button=>button.addEventListener('click',()=>{
      activeTab=button.dataset.tab;
      document.querySelectorAll('[data-tab]').forEach(b=>{b.classList.toggle('selected',b===button);b.setAttribute('aria-selected',String(b===button))});
      if(state)portfolioTable(state);
    }));
    document.querySelectorAll('.nav-links a').forEach(link=>link.addEventListener('click',()=>{
      document.querySelectorAll('.nav-links a').forEach(x=>x.classList.remove('active'));link.classList.add('active');
    }));
    refresh(true);updateScan();refreshDiscovery();updateDiscoveryStatus();refreshAutopilot();
    setInterval(()=>refresh(true),20000);
    setInterval(updateScan,2500);
    setInterval(refreshDiscovery,25000);
    setInterval(updateDiscoveryStatus,3000);
    setInterval(refreshAutopilot,15000);
  }
  document.addEventListener('DOMContentLoaded',init);
})();
