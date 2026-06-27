export function Spinner({ size = "md", className = "" }: { size?: "sm" | "md" | "lg"; className?: string }) {
  const dim = size === "sm" ? "w-4 h-4" : size === "lg" ? "w-8 h-8" : "w-5 h-5";
  return (
    <div
      className={`${dim} rounded-full border-2 border-sky-500/30 border-t-sky-400 animate-spin ${className}`}
      role="status"
      aria-label="Loading"
    />
  );
}
