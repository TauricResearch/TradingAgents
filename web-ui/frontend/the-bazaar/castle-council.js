/* Traders of the Round Table - drop-in castle UI */
(function(){
'use strict';

function ready(fn){
  if (document.readyState !== 'loading') fn();
  else document.addEventListener('DOMContentLoaded', fn);
}

function getAssetURL(name){
  const s = document.currentScript || Array.from(document.scripts).find(x => /castle-council\.js/.test(x.src));
  if (!s) return name;
  return s.src.replace(/castle-council\.js.*/, name);
}

function rebrandTextNodes(root){
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
  const replacements = [
    [/\bThe Bazaar\b/g, 'The Round Table'],
    [/\bBazaar\b/g, 'Round Table'],
    [/\bMarket Square\b/g, 'The Keep'],
    [/\bArchives\b/g, 'Chronicles'],
    [/\bTHE CHAMBER CONVENES\b/g, 'THE COUNCIL CONVENES'],
    [/\bThe chamber rules\b/g, 'The council rules'],
  ];
  const nodes = []; let n;
  while ((n = walker.nextNode())) nodes.push(n);
  nodes.forEach(node => {
    let t = node.nodeValue, changed = false;
    replacements.forEach(([re, to]) => { if (re.test(t)) { t = t.replace(re, to); changed = true; } });
    if (changed) node.nodeValue = t;
  });
}

const SCRIPT = [
  { id:'market',       text:"Bearish divergence on the MACD histogram. Price made higher highs into $305, but momentum is fading.", sentiment:-2, reactions:[{to:'fundamentals', type:'thinking'},{to:'risk', type:'agree'}] },
  { id:'social',       text:"Sentiment held strong through the week, but volume of mentions is cooling. Crowds are getting cautious.", sentiment:-1, reactions:[{to:'trader', type:'agree'},{to:'debater', type:'thinking'}] },
  { id:'news',         text:"Services revenue narrative is intact. No catalysts to derail the long thesis in the next two weeks.", sentiment:+2, reactions:[{to:'fundamentals', type:'agree'},{to:'market', type:'disagree'}] },
  { id:'fundamentals', text:"Margins are healthy and FCF is expanding. The fundamentals support a higher multiple from here.", sentiment:+3, reactions:[{to:'news', type:'agree'},{to:'debater', type:'disagree'}] },
  { id:'debater',      text:"With respect - fundamentals are a 12-month story. Technicals say the next move is a pullback.", sentiment:-2, reactions:[{to:'market', type:'agree'},{to:'fundamentals', type:'disagree'}], rebuttal:true, target:'fundamentals' },
  { id:'fundamentals', text:"A pullback would only improve the entry. The base case still ends materially higher.", sentiment:+1, reactions:[{to:'debater', type:'disagree'}], rebuttal:true, target:'debater' },
  { id:'debater',      text:"Then we agree we wait. A tactical hold, not a fresh buy.", sentiment:0, reactions:[{to:'fundamentals', type:'thinking'},{to:'judge', type:'agree'}], rebuttal:true, target:'fundamentals' },
  { id:'risk',         text:"Position sizing matters more than direction here. Volatility is creeping up; reduce exposure.", sentiment:-1, reactions:[{to:'trader', type:'agree'}] },
  { id:'trader',       text:"I can defend the current position. I would not add until we see $295 hold.", sentiment:0, reactions:[{to:'risk', type:'agree'},{to:'debater', type:'agree'}] },
  { id:'judge',        text:"Trend is up. Conviction is down. The council rules: HOLD.", sentiment:0, verdict:true },
];

const SEATS = [
  { id:'judge',        angle: 270, name:'Elder Aldric',   role:'High Judge' },
  { id:'market',       angle: 315, name:'Flint',          role:'Market Analyst' },
  { id:'social',       angle: 0,   name:'Vera',           role:'Sentiment Seer' },
  { id:'news',         angle: 45,  name:'Reed',           role:'News Herald' },
  { id:'fundamentals', angle: 90,  name:'Sage',           role:'Fundamentals' },
  { id:'debater',      angle: 135, name:'Balthazar',      role:'Adversary' },
  { id:'risk',         angle: 180, name:'Morwen',         role:'Risk Warden' },
  { id:'trader',       angle: 225, name:'Kael',           role:'Swift Trader' },
];

const AGENT_TO_SEAT = {
  'market':'market','market_analyst':'market','flint':'market','Flint':'market',
  'social':'social','social_analyst':'social','vera':'social','Vera':'social',
  'news':'news','news_analyst':'news','reed':'news','Reed':'news',
  'fundamentals':'fundamentals','fundamentals_analyst':'fundamentals','sage':'fundamentals','Sage':'fundamentals',
  'bull':'fundamentals','bull_researcher':'fundamentals',
  'bear':'debater','bear_researcher':'debater','debater':'debater','balthazar':'debater',
  'risk':'risk','risk_manager':'risk','morwen':'risk',
  'trader':'trader','kael':'trader',
  'judge':'judge','aldric':'judge','researcher_judge':'judge','risk_judge':'judge',
};

const META = SEATS.reduce((a,s)=>{a[s.id]=s;return a;},{});
let seatEls = {}, stage, speed=1, playing=false, stopFlag=false, currentIdx=0, tilt=0;
let activeBubble=null, activeReactions=[];
const liveBubbles = {};

function injectPortraits(cb){
  if (document.getElementById('debate-portrait-defs')) return cb();
  fetch(getAssetURL('castle-portraits.svg')).then(r=>r.text()).then(svg=>{
    const wrap = document.createElement('div');
    wrap.id = 'debate-portrait-defs';
    wrap.style.cssText = 'position:absolute;width:0;height:0;overflow:hidden;';
    // The SVG file already has an outer <svg>; we want symbol defs inside.
    wrap.innerHTML = svg;
    document.body.appendChild(wrap);
    cb();
  }).catch(e=>{ console.warn('[council] portraits failed', e); cb(); });
}

function buildScene(){
  ['debate-scene-root','rt-verdict-card','rt-report-carousel'].forEach(id=>{
    const el = document.getElementById(id); if (el) el.remove();
  });

  const root = document.createElement('div');
  root.id = 'debate-scene-root';
  root.innerHTML = ''
    + '<div class="rt-chrome">'
    +   '<div class="rt-header">'
    +     '<div class="rt-title">'
    +       '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 21h18M5 21V10l7-5 7 5v11M10 21v-6h4v6"/></svg>'
    +       '<span>The Council Convenes</span>'
    +     '</div>'
    +     '<div class="rt-controls">'
    +       '<span id="rt-live-indicator" style="display:inline-flex;align-items:center;gap:6px;padding:6px 10px;background:linear-gradient(180deg,#2a3043,#1a1f2e);border:1px solid var(--castle-stone-light);color:var(--text-dim);border-radius:6px;font-family:inherit;font-size:10px;letter-spacing:.14em;text-transform:uppercase;">'
    +         '<span id="rt-live-dot" style="width:8px;height:8px;border-radius:50%;background:#666;"></span>'
    +         '<span id="rt-live-text">Idle</span>'
    +       '</span>'
    +       '<button class="rt-btn" id="rt-replay">Replay</button>'
    +       '<button class="rt-btn" id="rt-speed">1x</button>'
    +       '<button class="rt-btn primary" id="rt-play">Play</button>'
    +       '<button class="rt-btn" id="rt-toggle-reports">Hide Chronicles</button>'
    +     '</div>'
    +   '</div>'
    +   '<div class="rt-stage" id="rt-stage">'
    +     '<div class="rt-banner left"></div>'
    +     '<div class="rt-banner right"></div>'
    +     '<div class="rt-table"></div>'
    +     '<svg class="rt-crest"><use href="#castle-crest"/></svg>'
    +     '<div class="rt-verdict-banner" id="rt-verdict-banner"></div>'
    +     '<div class="rt-status" id="rt-status">The council awaits...</div>'
    +   '</div>'
    +   '<div class="rt-tilt">'
    +     '<div class="rt-tilt-labels"><span>Bearish</span><span>Bullish</span></div>'
    +     '<div class="rt-tilt-needle" id="rt-needle"></div>'
    +   '</div>'
    +   '<div class="rt-progress" id="rt-progress"></div>'
    + '</div>';

  const reactRoot = document.getElementById('root') || document.body.firstChild;
  if (reactRoot && reactRoot.parentNode) reactRoot.parentNode.insertBefore(root, reactRoot);
  else document.body.appendChild(root);

  stage = document.getElementById('rt-stage');
  const sw = stage.clientWidth, sh = stage.clientHeight;
  const cx = sw/2, cy = sh/2, radius = Math.min(sw,sh)*0.40;
  seatEls = {};
  SEATS.forEach(seat=>{
    const r = seat.angle * Math.PI / 180;
    const x = cx + radius * Math.cos(r);
    const y = cy + radius * Math.sin(r);
    const el = document.createElement('div');
    el.className = 'rt-seat';
    el.dataset.id = seat.id;
    el.dataset.angle = seat.angle;
    el.style.left = x + 'px';
    el.style.top = y + 'px';
    el.innerHTML = '<div class="rt-portrait"><svg viewBox="0 0 100 100"><use href="#portrait-'+seat.id+'"/></svg></div>'
      + '<div class="rt-name">'+seat.name+'</div>'
      + '<div class="rt-role">'+seat.role+'</div>';
    stage.appendChild(el);
    seatEls[seat.id] = el;
  });
  for (let i=0; i<SEATS.length; i++){
    const a1 = SEATS[i].angle, a2 = SEATS[(i+1)%SEATS.length].angle;
    let mid = (i === SEATS.length-1) ? ((a1+a2+360)/2)%360 : (a1+a2)/2;
    const r = (mid*Math.PI/180);
    const rr = radius * 1.18;
    const x = cx + rr*Math.cos(r), y = cy + rr*Math.sin(r);
    const c = document.createElement('div');
    c.className = 'rt-candle';
    c.style.left = x+'px'; c.style.top = y+'px';
    c.style.animationDelay = (i*0.2)+'s';
    stage.appendChild(c);
  }
  const prog = document.getElementById('rt-progress');
  SCRIPT.forEach(()=>{ const p=document.createElement('div'); p.className='rt-pip'; prog.appendChild(p); });
}

function setStatus(t){ const e=document.getElementById('rt-status'); if(e) e.textContent=t; }
function setTilt(v){ tilt=Math.max(-10,Math.min(10,v)); const pct=((tilt+10)/20)*100; const n=document.getElementById('rt-needle'); if(n) n.style.left=pct+'%'; }
function clearReactions(){ activeReactions.forEach(r=>r.remove()); activeReactions=[]; }
function clearBubble(){ if(activeBubble){ activeBubble.classList.remove('visible'); const b=activeBubble; setTimeout(()=>b.remove(),300); activeBubble=null; } }
function resetSeats(){ Object.values(seatEls).forEach(el=>el.classList.remove('speaking','thinking','done','dimmed')); }

function placeBubble(bubble, seatId){
  const seatEl = seatEls[seatId];
  if (!seatEl) return;
  const angle = parseFloat(seatEl.dataset.angle);
  bubble.style.opacity='0';
  bubble.style.left='0px'; bubble.style.top='0px';
  requestAnimationFrame(()=>{
    const sb = seatEl.getBoundingClientRect();
    const stb = stage.getBoundingClientRect();
    const bb = bubble.getBoundingClientRect();
    const bw=bb.width, bh=bb.height;
    const sx = sb.left - stb.left + sb.width/2;
    const sy = sb.top - stb.top + sb.height/2;
    let x=sx, y=sy;
    if (angle===270){ x=sx-bw/2; y=sy-sb.height/2-bh-8; }
    else if (angle===315){ x=sx-bw-8; y=sy-bh-4; }
    else if (angle===0){ x=sx+sb.width/2+4; y=sy-bh/2; }
    else if (angle===45){ x=sx+8; y=sy+4; }
    else if (angle===90){ x=sx-bw/2; y=sy+sb.height/2+8; }
    else if (angle===135){ x=sx-bw-8; y=sy+4; }
    else if (angle===180){ x=sx-bw-sb.width/2-4; y=sy-bh/2; }
    else if (angle===225){ x=sx-bw+8; y=sy-bh-4; }
    x=Math.max(8,Math.min(stb.width-bw-8,x));
    y=Math.max(8,Math.min(stb.height-bh-8,y));
    bubble.style.left=x+'px'; bubble.style.top=y+'px';
    bubble.style.opacity=''; bubble.classList.add('visible');
  });
}

function showBubble(line){
  clearBubble();
  const meta = META[line.id];
  const b = document.createElement('div');
  b.className = 'rt-bubble' + (line.rebuttal?' rebuttal':'');
  b.innerHTML = '<div class="rt-bubble-name"><span class="dot"></span>'+meta.name+' &mdash; '+meta.role+'</div><div>'+line.text+'</div>';
  stage.appendChild(b);
  activeBubble = b;
  placeBubble(b, line.id);
  if (line.rebuttal){
    setTimeout(()=>b.classList.add('shake'),200);
    setTimeout(()=>b.classList.remove('shake'),700);
  }
}

function showReactions(reactions){
  clearReactions();
  if (!reactions) return;
  reactions.forEach((r,i)=>{
    const seatEl = seatEls[r.to]; if (!seatEl) return;
    const sb = seatEl.getBoundingClientRect();
    const stb = stage.getBoundingClientRect();
    const sx = sb.left - stb.left + sb.width/2;
    const sy = sb.top - stb.top;
    const el = document.createElement('div');
    el.className = 'rt-reaction ' + r.type;
    const label = { agree:'Aye', disagree:'Nay', thinking:'Pondering' }[r.type] || r.type;
    el.innerHTML = '<span class="chip"><svg viewBox="0 0 100 100"><use href="#portrait-'+r.to+'"/></svg></span><span>'+label+'</span>';
    el.style.left = sx+'px'; el.style.top = sy+'px';
    stage.appendChild(el);
    activeReactions.push(el);
    setTimeout(()=>el.classList.add('visible'), 80 + i*120);
  });
}

function setActiveSeat(id){ Object.entries(seatEls).forEach(([k,el])=>{ el.classList.remove('speaking','thinking'); if(k===id) el.classList.add('speaking'); }); }
function markDone(id){ if(seatEls[id]) seatEls[id].classList.add('done'); }
function updateProgress(i){ document.querySelectorAll('#rt-progress .rt-pip').forEach((p,idx)=>{ p.classList.remove('active'); if(idx<i) p.classList.add('done'); if(idx===i) p.classList.add('active'); }); }
async function wait(ms){ const step=50; let e=0; while(e<ms/speed){ if(stopFlag) throw new Error('stop'); await new Promise(r=>setTimeout(r,step)); e+=step; } }

async function freezeFrame(){
  Object.entries(seatEls).forEach(([k,el])=>{ if(k!=='judge') el.classList.add('dimmed'); });
  if (seatEls.judge){ seatEls.judge.classList.remove('done','dimmed'); seatEls.judge.classList.add('speaking'); }
  const banner = document.getElementById('rt-verdict-banner');
  if (banner){
    banner.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#1a1408" stroke-width="1.8"><path d="M12 2 L 19 6 L 19 11 Q 19 19 12 22 Q 5 19 5 11 L 5 6 Z"/><path d="M9 12 L 12 9 L 15 12 M 12 9 L 12 15"/></svg><span>Final Verdict</span>';
    banner.classList.add('show');
  }
}

async function playFrom(idx){
  playing=true; stopFlag=false;
  const pb = document.getElementById('rt-play'); if (pb) pb.textContent='Pause';
  if (idx===0){
    resetSeats(); clearBubble(); clearReactions(); setTilt(0);
    const vb = document.getElementById('rt-verdict-banner'); if (vb) vb.classList.remove('show');
    updateProgress(-1);
  }
  try {
    for (let i=idx; i<SCRIPT.length; i++){
      if (stopFlag) break;
      currentIdx=i;
      const line = SCRIPT[i];
      updateProgress(i);
      setActiveSeat(line.id);
      setStatus(line.rebuttal?'Rebuttal in progress...':(line.verdict?'The council renders its verdict...':META[line.id].name+' speaks'));
      showBubble(line);
      showReactions(line.reactions);
      setTilt(tilt + (line.sentiment||0));
      await wait(line.verdict?3800:3000);
      markDone(line.id);
      clearReactions();
    }
    if (!stopFlag){
      clearBubble();
      await freezeFrame();
      setStatus('Verdict rendered. Long may the council reign.');
      updateProgress(SCRIPT.length);
    }
  } catch(e){}
  playing=false;
  const pb2 = document.getElementById('rt-play'); if (pb2) pb2.textContent='Play';
}

function wireControls(){
  document.getElementById('rt-play').addEventListener('click', ()=>{
    if (playing) stopFlag=true;
    else {
      if (currentIdx >= SCRIPT.length-1) currentIdx=0;
      playFrom(currentIdx===0?0:currentIdx+1);
    }
  });
  document.getElementById('rt-replay').addEventListener('click', ()=>{
    stopFlag=true;
    setTimeout(()=>{ currentIdx=0; playFrom(0); }, 200);
  });
  document.getElementById('rt-speed').addEventListener('click', (e)=>{
    const speeds=[1,1.5,2,0.75];
    const idx = speeds.indexOf(speed);
    speed = speeds[(idx+1)%speeds.length];
    e.target.textContent = speed+'x';
  });
  document.getElementById('rt-toggle-reports').addEventListener('click', (e)=>{
    const c = document.getElementById('rt-report-carousel');
    const r = document.getElementById('root');
    if (e.target.textContent.startsWith('Hide')){
      if (c) c.style.display='none';
      if (r) r.style.display='none';
      e.target.textContent='Show Chronicles';
    } else {
      if (c) c.style.display='';
      if (r) r.style.display='';
      e.target.textContent='Hide Chronicles';
    }
  });
}

function analystFromTitle(title){
  const t = (title||'').toLowerCase();
  if (t.includes('flint') || t.includes('market')) return { id:'market', name:'Flint', role:'Market Analyst' };
  if (t.includes('vera') || t.includes('sentiment') || t.includes('social')) return { id:'social', name:'Vera', role:'Sentiment Seer' };
  if (t.includes('reed') || t.includes('news')) return { id:'news', name:'Reed', role:'News Herald' };
  if (t.includes('sage') || t.includes('fundamentals')) return { id:'fundamentals', name:'Sage', role:'Fundamentals Scholar' };
  if (t.includes('balthazar') || t.includes('debater')) return { id:'debater', name:'Balthazar', role:'Adversary' };
  if (t.includes('morwen') || t.includes('risk')) return { id:'risk', name:'Morwen', role:'Risk Warden' };
  if (t.includes('kael') || t.includes('trader')) return { id:'trader', name:'Kael', role:'Swift Trader' };
  if (t.includes('aldric') || t.includes('judge')) return { id:'judge', name:'Elder Aldric', role:'High Judge' };
  return { id:'market', name:'Analyst', role:'Council' };
}

function buildVerdictAndCarousel(){
  const sections = Array.from(document.querySelectorAll('#root .detail-section'));
  const reports = sections.map(sec=>{
    const t = sec.querySelector('h4,h3,h2');
    const b = sec.querySelector('.detail-content') || sec;
    return { title:(t&&t.textContent.trim())||'', html:b.innerHTML };
  }).filter(r=>r.title && r.html.length>50);

  // Find verdict value (HOLD/BUY/SELL)
  let verdict = 'HOLD';
  const verdictEl = Array.from(document.querySelectorAll('#root *')).find(el=>{
    if (el.children.length>30) return false;
    const t=(el.textContent||'').trim();
    return /^HOLD$|^BUY$|^SELL$/i.test(t);
  });
  if (verdictEl) verdict = verdictEl.textContent.trim().toUpperCase();

  const vc = document.createElement('div');
  vc.id = 'rt-verdict-card'; vc.className = 'rt-verdict-card';
  vc.innerHTML = ''
    + '<svg class="rt-crest-large" viewBox="0 0 100 100"><use href="#castle-crest"/></svg>'
    + '<div class="rt-verdict-label">By Decree of the Round Table</div>'
    + '<div class="rt-verdict-value">'+verdict+'</div>'
    + '<div class="rt-verdict-meta"><span id="rt-verdict-ticker">&mdash;</span><span class="sep">&middot;</span><span>Unanimous Council</span></div>';
  document.getElementById('debate-scene-root').insertAdjacentElement('afterend', vc);

  const car = document.createElement('div');
  car.id = 'rt-report-carousel'; car.className = 'rt-report-carousel';
  car.innerHTML = ''
    + '<div class="rt-carousel-controls">'
    +   '<div class="rt-carousel-title">Council Chronicles &middot; Analyst Reports</div>'
    +   '<div style="display:flex;gap:8px;"><button class="rt-arrow" id="rt-prev">&lsaquo;</button><button class="rt-arrow" id="rt-next">&rsaquo;</button></div>'
    + '</div>'
    + '<div class="rt-report-track" id="rt-report-track"></div>';
  vc.insertAdjacentElement('afterend', car);

  const track = document.getElementById('rt-report-track');
  reports.forEach(src=>{
    const a = analystFromTitle(src.title);
    const card = document.createElement('div');
    card.className = 'rt-report-card';
    card.innerHTML = ''
      + '<div class="rt-report-head">'
      +   '<div class="rt-mini-portrait"><svg viewBox="0 0 100 100"><use href="#portrait-'+a.id+'"/></svg></div>'
      +   '<div><h3>'+a.name+'</h3><div class="rt-report-role">'+a.role+' &middot; '+src.title+'</div></div>'
      + '</div>'
      + '<div class="rt-report-body">'+src.html+'</div>';
    const btn = document.createElement('button');
    btn.className = 'rt-read-full';
    btn.innerHTML = 'Read Full Scroll';
    btn.addEventListener('click', ()=>openModal(card));
    card.appendChild(btn);
    track.appendChild(card);
  });
  document.getElementById('rt-prev').addEventListener('click', ()=>{ const c=track.querySelector('.rt-report-card'); if(c) track.scrollBy({left:-(c.clientWidth+16),behavior:'smooth'}); });
  document.getElementById('rt-next').addEventListener('click', ()=>{ const c=track.querySelector('.rt-report-card'); if(c) track.scrollBy({left:(c.clientWidth+16),behavior:'smooth'}); });
}

function openModal(card){
  const portrait = card.querySelector('.rt-mini-portrait').innerHTML;
  const name = card.querySelector('h3').textContent;
  const role = card.querySelector('.rt-report-role').textContent;
  const body = card.querySelector('.rt-report-body').innerHTML;
  const back = document.createElement('div');
  back.className='rt-modal-backdrop';
  back.innerHTML = '<div class="rt-modal"><div class="rt-modal-head"><div class="rt-modal-portrait">'+portrait+'</div><div class="rt-modal-title-block"><div class="rt-modal-title">'+name+'</div><div class="rt-modal-sub">'+role+'</div></div><button class="rt-modal-close">&times;</button></div><div class="rt-modal-body">'+body+'</div></div>';
  document.body.appendChild(back);
  requestAnimationFrame(()=>back.classList.add('visible'));
  function close(){ back.classList.remove('visible'); setTimeout(()=>back.remove(),300); document.removeEventListener('keydown',onKey); }
  function onKey(e){ if(e.key==='Escape') close(); }
  back.addEventListener('click', e=>{ if (e.target===back) close(); });
  back.querySelector('.rt-modal-close').addEventListener('click', close);
  document.addEventListener('keydown', onKey);
}

function installLiveWiring(){
  if (window.__sseHookInstalled) return;
  window.__sseHookInstalled = true;
  window.__sseListeners = [];
  const RealES = window.EventSource;
  window.EventSource = function HookedES(url, opts){
    const es = new RealES(url, opts);
    const safe = (url||'').toString().replace(/token=[a-zA-Z0-9_\-]+/g,'TOK');
    console.log('[live] EventSource:', safe);
    const origAdd = es.addEventListener.bind(es);
    es.addEventListener = function(type, fn, opts2){
      const wrapped = function(ev){
        try { window.__sseListeners.forEach(l=>{ try{ l(type, ev); }catch(e){} }); } catch(e){}
        return fn.apply(this, arguments);
      };
      return origAdd(type, wrapped, opts2);
    };
    return es;
  };
  Object.keys(RealES).forEach(k=>{ try{ window.EventSource[k]=RealES[k]; }catch(e){} });
  window.EventSource.prototype = RealES.prototype;

  window.__sseListeners.push((type, ev)=>{
    let data;
    try { data = ev.data ? JSON.parse(ev.data) : null; } catch(e){ data = ev.data; }
    if (!data) return;
    const agent = data.agent || data.analyst || data.author || (data.payload && data.payload.agent);
    const status = data.status || data.event || data.state || type;
    const text = data.message || data.text || data.content || (data.payload && data.payload.text);
    const seatId = AGENT_TO_SEAT[agent] || AGENT_TO_SEAT[(agent||'').toLowerCase().replace(/[^a-z_]/g,'')];
    if (!seatId) return;
    const seatEl = seatEls[seatId]; if (!seatEl) return;
    if (/think|start|begin|working/i.test(status)){
      Object.values(seatEls).forEach(el=>el.classList.remove('speaking'));
      seatEl.classList.remove('done'); seatEl.classList.add('thinking');
    } else if (/speak|message|delta|chunk|update/i.test(status)){
      Object.values(seatEls).forEach(el=>el.classList.remove('speaking','thinking'));
      seatEl.classList.add('speaking');
      if (text) showLiveBubble(seatId, text);
    } else if (/done|complete|finish|end/i.test(status)){
      seatEl.classList.remove('speaking','thinking');
      seatEl.classList.add('done');
    }
  });

  const _fetch = window.fetch;
  window.fetch = function(){
    const url = (arguments[0]||'').toString();
    if (/\/analyze/.test(url)){
      const dot = document.getElementById('rt-live-dot');
      const txt = document.getElementById('rt-live-text');
      const ind = document.getElementById('rt-live-indicator');
      if (dot){ dot.style.background='#c43f54'; dot.style.boxShadow='0 0 8px #c43f54'; }
      if (txt) txt.textContent='Live - Council in session';
      if (ind){ ind.style.borderColor='var(--castle-crimson-bright)'; ind.style.color='#f5b8c2'; }
      Object.values(seatEls).forEach(el=>el.classList.remove('done','speaking','thinking','dimmed'));
    }
    return _fetch.apply(this, arguments);
  };
}

function showLiveBubble(seatId, text){
  let disp = (typeof text === 'string' && text.length > 220) ? text.slice(0,217)+'...' : text;
  if (liveBubbles[seatId]){ liveBubbles[seatId].remove(); delete liveBubbles[seatId]; }
  const meta = META[seatId]; if (!meta) return;
  const b = document.createElement('div');
  b.className = 'rt-bubble';
  b.innerHTML = '<div class="rt-bubble-name"><span class="dot"></span>'+meta.name+' &mdash; '+meta.role+'</div><div>'+disp+'</div>';
  stage.appendChild(b);
  liveBubbles[seatId] = b;
  placeBubble(b, seatId);
  setTimeout(()=>{ if (liveBubbles[seatId]===b){ b.classList.remove('visible'); setTimeout(()=>b.remove(),300); delete liveBubbles[seatId]; } }, 6000);
}

function mount(){
  document.title = 'Traders of the Round Table';
  rebrandTextNodes(document.body);
  if (window.__brandObserver) window.__brandObserver.disconnect();
  window.__brandObserver = new MutationObserver(()=>rebrandTextNodes(document.body));
  window.__brandObserver.observe(document.body, { childList:true, subtree:true, characterData:true });

  injectPortraits(()=>{
    buildScene();
    wireControls();
    buildVerdictAndCarousel();
    installLiveWiring();
    setTimeout(()=>{ try { playFrom(0); } catch(e){} }, 500);
  });
}

ready(mount);

})();
