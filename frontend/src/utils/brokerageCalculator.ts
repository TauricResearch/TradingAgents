/**
 * Zerodha Brokerage Calculator
 * Based on https://github.com/hemangjoshi37a/Zerodha-Brokerage-Calculator
 *
 * Implements accurate brokerage calculation for Indian equity markets
 */

export interface BrokerageBreakdown {
  brokerage: number;
  stt: number;
  exchangeCharges: number;
  sebiCharges: number;
  gst: number;
  stampDuty: number;
  totalCharges: number;
  netProfit: number;
  turnover: number;
}

export interface TradeDetails {
  buyPrice: number;
  sellPrice: number;
  quantity: number;
  tradeType: 'delivery' | 'intraday';
}

// Zerodha charge rates
const RATES = {
  // Equity Delivery
  delivery: {
    brokerage: 0, // Zero brokerage for delivery
    sttBuy: 0.001, // 0.1% on buy
    sttSell: 0.001, // 0.1% on sell
    exchangeCharges: 0.0000345, // 0.00345%
    sebiCharges: 0.000001, // 0.0001%
    gst: 0.18, // 18%
    stampDuty: 0.00015, // 0.015% on buy side
  },
  // Equity Intraday
  intraday: {
    brokerageRate: 0.0003, // 0.03%
    brokerageCap: 20, // Max Rs. 20 per side
    sttSell: 0.00025, // 0.025% on sell side only
    exchangeCharges: 0.0000345, // 0.00345%
    sebiCharges: 0.000001, // 0.0001%
    gst: 0.18, // 18%
    stampDuty: 0.00003, // 0.003% on buy side
  },
};

/**
 * Calculate brokerage for a single trade
 */
export function calculateBrokerage(trade: TradeDetails): BrokerageBreakdown {
  const { buyPrice, sellPrice, quantity, tradeType } = trade;
  const buyValue = buyPrice * quantity;
  const sellValue = sellPrice * quantity;
  const turnover = buyValue + sellValue;

  if (tradeType === 'delivery') {
    return calculateDeliveryBrokerage(buyValue, sellValue, turnover);
  } else {
    return calculateIntradayBrokerage(buyValue, sellValue, turnover);
  }
}

function calculateDeliveryBrokerage(
  buyValue: number,
  sellValue: number,
  turnover: number
): BrokerageBreakdown {
  const rates = RATES.delivery;

  // Brokerage is zero for delivery
  const brokerage = 0;

  // STT on both buy and sell
  const stt = (buyValue * rates.sttBuy) + (sellValue * rates.sttSell);

  // Exchange transaction charges on turnover
  const exchangeCharges = turnover * rates.exchangeCharges;

  // SEBI charges on turnover
  const sebiCharges = turnover * rates.sebiCharges;

  // GST on brokerage + exchange charges
  const gst = (brokerage + exchangeCharges) * rates.gst;

  // Stamp duty on buy side only
  const stampDuty = buyValue * rates.stampDuty;

  const totalCharges = brokerage + stt + exchangeCharges + sebiCharges + gst + stampDuty;
  const netProfit = sellValue - buyValue - totalCharges;

  return {
    brokerage,
    stt,
    exchangeCharges,
    sebiCharges,
    gst,
    stampDuty,
    totalCharges,
    netProfit,
    turnover,
  };
}

function calculateIntradayBrokerage(
  buyValue: number,
  sellValue: number,
  turnover: number
): BrokerageBreakdown {
  const rates = RATES.intraday;

  // Brokerage: min(0.03% * value, Rs. 20) per side
  const buyBrokerage = Math.min(buyValue * rates.brokerageRate, rates.brokerageCap);
  const sellBrokerage = Math.min(sellValue * rates.brokerageRate, rates.brokerageCap);
  const brokerage = buyBrokerage + sellBrokerage;

  // STT on sell side only for intraday
  const stt = sellValue * rates.sttSell;

  // Exchange transaction charges on turnover
  const exchangeCharges = turnover * rates.exchangeCharges;

  // SEBI charges on turnover
  const sebiCharges = turnover * rates.sebiCharges;

  // GST on brokerage + exchange charges
  const gst = (brokerage + exchangeCharges) * rates.gst;

  // Stamp duty on buy side only
  const stampDuty = buyValue * rates.stampDuty;

  const totalCharges = brokerage + stt + exchangeCharges + sebiCharges + gst + stampDuty;
  const netProfit = sellValue - buyValue - totalCharges;

  return {
    brokerage,
    stt,
    exchangeCharges,
    sebiCharges,
    gst,
    stampDuty,
    totalCharges,
    netProfit,
    turnover,
  };
}

/**
 * Calculate total brokerage for multiple trades
 */
export function calculateTotalBrokerage(
  trades: TradeDetails[]
): {
  breakdown: BrokerageBreakdown;
  tradeCount: number;
} {
  const totals: BrokerageBreakdown = {
    brokerage: 0,
    stt: 0,
    exchangeCharges: 0,
    sebiCharges: 0,
    gst: 0,
    stampDuty: 0,
    totalCharges: 0,
    netProfit: 0,
    turnover: 0,
  };

  for (const trade of trades) {
    const result = calculateBrokerage(trade);
    totals.brokerage += result.brokerage;
    totals.stt += result.stt;
    totals.exchangeCharges += result.exchangeCharges;
    totals.sebiCharges += result.sebiCharges;
    totals.gst += result.gst;
    totals.stampDuty += result.stampDuty;
    totals.totalCharges += result.totalCharges;
    totals.netProfit += result.netProfit;
    totals.turnover += result.turnover;
  }

  return {
    breakdown: totals,
    tradeCount: trades.length,
  };
}

/**
 * Quick estimate for a round-trip delivery trade
 * (buy and later sell the same quantity)
 */
export function estimateDeliveryCharges(
  buyPrice: number,
  sellPrice: number,
  quantity: number
): BrokerageBreakdown {
  return calculateBrokerage({
    buyPrice,
    sellPrice,
    quantity,
    tradeType: 'delivery',
  });
}

/**
 * Quick estimate for intraday trade
 */
export function estimateIntradayCharges(
  buyPrice: number,
  sellPrice: number,
  quantity: number
): BrokerageBreakdown {
  return calculateBrokerage({
    buyPrice,
    sellPrice,
    quantity,
    tradeType: 'intraday',
  });
}

/**
 * Format currency in Indian format
 */
export function formatINR(value: number, decimals: number = 2): string {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}
