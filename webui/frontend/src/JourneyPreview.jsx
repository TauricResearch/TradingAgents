import { useState } from 'react'
import AgentActivityPanel from './AgentActivityPanel.jsx'
import { visibleAgents } from './agents.js'

const ANALYSTS = ['market', 'social', 'news', 'fundamentals']

/** A backend-free preview of the actual activity panel, with sample events. */
export default function JourneyPreview() {
  const [sections, setSections] = useState([])
  const [activity, setActivity] = useState([])
  const [filterId, setFilterId] = useState(null)
  const [theme, setTheme] = useState('dark')
  const agents = visibleAgents(ANALYSTS)
  const next = agents[sections.length]

  function finishStage() {
    if (!next) return
    setSections((prev) => [...prev, { key: next.section }])
    setActivity((prev) => [{ id: next.id, agentId: next.id, ts: Date.now(),
      title: `${next.label} finished`, status: 'done', detail: `Sample ${next.short.toLowerCase()} report. Your live analysis will show the actual research here.` }, ...prev])
  }

  return (
    <div className="app journey-preview-app" data-theme={theme}>
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark">TA</span>TradingAgents</div>
        <AgentActivityPanel selectedAnalysts={ANALYSTS} sections={sections} running={sections.length > 0 && !!next}
          statusMsg="" activity={activity} filterId={filterId} onFilter={setFilterId} />
      </aside>
      <main className="main">
        <header className="header">
          <div><div className="header-title">A new way to follow your analysis</div><div className="header-sub">Interactive UI preview · Sample data</div></div>
          <div className="theme-toggle" role="group" aria-label="Preview theme">
            {['light', 'dark'].map((value) => <button key={value} className={`theme-btn${theme === value ? ' on' : ''}`}
              onClick={() => setTheme(value)} aria-pressed={theme === value}>{value === 'light' ? 'Light' : 'Dark'}</button>)}
          </div>
        </header>
        <div className="journey-preview-content">
          <span className="journey-eyebrow">One companion. Every step.</span>
          <h1>Good research<br />is a journey.</h1>
          <p>Meet your research companion. A single friendly robot follows your analysis from the first market signal to the final portfolio decision.</p>
          <p>Watch it travel between checkpoints using <strong>Preview the journey</strong>, or complete a sample stage below to try a real handoff.</p>
          <div className="preview-controls">
            <button className="confirm" onClick={finishStage} disabled={!next}>{next ? `Complete ${next.short} stage →` : 'All stages complete'}</button>
            <button className="filter-clear" onClick={() => { setSections([]); setActivity([]); setFilterId(null) }}>Reset stages</button>
          </div>
          <a className="preview-back" href="/">Open TradingAgents ↗</a>
        </div>
      </main>
    </div>
  )
}
