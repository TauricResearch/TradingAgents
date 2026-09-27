import { useEffect, useMemo, useRef, useState } from 'react'
import AgentBot from './AgentBot.jsx'
import { HANDOFF, STATUS_LABEL, agentBySection, visibleAgents } from './agents.js'

const STATION_H = 76
const WALK_MS = 1500
const PAUSE_MS = 420

function prefersReducedMotion() {
  return (
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
}

function formatTime(ts) {
  try {
    return new Date(ts).toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return ''
  }
}

function stationState(agent, { doneKeys, next, awayIds, receivingIds, running }) {
  if (awayIds.has(agent.id)) return 'walking'
  if (receivingIds.has(agent.id)) return 'receiving'
  if (doneKeys.has(agent.section)) return 'done'
  if (running && next === agent.section) return 'processing'
  if (running) return 'idle'
  return 'idle'
}

function Walker({ job, yMap, accent, onDone }) {
  const [top, setTop] = useState(yMap[job.from] ?? 0)
  const [phase, setPhase] = useState('go')
  const reduce = prefersReducedMotion()

  useEffect(() => {
    if (reduce) {
      onDone(job.id)
      return undefined
    }
    const go = requestAnimationFrame(() => {
      requestAnimationFrame(() => setTop(yMap[job.to] ?? 0))
    })
    const pause = setTimeout(() => setPhase('pause'), WALK_MS)
    const back = setTimeout(() => {
      setPhase('back')
      setTop(yMap[job.from] ?? 0)
    }, WALK_MS + PAUSE_MS)
    const done = setTimeout(() => onDone(job.id), WALK_MS * 2 + PAUSE_MS + 40)
    return () => {
      cancelAnimationFrame(go)
      clearTimeout(pause)
      clearTimeout(back)
      clearTimeout(done)
    }
    // yMap is keyed by agent id; jobs only start after stations are known.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job.id, job.from, job.to, onDone, reduce])

  const walking = phase === 'go' || phase === 'back'
  return (
    <div
      className={`walker${walking ? ' is-walking' : ''}${phase === 'back' ? ' facing-up' : ''}`}
      style={{
        top,
        left: 8 + job.lane,
        transitionDuration: `${WALK_MS}ms`,
      }}
    >
      <AgentBot
        accent={accent}
        state={walking ? 'walking' : 'sending'}
        speaking
        size={48}
      />
      <span className="packet" aria-hidden />
    </div>
  )
}

function ActivityRow({ row, agent, expanded, onToggle, dim }) {
  return (
    <div className={`act-row${dim ? ' dim' : ''}`}>
      <button
        type="button"
        className="act-main"
        onClick={() => row.detail && onToggle(row.id)}
        aria-expanded={expanded}
      >
        <span className="act-icon">
          {agent ? (
            <AgentBot accent={agent.accent} state={row.status} size={28} />
          ) : (
            <span className="act-dot" />
          )}
        </span>
        <span className="act-copy">
          <span className="act-name">{row.title}</span>
          <span className="act-meta">{formatTime(row.ts)}</span>
        </span>
        <span className={`pill pill-${row.status}`}>{STATUS_LABEL[row.status] || row.status}</span>
      </button>
      {row.detail && expanded && (
        <pre className="act-detail">{row.detail}</pre>
      )}
    </div>
  )
}

export default function AgentActivityPanel({
  selectedAnalysts,
  sections,
  running,
  statusMsg,
  activity,
  walks,
  onWalkDone,
  filterId,
  onFilter,
}) {
  const agents = useMemo(
    () => visibleAgents(selectedAnalysts),
    [selectedAnalysts],
  )
  const [openId, setOpenId] = useState(null)
  const [tip, setTip] = useState(null)
  const [demoWalks, setDemoWalks] = useState([])
  const logRef = useRef(null)

  const doneKeys = useMemo(
    () => new Set(sections.map((s) => s.key)),
    [sections],
  )
  const next = useMemo(() => {
    return agents.find((a) => !doneKeys.has(a.section))?.section ?? null
  }, [agents, doneKeys])

  const allWalks = walks.concat(demoWalks)
  const awayIds = useMemo(
    () => new Set(allWalks.map((w) => w.from)),
    [allWalks],
  )
  const receivingIds = useMemo(() => {
    const s = new Set()
    for (const w of allWalks) s.add(w.to)
    return s
  }, [allWalks])

  const yMap = useMemo(() => {
    const m = {}
    agents.forEach((a, i) => {
      m[a.id] = i * STATION_H + 8
    })
    return m
  }, [agents])

  const stageH = agents.length * STATION_H + 16

  useEffect(() => {
    const el = logRef.current
    if (el) el.scrollTop = 0
  }, [activity.length])

  const lastByAgent = useMemo(() => {
    const m = {}
    for (const row of activity) {
      if (row.agentId && !m[row.agentId]) m[row.agentId] = row
    }
    return m
  }, [activity])

  const filtered = filterId
    ? activity.filter((r) => r.agentId === filterId)
    : activity

  const finishWalk = (id) => {
    if (String(id).startsWith('demo-')) {
      setDemoWalks((d) => d.filter((w) => w.id !== id))
    } else {
      onWalkDone(id)
    }
  }

  const previewWalk = () => {
    if (allWalks.length) return
    const from = agents[0]
    const to = agents.find((a) => a.id === 'research') || agents[1]
    if (!from || !to || from.id === to.id) return
    setDemoWalks((d) => [
      ...d,
      { id: `demo-${Date.now()}`, from: from.id, to: to.id, lane: 0 },
    ])
  }

  return (
    <div className="agent-panel">
      <div className="rail-title">Agent activity</div>

      <div className="agent-stage" style={{ height: stageH }}>
        <div className="track" />
        {agents.map((a) => {
          const st = stationState(a, {
            doneKeys,
            next,
            awayIds,
            receivingIds,
            running,
          })
          const last = lastByAgent[a.id]
          return (
            <button
              key={a.id}
              type="button"
              className={`station${filterId === a.id ? ' on' : ''}${st === 'processing' ? ' live' : ''}`}
              style={{ top: yMap[a.id] }}
              onClick={() => onFilter(filterId === a.id ? null : a.id)}
              onMouseEnter={() =>
                setTip({
                  id: a.id,
                  text: last
                    ? last.title
                    : st === 'processing'
                      ? statusMsg || 'Working…'
                      : STATUS_LABEL[st],
                })
              }
              onMouseLeave={() => setTip(null)}
              aria-pressed={filterId === a.id}
              title={a.label}
            >
              <span className="station-slot">
                {!awayIds.has(a.id) && (
                  <AgentBot
                    accent={a.accent}
                    state={st}
                    speaking={st === 'receiving' || st === 'sending'}
                    size={46}
                    title={a.label}
                  />
                )}
              </span>
              <span className="station-label">{a.short}</span>
              <span className={`station-badge badge-${st}`}>{STATUS_LABEL[st]}</span>
              {tip?.id === a.id && <span className="station-tip">{tip.text}</span>}
            </button>
          )
        })}

        {allWalks.map((job) => {
          const src = agents.find((a) => a.id === job.from)
          return (
            <Walker
              key={job.id}
              job={job}
              yMap={yMap}
              accent={src?.accent || '#2ee6d6'}
              onDone={finishWalk}
            />
          )
        })}
      </div>

      <div className="panel-actions">
        {!running && (
          <button type="button" className="filter-clear" onClick={previewWalk}>
            Preview a walking handoff
          </button>
        )}
        {filterId && (
          <button type="button" className="filter-clear" onClick={() => onFilter(null)}>
            Showing {agents.find((a) => a.id === filterId)?.short} · Clear
          </button>
        )}
      </div>

      <div className="act-log" ref={logRef}>
        {filtered.length === 0 ? (
          <div className="act-empty">
            {running
              ? 'Waiting for the first agent to report…'
              : 'Agents idle. Start a run to watch handoffs.'}
          </div>
        ) : (
          filtered.map((row) => (
            <ActivityRow
              key={row.id}
              row={row}
              agent={agentBySection(row.section) || agents.find((a) => a.id === row.agentId)}
              expanded={openId === row.id}
              onToggle={(id) => setOpenId((cur) => (cur === id ? null : id))}
              dim={filterId && row.agentId !== filterId}
            />
          ))
        )}
      </div>
    </div>
  )
}

export function nextHandoffJob(sectionKey, selectedAnalysts, lane) {
  const from = agentBySection(sectionKey)
  const toId = HANDOFF[sectionKey]
  if (!from || !toId) return null
  const team = visibleAgents(selectedAnalysts)
  if (!team.some((a) => a.id === from.id) || !team.some((a) => a.id === toId)) {
    return null
  }
  return {
    from: from.id,
    to: toId,
    lane: lane ?? 0,
  }
}
