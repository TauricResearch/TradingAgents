import * as React from "react";

import { cn } from "@/lib/utils";

export const Input = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(({ className, ...props }, ref) => (
  <input
    ref={ref}
    className={cn(
      "h-8 w-full rounded-md border border-border-strong bg-surface-2 px-3 text-sm",
      "placeholder:text-fg-subtle focus-visible:outline-2 focus-visible:outline-accent",
      className,
    )}
    {...props}
  />
));
Input.displayName = "Input";
