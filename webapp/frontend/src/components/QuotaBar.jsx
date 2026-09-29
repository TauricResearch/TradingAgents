export function QuotaBar({ used, limit }) {
  const pct = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;
  const tone = pct >= 100 ? "sell" : pct >= 70 ? "hold" : "brand";
  return (
    <div className="quota-bar">
      <div className="quota-bar__track">
        <div className="quota-bar__fill" data-tone={tone} style={{ width: `${pct}%` }} />
      </div>
      <span className="quota-bar__label">
        {used}/{limit} runs this month
      </span>
    </div>
  );
}
