import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 rounded-md text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-accent disabled:pointer-events-none disabled:opacity-50 cursor-pointer",
  {
    variants: {
      variant: {
        default: "bg-accent-muted text-accent hover:bg-accent/20 border border-border-strong",
        ghost: "hover:bg-surface-2 text-fg-muted hover:text-fg",
        outline: "border border-border-strong bg-transparent hover:bg-surface-2",
        destructive: "bg-bear-muted text-bear border border-bear/40 hover:bg-bear/25",
      },
      size: {
        sm: "h-7 px-2 text-xs",
        md: "h-8 px-3",
        icon: "h-8 w-8",
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
