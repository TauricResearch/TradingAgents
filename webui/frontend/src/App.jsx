import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import AgentActivityPanel from './AgentActivityPanel.jsx'
import { agentBySection } from './agents.js'
import JourneyPreview from './JourneyPreview.jsx'

const THEME_KEY = 'ta-theme'

/* localStorage throws in private mode and when site data is blocked, so every
   access is guarded and the UI falls back to following the system theme. */
function readTheme() {
  try {
    const v = localStorage.getItem(THEME_KEY)
    if (v === 'light' || v === 'dark' || v === 'system') return v
  } catch {
    /* unavailable — fall through to system */
  }
  return 'system'
}

function writeTheme(v) {
  try {
    localStorage.setItem(THEME_KEY, v)
  } catch {
    /* preference simply will not persist */
  }
}

const TICKER_RE = /^[A-Za-z0-9.\-^=]{1,20}$/
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/

function Prose({ children }) {
  return (
    <div className="prose">
      <Markdown remarkPlugins={[remarkGfm]}>{children}</Markdown>
    </div>
  )
}

function Report({ label, content, highlight }) {
  const [open, setOpen] = useState(true)
  return (
    <div className={highlight ? 'report decision' : 'report'}>
      <button
        className="report-head"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <span className={open ? 'chev open' : 'chev'}>›</span>
        {label}
      </button>
      {open && (
        <div className="report-body">
          <Prose>{content}</Prose>
        </div>
      )}
    </div>
  )
}

export default function App() {
  return new URLSearchParams(window.location.search).get('preview') === 'journey'
    ? <JourneyPreview />
    : <TradingApp />
}

