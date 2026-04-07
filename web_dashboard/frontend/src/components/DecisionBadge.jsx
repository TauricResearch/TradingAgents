export default function DecisionBadge({ decision }) {
  if (!decision) return null
  const cls = decision === 'BUY' ? 'badge-buy' : decision === 'SELL' ? 'badge-sell' : 'badge-hold'
  return <span className={cls}>{decision}</span>
}
