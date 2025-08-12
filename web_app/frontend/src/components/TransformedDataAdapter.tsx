import React from 'react';

// New interface for the transformed JSON structure
interface TransformedAnalysisData {
  metadata: {
    company_ticker: string;
    company_name: string;
    analysis_date: string;
    final_recommendation: 'BUY' | 'SELL' | 'HOLD';
    confidence_level: 'HIGH' | 'MEDIUM' | 'LOW';
  };
  
  financial_data: {
    current_price: number;
    price_change: number;
    price_change_percent: number;
    market_cap: string;
    enterprise_value: string;
    shares_outstanding: string;
    trading_range: {
      high: number;
      low: number;
      open: number;
    };
    volume: number;
    valuation_ratios: {
      current_ps_ratio: number;
      fair_value_ps_ratio: number;
      forward_pe: number;
      forward_ps: number;
      forward_pcf: number;
      forward_pocf: number;
    };
    ownership: {
      insider_percent: number;
      institutional_percent: number;
    };
    analyst_data: {
      consensus_rating: string;
      price_target: number;
      forecast_price: number;
    };
  };

  technical_indicators: {
    sma_50: number;
    sma_200: number;
    ema_10: number;
    macd: number;
    macd_signal: number;
    rsi: number;
    atr: number;
    trend_directions: {
      sma_50: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
      sma_200: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
      ema_10: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
      macd: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
      rsi_condition: 'OVERSOLD' | 'OVERBOUGHT' | 'NEUTRAL';
    };
  };

  investment_strategy: {
    position_sizing: {
      total_allocation_percent: string;
      entry_strategy: string;
      tranche_1_percent: string;
      tranche_2_percent: string;
    };
    risk_management: {
      initial_stop_loss: number;
      stop_loss_percent: number;
      breakeven_strategy: string;
    };
    profit_targets: Array<{
      target_price: number;
      action: string;
      rationale: string;
    }>;
    monitoring_points: string[];
  };

  debate_summary: {
    bull_key_points: string[];
    bear_key_points: string[];
    neutral_perspective: string;
    final_decision_rationale: string;
  };

  text_content: {
    market_report: {
      title: string;
      content: string;
      key_takeaways: string[];
    };
    sentiment_report: {
      title: string;
      content: string;
      recent_developments: string[];
    };
    fundamentals_report: {
      title: string;
      content: string;
      financial_highlights: string[];
    };
    news_report: {
      title: string;
      content: string;
      key_developments: Array<{
        date: string;
        event: string;
        impact: string;
      }>;
    };
    investment_plan_full: {
      title: string;
      content: string;
    };
    debate_transcripts: {
      bull_analysis: string;
      bear_analysis: string;
      neutral_analysis: string;
      risk_discussion: string;
    };
  };

  widgets_config: {
    charts_needed: Array<{
      type: string;
      data_source: string;
      timeframe: string;
    }>;
    text_widgets: Array<{
      type: string;
      title: string;
      content_source: string;
    }>;
  };
}

// Legacy interface for backward compatibility
interface LegacyTradingAgentsResult {
  symbol: string;
  final_decision?: {
    decision: string;
    reasoning: string;
  };
  technical_analysis?: {
    current_price: number;
    rsi: number;
    macd: number;
    moving_averages: {
      ma_50: number;
      ma_200: number;
    };
  };
  fundamental_analysis?: {
    market_cap: string;
    ps_ratio: number;
    forward_pe: number;
    analyst_target: number;
  };
  bull_arguments?: string[];
  bear_arguments?: string[];
  neutral_perspective?: string;
  risk_assessment?: {
    overall_risk: number;
  };
  sentiment_analysis?: {
    overall_score: number;
  };
  ownership_structure?: {
    insider_ownership: number;
    institutional_ownership: number;
    retail_ownership: number;
  };
  investment_plan?: {
    stop_loss: number;
    profit_targets: number[];
  };
  earnings_date?: string;
}