function TradingApp() {
  const [theme, setTheme] = useState(readTheme)
  const [opts, setOpts] = useState(null)
  const [bootError, setBootError] = useState('')
  const [turns, setTurns] = useState([])
  const [step, setStep] = useState('ticker')
  const [sel, setSel] = useState({})
  const [draft, setDraft] = useState('')
  const [modelOpts, setModelOpts] = useState(null)
  const [analystPick, setAnalystPick] = useState([])
  const [running, setRunning] = useState(false)
  const [statusMsg, setStatusMsg] = useState('')
  const [sections, setSections] = useState([])
  const [runError, setRunError] = useState(null)
  const [atBottom, setAtBottom] = useState(true)
  const [checking, setChecking] = useState(false)
  const [activity, setActivity] = useState([])
  const [filterId, setFilterId] = useState(null)

  const chatRef = useRef(null)
  const wsRef = useRef(null)
  const activityId = useRef(0)
  const seenSections = useRef(new Set())
  const lastStatus = useRef('')

  const pushActivity = useCallback((row) => {
    const id = ++activityId.current
    setActivity((prev) => [{ id, ts: Date.now(), ...row }, ...prev])
  }, [])

  /* ---------- theme ---------- */

  useEffect(() => {
    const root = document.documentElement
    if (theme === 'system') root.removeAttribute('data-theme')
    else root.setAttribute('data-theme', theme)
    writeTheme(theme)
  }, [theme])

  /* ---------- scroll ----------

     The previous build forced scrollTop to the bottom on every render, which
     during a run fires many times a minute and yanks you back down while you
     are reading. Auto-follow now happens only when you are already near the
     bottom; otherwise a jump pill appears and leaves you alone. */

  const NEAR_BOTTOM_PX = 90

  const onScroll = useCallback(() => {
    const el = chatRef.current
    if (!el) return
    const gap = el.scrollHeight - el.scrollTop - el.clientHeight
    setAtBottom(gap < NEAR_BOTTOM_PX)
  }, [])

  /* Layout effect, not effect: scroll before paint so new content never
     flashes at the old offset first. */
  useLayoutEffect(() => {
    const el = chatRef.current
    if (el && atBottom) el.scrollTop = el.scrollHeight
  }, [turns, sections, statusMsg, runError, atBottom])

  const jumpToLatest = () => {
    const el = chatRef.current
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
    setAtBottom(true)
  }

  /* ---------- boot ---------- */

  useEffect(() => {
    let alive = true
    fetch('/api/options')
      .then((r) => {
        if (!r.ok) throw new Error(`options returned ${r.status}`)
        return r.json()
      })
      .then((o) => {
        if (!alive) return
        setOpts(o)
        setAnalystPick(o.defaults.analysts)
        setTurns([
          {
            who: 'assistant',
            text:
              "**TradingAgents**\n\nI'll run a multi-agent analysis on any ticker Yahoo Finance covers — US, India (`.NS`), Hong Kong (`.HK`), crypto (`BTC-USD`) and more.\n\nWhich ticker should I analyze?",
          },
        ])
      })
      .catch((e) => alive && setBootError(e.message))
    return () => {
      alive = false
    }
  }, [])

  useEffect(() => () => wsRef.current?.close(), [])

  /* ---------- helpers ---------- */

  const say = (who, text) => setTurns((t) => [...t, { who, text }])

  const loadModels = useCallback(async (provider, mode) => {
    setModelOpts(null)
    const r = await fetch(
      `/api/models?provider=${encodeURIComponent(provider)}&mode=${mode}`,
    )
    setModelOpts(await r.json())
  }, [])

  /* ---------- step transitions ---------- */

  const askDate = () => {
    say(
      'assistant',
      `What analysis date? Use \`YYYY-MM-DD\`, or send **today** for ${opts.today}.`,
    )
    setStep('date')
  }

  const askLanguage = () => {
    say('assistant', 'Which language should the reports be written in?')
    setStep('language')
  }

  const askAnalysts = () => {
    say('assistant', 'Which analysts should join the team? Pick at least one.')
    setStep('analysts')
  }

  const askDepth = () => {
    say('assistant', 'How deep should the research go?')
    setStep('depth')
  }

  const askProvider = () => {
    say('assistant', 'Which LLM provider should power the agents?')
    setStep('provider')
  }

  const submitTicker = async (value) => {
    const t = value.trim()
    if (!TICKER_RE.test(t)) {
      say('assistant', "That doesn't look like a ticker. Try `AAPL`, `RELIANCE.NS` or `BTC-USD`.")
      return
    }
    say('user', t.toUpperCase())

    // Confirm the symbol actually prices before going any further. A bad ticker
    // used to surface only once the run had started and spent LLM calls.
    setChecking(true)
    let res
    try {
      const r = await fetch(`/api/validate?symbol=${encodeURIComponent(t)}`)
      res = await r.json()
    } catch {
      res = { ok: false, message: 'Could not reach the backend to check that symbol.' }
    }
    setChecking(false)

    if (!res.ok) {
      say('assistant', `${res.message}\n\nTry another ticker.`)
      return
    }

    const ticker = res.canonical
    // Mirrors the CLI's detect_asset_type: a dash-quoted pair is crypto.
    const asset = /-(USD|USDT|EUR|BTC)$/.test(ticker) ? 'crypto' : 'stock'
    setSel((s) => ({ ...s, ticker, asset_type: asset }))
    askDate()
  }

  const submitDate = (value) => {
    const raw = value.trim()
    const d = raw.toLowerCase() === 'today' ? opts.today : raw
    if (!DATE_RE.test(d) || Number.isNaN(Date.parse(d))) {
      say('assistant', 'Please give the date as `YYYY-MM-DD` — for example `2026-01-15`.')
      return
    }
    say('user', d)
    setSel((s) => ({ ...s, analysis_date: d }))
    askLanguage()
  }

  const pickLanguage = (o) => {
    say('user', o.label)
    setSel((s) => ({ ...s, output_language: o.value }))
    askAnalysts()
  }

  const confirmAnalysts = () => {
    const labels = opts.analysts
      .filter((a) => analystPick.includes(a.value))
      .map((a) => a.label)
    say('user', labels.join(', '))
    setSel((s) => ({ ...s, analysts: analystPick }))
    askDepth()
  }

  const pickDepth = (o) => {
    say('user', o.label)
    setSel((s) => ({ ...s, research_depth: o.value }))
    askProvider()
  }

  const pickProvider = async (p) => {
    say('user', p.label)
    setSel((s) => ({ ...s, llm_provider: p.value, backend_url: p.backend_url }))
    say('assistant', 'Which model should handle the **quick-thinking** work?')
    setStep('quick')
    await loadModels(p.value, 'quick')
  }

  const pickQuick = async (value, label) => {
    say('user', label || value)
    setSel((s) => ({ ...s, quick_think_llm: value }))
    say('assistant', 'And the **deep-thinking** model for debate and final calls?')
    setStep('deep')
    await loadModels(sel.llm_provider, 'deep')
  }

  const pickDeep = (value, label) => {
    say('user', label || value)
    const next = { ...sel, deep_think_llm: value }
    setSel(next)
    const effort = opts.effort_steps[next.llm_provider]
    if (effort) {
      say('assistant', `${effort.prompt}.`)
      setStep('effort')
    } else {
      start(next)
    }
  }

  const pickEffort = (o) => {
    say('user', o[0])
    start({ ...sel, effort: o[1] })
  }

  /* ---------- run ---------- */

  const start = (finalSel) => {
    setSel(finalSel)
    setStep('running')
    setRunning(true)
    setSections([])
    setRunError(null)
    setAtBottom(true)
    setActivity([])
    setFilterId(null)
    seenSections.current = new Set()
    lastStatus.current = ''
    pushActivity({
      title: 'Team assembled',
      agentId: null,
      status: 'processing',
      detail: `${finalSel.ticker} · ${finalSel.analysis_date}`,
    })
    say(
      'assistant',
      `Starting analysis of **${finalSel.ticker}** as of **${finalSel.analysis_date}**. Reports appear below as each agent finishes.`,
    )

    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${window.location.host}/ws/run`)
    wsRef.current = ws

    ws.onopen = () => ws.send(JSON.stringify(finalSel))

    ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data)
      if (m.type === 'status') {
        setStatusMsg(m.message)
        if (m.message && m.message !== lastStatus.current) {
          lastStatus.current = m.message
          pushActivity({
            title: m.message,
            agentId: null,
            status: 'processing',
          })
        }
      } else if (m.type === 'section') {
        setStatusMsg('')
        const agent = agentBySection(m.key)
        const first = !seenSections.current.has(m.key)
        seenSections.current.add(m.key)
        pushActivity({
          title: first ? `${agent?.label || m.label} finished` : `${m.label} revised`,
          agentId: agent?.id || null,
          section: m.key,
          status: 'done',
          detail: typeof m.content === 'string' ? m.content.slice(0, 480) : '',
        })
        setSections((prev) => {
          const i = prev.findIndex((s) => s.key === m.key)
          if (i === -1) return [...prev, { key: m.key, label: m.label, content: m.content }]
          const copy = [...prev]
          copy[i] = { key: m.key, label: m.label, content: m.content }
          return copy
        })
      } else if (m.type === 'error') {
        setRunError({ message: m.message, detail: m.detail })
        setStatusMsg('')
        setRunning(false)
        pushActivity({ title: 'Run failed', status: 'idle', detail: m.message })
      } else if (m.type === 'done') {
        setStatusMsg('')
        setRunning(false)
        setStep('finished')
        pushActivity({
          title: 'Analysis complete',
          agentId: 'portfolio',
          section: 'final_trade_decision',
          status: 'done',
        })
        say('assistant', 'Analysis complete. The full decision is in the report above.')
      }
    }

    ws.onerror = () => {
      setRunError({ message: 'Lost the connection to the backend.', detail: '' })
      setRunning(false)
    }

    ws.onclose = () => setRunning(false)
  }

  const reset = () => {
    wsRef.current?.close()
    setTurns([
      { who: 'assistant', text: 'Starting fresh. Which ticker should I analyze?' },
    ])
    setSel({})
    setSections([])
    setRunError(null)
    setStatusMsg('')
    setStep('ticker')
    setAnalystPick(opts.defaults.analysts)
    setAtBottom(true)
    setActivity([])
    setFilterId(null)
    seenSections.current = new Set()
    lastStatus.current = ''
  }

  /* ---------- composer ---------- */

  const textStep = step === 'ticker' || step === 'date'
  const freeText =
    (step === 'quick' || step === 'deep') && modelOpts?.free_text

  const canSend =
    (textStep || freeText) && draft.trim().length > 0 && !checking

  const send = () => {
    if (!canSend) return
    const v = draft
    setDraft('')
    if (step === 'ticker') submitTicker(v)
    else if (step === 'date') submitDate(v)
    else if (step === 'quick') pickQuick(v.trim(), v.trim())
    else if (step === 'deep') pickDeep(v.trim(), v.trim())
  }

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  /* ---------- render ---------- */

  if (bootError) {
    return (
      <div style={{ padding: 40, maxWidth: 620, margin: '0 auto' }}>
        <h2>Can't reach the backend</h2>
        <p style={{ color: 'var(--text-muted)' }}>{bootError}</p>
        <p>
          Start it from the repo root:
          <br />
          <code>
            .venv\Scripts\python.exe -m uvicorn webui.backend.app:app --port 8000
          </code>
        </p>
      </div>
    )
  }

  if (!opts) {
    return (
      <div style={{ padding: 40, color: 'var(--text-muted)' }}>Loading…</div>
    )
  }

  const doneKeys = new Set(sections.map((s) => s.key))
  const pct = Math.round((doneKeys.size / opts.sections.length) * 100)
  const effortStep = opts.effort_steps[sel.llm_provider]

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">TA</span>
          TradingAgents
        </div>

        <AgentActivityPanel
          selectedAnalysts={sel.analysts || opts.defaults.analysts}
          sections={sections}
          running={running}
          statusMsg={statusMsg}
          activity={activity}
          filterId={filterId}
          onFilter={setFilterId}
        />

        <div>
          <div className="progress">
            <div className="progress-fill" style={{ width: `${pct}%` }} />
          </div>
          <div className="progress-label">
            {doneKeys.size} of {opts.sections.length} complete
          </div>
        </div>
      </aside>

      <div className="main">
        <header className="header">
          <div>
            <div className="header-title">
              {sel.ticker ? `${sel.ticker} analysis` : 'New analysis'}
            </div>
            <div className="header-sub">
              {sel.analysis_date || 'Not financial advice — research only'}
            </div>
          </div>
          <div className="theme-toggle" role="group" aria-label="Theme">
            {['light', 'system', 'dark'].map((t) => (
              <button
                key={t}
                className={`theme-btn${theme === t ? ' on' : ''}`}
                onClick={() => setTheme(t)}
                aria-pressed={theme === t}
              >
                {t[0].toUpperCase() + t.slice(1)}
              </button>
            ))}
          </div>
        </header>

        <div className="chat-wrap">
          <div className="chat" ref={chatRef} onScroll={onScroll}>
            <div className="col">
              {turns.map((t, i) =>
                t.who === 'user' ? (
                  <div className="turn-user" key={i}>
                    <div className="bubble">{t.text}</div>
                  </div>
                ) : (
                  <div className="turn-assistant" key={i}>
                    <Prose>{t.text}</Prose>
                  </div>
                ),
              )}

              {/* choices for the current step */}
              {step === 'language' && (
                <div className="choices chips">
                  {opts.languages.map((o) => (
                    <button
                      key={o.value}
                      className="choice"
                      onClick={() => pickLanguage(o)}
                    >
                      {o.label}
                    </button>
                  ))}
                </div>
              )}

              {step === 'analysts' && (
                <div className="choices">
                  {opts.analysts.map((a) => {
                    const on = analystPick.includes(a.value)
                    return (
                      <button
                        key={a.value}
                        className={`choice${on ? ' sel' : ''}`}
                        onClick={() =>
                          setAnalystPick((p) =>
                            on ? p.filter((x) => x !== a.value) : [...p, a.value],
                          )
                        }
                      >
                        <span className={`check${on ? ' on' : ''}`}>{on ? '✓' : ''}</span>
                        {a.label}
                      </button>
                    )
                  })}
                  <button
                    className="confirm"
                    disabled={analystPick.length === 0}
                    onClick={confirmAnalysts}
                  >
                    Continue with {analystPick.length}
                  </button>
                </div>
              )}

              {step === 'depth' && (
                <div className="choices">
                  {opts.depths.map((o) => (
                    <button
                      key={o.value}
                      className="choice"
                      onClick={() => pickDepth(o)}
                    >
                      <span>
                        {o.label}
                        <span className="choice-desc">{o.description}</span>
                      </span>
                    </button>
                  ))}
                </div>
              )}

              {step === 'provider' && (
                <div className="choices">
                  {opts.providers.map((p) => (
                    <button
                      key={p.value}
                      className="choice"
                      onClick={() => pickProvider(p)}
                    >
                      <span>{p.label}</span>
                      {!p.has_key && (
                        <span className="choice-warn">{p.key_env} not set</span>
                      )}
                    </button>
                  ))}
                </div>
              )}

              {(step === 'quick' || step === 'deep') && modelOpts && !modelOpts.free_text && (
                <div className="choices">
                  {modelOpts.options.length === 0 && (
                    <div className="status">No catalog models — type an ID below.</div>
                  )}
                  {modelOpts.options.map((o) => (
                    <button
                      key={o.value}
                      className="choice"
                      onClick={() =>
                        step === 'quick'
                          ? pickQuick(o.value, o.label)
                          : pickDeep(o.value, o.label)
                      }
                    >
                      {o.label}
                    </button>
                  ))}
                </div>
              )}

              {step === 'effort' && effortStep && (
                <div className="choices chips">
                  {effortStep.options.map((o) => (
                    <button
                      key={o[1]}
                      className="choice"
                      onClick={() => pickEffort(o)}
                    >
                      {o[0]}
                    </button>
                  ))}
                </div>
              )}

              {/* streamed reports */}
              {sections.map((s) => (
                <Report
                  key={s.key}
                  label={s.label}
                  content={s.content}
                  highlight={s.key === 'final_trade_decision'}
                />
              ))}

              {statusMsg && (
                <div className="status">
                  <span className="spinner" />
                  {statusMsg}
                </div>
              )}

              {running && !statusMsg && (
                <div className="status">
                  <span className="spinner" />
                  Agents are working…
                </div>
              )}

              {runError && (
                <div className="error">
                  <strong>The run failed.</strong>
                  <div>{runError.message}</div>
                  {runError.detail && <pre>{runError.detail}</pre>}
                </div>
              )}

              {step === 'finished' && (
                <button className="confirm" onClick={reset}>
                  Run another analysis
                </button>
              )}
            </div>
          </div>

          {!atBottom && (
            <button className="jump" onClick={jumpToLatest}>
              ↓ Jump to latest
            </button>
          )}
        </div>

        <div className="composer">
          <div className="composer-col">
            {textStep || freeText ? (
              <div className="input-row">
                <textarea
                  rows={1}
                  value={draft}
                  placeholder={
                    step === 'ticker'
                      ? 'Enter a ticker — AAPL, RELIANCE.NS, BTC-USD…'
                      : step === 'date'
                        ? `YYYY-MM-DD, or "today" for ${opts.today}`
                        : modelOpts?.hint || 'Enter a model ID'
                  }
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={onKeyDown}
                  autoFocus
                />
                <button className="send" onClick={send} disabled={!canSend} aria-label="Send">
                  ↑
                </button>
              </div>
            ) : (
              <div className="composer-hint">
                {checking
                  ? 'Checking that symbol…'
                  : running
                  ? 'Analysis in progress…'
                  : step === 'finished'
                    ? 'Run finished — start another above.'
                    : 'Choose an option above to continue'}
              </div>
            )}
            <div className="disclaimer">
              TradingAgents is for research only — not financial advice.
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

