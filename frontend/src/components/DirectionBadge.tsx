/** A11Y-01 enforced by construction: direction always renders as
 * glyph + word + color together — never color alone. */
import { DIRECTION_GLYPH, directionOf } from "@/lib/format";
import { cn } from "@/lib/utils";

const TEXT: Record<string, string> = {
  bull: "text-bull",
  bear: "text-bear",
  neutral: "text-neutral",
};

export function DirectionBadge({
  value,
  showWord = true,
  className,
}: {
  value: string | null | undefined;
  showWord?: boolean;
  className?: string;
}) {
  const direction = directionOf(value);
  return (
    <span className={cn("inline-flex items-center gap-1", TEXT[direction], className)}>
      <span aria-hidden="true">{DIRECTION_GLYPH[direction]}</span>
      {showWord && <span>{value ?? "—"}</span>}
    </span>
  );
}
