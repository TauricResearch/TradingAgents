/**
 * IndexedDB database for storing analysis reports
 * Uses Dexie.js for a cleaner API
 */

import Dexie, { type Table } from "dexie";
import type { AnalysisResponse } from "./types";

// Saved report interface
export interface SavedReport {
  id?: number; // Auto-generated primary key
  ticker: string; // Stock ticker symbol
  market_type: "us" | "twse" | "tpex"; // Market type
  analysis_date: string; // Analysis date (YYYY-MM-DD)
  saved_at: Date; // Save timestamp
  task_id?: string; // Original task ID
  result: AnalysisResponse; // Full analysis result
}

// Database class extending Dexie
class ReportsDatabase extends Dexie {
  reports!: Table<SavedReport>;

  constructor() {
    super("TradingAgentsReports");
    this.version(1).stores({
      // Define indexes: ++id = auto-increment, others are indexed fields
      reports: "++id, ticker, market_type, analysis_date, saved_at",
    });
  }
}

// Database singleton instance
const db = new ReportsDatabase();

/**
 * Save a report to the database
 */
export async function saveReport(
  ticker: string,
  market_type: "us" | "twse" | "tpex",
  analysis_date: string,
  result: AnalysisResponse,
  task_id?: string
): Promise<number> {
  const report: SavedReport = {
    ticker,
    market_type,
    analysis_date,
    saved_at: new Date(),
    task_id,
    result,
  };

  return await db.reports.add(report);
}

/**
 * Get all reports by market type
 */
export async function getReportsByMarketType(
  market_type: "us" | "twse" | "tpex"
): Promise<SavedReport[]> {
  return await db.reports
    .where("market_type")
    .equals(market_type)
    .reverse()
    .sortBy("saved_at");
}

/**
 * Get all saved reports, sorted by saved_at descending
 */
export async function getAllReports(): Promise<SavedReport[]> {
  return await db.reports.orderBy("saved_at").reverse().toArray();
}

/**
 * Get a single report by ID
 */
export async function getReportById(
  id: number
): Promise<SavedReport | undefined> {
  return await db.reports.get(id);
}

/**
 * Delete a report by ID
 */
export async function deleteReport(id: number): Promise<void> {
  await db.reports.delete(id);
}

/**
 * Delete multiple reports by IDs
 */
export async function deleteReports(ids: number[]): Promise<void> {
  await db.reports.bulkDelete(ids);
}

/**
 * Get report count by market type
 */
export async function getReportCountByMarketType(): Promise<{
  us: number;
  twse: number;
  tpex: number;
}> {
  const [us, twse, tpex] = await Promise.all([
    db.reports.where("market_type").equals("us").count(),
    db.reports.where("market_type").equals("twse").count(),
    db.reports.where("market_type").equals("tpex").count(),
  ]);

  return { us, twse, tpex };
}

/**
 * Check if a report with the same ticker and analysis_date already exists
 */
export async function checkDuplicateReport(
  ticker: string,
  analysis_date: string
): Promise<SavedReport | undefined> {
  return await db.reports
    .where("ticker")
    .equals(ticker)
    .and((report) => report.analysis_date === analysis_date)
    .first();
}

/**
 * Clear all reports from the database (for logout)
 */
export async function clearAllReports(): Promise<void> {
  await db.reports.clear();
}

// Export the db instance for advanced usage
export { db };
