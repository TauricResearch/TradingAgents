import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs whitespace-nowrap",
  {
    variants: {
      variant: {
        default: "border-border-strong bg-surface-2 text-fg-muted",
        bull: "border-bull/40 bg-bull-muted text-bull",
        bear: "border-bear/40 bg-bear-muted text-bear",
        neutral: "border-neutral/40 bg-neutral-muted text-neutral",
        accent: "border-accent/40 bg-accent-muted text-accent",
        stale: "border-stale border-dashed text-stale",
        locked: "border-border text-locked",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
