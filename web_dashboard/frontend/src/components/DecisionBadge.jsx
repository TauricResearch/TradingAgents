export default function DecisionBadge({ decision }) {
  if (!decision) return null
  const classMap = {
    BUY: 'badge-buy',
    OVERWEIGHT: 'badge-overweight',
    HOLD: 'badge-hold',
    UNDERWEIGHT: 'badge-underweight',
    SELL: 'badge-sell',
  }
  const cls = classMap[decision] || 'badge-hold'
  return <span className={cls}>{decision}</span>
}
