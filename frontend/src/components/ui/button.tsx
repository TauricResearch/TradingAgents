import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 rounded-xl font-bold transition-colors focus-visible:outline-2 focus-visible:outline-accent disabled:pointer-events-none disabled:opacity-50 cursor-pointer",
  {
    variants: {
      variant: {
        // primary CTA: solid brand with a soft brand shadow (reskin)
        default:
          "bg-accent text-on-solid hover:bg-brand-strong shadow-[0_8px_18px_-8px_rgba(36,86,197,0.6)]",
        // the pre-reskin default look, kept for chip-like secondary actions
        muted:
          "bg-accent-muted text-accent hover:bg-accent/20 border border-border",
        ghost: "hover:bg-surface-2 text-fg-muted hover:text-fg",
        outline: "border border-border-strong bg-transparent hover:bg-surface-2",
        destructive: "bg-bear-muted text-bear border border-bear/40 hover:bg-bear/25",
      },
      // dims mirror the mockup: md = 36px/20px pad/13px, sm = 32px/14px/10px radius
      size: {
        sm: "h-8 rounded-[10px] px-3.5 text-xs",
        md: "h-9 px-5 text-[13px]",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: { variant: "default", size: "md" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  ),
);
Button.displayName = "Button";