interface TransformedDataAdapterProps {
  analysisData: TransformedAnalysisData | LegacyTradingAgentsResult;
}

const TransformedDataAdapter: React.FC<TransformedDataAdapterProps> = ({ analysisData }) => {
  // Check if this is the new transformed format or legacy format
  const isTransformedFormat = (data: any): data is TransformedAnalysisData => {
    return data.metadata && data.financial_data && data.technical_indicators;
  };

  // Convert legacy format to new format for backward compatibility
  const convertLegacyToTransformed = (legacyData: LegacyTradingAgentsResult): TransformedAnalysisData => {
    return {
      metadata: {
        company_ticker: legacyData.symbol || 'UNKNOWN',
        company_name: legacyData.symbol || 'Unknown Company',
        analysis_date: new Date().toISOString().split('T')[0],
        final_recommendation: (legacyData.final_decision?.decision?.toUpperCase() as 'BUY' | 'SELL' | 'HOLD') || 'HOLD',
        confidence_level: 'MEDIUM'
      },
      financial_data: {
        current_price: legacyData.technical_analysis?.current_price || 0,
        price_change: 0,
        price_change_percent: 0,
        market_cap: legacyData.fundamental_analysis?.market_cap || 'N/A',
        enterprise_value: 'N/A',
        shares_outstanding: 'N/A',
        trading_range: {
          high: 0,
          low: 0,
          open: 0
        },
        volume: 0,
        valuation_ratios: {
          current_ps_ratio: legacyData.fundamental_analysis?.ps_ratio || 0,
          fair_value_ps_ratio: 0,
          forward_pe: legacyData.fundamental_analysis?.forward_pe || 0,
          forward_ps: 0,
          forward_pcf: 0,
          forward_pocf: 0
        },
        ownership: {
          insider_percent: legacyData.ownership_structure?.insider_ownership || 0,
          institutional_percent: legacyData.ownership_structure?.institutional_ownership || 0
        },
        analyst_data: {
          consensus_rating: 'N/A',
          price_target: legacyData.fundamental_analysis?.analyst_target || 0,
          forecast_price: 0
        }
      },
      technical_indicators: {
        sma_50: legacyData.technical_analysis?.moving_averages?.ma_50 || 0,
        sma_200: legacyData.technical_analysis?.moving_averages?.ma_200 || 0,
        ema_10: 0,
        macd: legacyData.technical_analysis?.macd || 0,
        macd_signal: 0,
        rsi: legacyData.technical_analysis?.rsi || 50,
        atr: 0,
        trend_directions: {
          sma_50: 'NEUTRAL',
          sma_200: 'NEUTRAL',
          ema_10: 'NEUTRAL',
          macd: 'NEUTRAL',
          rsi_condition: 'NEUTRAL'
        }
      },
      investment_strategy: {
        position_sizing: {
          total_allocation_percent: '0%',
          entry_strategy: 'N/A',
          tranche_1_percent: '0%',
          tranche_2_percent: '0%'
        },
        risk_management: {
          initial_stop_loss: legacyData.investment_plan?.stop_loss || 0,
          stop_loss_percent: 0,
          breakeven_strategy: 'N/A'
        },
        profit_targets: legacyData.investment_plan?.profit_targets?.map(target => ({
          target_price: target,
          action: 'SELL',
          rationale: 'Profit target'
        })) || [],
        monitoring_points: []
      },
      debate_summary: {
        bull_key_points: legacyData.bull_arguments || [],
        bear_key_points: legacyData.bear_arguments || [],
        neutral_perspective: legacyData.neutral_perspective || 'No neutral perspective available',
        final_decision_rationale: legacyData.final_decision?.reasoning || 'No decision rationale available'
      },
      text_content: {
        market_report: {
          title: 'Technical Analysis Report',
          content: 'Legacy data - detailed technical analysis not available',
          key_takeaways: []
        },
        sentiment_report: {
          title: 'Company Sentiment Analysis',
          content: 'Legacy data - detailed sentiment analysis not available',
          recent_developments: []
        },
        fundamentals_report: {
          title: 'Fundamental Analysis',
          content: 'Legacy data - detailed fundamental analysis not available',
          financial_highlights: []
        },
        news_report: {
          title: 'Macroeconomic Context',
          content: 'Legacy data - news report not available',
          key_developments: []
        },
        investment_plan_full: {
          title: 'Complete Investment Strategy',
          content: 'Legacy data - detailed investment plan not available'
        },
        debate_transcripts: {
          bull_analysis: legacyData.bull_arguments?.join('\n') || '',
          bear_analysis: legacyData.bear_arguments?.join('\n') || '',
          neutral_analysis: legacyData.neutral_perspective || '',
          risk_discussion: ''
        }
      },
      widgets_config: {
        charts_needed: [
          { type: 'price_chart', data_source: 'financial_data.current_price', timeframe: '30_days' },
          { type: 'technical_indicators', data_source: 'technical_indicators', timeframe: '30_days' }
        ],
        text_widgets: [
          { type: 'expandable_report', title: 'Technical Analysis', content_source: 'text_content.market_report' }
        ]
      }
    };
  };

  // Get the transformed data (either already transformed or converted from legacy)
  const transformedData: TransformedAnalysisData = isTransformedFormat(analysisData) 
    ? analysisData 
    : convertLegacyToTransformed(analysisData);

  // Builds a default widgets_config for transformed analyses when missing
  const buildTransformedWidgetsConfig = (data: any) => {
    const confidenceMap: Record<string, number> = { LOW: 33, MEDIUM: 66, HIGH: 90 };
    return {
      layout: [
        ["kpi_recommendation", "kpi_confidence", "kpi_price_change", "kpi_marketcap", "kpi_ev"],
        ["ownership_donut", "range_bar", "volume_chip"],
        ["rsi_gauge", "macd_mini", "ma_trends", "atr_chip"],
        ["strategy_ladder", "position_sizing", "monitoring_points"],
        ["analyst_target_vs_price"],
        ["report_technical", "report_sentiment"],
        ["report_fundamentals", "report_investment_plan"],
        ["debate_summary"]
      ],
      widgets: [
        { id: "kpi_recommendation", type: "kpi_badge", title: "Recommendation", dataPath: "metadata.final_recommendation", colorMapping: { BUY: "green", HOLD: "yellow", SELL: "red" } },
        { id: "kpi_confidence", type: "radial_gauge", title: "Confidence", value: confidenceMap[(data?.metadata?.confidence_level || "MEDIUM").toUpperCase()] || 66 },
        { id: "kpi_price_change", type: "price_kpi", title: "Current Price", valuePath: "financial_data.current_price", deltaPath: "financial_data.price_change_percent", format: { value: "currency", delta: "percent" } },
        { id: "kpi_marketcap", type: "kpi_text", title: "Market Cap", dataPath: "financial_data.market_cap" },
        { id: "kpi_ev", type: "kpi_text", title: "Enterprise Value", dataPath: "financial_data.enterprise_value" },
        { id: "ownership_donut", type: "donut", title: "Ownership", series: [
          { label: "Insider %", valuePath: "financial_data.ownership.insider_percent" },
          { label: "Institutional %", valuePath: "financial_data.ownership.institutional_percent" }
        ], valueFormat: "percent" },
        { id: "range_bar", type: "range_bar", title: "Trading Range", lowPath: "financial_data.trading_range.low", highPath: "financial_data.trading_range.high", openPath: "financial_data.trading_range.open", currentPath: "financial_data.current_price" },
        { id: "volume_chip", type: "kpi_text", title: "Volume", dataPath: "financial_data.volume", format: { value: "number_compact" } },
        { id: "rsi_gauge", type: "linear_gauge", title: "RSI", dataPath: "technical_indicators.rsi", min: 0, max: 100, zones: [ { to: 30, color: "blue", label: "Oversold" }, { from: 70, to: 100, color: "red", label: "Overbought" } ] },
        { id: "macd_mini", type: "macd_snapshot", title: "MACD", macdPath: "technical_indicators.macd", signalPath: "technical_indicators.macd_signal", histogramCompute: "macd - macd_signal" },
        { id: "ma_trends", type: "badges", title: "MA & Trend", badges: [
          { label: "SMA 50", valuePath: "technical_indicators.sma_50", trendPath: "technical_indicators.trend_directions.sma_50" },
          { label: "SMA 200", valuePath: "technical_indicators.sma_200", trendPath: "technical_indicators.trend_directions.sma_200" },
          { label: "EMA 10", valuePath: "technical_indicators.ema_10", trendPath: "technical_indicators.trend_directions.ema_10" }
        ], trendColors: { BULLISH: "green", BEARISH: "red", NEUTRAL: "gray" } },
        { id: "atr_chip", type: "kpi_text", title: "ATR (Volatility)", dataPath: "technical_indicators.atr" },
        { id: "strategy_ladder", type: "price_ladder", title: "Entry, Stop, Targets", entryStrategyPath: "investment_strategy.position_sizing.entry_strategy", stopPricePath: "investment_strategy.risk_management.initial_stop_loss", stopPercentPath: "investment_strategy.risk_management.stop_loss_percent", targetsPath: "investment_strategy.profit_targets", targetMapping: { price: "target_price", label: "action" }, currentPricePath: "financial_data.current_price" },
        { id: "position_sizing", type: "chips", title: "Position Sizing", items: [
          { label: "Total Allocation", valuePath: "investment_strategy.position_sizing.total_allocation_percent" },
          { label: "Tranche 1", valuePath: "investment_strategy.position_sizing.tranche_1_percent" },
          { label: "Tranche 2", valuePath: "investment_strategy.position_sizing.tranche_2_percent" }
        ] },
        { id: "monitoring_points", type: "bullet_list", title: "Monitoring Points", itemsPath: "investment_strategy.monitoring_points" },
        { id: "analyst_target_vs_price", type: "bar_compare", title: "Analyst Target vs Current", series: [ { label: "Current", valuePath: "financial_data.current_price" }, { label: "Target", valuePath: "financial_data.analyst_data.price_target" } ], yFormat: "currency" },
        { id: "report_technical", type: "expandable_report", titlePath: "text_content.market_report.title", contentPath: "text_content.market_report.content", bulletsPath: "text_content.market_report.key_takeaways" },
        { id: "report_sentiment", type: "expandable_report", titlePath: "text_content.sentiment_report.title", contentPath: "text_content.sentiment_report.content", bulletsPath: "text_content.sentiment_report.recent_developments" },
        { id: "report_fundamentals", type: "expandable_report", titlePath: "text_content.fundamentals_report.title", contentPath: "text_content.fundamentals_report.content", bulletsPath: "text_content.fundamentals_report.financial_highlights" },
        { id: "report_investment_plan", type: "expandable_report", titlePath: "text_content.investment_plan_full.title", contentPath: "text_content.investment_plan_full.content" },
        { id: "debate_summary", type: "debate_viewer", bullPath: "debate_summary.bull_key_points", bearPath: "debate_summary.bear_key_points", neutralPath: "debate_summary.neutral_perspective", finalPath: "debate_summary.final_decision_rationale" }
      ]
    };
  };

  // Ensure we have a widgets_config; if missing, build a sensible default
  const transformedWithConfig = {
    ...transformedData,
    widgets_config: transformedData?.widgets_config || buildTransformedWidgetsConfig(transformedData)
  };

  // Minimalist dashboard that shows ALL main sections of transformed JSON
  const MinimalTransformedDashboard: React.FC<{ data: TransformedAnalysisData }> = ({ data }) => {
    const md = (data?.metadata as any) || {};
    const fd = (data?.financial_data as any) || {};
    const ti = (data?.technical_indicators as any) || {};
    const istrat = (data?.investment_strategy as any) || {};
    const ds = React.useMemo(() => ((data?.debate_summary as any) || {}), [data]);
    const txt = React.useMemo(() => ((data?.text_content as any) || {}), [data]);

    const trends = ti?.trend_directions || {};
    const fmt = (v: any, d = 0) => {
      const n = Number(v);
      if (v === null || v === undefined || Number.isNaN(n)) return '-';
      return Number.isFinite(n) ? n.toFixed(d) : String(v);
    };
    const fmtNumber = (v: any, d = 0) => {
      const n = Number(v);
      if (!Number.isFinite(n)) return '-';
      return n.toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d });
    };
    const fmtCurrency = (v: any, d = 2) => {
      const n = Number(v);
      if (!Number.isFinite(n)) return '-';
      return n.toLocaleString(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: d, minimumFractionDigits: d });
    };
    const fmtPercent = (v: any, d = 2) => {
      const n = Number(v);
      if (!Number.isFinite(n)) return '-';
      return `${n.toFixed(d)}%`;
    };
    const toneFromNumber = (v: any): 'pos' | 'neg' | 'neutral' => {
      const n = Number(v);
      if (!Number.isFinite(n)) return 'neutral';
      if (n > 0) return 'pos';
      if (n < 0) return 'neg';
      return 'neutral';
    };
    const Stat: React.FC<{ label: string; value: React.ReactNode; sub?: React.ReactNode; tone?: 'pos' | 'neg' | 'neutral' }>
      = ({ label, value, sub, tone = 'neutral' }) => {
      const toneCls = tone === 'pos' ? 'text-green-600' : tone === 'neg' ? 'text-red-600' : 'text-gray-900';
      const ringCls = tone === 'pos' ? 'ring-green-200' : tone === 'neg' ? 'ring-red-200' : 'ring-gray-200';
      return (
        <div className={`rounded-lg border border-gray-200 ring-1 ${ringCls} p-4 bg-white shadow-sm`}> 
          <p className="text-xs text-gray-500">{label}</p>
          <p className={`text-xl font-semibold ${toneCls}`}>{value}</p>
          {sub && <p className="text-xs text-gray-500 mt-0.5">{sub}</p>}
        </div>
      );
    };

    const chip = (label: string, val?: string) => (
      <span className="px-2 py-1 rounded bg-gray-100 text-gray-700 text-xs font-medium">{label}: {val ?? '-'}</span>
    );

    // Tabs state and memoized content for text-heavy sections
    const debateTabs = React.useMemo(() => ([
      { key: 'bull', label: 'Bull', content: Array.isArray(ds?.bull_key_points) ? ds.bull_key_points : [] as any[] },
      { key: 'bear', label: 'Bear', content: Array.isArray(ds?.bear_key_points) ? ds.bear_key_points : [] as any[] },
      { key: 'neutral', label: 'Neutral', content: ds?.neutral_perspective ? [ds.neutral_perspective] : [] as any[] },
      { key: 'final', label: 'Final', content: ds?.final_decision_rationale ? [ds.final_decision_rationale] : [] as any[] },
    ]), [ds]);
    const firstDebateWithContent = React.useMemo(
      () => debateTabs.find(t => (t.content?.length ?? 0) > 0)?.key || 'bull',
      [debateTabs]
    );
    const [activeDebateTab, setActiveDebateTab] = React.useState<string>(firstDebateWithContent);
    React.useEffect(() => { setActiveDebateTab(firstDebateWithContent); }, [firstDebateWithContent]);

    const reportTabsAll = React.useMemo(() => ([
      { key: 'market', title: txt?.market_report?.title || 'Market Report', bullets: txt?.market_report?.key_takeaways, content: txt?.market_report?.content },
      { key: 'sentiment', title: txt?.sentiment_report?.title || 'Sentiment Report', bullets: txt?.sentiment_report?.recent_developments, content: txt?.sentiment_report?.content },
      { key: 'fundamentals', title: txt?.fundamentals_report?.title || 'Fundamentals Report', bullets: txt?.fundamentals_report?.financial_highlights, content: txt?.fundamentals_report?.content },
    ]), [txt]);
    const availableReports = React.useMemo(
      () => reportTabsAll.filter(t => t.title || (Array.isArray(t.bullets) && t.bullets.length) || t.content),
      [reportTabsAll]
    );
    const [activeReportTab, setActiveReportTab] = React.useState<string>(availableReports[0]?.key || 'market');
    React.useEffect(() => { setActiveReportTab(availableReports[0]?.key || 'market'); }, [availableReports]);

    return (
      <div className="p-6">
        <div className="mx-auto max-w-6xl space-y-4">
          {/* Metadata - Full width */}
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-lg font-semibold mb-3">Company Information</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <Stat label="Company" value={`${md?.company_name ?? '-'} (${md?.company_ticker ?? '-'})`} />
              <Stat label="Analysis Date" value={md?.analysis_date ?? '-'} />
              <Stat label="Final Recommendation" value={md?.final_recommendation ?? '-'} />
              <Stat label="Confidence" value={md?.confidence_level ?? '-'} />
            </div>
          </div>

          {/* Two column layout for remaining sections */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Debate Summary with sub-tabs */}
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-lg font-semibold mb-3">Debate Summary</h2>
              <div>
                <div className="flex gap-2 border-b border-gray-200 mb-3">
                  {debateTabs.map(t => (
                    <button
                      key={t.key}
                      onClick={() => setActiveDebateTab(t.key)}
                      className={`px-3 py-1.5 text-sm rounded-t ${activeDebateTab === t.key ? 'bg-gray-100 text-gray-900' : 'text-gray-500 hover:text-gray-700'}`}
                    >{t.label}</button>
                  ))}
                </div>
                <div className="text-sm text-gray-800 space-y-2 max-h-64 overflow-auto pr-1">
                  {debateTabs.find(t => t.key === activeDebateTab)?.content?.length ? (
                    <ul className="list-disc list-inside">
                      {(debateTabs.find(t => t.key === activeDebateTab)?.content as any[]).map((c, i) => <li key={i}>{c}</li>)}
                    </ul>
                  ) : (
                    <p className="text-gray-500">No content.</p>
                  )}
                </div>
              </div>
            </div>

            {/* Text Content with sub-tabs */}
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-lg font-semibold mb-3">Reports</h2>
              {!availableReports.length ? (
                <p className="text-sm text-gray-500">No reports available.</p>
              ) : (
                <div>
                  <div className="flex gap-2 border-b border-gray-200 mb-3">
                    {availableReports.map(t => (
                      <button
                        key={t.key}
                        onClick={() => setActiveReportTab(t.key)}
                        className={`px-3 py-1.5 text-sm rounded-t ${activeReportTab === t.key ? 'bg-gray-100 text-gray-900' : 'text-gray-500 hover:text-gray-700'}`}
                      >{t.title}</button>
                    ))}
                  </div>
                  {(() => {
                    const activeTab = availableReports.find(t => t.key === activeReportTab);
                    if (!activeTab) return null;
                    return (
                      <div className="space-y-3 max-h-72 overflow-auto pr-1">
                        {Array.isArray(activeTab.bullets) && activeTab.bullets.length > 0 && (
                          <ul className="list-disc list-inside text-sm text-gray-700">
                            {activeTab.bullets.map((k: string, i: number) => <li key={i}>{k}</li>)}
                          </ul>
                        )}
                        {activeTab.content && (
                          <p className="text-sm text-gray-700 whitespace-pre-wrap">{activeTab.content}</p>
                        )}
                      </div>
                    );
                  })()}
                </div>
              )}
            </div>

            {/* Financial Data */}
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-lg font-semibold mb-3">Financial Data</h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Stat label="Current Price" value={fmtCurrency(fd?.current_price)} />
                <Stat label="Target Price" value={fmtCurrency(fd?.analyst_data?.price_target ?? fd?.target_price)} />
                <Stat label="Price Change" value={fmtPercent(fd?.price_change)} tone={toneFromNumber(fd?.price_change)} />
                <Stat label="Price Change %" value={fmtPercent(fd?.price_change_percent)} tone={toneFromNumber(fd?.price_change_percent)} />
                <Stat label="Market Cap" value={fd?.market_cap ?? '-'} />
                <Stat label="Enterprise Value" value={fd?.enterprise_value ?? '-'} />
                <Stat label="Shares Outstanding" value={fd?.shares_outstanding ?? '-'} />
                <Stat label="Volume" value={fmtNumber(fd?.volume, 0)} />
                <Stat label="P/E Ratio" value={fmtNumber(fd?.pe_ratio ?? fd?.valuation_ratios?.forward_pe, 2)} />
                <Stat label="P/S Ratio" value={fmtNumber(fd?.valuation_ratios?.current_ps_ratio, 2)} />
              </div>
            </div>

            {/* Technical Indicators */}
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-lg font-semibold mb-3">Technical Indicators</h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Stat label="RSI" value={fmtNumber(ti?.rsi, 2)} tone={toneFromNumber((Number(ti?.rsi) - 50))} />
                <Stat label="MACD" value={fmtNumber(ti?.macd, 3)} />
                <Stat label="Signal" value={fmtNumber(ti?.macd_signal, 3)} />
                <Stat label="SMA 50" value={fmtCurrency((ti?.sma_50 ?? ti?.moving_avg_50), 2)} />
                <Stat label="SMA 200" value={fmtCurrency((ti?.sma_200 ?? ti?.moving_avg_200), 2)} />
                <Stat label="MA 20" value={fmtCurrency(ti?.moving_avg_20, 2)} />
                <Stat label="EMA 10" value={fmtCurrency(ti?.ema_10, 2)} />
                <Stat label="ATR" value={fmtNumber(ti?.atr, 3)} />
                <Stat label="Bollinger Upper" value={fmtCurrency(ti?.bollinger_upper, 2)} />
                <Stat label="Bollinger Lower" value={fmtCurrency(ti?.bollinger_lower, 2)} />
                <Stat label="Support" value={fmtCurrency(ti?.support_level, 2)} />
                <Stat label="Resistance" value={fmtCurrency(ti?.resistance_level, 2)} />
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                {chip('Trend SMA 50', trends?.sma_50)}
                {chip('Trend SMA 200', trends?.sma_200)}
                {trends?.ema_10 !== undefined && chip('Trend EMA 10', trends?.ema_10)}
                {trends?.price_action !== undefined && chip('Price', trends?.price_action)}
              </div>
            </div>

            {/* Investment Strategy */}
            <div className="bg-white rounded-lg shadow p-6 lg:col-span-2">
              <h2 className="text-lg font-semibold mb-3">Investment Strategy</h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                <Stat label="Risk Level (SL%)" value={fmtPercent(istrat?.risk_management?.stop_loss_percent ?? md?.risk_level)} />
                <Stat label="Initial Stop Loss" value={fmtCurrency(istrat?.risk_management?.initial_stop_loss)} />
                <Stat label="Profit Targets" value={istrat.profit_targets.map((t: any, idx: number) => (
                          <li key={idx} className="flex gap-4">
                            <span className="font-semibold">{fmtCurrency(t?.target_price)}</span>
                            {t?.action && <span className="text-xs text-gray-500">{t.action}</span>}
                            {t?.rationale && <span className="text-xs text-gray-500">{t.rationale}</span>}
                            <hr />
                          </li>
                    ))} />
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  };

  // Render minimalist dashboard with all keys from the transformed JSON
  return <MinimalTransformedDashboard data={transformedWithConfig} />;
};

export default TransformedDataAdapter;
export type { TransformedAnalysisData, LegacyTradingAgentsResult };
