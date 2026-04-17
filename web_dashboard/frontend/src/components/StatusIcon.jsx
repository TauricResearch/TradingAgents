import { CheckCircleOutlined, CloseCircleOutlined, SyncOutlined } from '@ant-design/icons'

const STATUS_TAG_MAP = {
  pending:   { text: '等待',  bg: 'var(--bg-elevated)',  color: 'var(--text-muted)' },
  running:   { text: '分析中', bg: 'var(--running-dim)', color: 'var(--running)' },
  completed: { text: '完成',  bg: 'var(--buy-dim)',     color: 'var(--buy)' },
  degraded_success: { text: '降级完成', bg: 'var(--hold-dim)', color: 'var(--hold)' },
  failed:    { text: '失败',  bg: 'var(--sell-dim)',   color: 'var(--sell)' },
}

export function StatusIcon({ status }) {
  switch (status) {
    case 'completed':
      return <CheckCircleOutlined style={{ color: 'var(--buy)', fontSize: 16 }} />
    case 'degraded_success':
      return <CheckCircleOutlined style={{ color: 'var(--hold)', fontSize: 16 }} />
    case 'failed':
      return <CloseCircleOutlined style={{ color: 'var(--sell)', fontSize: 16 }} />
    case 'running':
      return <SyncOutlined spin style={{ color: 'var(--running)', fontSize: 16 }} />
    default:
      return (
        <span
          style={{
            width: 16,
            height: 16,
            borderRadius: '50%',
            border: '2px solid var(--border-strong)',
            display: 'inline-block',
          }}
        />
      )
  }
}

export function StatusTag({ status }) {
  const s = STATUS_TAG_MAP[status] || STATUS_TAG_MAP.pending
  return (
    <span
      style={{
        background: s.bg,
        color: s.color,
        padding: '2px 10px',
        borderRadius: 'var(--radius-pill)',
        fontSize: 12,
        fontWeight: 600,
      }}
    >
      {s.text}
    </span>
  )
}
