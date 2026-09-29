export function StatCard({ label, value, hint, tone }) {
  return (
    <div className="stat-card">
      <span className="stat-card__label">{label}</span>
      <span className="stat-card__value" data-tone={tone}>
        {value}
      </span>
      {hint && <span className="stat-card__hint">{hint}</span>}
    </div>
  );
}
