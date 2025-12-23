"use client";

import { useState, useMemo } from "react";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Rectangle,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useLanguage } from "@/contexts/LanguageContext";
import type { PriceData, PriceStats } from "@/lib/types";

interface PriceChartProps {
  priceData: PriceData[];
  priceStats: PriceStats;
  ticker: string;
}

// Heikin Ashi data structure
interface HeikinAshiData extends PriceData {
  HA_Open: number;
  HA_Close: number;
  HA_High: number;
  HA_Low: number;
}

// Calculate Heikin Ashi values from regular OHLC data
function calculateHeikinAshi(data: PriceData[]): HeikinAshiData[] {
  const haData: HeikinAshiData[] = [];
  
  for (let i = 0; i < data.length; i++) {
    const current = data[i];
    const { Open, High, Low, Close } = current;
    const adjClose = current["Adj Close"] ?? Close;
    
    // HA Close = (Open + High + Low + Close) / 4
    const HA_Close = (Open + High + Low + adjClose) / 4;
    
    // HA Open = (previous HA Open + previous HA Close) / 2
    let HA_Open: number;
    if (i === 0) {
      // For the first candle, use regular Open
      HA_Open = Open;
    } else {
      HA_Open = (haData[i - 1].HA_Open + haData[i - 1].HA_Close) / 2;
    }
    
    // HA High = max(High, HA Open, HA Close)
    const HA_High = Math.max(High, HA_Open, HA_Close);
    
    // HA Low = min(Low, HA Open, HA Close)
    const HA_Low = Math.min(Low, HA_Open, HA_Close);
    
    haData.push({
      ...current,
      HA_Open,
      HA_Close,
      HA_High,
      HA_Low,
    });
  }
  
  return haData;
}

