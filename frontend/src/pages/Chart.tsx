import { useEffect, useRef, useState, useCallback } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import axios from 'axios'
import {
  createChart,
  ColorType,
  CandlestickSeries,
  HistogramSeries,
  createSeriesMarkers,
} from 'lightweight-charts'
import type { IChartApi, ISeriesApi } from 'lightweight-charts'
import { Search, TrendingUp, TrendingDown, Minus, RefreshCw, ExternalLink } from 'lucide-react'

// ── Types ──────────────────────────────────────────────────────────────────────

interface Candle {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

interface KeyLevel { price: number; label: string; type: string }

interface ChartAnnotations {
  support_levels?: number[]
  resistance_levels?: number[]
  target_price?: number | null
  stop_loss?: number | null
  key_levels?: KeyLevel[]
}

interface AnalysisItem {
  id: number
  ticker: string
  trade_date: string
  signal: string | null
  chart_annotations: string
  created_at: string
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function parseAnnotations(raw: string): ChartAnnotations {
  try { return raw ? JSON.parse(raw) : {} } catch { return {} }
}

const SIGNAL_COLOR: Record<string, string> = {
  Buy: '#10b981',
  Overweight: '#10b981',
  Hold: '#f59e0b',
  Neutral: '#f59e0b',
  Sell: '#ef4444',
  Underweight: '#ef4444',
}

function SignalBadge({ signal }: { signal: string | null }) {
  if (!signal) return <span className="text-gray-500 text-xs">—</span>
  const color = SIGNAL_COLOR[signal] ?? '#6b7280'
  const Icon = ['Buy', 'Overweight'].includes(signal) ? TrendingUp
    : ['Sell', 'Underweight'].includes(signal) ? TrendingDown : Minus
  return (
    <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full"
      style={{ backgroundColor: color + '22', color }}>
      <Icon size={11} />
      {signal}
    </span>
  )
}

const PERIODS = [
  { label: '1A', value: '1m' },
  { label: '3A', value: '3m' },
  { label: '6A', value: '6m' },
  { label: '1Y', value: '1y' },
  { label: '2Y', value: '2y' },
]

// ── Component ─────────────────────────────────────────────────────────────────

export default function ChartPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  const [tickerInput, setTickerInput] = useState(searchParams.get('ticker') ?? '')
  const [activeTicker, setActiveTicker] = useState(searchParams.get('ticker') ?? '')
  const [period, setPeriod] = useState(searchParams.get('period') ?? '1y')
  const [candles, setCandles] = useState<Candle[]>([])
  const [analyses, setAnalyses] = useState<AnalysisItem[]>([])
  const [selected, setSelected] = useState<AnalysisItem | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick', any> | null>(null)
  const volSeriesRef = useRef<ISeriesApi<'Histogram', any> | null>(null)
  const markersRef = useRef<ReturnType<typeof createSeriesMarkers> | null>(null)
  const priceLineRefs = useRef<any[]>([])

  // ── Data fetching ────────────────────────────────────────────────────────────

  const load = useCallback(async (ticker: string, p: string) => {
    if (!ticker) return
    setLoading(true)
    setError(null)
    setSelected(null)
    try {
      const [ohlcvRes, histRes] = await Promise.all([
        axios.get('/api/market/ohlcv', { params: { ticker, period: p } }),
        axios.get('/api/analysis/history', { params: { ticker, limit: 200 } }),
      ])
      setCandles(ohlcvRes.data.candles)
      setAnalyses(histRes.data)
    } catch (e: any) {
      setError(e.response?.data?.detail ?? 'Veri alınamadı.')
    } finally {
      setLoading(false)
    }
  }, [])

  const handleSearch = () => {
    const t = tickerInput.trim().toUpperCase()
    if (!t) return
    setActiveTicker(t)
    setSearchParams({ ticker: t, period })
    load(t, period)
  }

  const handlePeriod = (p: string) => {
    setPeriod(p)
    setSearchParams({ ticker: activeTicker, period: p })
    if (activeTicker) load(activeTicker, p)
  }

  useEffect(() => {
    if (activeTicker) load(activeTicker, period)
  }, []) // initial load from URL params

  // ── Chart setup ──────────────────────────────────────────────────────────────

