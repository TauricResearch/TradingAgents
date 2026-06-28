interface SkeletonProps {
  className?: string;
  lines?: number;
  width?: string;
  height?: string;
}

function SkeletonBox({ className = "" }: { className: string }) {
  return (
    <div
      className={`animate-pulse rounded-md bg-slate-700/50 ${className}`}
      aria-hidden="true"
    />
  );
}

export function Skeleton({ className = "", lines, width, height }: SkeletonProps) {
  if (lines) {
    return (
      <div className={`space-y-2 ${className}`} role="status" aria-label="Loading">
        {Array.from({ length: lines }).map((_, i) => (
          <SkeletonBox
            key={i}
            className={`h-3 ${width ?? ""} ${i === lines - 1 ? "w-3/4" : "w-full"}`}
          />
        ))}
        <span className="sr-only">Loading...</span>
      </div>
    );
  }

  return (
    <div role="status" aria-label="Loading">
      <SkeletonBox className={`${height ?? "h-4"} ${width ?? "w-full"} ${className}`} />
      <span className="sr-only">Loading...</span>
    </div>
  );
}

export function PanelSkeleton({ className = "" }: { className?: string }) {
  return (
    <div className={`glass-panel p-4 space-y-3 ${className}`} role="status" aria-label="Loading panel">
      <div className="flex items-center gap-2">
        <SkeletonBox className="h-4 w-4 rounded-full" />
        <SkeletonBox className="h-3 w-32" />
      </div>
      <SkeletonBox className="h-2 w-full" />
      <SkeletonBox className="h-2 w-5/6" />
      <SkeletonBox className="h-2 w-4/6" />
      <span className="sr-only">Loading...</span>
    </div>
  );
}
