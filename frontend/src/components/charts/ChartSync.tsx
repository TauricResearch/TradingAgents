/** Crosshair + visible-range synchronization across charts in a group.
 * Time-based only: each chart keeps its own price scale (overlaying two
 * assets on one scale would be dishonest visual math). An isSyncing
 * guard breaks the feedback loop. */
import type { IChartApi, LogicalRange, MouseEventParams } from "lightweight-charts";
import {
  createContext,
  useContext,
  useEffect,
  useRef,
  type ReactNode,
  type RefObject,
} from "react";

interface SyncRegistry {
  register: (id: string, chart: IChartApi) => () => void;
}

const SyncContext = createContext<SyncRegistry | null>(null);

export function ChartSyncProvider({ children }: { children: ReactNode }) {
  const chartsRef = useRef(new Map<string, IChartApi>());
  const isSyncingRef = useRef(false);

  const registryRef = useRef<SyncRegistry>({
    register(id, chart) {
      chartsRef.current.set(id, chart);

      const onRange = (range: LogicalRange | null) => {
        if (!range || isSyncingRef.current) return;
        isSyncingRef.current = true;
        try {
          chartsRef.current.forEach((peer, peerId) => {
            if (peerId !== id) {
              peer.timeScale().setVisibleLogicalRange(range);
            }
          });
        } finally {
          isSyncingRef.current = false;
        }
      };

      const onCrosshair = (params: MouseEventParams) => {
        if (isSyncingRef.current) return;
        isSyncingRef.current = true;
        try {
          chartsRef.current.forEach((peer, peerId) => {
            if (peerId === id) return;
            if (params.time == null) {
              peer.clearCrosshairPosition();
              return;
            }
            // sync by time against the peer's first series
            const peerSeries = peer.panes()[0]?.getSeries()[0];
            if (peerSeries) {
              peer.setCrosshairPosition(NaN, params.time, peerSeries);
            }
          });
        } finally {
          isSyncingRef.current = false;
        }
      };

      chart.timeScale().subscribeVisibleLogicalRangeChange(onRange);
      chart.subscribeCrosshairMove(onCrosshair);
      return () => {
        chart.timeScale().unsubscribeVisibleLogicalRangeChange(onRange);
        chart.unsubscribeCrosshairMove(onCrosshair);
        chartsRef.current.delete(id);
      };
    },
  });

  return (
    <SyncContext.Provider value={registryRef.current}>
      {children}
    </SyncContext.Provider>
  );
}

/** Called by PriceChart: joins the surrounding sync group when syncId set. */
export function useChartSync(
  syncId: string | undefined,
  chartRef: RefObject<IChartApi | null>,
) {
  const registry = useContext(SyncContext);
  useEffect(() => {
    const chart = chartRef.current;
    if (!syncId || !registry || !chart) return;
    return registry.register(syncId, chart);
  }, [syncId, registry, chartRef]);
}
