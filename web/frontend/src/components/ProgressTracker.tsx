import type { CSSProperties } from 'react';
import type { AgentState, AgentStatus, Stats } from '../types';

interface Team {
  name: string;
  agents: string[];
}

const FIXED_TEAMS: Team[] = [
  { name: 'Research', agents: ['Bull Researcher', 'Bear Researcher', 'Research Manager'] },
  { name: 'Trading',  agents: ['Trader'] },
  { name: 'Risk',     agents: ['Aggressive Analyst', 'Neutral Analyst', 'Conservative Analyst'] },
  { name: 'Portfolio', agents: ['Portfolio Manager'] },
];

const ANALYST_MAP: Record<string, string> = {
  market:       'Market Analyst',
  social:       'Social Analyst',
  news:         'News Analyst',
  fundamentals: 'Fundamentals Analyst',
};

interface Props {
  agentState: AgentState;
  selectedAnalysts: string[];
  stats: Stats | null;
}

function Dot({ status }: { status: AgentStatus }) {
  const styles: Record<AgentStatus, CSSProperties> = {
    pending:     { background: 'var(--border)' },
    in_progress: { background: 'var(--accent)', boxShadow: '0 0 6px var(--accent)' },
    completed:   { background: 'var(--green)' },
  };
  return (
    <span style={{
      display: 'inline-block', width: 10, height: 10, borderRadius: '50%',
      flexShrink: 0, ...styles[status],
    }} />
  );
}

function AgentDot({ name, status }: { name: string; status: AgentStatus }) {
  const color = status === 'completed'   ? 'var(--green)'
              : status === 'in_progress' ? 'var(--accent-light)'
              : 'var(--text-muted)';
  return (
    <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 12 }}>
      <Dot status={status} />
      <span style={{ color }}>{name}</span>
    </span>
  );
}

function fmtTokens(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n);
}

function fmtTime(s: number): string {
  const m   = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
}

export default function ProgressTracker({ agentState, selectedAnalysts, stats }: Props) {
  const analystTeam: Team = {
    name: 'Analysts',
    agents: selectedAnalysts.map(k => ANALYST_MAP[k]).filter(Boolean),
  };
  const allTeams = analystTeam.agents.length > 0
    ? [analystTeam, ...FIXED_TEAMS]
    : FIXED_TEAMS;

  return (
    <div style={{
      background: 'var(--bg-card)', borderRadius: 8, padding: '12px 16px',
      display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 8, marginBottom: 16,
    }}>
      {allTeams.map((team, ti) => (
        <span key={team.name} style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          {ti > 0 && <span style={{ color: 'var(--border)', fontSize: 16, padding: '0 4px' }}>›</span>}
          {team.agents.map(agent => (
            <AgentDot
              key={agent}
              name={agent}
              status={(agentState[agent] ?? 'pending') as AgentStatus}
            />
          ))}
        </span>
      ))}
      {stats && (
        <span style={{
          marginLeft: 'auto', display: 'flex', gap: 14,
          fontSize: 12, color: 'var(--text-secondary)', whiteSpace: 'nowrap',
        }}>
          <span>LLM: <strong>{stats.llm_calls}</strong></span>
          <span>Tools: <strong>{stats.tool_calls}</strong></span>
          <span>Tokens: <strong>{fmtTokens(stats.tokens_in)}↑ {fmtTokens(stats.tokens_out)}↓</strong></span>
          <span>⏱ {fmtTime(stats.elapsed_seconds)}</span>
        </span>
      )}
    </div>
  );
}
