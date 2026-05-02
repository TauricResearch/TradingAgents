/**
 * Datatype sparkline helper for TradingAgents dashboard.
 * Renders sparklines, bar charts, and pie charts using the Datatype font.
 * https://github.com/franktisellano/datatype
 */

export type ChartVariant = "sparkline" | "bar" | "pie";

export interface SparklineProps {
  values: number[];
  variant?: ChartVariant;
  className?: string;
  title?: string;
}

/**
 * Normalize values to 0-100 range for Datatype rendering.
 */
function normalize(values: number[], min?: number, max?: number): number[] {
  if (values.length === 0) return [];
  const lo = min ?? Math.min(...values);
  const hi = max ?? Math.max(...values);
  const range = hi - lo || 1;
  return values.map((v) => Math.round(((v - lo) / range) * 100));
}

/**
 * Build a Datatype sparkline expression.
 * {l:10,40,25,70,50,90}
 */
function sparklineExpr(values: number[]): string {
  return `{l:${values.join(",")}}`;
}

/**
 * Build a Datatype bar chart expression.
 * {b:30,70,20,90}
 */
function barExpr(values: number[]): string {
  return `{b:${values.join(",")}}`;
}

/**
 * Build a Datatype pie chart expression.
 * {p:65}
 */
function pieExpr(value: number): string {
  return `{p:${value}}`;
}

export function DatatypeChart({
  values,
  variant = "sparkline",
  className = "",
  title,
}: SparklineProps) {
  if (values.length === 0) return null;

  let expr: string;
  if (variant === "pie") {
    expr = pieExpr(values[0] ?? 0);
  } else if (variant === "bar") {
    const norm = normalize(values);
    expr = barExpr(norm);
  } else {
    const norm = normalize(values);
    expr = sparklineExpr(norm);
  }

  return (
    <span class={`datatype-chart ${className}`} title={title}>
      {expr}
    </span>
  );
}

/**
 * Determine CSS class for signal-based coloring.
 */
export function signalClass(signal: string): string {
  const s = signal.toLowerCase();
  if (s.includes("buy") || s.includes("overweight")) return "buy";
  if (s.includes("sell") || s.includes("underweight")) return "sell";
  return "hold";
}
