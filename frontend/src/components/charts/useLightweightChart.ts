/** Chart lifecycle hook: owns the Lightweight Charts instance, resize
 * observation, and theme reactivity. Series management stays with the
 * calling component (imperative core, declarative edges). */
import {
  createChart,
  type ChartOptions,
  type DeepPartial,
  type IChartApi,
} from "lightweight-charts";
import { useEffect, useRef } from "react";

import { useUiStore } from "@/stores/ui";

function themeOptions(): DeepPartial<ChartOptions> {
  const css = getComputedStyle(document.documentElement);
  const v = (name: string) => css.getPropertyValue(name).trim();
  return {
    layout: {
      background: { color: "transparent" },
      textColor: v("--fg-muted"),
      fontFamily: v("--font-mono") || "ui-monospace, monospace",
      fontSize: 11,
      attributionLogo: false,
    },
    grid: {
      vertLines: { color: v("--border") },
      horzLines: { color: v("--border") },
    },
    crosshair: { mode: 0 },
    timeScale: { borderColor: v("--border-strong"), timeVisible: true },
    rightPriceScale: { borderColor: v("--border-strong") },
  };
}

export function useLightweightChart(
  onReady: (chart: IChartApi) => void | (() => void),
) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const theme = useUiStore((s) => s.theme);
  const onReadyRef = useRef(onReady);
  onReadyRef.current = onReady;

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const chart = createChart(container, {
      ...themeOptions(),
      autoSize: true,
    });
    chartRef.current = chart;
    const cleanup = onReadyRef.current(chart);
    return () => {
      cleanup?.();
      chart.remove();
      chartRef.current = null;
    };
     
  }, []);

  // re-theme in place (no chart rebuild) when the theme flips
  useEffect(() => {
    chartRef.current?.applyOptions(themeOptions());
  }, [theme]);

  return { containerRef, chartRef };
}

/** hex token -> rgba with alpha (gradients must follow the theme) */
export function hexToRgba(hex: string, alpha: number): string {
  const n = parseInt(hex.replace("#", ""), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${alpha})`;
}

export function chartColors() {
  const css = getComputedStyle(document.documentElement);
  const v = (name: string) => css.getPropertyValue(name).trim();
  return {
    bull: v("--bull"),
    bear: v("--bear"),
    neutral: v("--neutral"),
    accent: v("--accent"),
    muted: v("--fg-subtle"),
    onSolid: v("--on-solid"),
  };
}
