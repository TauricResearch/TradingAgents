/**
 * The brand mark: a filled badge (works as a favicon/app icon too) with an
 * ascending-bars glyph — three market bars of rising height, the same
 * abstraction the decision print is built on top of (agents read the tape,
 * print a call). Solid brand fill + a white glyph reads as a real product
 * icon, not a line-art sketch.
 */
export function Logo({ size = 28 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label="TradingAgents"
    >
      <rect width="32" height="32" rx="9" fill="var(--brand)" />
      <rect x="7" y="17" width="4.5" height="9" rx="1.4" fill="var(--on-brand)" />
      <rect x="13.75" y="11" width="4.5" height="15" rx="1.4" fill="var(--on-brand)" />
      <rect x="20.5" y="6" width="4.5" height="20" rx="1.4" fill="var(--on-brand)" />
    </svg>
  );
}
