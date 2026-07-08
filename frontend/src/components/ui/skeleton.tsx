import { cn } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn("animate-pulse rounded-md bg-surface-2", className)}
      aria-hidden="true"
    />
  );
}

export function SkeletonCard({ lines = 3 }: { lines?: number }) {
  return (
    <div className="space-y-2 p-1">
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} className={i === 0 ? "h-5 w-1/3" : "h-4 w-full"} />
      ))}
    </div>
  );
}
