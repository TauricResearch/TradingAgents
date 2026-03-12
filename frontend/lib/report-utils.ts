/**
 * Shared utilities for report deduplication, language detection, and date parsing.
 * Single source of truth — imported by history/page.tsx, analysis/page.tsx, results/page.tsx, etc.
 */

/**
 * Normalize report language. All null/undefined values become "zh-TW"
 * to match backend behavior (COALESCE(language, 'zh-TW')).
 */
export function normalizeLanguage(
  language?: string | null
): "en" | "zh-TW" {
  if (language === "en") return "en";
  return "zh-TW";
}

/**
 * Detect report language from content (for backward compatibility with old reports
 * that don't have a language field stored).
 * Checks trader_investment_plan for Chinese/English keywords.
 */
export function detectReportLanguage(reports: any): "en" | "zh-TW" {
  const traderPlan = reports?.trader_investment_plan;
  if (!traderPlan || typeof traderPlan !== "string") {
    // If no trader plan, check other reports for Chinese characters
    const allText = JSON.stringify(reports || {});
    const chineseRegex = /[\u4e00-\u9fa5]/;
    return chineseRegex.test(allText) ? "zh-TW" : "en";
  }

  // Check for Chinese decision keywords
  const chineseKeywords = ["買入", "賣出", "持有", "最終交易提案"];
  for (const keyword of chineseKeywords) {
    if (traderPlan.includes(keyword)) {
      return "zh-TW";
    }
  }

  // Check for English decision keywords
  const englishKeywords = ["buy", "sell", "hold", "final trading proposal"];
  const lowerPlan = traderPlan.toLowerCase();
  for (const keyword of englishKeywords) {
    if (lowerPlan.includes(keyword)) {
      return "en";
    }
  }

  // Fallback: check for Chinese characters in the content
  const chineseRegex = /[\u4e00-\u9fa5]/;
  return chineseRegex.test(traderPlan) ? "zh-TW" : "en";
}

/**
 * Generate a unique signature for report deduplication.
 * Uses stable key fields: ticker + date + market_type + language.
 * Language is normalized to "zh-TW" when null/undefined to match backend behavior.
 */
export function getReportSignature(report: {
  ticker: string;
  analysis_date: string;
  market_type?: string;
  language?: string | null;
}): string {
  const lang = normalizeLanguage(report.language);
  return `${report.ticker}_${report.analysis_date}_${report.market_type || "us"}_${lang}`;
}

/**
 * Parse a date string from the backend as UTC.
 * Backend stores created_at in UTC but may not always include timezone info.
 * This ensures the date is correctly interpreted as UTC so the browser
 * converts it to the user's local timezone for display.
 */
export function parseUTCDate(dateStr: string): Date {
  // If the string already has timezone info (Z, +, or - offset), parse directly
  if (dateStr.endsWith("Z") || /[+-]\d{2}:\d{2}$/.test(dateStr)) {
    return new Date(dateStr);
  }
  // Otherwise, append 'Z' to treat as UTC
  return new Date(dateStr + "Z");
}