  useEffect(() => {
    if (!chartContainerRef.current) return

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#111827' },
        textColor: '#9ca3af',
      },
      grid: {
        vertLines: { color: '#1f2937' },
        horzLines: { color: '#1f2937' },
      },
      crosshair: { mode: 1 },
      rightPriceScale: { borderColor: '#374151' },
      timeScale: { borderColor: '#374151', timeVisible: true },
      width: chartContainerRef.current.clientWidth,
      height: 420,
    })

    // Candlestick series (top 70%)
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981',
      downColor: '#ef4444',
      borderUpColor: '#10b981',
      borderDownColor: '#ef4444',
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
      priceScaleId: 'right',
    })

    // Volume histogram (bottom 30%)
    const volSeries = chart.addSeries(HistogramSeries, {
      color: '#374151',
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    })
    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    })
    chart.priceScale('right').applyOptions({
      scaleMargins: { top: 0, bottom: 0.25 },
    })

    chartRef.current = chart
    candleSeriesRef.current = candleSeries
    volSeriesRef.current = volSeries

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth })
      }
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
      chartRef.current = null
      candleSeriesRef.current = null
      volSeriesRef.current = null
      markersRef.current = null
    }
  }, [])

  // ── Update chart data ─────────────────────────────────────────────────────────

  useEffect(() => {
    if (!candleSeriesRef.current || !volSeriesRef.current || candles.length === 0) return

    candleSeriesRef.current.setData(candles.map(c => ({
      time: c.time as any,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    })))

    volSeriesRef.current.setData(candles.map(c => ({
      time: c.time as any,
      value: c.volume,
      color: c.close >= c.open ? '#10b98133' : '#ef444433',
    })))

    // Clear old price lines
    priceLineRefs.current.forEach(pl => {
      try { candleSeriesRef.current?.removePriceLine(pl) } catch { /* ignore */ }
    })
    priceLineRefs.current = []

    // Add AI price level lines from ALL analyses in current range
    const tradeDatesInRange = new Set(candles.map(c => c.time))

    analyses.forEach(a => {
      if (!tradeDatesInRange.has(a.trade_date)) return
      const ann = parseAnnotations(a.chart_annotations)

      ;(ann.support_levels ?? []).forEach(price => {
        try {
          const pl = candleSeriesRef.current!.createPriceLine({
            price, color: '#ef444466', lineWidth: 1, lineStyle: 2,
            axisLabelVisible: false, title: '',
          })
          priceLineRefs.current.push(pl)
        } catch { /* ignore */ }
      })
      ;(ann.resistance_levels ?? []).forEach(price => {
        try {
          const pl = candleSeriesRef.current!.createPriceLine({
            price, color: '#3b82f666', lineWidth: 1, lineStyle: 2,
            axisLabelVisible: false, title: '',
          })
          priceLineRefs.current.push(pl)
        } catch { /* ignore */ }
      })
      if (ann.target_price) {
        try {
          const pl = candleSeriesRef.current!.createPriceLine({
            price: ann.target_price, color: '#10b98199', lineWidth: 1, lineStyle: 3,
            axisLabelVisible: true, title: 'Hedef',
          })
          priceLineRefs.current.push(pl)
        } catch { /* ignore */ }
      }
      if (ann.stop_loss) {
        try {
          const pl = candleSeriesRef.current!.createPriceLine({
            price: ann.stop_loss, color: '#ef444499', lineWidth: 1, lineStyle: 3,
            axisLabelVisible: true, title: 'Stop',
          })
          priceLineRefs.current.push(pl)
        } catch { /* ignore */ }
      }
    })

    // Add signal markers (v5: createSeriesMarkers plugin)
    if (markersRef.current) {
      try { markersRef.current.setMarkers([]) } catch { /* ignore */ }
    }
    const markerData = analyses
      .filter(a => a.signal && tradeDatesInRange.has(a.trade_date))
      .map(a => ({
        time: a.trade_date as any,
        position: (['Buy', 'Overweight'].includes(a.signal!) ? 'belowBar' : 'aboveBar') as any,
        color: SIGNAL_COLOR[a.signal!] ?? '#6b7280',
        shape: (['Buy', 'Overweight'].includes(a.signal!) ? 'arrowUp' : ['Sell', 'Underweight'].includes(a.signal!) ? 'arrowDown' : 'circle') as any,
        text: a.signal!,
        size: 1,
      }))
      .sort((a, b) => (a.time as string).localeCompare(b.time as string))

    try {
      if (!markersRef.current) {
        markersRef.current = createSeriesMarkers(candleSeriesRef.current as any, markerData)
      } else {
        markersRef.current.setMarkers(markerData)
      }
    } catch { /* ignore */ }

    chartRef.current?.timeScale().fitContent()
  }, [candles, analyses])

  // ── Render ───────────────────────────────────────────────────────────────────

  const analysesInRange = activeTicker
    ? analyses.filter(a => candles.some(c => c.time === a.trade_date))
    : []

  return (
    <div className="p-6 space-y-5 max-w-7xl">
      <h2 className="text-xl font-bold text-white tracking-tight">Trading Grafik</h2>

      {/* Search bar */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 bg-gray-900 border border-gray-700 rounded-xl px-3 py-2 flex-1 max-w-xs">
          <Search size={15} className="text-gray-500" />
          <input
            className="bg-transparent text-white text-sm outline-none flex-1 uppercase"
            placeholder="AAPL, TSLA, NVDA..."
            value={tickerInput}
            onChange={e => setTickerInput(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === 'Enter' && handleSearch()}
          />
        </div>
        <button
          onClick={handleSearch}
          className="bg-violet-600 hover:bg-violet-500 text-white text-sm font-semibold px-4 py-2 rounded-xl transition"
        >
          Göster
        </button>

        {/* Period selector */}
        {activeTicker && (
          <div className="flex gap-1 ml-2">
            {PERIODS.map(p => (
              <button
                key={p.value}
                onClick={() => handlePeriod(p.value)}
                className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition ${
                  period === p.value
                    ? 'bg-violet-600 text-white'
                    : 'bg-gray-800 text-gray-400 hover:text-white'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        )}

        {loading && <RefreshCw size={16} className="text-violet-400 animate-spin" />}
      </div>

      {error && (
        <div className="bg-red-900/30 border border-red-700 text-red-300 text-sm rounded-xl px-4 py-3">
          {error}
        </div>
      )}

      {/* Main layout: chart + side panel */}
      <div className="flex gap-5">
        {/* Chart */}
        <div className="flex-1 min-w-0">
          <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden">
            {activeTicker && (
              <div className="px-5 py-3 border-b border-gray-800 flex items-center gap-3">
                <span className="text-white font-bold">{activeTicker}</span>
                {candles.length > 0 && (
                  <span className="text-gray-400 text-sm">
                    {candles[candles.length - 1].close.toFixed(2)} USD
                  </span>
                )}
              </div>
            )}
            <div ref={chartContainerRef} className="w-full" />
            {!activeTicker && (
              <div className="flex flex-col items-center justify-center h-[420px] text-gray-600">
                <TrendingUp size={40} className="mb-3 opacity-30" />
                <p className="text-sm">Bir hisse sembolü girin ve "Göster" tuşuna basın</p>
                <p className="text-xs mt-1 opacity-60">AI sinyalleri grafik üzerinde işaretlenir</p>
              </div>
            )}
          </div>

          {/* Legend */}
          {activeTicker && (
            <div className="flex flex-wrap gap-4 mt-3 px-1 text-xs text-gray-500">
              <span className="flex items-center gap-1"><span className="inline-block w-4 h-0.5 bg-emerald-500 opacity-60" style={{borderTop: '2px dashed #10b981'}} /> Destek</span>
              <span className="flex items-center gap-1"><span className="inline-block w-4 h-0.5" style={{borderTop: '2px dashed #3b82f6'}} /> Direnç</span>
              <span className="flex items-center gap-1"><span className="inline-block w-4 h-0.5" style={{borderTop: '1px solid #10b981'}} /> Hedef</span>
              <span className="flex items-center gap-1"><span className="inline-block w-4 h-0.5" style={{borderTop: '1px solid #ef4444'}} /> Stop-Loss</span>
              <span className="flex items-center gap-1 text-emerald-400">▲ Al sinyali</span>
              <span className="flex items-center gap-1 text-red-400">▼ Sat sinyali</span>
            </div>
          )}
        </div>

        {/* Side panel */}
        {activeTicker && (
          <div className="w-72 flex-shrink-0 space-y-4">
            {/* Analysis list */}
            <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden">
              <div className="px-4 py-3 border-b border-gray-800">
                <h3 className="text-xs font-semibold text-violet-400 uppercase tracking-wider">
                  AI Analizleri ({analysesInRange.length})
                </h3>
              </div>
              <div className="max-h-80 overflow-y-auto">
                {analysesInRange.length === 0 && !loading && (
                  <p className="text-gray-600 text-xs p-4">Bu aralıkta analiz yok</p>
                )}
                {analysesInRange
                  .sort((a, b) => b.trade_date.localeCompare(a.trade_date))
                  .map(a => (
                    <button
                      key={a.id}
                      onClick={() => setSelected(selected?.id === a.id ? null : a)}
                      className={`w-full text-left px-4 py-2.5 border-b border-gray-800 last:border-0 hover:bg-gray-800 transition ${
                        selected?.id === a.id ? 'bg-gray-800' : ''
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-sm text-white font-mono">{a.trade_date}</span>
                        <SignalBadge signal={a.signal} />
                      </div>
                    </button>
                  ))}
              </div>
            </div>

            {/* Selected analysis detail */}
            {selected && (
              <AnalysisDetail
                analysis={selected}
                onReanalyze={() => navigate(`/analysis?ticker=${activeTicker}&date=${selected.trade_date}`)}
                onViewFull={() => navigate(`/analysis?id=${selected.id}`)}
              />
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Analysis detail panel ─────────────────────────────────────────────────────

function AnalysisDetail({
  analysis,
  onReanalyze,
  onViewFull,
}: {
  analysis: AnalysisItem
  onReanalyze: () => void
  onViewFull: () => void
}) {
  const ann = parseAnnotations(analysis.chart_annotations)
  const hasAnnotations = (
    (ann.support_levels?.length ?? 0) > 0 ||
    (ann.resistance_levels?.length ?? 0) > 0 ||
    ann.target_price ||
    ann.stop_loss
  )

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-2xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-400">{analysis.trade_date}</span>
        <SignalBadge signal={analysis.signal} />
      </div>

      {hasAnnotations && (
        <div className="space-y-1.5">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">AI Fiyat Seviyeleri</p>
          {(ann.support_levels ?? []).map((p, i) => (
            <div key={i} className="flex justify-between text-xs">
              <span className="text-red-400">Destek {i + 1}</span>
              <span className="text-white font-mono">${p.toFixed(2)}</span>
            </div>
          ))}
          {(ann.resistance_levels ?? []).map((p, i) => (
            <div key={i} className="flex justify-between text-xs">
              <span className="text-blue-400">Direnç {i + 1}</span>
              <span className="text-white font-mono">${p.toFixed(2)}</span>
            </div>
          ))}
          {ann.target_price && (
            <div className="flex justify-between text-xs">
              <span className="text-emerald-400">Hedef</span>
              <span className="text-white font-mono">${ann.target_price.toFixed(2)}</span>
            </div>
          )}
          {ann.stop_loss && (
            <div className="flex justify-between text-xs">
              <span className="text-red-400">Stop-Loss</span>
              <span className="text-white font-mono">${ann.stop_loss.toFixed(2)}</span>
            </div>
          )}
          {(ann.key_levels ?? []).map((kl, i) => (
            <div key={i} className="flex justify-between text-xs">
              <span className="text-gray-400 truncate pr-2">{kl.label}</span>
              <span className="text-white font-mono">${kl.price.toFixed(2)}</span>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-col gap-2 pt-1">
        <button
          onClick={onViewFull}
          className="flex items-center justify-center gap-1.5 text-xs text-violet-400 hover:text-violet-300 border border-violet-800 hover:border-violet-600 rounded-lg py-1.5 transition"
        >
          <ExternalLink size={11} /> Tam Raporu Gör
        </button>
        <button
          onClick={onReanalyze}
          className="flex items-center justify-center gap-1.5 text-xs bg-violet-600 hover:bg-violet-500 text-white rounded-lg py-1.5 transition"
        >
          <RefreshCw size={11} /> Bu Tarihe Yeniden Analiz
        </button>
      </div>
    </div>
  )
}
