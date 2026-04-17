import {
  getDataQualitySummary,
  getDegradationSummary,
  isDegradedPayload,
} from '../utils/contractView'

const cueStyle = {
  display: 'inline-flex',
  alignItems: 'center',
  padding: '2px 8px',
  borderRadius: 'var(--radius-pill)',
  background: 'var(--hold-dim)',
  color: 'var(--hold)',
  fontSize: 11,
  fontWeight: 600,
  lineHeight: 1.4,
}

function formatCode(code) {
  return String(code).replace(/_/g, ' ')
}

export default function ContractCues({ payload, style = null }) {
  const dataQuality = getDataQualitySummary(payload)
  const degradation = getDegradationSummary(payload)
  const primaryReason = degradation?.reason_codes?.[0] || null
  const dataQualityState = dataQuality?.state || null
  const items = []

  if (isDegradedPayload(payload)) {
    items.push(primaryReason && primaryReason !== dataQualityState
      ? `降级 · ${formatCode(primaryReason)}`
      : '降级结果')
  }

  if (dataQualityState) {
    items.push(`数据 · ${formatCode(dataQualityState)}`)
  }

  if (items.length === 0) return null

  return (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', ...style }}>
      {items.map((item) => (
        <span key={item} style={cueStyle}>
          {item}
        </span>
      ))}
    </div>
  )
}
