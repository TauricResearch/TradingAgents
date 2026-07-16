/** Volume-profile renderer (review P2.4): right-anchored horizontal bars
 * on the price pane — width ∝ volume, value-area bins stronger, POC line
 * highlighted. The SERVER computes the distribution (Constraint 2); this
 * class only maps price→pixel and draws rectangles. */
import type { CanvasRenderingTarget2D } from "fancy-canvas";
import type {
  IChartApi,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesApi,
  ISeriesPrimitive,
  SeriesAttachedParameter,
  SeriesType,
  Time,
} from "lightweight-charts";

import type { VolumeProfile } from "@/lib/api/types";

export interface ProfileColors {
  bar: string;
  valueArea: string;
  poc: string;
}

const MAX_WIDTH_FRACTION = 0.22; // widest bin uses ≤22% of the pane

export class VolumeProfilePrimitive implements ISeriesPrimitive<Time> {
  private chart: IChartApi | null = null;
  private series: ISeriesApi<SeriesType> | null = null;
  private requestUpdateFn: (() => void) | null = null;
  private profile: VolumeProfile | null = null;
  private colors: ProfileColors = {
    bar: "rgba(100,111,132,0.18)",
    valueArea: "rgba(36,86,197,0.25)",
    poc: "#c03434",
  };
  private paneView: IPrimitivePaneView;

  constructor() {
    // eslint-disable-next-line @typescript-eslint/no-this-alias
    const source = this;
    const renderer: IPrimitivePaneRenderer = {
      draw(target: CanvasRenderingTarget2D) {
        const profile = source.profile;
        const chart = source.chart;
        const series = source.series;
        if (!profile || !chart || !series || profile.levels.length === 0) return;
        const paneWidth = chart.timeScale().width();
        const maxVolume = Math.max(...profile.levels.map((l) => l.volume));
        if (maxVolume <= 0) return;
        // bin pixel height from adjacent level midpoints
        const step =
          profile.levels.length > 1
            ? Math.abs(profile.levels[1]!.price - profile.levels[0]!.price)
            : 0;
        target.useBitmapCoordinateSpace((scope) => {
          const ctx = scope.context;
          const hr = scope.horizontalPixelRatio;
          const vr = scope.verticalPixelRatio;
          ctx.save();
          for (const level of profile.levels) {
            const yMid = series.priceToCoordinate(level.price);
            const yTop = series.priceToCoordinate(level.price + step / 2);
            const yBottom = series.priceToCoordinate(level.price - step / 2);
            if (yMid == null || yTop == null || yBottom == null) continue;
            const width =
              (level.volume / maxVolume) * paneWidth * MAX_WIDTH_FRACTION;
            const inValueArea =
              profile.value_area_low != null &&
              profile.value_area_high != null &&
              level.price >= profile.value_area_low &&
              level.price <= profile.value_area_high;
            ctx.fillStyle = inValueArea
              ? source.colors.valueArea
              : source.colors.bar;
            ctx.fillRect(
              (paneWidth - width) * hr,
              Math.min(yTop, yBottom) * vr + 0.5 * vr,
              width * hr,
              Math.max(1, Math.abs(yBottom - yTop) - 1) * vr,
            );
          }
          if (profile.poc != null) {
            const yPoc = series.priceToCoordinate(profile.poc);
            if (yPoc != null) {
              ctx.strokeStyle = source.colors.poc;
              ctx.lineWidth = 1 * vr;
              ctx.setLineDash([2 * hr, 3 * hr]);
              ctx.beginPath();
              ctx.moveTo((paneWidth * (1 - MAX_WIDTH_FRACTION)) * hr, yPoc * vr);
              ctx.lineTo(paneWidth * hr, yPoc * vr);
              ctx.stroke();
            }
          }
          ctx.restore();
        });
      },
    };
    this.paneView = { renderer: () => renderer };
  }

  attached(param: SeriesAttachedParameter<Time>): void {
    this.chart = param.chart;
    this.series = param.series;
    this.requestUpdateFn = param.requestUpdate;
  }

  detached(): void {
    this.chart = null;
    this.series = null;
    this.requestUpdateFn = null;
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return [this.paneView];
  }

  setProfile(profile: VolumeProfile | null, colors?: Partial<ProfileColors>): void {
    this.profile = profile;
    if (colors) this.colors = { ...this.colors, ...colors };
    this.requestUpdateFn?.();
  }
}