export function PriceChart({ priceData, priceStats, ticker }: PriceChartProps) {
  const { t, locale } = useLanguage();
  const [chartType, setChartType] = useState<"line" | "candlestick">("line");

  // Calculate Heikin Ashi data
  const heikinAshiData = useMemo(() => calculateHeikinAshi(priceData), [priceData]);

  // 格式化數字
  const formatNumber = (num: number) => {
    return num.toLocaleString(locale === 'en' ? 'en-US' : 'zh-TW', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  };

  // 格式化日期（只顯示月-日）
  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return `${date.getMonth() + 1}/${date.getDate()}`;
  };

  // Get the close field to use (prefer Adj Close)
  const getCloseValue = (data: PriceData) => {
    return data["Adj Close"] ?? data.Close;
  };

  // 計算價格範圍用於標準化
  const priceValues = heikinAshiData.flatMap(d => [d.HA_High, d.HA_Low]);
  const minPrice = Math.min(...priceValues);
  const maxPrice = Math.max(...priceValues);
  const priceRange = maxPrice - minPrice;

  // Localized labels
  const labels = {
    priceTitle: t.results.priceSection.title,
    growth: t.results.priceSection.growth,
    duration: t.results.priceSection.duration,
    days: t.results.priceSection.days,
    startPrice: t.results.priceSection.startPrice,
    endPrice: t.results.priceSection.endPrice,
    lineChart: t.results.priceSection.lineChart,
    candlestick: t.results.priceSection.candlestick,
    volume: t.results.volumeChart,
    closePrice: locale === 'en' ? 'Close' : '收盤價',
    date: locale === 'en' ? 'Date' : '日期',
    open: locale === 'en' ? 'Open' : '開',
    close: locale === 'en' ? 'Close' : '收',
    high: locale === 'en' ? 'High' : '高',
    low: locale === 'en' ? 'Low' : '低',
    up: locale === 'en' ? '↑ Up' : '↑ 上漲',
    down: locale === 'en' ? '↓ Down' : '↓ 下跌',
    noChange: locale === 'en' ? '→ No Change' : '→ 無變化',
  };

  return (
    <Card className="w-full hover-lift animate-scale-up">
      <CardHeader>
        <div className="flex justify-between items-center">
          <CardTitle className="text-2xl">{ticker} {labels.priceTitle}</CardTitle>
          <Tabs value={chartType} onValueChange={(v: string) => setChartType(v as "line" | "candlestick")}>
            <TabsList>
              <TabsTrigger value="line">{labels.lineChart}</TabsTrigger>
              <TabsTrigger value="candlestick">{labels.candlestick}</TabsTrigger>
            </TabsList>
          </Tabs>
        </div>

        {/* 統計資訊 */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
          <div className="bg-gradient-to-br from-green-50 to-emerald-50 dark:from-green-900/20 dark:to-emerald-900/20 p-4 rounded-lg border border-green-200 dark:border-green-800">
            <p className="text-sm text-muted-foreground">{labels.growth}</p>
            <p className={`text-2xl font-bold ${priceStats.growth_rate >= 0 ? 'text-green-600' : 'text-red-600'}`}>
              {priceStats.growth_rate >= 0 ? '+' : ''}{priceStats.growth_rate}%
            </p>
          </div>
          <div className="bg-gradient-to-br from-blue-50 to-cyan-50 dark:from-blue-900/20 dark:to-cyan-900/20 p-4 rounded-lg border border-blue-200 dark:border-blue-800">
            <p className="text-sm text-muted-foreground">{labels.duration}</p>
            <p className="text-2xl font-bold">{priceStats.duration_days} {labels.days}</p>
          </div>
          <div className="bg-gradient-to-br from-purple-50 to-pink-50 dark:from-purple-900/20 dark:to-pink-900/20 p-4 rounded-lg border border-purple-200 dark:border-purple-800">
            <p className="text-sm text-muted-foreground">{labels.startPrice}</p>
            <p className="text-lg font-semibold">${formatNumber(priceStats.start_price)}</p>
            <p className="text-xs text-muted-foreground">{priceStats.start_date}</p>
          </div>
          <div className="bg-gradient-to-br from-orange-50 to-amber-50 dark:from-orange-900/20 dark:to-amber-900/20 p-4 rounded-lg border border-orange-200 dark:border-orange-800">
            <p className="text-sm text-muted-foreground">{labels.endPrice}</p>
            <p className="text-lg font-semibold">${formatNumber(priceStats.end_price)}</p>
            <p className="text-xs text-muted-foreground">{priceStats.end_date}</p>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-6">
        {/* 價格圖表 */}
        <div>
          <h3 className="text-lg font-semibold mb-4">{labels.priceTitle}</h3>
          <ResponsiveContainer width="100%" height={400}>
            {chartType === "line" ? (
              <LineChart data={priceData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis 
                  dataKey="Date" 
                  tickFormatter={formatDate}
                  minTickGap={30}
                />
                <YAxis 
                  domain={['auto', 'auto']}
                  tickFormatter={(value) => `$${value.toFixed(0)}`}
                />
                <Tooltip 
                  formatter={(value: number | undefined) => [
                    value !== undefined ? `$${formatNumber(value)}` : '-', 
                    labels.closePrice
                  ]}
                  labelFormatter={(label) => `${labels.date}: ${label}`}
                />
                <Line 
                  type="monotone" 
                  dataKey={(data: PriceData) => getCloseValue(data)}
                  stroke="#93c5fd" 
                  strokeWidth={2}
                  name={labels.closePrice} 
                  dot={false}
                />
              </LineChart>
            ) : (
              // 平均K線圖（Heikin Ashi）
              <BarChart data={heikinAshiData} barCategoryGap="20%">
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis 
                  dataKey="Date" 
                  tickFormatter={formatDate}
                  minTickGap={30}
                />
                <YAxis 
                  domain={[minPrice * 0.98, maxPrice * 1.02]}
                  tickFormatter={(value) => `$${value.toFixed(0)}`}
                />
                <Tooltip 
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      const data = payload[0].payload as HeikinAshiData;
                      const isUp = data.HA_Close > data.HA_Open;
                      const isDown = data.HA_Close < data.HA_Open;
                      const isNeutral = data.HA_Close === data.HA_Open;
                      
                      // Trend color coding for the direction indicator
                      const trendColor = isUp ? 'text-green-600' : isDown ? 'text-red-600' : 'text-gray-600';
                      const direction = isUp ? labels.up : isDown ? labels.down : labels.noChange;
                      
                      return (
                        <div className="bg-background border border-border p-3 rounded-lg shadow-lg">
                          <p className="text-sm font-semibold mb-2">{labels.date}: {data.Date}</p>
                          <div className="space-y-1 text-sm">
                            <p className="text-purple-600">
                              {labels.open}: ${formatNumber(data.HA_Open)}
                            </p>
                            <p className="text-cyan-600">
                              {labels.close}: ${formatNumber(data.HA_Close)}
                            </p>
                            <p className="text-pink-600">{labels.high}: ${formatNumber(data.HA_High)}</p>
                            <p className="text-amber-600">{labels.low}: ${formatNumber(data.HA_Low)}</p>
                            <p className={`text-sm mt-2 ${trendColor}`}>
                              {direction} ${formatNumber(Math.abs(data.HA_Close - data.HA_Open))}
                            </p>
                          </div>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
                {/* 使用自定義 shape 來繪製平均蠟燭 */}
                <Bar 
                  dataKey="HA_High"
                  shape={(props: any) => <HeikinAshiCandlestickShape {...props} minPrice={minPrice} maxPrice={maxPrice} />}
                />
              </BarChart>
            )}
          </ResponsiveContainer>
        </div>

        {/* 交易量圖表 */}
        <div>
          <h3 className="text-lg font-semibold mb-4">{labels.volume}</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={priceData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis 
                dataKey="Date" 
                tickFormatter={formatDate}
                minTickGap={30}
              />
              <YAxis 
                tickFormatter={(value) => {
                  if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M`;
                  if (value >= 1000) return `${(value / 1000).toFixed(1)}K`;
                  return value.toString();
                }}
              />
              <Tooltip 
                formatter={(value: number | undefined) => [
                  value !== undefined ? value.toLocaleString() : '-', 
                  labels.volume
                ]}
                labelFormatter={(label) => `${labels.date}: ${label}`}
              />
              <Bar dataKey="Volume" fill="#93c5fd" name={labels.volume} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

// 自定義平均蠟燭圖形狀組件（Heikin Ashi）
interface HeikinAshiCandlestickShapeProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  payload?: HeikinAshiData;
  minPrice: number;
  maxPrice: number;
}

const HeikinAshiCandlestickShape: React.FC<HeikinAshiCandlestickShapeProps> = (props) => {
  const { x = 0, y = 0, width = 0, height = 0, payload, minPrice, maxPrice } = props;
  
  if (!payload) return null;
  
  const { HA_Open, HA_Close, HA_High, HA_Low } = payload;
  const isUp = HA_Close > HA_Open;
  const isDown = HA_Close < HA_Open;
  const isNeutral = HA_Close === HA_Open;
  
  // Color coding: green for up, red for down, gray for neutral
  let fillColor: string;
  let strokeColor: string;
  
  if (isUp) {
    fillColor = '#86efac'; // soft pastel green
    strokeColor = '#22c55e'; // darker green
  } else if (isDown) {
    fillColor = '#fca5a5'; // soft pastel pink/red
    strokeColor = '#ef4444'; // darker red
  } else {
    fillColor = '#d1d5db'; // soft gray
    strokeColor = '#6b7280'; // darker gray
  }
  
  // 計算實際的 Y 坐標位置
  const priceRange = maxPrice - minPrice;
  const pixelsPerPriceUnit = height / priceRange;

  // Calculate Y coordinates for HA values
  const highY = y + (maxPrice - HA_High) * pixelsPerPriceUnit;
  const lowY = y + (maxPrice - HA_Low) * pixelsPerPriceUnit;
  const openY = y + (maxPrice - HA_Open) * pixelsPerPriceUnit;
  const closeY = y + (maxPrice - HA_Close) * pixelsPerPriceUnit;
  
  // 蠟燭主體
  const bodyTop = Math.min(openY, closeY);
  const bodyBottom = Math.max(openY, closeY);
  const bodyHeight = Math.max(bodyBottom - bodyTop, 1); // 至少 1px
  
  // 蠟燭寬度和影線位置
  const candleWidth = width * 0.6; // 蠟燭佔 60% 寬度
  const candleX = x + (width - candleWidth) / 2;
  const wickX = x + width / 2; // 影線在中間
  
  return (
    <g>
      {/* 上影線（從最高價到蠟燭頂部） */}
      <line
        x1={wickX}
        y1={highY}
        x2={wickX}
        y2={bodyTop}
        stroke={strokeColor}
        strokeWidth={1.5}
      />
      {/* 下影線（從蠟燭底部到最低價） */}
      <line
        x1={wickX}
        y1={bodyBottom}
        x2={wickX}
        y2={lowY}
        stroke={strokeColor}
        strokeWidth={1.5}
      />
      {/* 蠟燭主體 */}
      <rect
        x={candleX}
        y={bodyTop}
        width={candleWidth}
        height={bodyHeight}
        fill={fillColor}
        stroke={strokeColor}
        strokeWidth={1}
      />
    </g>
  );
};
