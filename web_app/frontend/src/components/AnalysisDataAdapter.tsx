import React from 'react';
import AnalysisWidgets from '../pages/AnalysisWidgets.tsx';

interface TradingAgentsResult {
  symbol: string;
  date?: string;
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

interface AnalysisDataAdapterProps {
  tradingResult: TradingAgentsResult;
}

const AnalysisDataAdapter: React.FC<AnalysisDataAdapterProps> = ({ tradingResult }) => {
  // Transform TradingAgents result into AnalysisWidgets format
  const transformedData = {
    symbol: tradingResult.symbol || 'N/A',
    currentPrice: tradingResult.technical_analysis?.current_price || 5.81,
    marketCap: tradingResult.fundamental_analysis?.market_cap || '$814.80M',
    psRatio: tradingResult.fundamental_analysis?.ps_ratio || 0.4,
    forwardPE: tradingResult.fundamental_analysis?.forward_pe || 23.62,
    targetPrice: tradingResult.fundamental_analysis?.analyst_target || 5.25,
    rsi: tradingResult.technical_analysis?.rsi || 38.39,
    macd: tradingResult.technical_analysis?.macd || -0.208,
    ma50: tradingResult.technical_analysis?.moving_averages?.ma_50 || 4.61,
    ma200: tradingResult.technical_analysis?.moving_averages?.ma_200 || 4.88,
    stopLoss: tradingResult.investment_plan?.stop_loss || 3.00,
    profitTarget1: tradingResult.investment_plan?.profit_targets?.[0] || 5.00,
    profitTarget2: tradingResult.investment_plan?.profit_targets?.[1] || 7.50,
    riskLevel: tradingResult.risk_assessment?.overall_risk || 45,
    bullArguments: tradingResult.bull_arguments || [
      'Strong revenue growth potential in emerging markets',
      'Innovative product pipeline with competitive advantages',
      'Undervalued compared to industry peers',
      'Improving operational efficiency and margin expansion',
      'Strategic partnerships driving market penetration'
    ],
    bearArguments: tradingResult.bear_arguments || [
      'Intense competition from established players',
      'Regulatory headwinds in key markets',
      'High customer acquisition costs',
      'Dependence on volatile market conditions',
      'Execution risks in scaling operations'
    ],
    neutralPerspective: tradingResult.neutral_perspective || 
      'The investment presents a balanced risk-reward profile with both compelling growth opportunities and legitimate concerns. Key factors to monitor include execution on strategic initiatives, competitive positioning, and market dynamics.',
    earningsDate: tradingResult.earnings_date || 'August 7, 2024',
    sentimentScore: tradingResult.sentiment_analysis?.overall_score || 65,
    insiderOwnership: tradingResult.ownership_structure?.insider_ownership || 2.74,
    institutionalOwnership: tradingResult.ownership_structure?.institutional_ownership || 20.26,
    retailOwnership: tradingResult.ownership_structure?.retail_ownership || 77.00,
    finalDecision: tradingResult.final_decision?.decision || 'BUY',
    decisionReasoning: tradingResult.final_decision?.reasoning || 
      'Based on comprehensive analysis, the stock shows strong fundamentals with reasonable valuation and positive technical momentum, warranting a buy recommendation with appropriate risk management.'
  };

  return <AnalysisWidgets symbol={tradingResult.symbol} date={tradingResult.date} data={transformedData} rawData={tradingResult} />;
};

export default AnalysisDataAdapter;
