/**
 * G1 - RoleIcon renders one of the 13 custom inline SVGs by icon_id.
 *
 * Stroke-based, inherits team color via currentColor. Shared line weight
 * (1.8) and 24x24 viewBox match the approved V2 mockup's visual language.
 */
import { ROLE_ICON_PATHS } from "./roleIconPaths";

export interface RoleIconProps {
  icon_id: string;
  /** Pixel size; the SVG is square. Defaults to 24. */
  size?: number;
  /** Extra class for team-color styling (e.g. "bull" / "bear" / "risk"). */
  className?: string;
}

export function RoleIcon({ icon_id, size = 24, className }: RoleIconProps): JSX.Element {
  const bundle = ROLE_ICON_PATHS[icon_id];
  if (!bundle) {
    // Unknown icon_id: render a neutral dot so the layout never breaks, but
    // the cardinality test will catch any missing mapping in CI.
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        className={className}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.8}
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <circle cx="12" cy="12" r="3" />
      </svg>
    );
  }
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {bundle.children}
    </svg>
  );
}
