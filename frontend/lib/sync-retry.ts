/**
 * Cloud sync retry service
 * Handles retrying failed cloud syncs for reports stored in local IndexedDB
 */

import { getAllReports, saveReport } from "./reports-db";
import { saveCloudReport, isCloudSyncEnabled } from "./user-api";
import type { SavedReport } from "./reports-db";

// Retry configuration
const RETRY_INTERVAL = 30000; // 30 seconds between retry attempts
const MAX_RETRIES = 5; // Give up after 5 failed attempts
const RETRY_BACKOFF = 1.5; // Exponential backoff multiplier

interface RetryRecord {
  ticker: string;
  analysis_date: string;
  market_type: "us" | "twse" | "tpex";
  language?: "en" | "zh-TW";
  attempts: number;
  last_attempt: number;
}

// Track retry attempts in memory
const retryMap = new Map<string, RetryRecord>();

/**
 * Generate a unique key for a report for retry tracking
 */
function getReportKey(
  ticker: string,
  analysis_date: string,
  market_type: string,
  language?: string
): string {
  return `${ticker}|${analysis_date}|${market_type}|${language || "zh-TW"}`;
}

/**
 * Retry a single report's cloud sync
 */
async function retrySingleReport(report: SavedReport): Promise<boolean> {
  if (!isCloudSyncEnabled()) {
    console.log("Cloud sync not enabled, skipping retry");
    return false;
  }

  const key = getReportKey(
    report.ticker,
    report.analysis_date,
    report.market_type,
    report.language
  );

  // Check retry attempts
  const retryRecord = retryMap.get(key);
  if (retryRecord && retryRecord.attempts >= MAX_RETRIES) {
    console.warn(
      `⚠️  [${report.ticker}] Max retries exceeded, giving up on cloud sync`
    );
    retryMap.delete(key);
    return false;
  }

  try {
    console.log(
      `🔄 [${report.ticker}] Retrying cloud sync (attempt ${(retryRecord?.attempts || 0) + 1}/${MAX_RETRIES})`
    );

    const cloudId = await saveCloudReport({
      ticker: report.ticker,
      market_type: report.market_type,
      analysis_date: report.analysis_date,
      result: report.result,
      language: report.language,
    });

    if (cloudId) {
      console.log(`✅ [${report.ticker}] Cloud sync successful, clearing retry record`);
      retryMap.delete(key);
      return true;
    } else {
      // Still failed, increment retry count
      if (!retryRecord) {
        retryMap.set(key, {
          ticker: report.ticker,
          analysis_date: report.analysis_date,
          market_type: report.market_type,
          language: report.language,
          attempts: 1,
          last_attempt: Date.now(),
        });
      } else {
        retryRecord.attempts++;
        retryRecord.last_attempt = Date.now();
      }
      return false;
    }
  } catch (error) {
    console.error(`❌ [${report.ticker}] Cloud sync retry failed:`, error);

    // Increment retry count
    if (!retryRecord) {
      retryMap.set(key, {
        ticker: report.ticker,
        analysis_date: report.analysis_date,
        market_type: report.market_type,
        language: report.language,
        attempts: 1,
        last_attempt: Date.now(),
      });
    } else {
      retryRecord.attempts++;
      retryRecord.last_attempt = Date.now();
    }
    return false;
  }
}

/**
 * Attempt to sync all reports with pending_sync flag
 */
export async function retryPendingSyncs(): Promise<{
  successful: number;
  failed: number;
}> {
  if (!isCloudSyncEnabled()) {
    console.log("Cloud sync not enabled, skipping retry");
    return { successful: 0, failed: 0 };
  }

  try {
    const allReports = await getAllReports();
    let successful = 0;
    let failed = 0;

    // Try to sync reports (we'll assume any local report without a cloud_id needs syncing)
    for (const report of allReports) {
      if (!report.cloud_id && report.pending_sync) {
        const synced = await retrySingleReport(report);
        if (synced) {
          successful++;
          // Update the report to clear pending_sync flag
          // Note: This would require an updateReport function in reports-db.ts
        } else {
          failed++;
        }
      }
    }

    if (successful > 0 || failed > 0) {
      console.log(
        `📊 Cloud sync retry summary: ${successful} successful, ${failed} failed`
      );
    }

    return { successful, failed };
  } catch (error) {
    console.error("Error retrying pending syncs:", error);
    return { successful: 0, failed: 0 };
  }
}

/**
 * Get the number of pending syncs
 */
export function getPendingSyncCount(): number {
  return retryMap.size;
}

/**
 * Mark a report as needing retry
 */
export function markForRetry(
  ticker: string,
  analysis_date: string,
  market_type: "us" | "twse" | "tpex",
  language?: "en" | "zh-TW"
): void {
  const key = getReportKey(ticker, analysis_date, market_type, language);
  if (!retryMap.has(key)) {
    retryMap.set(key, {
      ticker,
      analysis_date,
      market_type,
      language,
      attempts: 0,
      last_attempt: 0,
    });
    console.log(`📌 [${ticker}] Marked for cloud sync retry`);
  }
}

/**
 * Start automatic retry loop (should be called once on app startup)
 */
let retryIntervalId: NodeJS.Timeout | null = null;

export function startRetryLoop(): void {
  if (retryIntervalId) {
    console.warn("Retry loop already started");
    return;
  }

  retryIntervalId = setInterval(async () => {
    if (isCloudSyncEnabled() && retryMap.size > 0) {
      await retryPendingSyncs();
    }
  }, RETRY_INTERVAL);

  console.log("🔄 Cloud sync retry loop started");
}

export function stopRetryLoop(): void {
  if (retryIntervalId) {
    clearInterval(retryIntervalId);
    retryIntervalId = null;
    console.log("⏹️  Cloud sync retry loop stopped");
  }
}
