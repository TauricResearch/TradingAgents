import { useEffect, useMemo, useRef, useState } from 'react'
import AgentBot from './AgentBot.jsx'
import { STATUS_LABEL, visibleAgents } from './agents.js'

const STATION_H = 56
const TRAVEL_MS = 1350
const DESCRIPTIONS = {
  market: 'Reading price action & trends',
  social: 'Listening to market sentiment',
  news: 'Connecting the latest headlines',
  fundamentals: 'Looking beneath the numbers',
  research: 'Bringing the evidence together',
  trader: 'Building the trading plan',
  portfolio: 'Making the final decision',
}

function useReducedMotion() {
  const [reduced, setReduced] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    const change = () => setReduced(media.matches)
    media.addEventListener('change', change)
    return () => media.removeEventListener('change', change)
  }, [])
  return reduced
}

function ActivityRow({ row, expanded, onToggle }) {
  return (
    <div className="act-row">
      <button type="button" className="act-main" onClick={() => row.detail && onToggle(row.id)}
        aria-expanded={row.detail ? expanded : undefined} disabled={!row.detail}>
        <span className={`act-dot ${row.status === 'done' ? 'complete' : ''}`} aria-hidden="true" />
        <span className="act-copy">
          <span className="act-name">{row.title}</span>
          <span className="act-meta">{new Date(row.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
        </span>
        {row.detail && <span className="act-expand" aria-hidden="true">{expanded ? '−' : '+'}</span>}
      </button>
      {row.detail && expanded && <pre className="act-detail">{row.detail}</pre>}
    </div>
  )
}

export default function AgentActivityPanel({ selectedAnalysts, sections, running, statusMsg, activity, filterId, onFilter }) {
  const agents = useMemo(() => visibleAgents(selectedAnalysts), [selectedAnalysts])
  const doneKeys = useMemo(() => new Set(sections.map((s) => s.key)), [sections])
  const firstPending = agents.findIndex((a) => !doneKeys.has(a.section))
  const actualTarget = firstPending === -1 ? agents.length - 1 : firstPending
  const [cursor, setCursor] = useState(0)
  const [travel, setTravel] = useState(null)
  const [demoTarget, setDemoTarget] = useState(null)
  const [openId, setOpenId] = useState(null)
  const reduced = useReducedMotion()
  const logRef = useRef(null)
  const demo = demoTarget !== null && !running
  const target = demo ? demoTarget : actualTarget
  const routeKey = agents.map((a) => a.id).join(',')

  useEffect(() => {
    setDemoTarget(null)
    setCursor(0)
    setTravel(null)
  }, [routeKey])

  // Reports may arrive in a burst. Visit every checkpoint with one robot.
  useEffect(() => {
    if (running) setDemoTarget(null)
    if (!demo && (target < cursor || sections.length === 0)) {
      setCursor(target)
      setTravel(null)
    }
  }, [running, demo, target, cursor, sections.length, routeKey])

  useEffect(() => {
    if (travel || cursor >= target) return undefined
    if (reduced) { setCursor(target); return undefined }
    const timer = setTimeout(() => setTravel({ from: cursor, to: cursor + 1 }), 380)
    return () => clearTimeout(timer)
  }, [cursor, target, travel, reduced])

  useEffect(() => {
    if (!travel) return undefined
    const timer = setTimeout(() => {
      setCursor(travel.to)
      setTravel(null)
    }, reduced ? 0 : TRAVEL_MS)
    return () => clearTimeout(timer)
  }, [travel, reduced])

  useEffect(() => {
    if (!demo || travel || cursor !== demoTarget) return undefined
    const timer = setTimeout(() => {
      setDemoTarget(demoTarget === agents.length - 1 ? null : demoTarget + 1)
    }, 1800)
    return () => clearTimeout(timer)
  }, [demo, demoTarget, cursor, travel, agents.length])

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = 0
  }, [activity.length])

  const safeCursor = Math.min(cursor, agents.length - 1)
  const current = agents[safeCursor]
  const destination = agents[Math.min(travel?.to ?? safeCursor + 1, agents.length - 1)]
  const complete = !demo && firstPending === -1 && !travel && cursor === target
  const working = running || demo || cursor < target
  const state = travel ? 'walking' : complete ? 'done' : working ? 'processing' : 'idle'
  const completedCount = demo ? demoTarget : agents.filter((a) => doneKeys.has(a.section)).length
  const filtered = filterId ? activity.filter((row) => row.agentId === filterId) : activity
  const preview = () => {
    setTravel(null)
    setCursor(demo ? actualTarget : 0)
    setDemoTarget(demo ? null : 0)
  }

  return (
    <div className="agent-panel">
      <div className="journey-heading">
        <span className="rail-title">Agent journey</span>
        <span className={`journey-indicator${working ? ' live' : ''}`}>
          <i />{demo ? 'Preview' : running ? 'Live' : complete ? 'Complete' : working ? 'Finishing' : sections.length ? 'Paused' : 'Standby'}
        </span>
      </div>

      <div className="journey-card">
        <div className="journey-intro" role="status" aria-live="polite">
          <span className="journey-eyebrow">{travel ? 'On the move' : complete ? 'Journey complete' : `Stage ${safeCursor + 1} / ${agents.length}`}</span>
          <h2>{travel ? `Next stop: ${destination.short}` : current.label}</h2>
          <p>{travel ? 'Carrying the research forward' : complete ? 'Your analysis is ready to explore.' : running && statusMsg ? statusMsg : DESCRIPTIONS[current.id]}</p>
        </div>

        <div className={`journey-route${travel ? ' is-traveling' : ''}`} style={{ height: agents.length * STATION_H, '--station-height': `${STATION_H}px` }}>
          <div className="journey-track" aria-hidden="true" />
          <div className="journey-track-fill" style={{ height: (travel?.to ?? safeCursor) * STATION_H }} aria-hidden="true" />
          {agents.map((agent, index) => {
            const done = demo ? index < demoTarget : doneKeys.has(agent.section)
            const active = index === safeCursor
            return (
              <button key={agent.id} type="button"
                className={`journey-stop${active ? ' active' : ''}${done ? ' done' : ''}${filterId === agent.id ? ' selected' : ''}`}
                style={{ top: index * STATION_H }}
                onClick={() => onFilter(filterId === agent.id ? null : agent.id)}
                aria-pressed={filterId === agent.id} aria-current={active ? 'step' : undefined}
                aria-label={`${agent.label}, ${done ? 'complete' : active ? STATUS_LABEL[state] : 'upcoming'}. Filter activity`}>
                <span className="checkpoint" aria-hidden="true">{done ? '✓' : String(index + 1).padStart(2, '0')}</span>
                <span className="stop-copy"><span className="stop-name">{agent.short}</span>
                  <span className="stop-status">{active ? (travel ? 'Passing the baton' : complete ? 'Analysis complete' : working ? 'Working on it' : sections.length ? 'Paused' : 'Ready to begin') : done ? 'Complete' : 'Up next'}</span>
                </span>
                {active && <span className={`stop-beacon${travel ? ' traveling' : ''}`} aria-hidden="true" />}
              </button>
            )
          })}
          <div className={`journey-companion${travel ? ' traveling' : ''}`}
            style={{ transform: `translateY(${(travel?.to ?? safeCursor) * STATION_H}px)` }}>
            <AgentBot state={state} size={48} title={travel ? `Robot traveling to ${destination.label}` : `Friendly robot at ${current.label}`} />
          </div>
        </div>

        <div className="journey-footer">
          <span>{complete ? 'All checkpoints complete' : `${completedCount} of ${agents.length} checkpoints`}</span>
          <span className="journey-footer-mark" aria-hidden="true">✦</span>
        </div>
      </div>

      {!running && <button type="button" className={`journey-preview${demo ? ' playing' : ''}`} onClick={preview}>
        <span className="preview-icon" aria-hidden="true">{demo ? '■' : '▷'}</span>
        {demo ? 'Stop preview' : 'Preview the journey'}<span aria-hidden="true">{demo ? '' : '↗'}</span>
      </button>}

      <div className="activity-heading"><span className="rail-title">Activity feed</span><span>{filtered.length}</span></div>
      {filterId && <button type="button" className="filter-clear" onClick={() => onFilter(null)}>Showing {agents.find((a) => a.id === filterId)?.short} · Clear</button>}
      <div className="act-log" ref={logRef}>
        {filtered.length === 0 ? <div className="act-empty">{running ? 'The journey has started. Updates appear here.' : 'A little teamwork. A clearer picture.\nStart an analysis to follow along.'}</div>
          : filtered.map((row) => <ActivityRow key={row.id} row={row} expanded={openId === row.id} onToggle={(id) => setOpenId((value) => value === id ? null : id)} />)}
      </div>
    </div>
  )
}
