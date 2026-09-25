/**
 * The brand mark, drawn to match "The Print" concept used for the decision
 * stamp: a rotated stamp border around a monogram, rendered in currentColor
 * so it inherits ink/paper from the theme instead of carrying its own
 * hard-coded colors.
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
      <rect
        x="2.5"
        y="4.5"
        width="24"
        height="24"
        rx="3"
        transform="rotate(-6 14.5 16.5)"
        stroke="currentColor"
        strokeWidth="2.25"
      />
      <path
        d="M10 13.5h11M15.5 13.5v9"
        transform="rotate(-6 14.5 16.5)"
        stroke="currentColor"
        strokeWidth="2.25"
        strokeLinecap="round"
      />
    </svg>
  );
}
