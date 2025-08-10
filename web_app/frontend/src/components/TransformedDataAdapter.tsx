import React from 'react';
import AnalysisWidgets from '../pages/AnalysisWidgets.tsx';

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
          { type: 'technical_indicators', data_source: 'technical_indicators' }
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

  // Convert transformed data to the format expected by AnalysisWidgets
  const convertToWidgetFormat = (data: TransformedAnalysisData) => {
    return {
      symbol: data.metadata.company_ticker,
      final_decision: {
        decision: data.metadata.final_recommendation,
        reasoning: data.debate_summary.final_decision_rationale
      },
      technical_analysis: {
        current_price: data.financial_data.current_price,
        rsi: data.technical_indicators.rsi,
        macd: data.technical_indicators.macd,
        moving_averages: {
          ma_50: data.technical_indicators.sma_50,
          ma_200: data.technical_indicators.sma_200
        }
      },
      fundamental_analysis: {
        market_cap: data.financial_data.market_cap,
        ps_ratio: data.financial_data.valuation_ratios.current_ps_ratio,
        forward_pe: data.financial_data.valuation_ratios.forward_pe,
        analyst_target: data.financial_data.analyst_data.price_target
      },
      bull_arguments: data.debate_summary.bull_key_points,
      bear_arguments: data.debate_summary.bear_key_points,
      neutral_perspective: data.debate_summary.neutral_perspective,
      risk_assessment: {
        overall_risk: data.investment_strategy.risk_management.stop_loss_percent
      },
      sentiment_analysis: {
        overall_score: data.technical_indicators.rsi / 100 // Approximate sentiment from RSI
      },
      ownership_structure: {
        insider_ownership: data.financial_data.ownership.insider_percent,
        institutional_ownership: data.financial_data.ownership.institutional_percent,
        retail_ownership: Math.max(0, 100 - data.financial_data.ownership.insider_percent - data.financial_data.ownership.institutional_percent)
      },
      investment_plan: {
        stop_loss: data.investment_strategy.risk_management.initial_stop_loss,
        profit_targets: data.investment_strategy.profit_targets.map(target => target.target_price)
      },
      earnings_date: data.metadata.analysis_date,
      
      // Extended data from new format
      extended_data: {
        metadata: data.metadata,
        financial_data: data.financial_data,
        technical_indicators: data.technical_indicators,
        investment_strategy: data.investment_strategy,
        text_content: data.text_content,
        widgets_config: data.widgets_config
      }
    };
  };

  const widgetData = convertToWidgetFormat(transformedData);

  return <AnalysisWidgets tradingResult={widgetData} />;
};

export default TransformedDataAdapter;
export type { TransformedAnalysisData, LegacyTradingAgentsResult };
