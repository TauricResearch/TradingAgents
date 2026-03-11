/**
 * User API service for cloud sync
 * Handles settings and reports sync with backend when logged in
 */

import { getAuthHeaders, getAuthToken } from "@/contexts/auth-context";
import type { ApiSettings } from "./storage";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

interface CloudReport {
  id: string;
  ticker: string;
  market_type: "us" | "twse" | "tpex";
  analysis_date: string;
  result: any;
  created_at: string;
  language?: "en" | "zh-TW"; // Language of the report
}

/**
 * Check if user is authenticated
 */
export function isCloudSyncEnabled(): boolean {
  return !!getAuthToken();
}

/**
 * Fetch user settings from cloud
 */
export async function getCloudSettings(): Promise<ApiSettings | null> {
  if (!isCloudSyncEnabled()) return null;

  try {
    const response = await fetch(`${API_BASE}/api/user/settings`, {
      headers: getAuthHeaders(),
    });

    if (!response.ok) {
      if (response.status === 401) return null;
      throw new Error("Failed to fetch settings");
    }

    const data = await response.json();
    return data.settings || null;
  } catch (error) {
    console.error("Failed to fetch cloud settings:", error);
    return null;
  }
}

/**
 * Save user settings to cloud
 */
export async function saveCloudSettings(settings: ApiSettings): Promise<boolean> {
  if (!isCloudSyncEnabled()) return false;

  try {
    const response = await fetch(`${API_BASE}/api/user/settings`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        ...getAuthHeaders(),
      },
      body: JSON.stringify(settings),
    });

    return response.ok;
  } catch (error) {
    console.error("Failed to save cloud settings:", error);
    return false;
  }
}

/**
 * Options for fetching cloud reports
 */
interface GetCloudReportsOptions {
  market_type?: "us" | "twse" | "tpex";
  language?: "en" | "zh-TW";
  limit?: number;
  offset?: number;
}

/**
 * Fetch reports from cloud with optional filtering and pagination
 */
export async function getCloudReports(options?: GetCloudReportsOptions): Promise<CloudReport[]> {
  if (!isCloudSyncEnabled()) return [];

  try {
    // Build query params
    const params = new URLSearchParams();
    if (options?.market_type) params.set("market_type", options.market_type);
    if (options?.language) params.set("language", options.language);
    if (options?.limit) params.set("limit", options.limit.toString());
    if (options?.offset) params.set("offset", options.offset.toString());

    const queryString = params.toString();
    const url = `${API_BASE}/api/user/reports${queryString ? `?${queryString}` : ""}`;

    const response = await fetch(url, {
      headers: getAuthHeaders(),
    });

    if (!response.ok) {
      if (response.status === 401) return [];
      throw new Error("Failed to fetch reports");
    }

    return await response.json();
  } catch (error) {
    console.error("Failed to fetch cloud reports:", error);
    return [];
  }
}

/**
 * Save a report to cloud
 */
export async function saveCloudReport(report: {
  ticker: string;
  market_type: "us" | "twse" | "tpex";
  analysis_date: string;
  result: any;
  language?: "en" | "zh-TW";
}): Promise<string | null> {
  if (!isCloudSyncEnabled()) {
    console.warn("☁️ Cloud sync not enabled (no auth token)");
    return null;
  }

  try {
    console.log(`☁️ Attempting to save report to cloud: ${report.ticker}`);
    
    const response = await fetch(`${API_BASE}/api/user/reports`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...getAuthHeaders(),
      },
      body: JSON.stringify(report),
    });

    if (!response.ok) {
      const errorText = await response.text().catch(() => "Unknown error");
      console.error(`☁️ Cloud save failed: HTTP ${response.status} - ${errorText}`);
      return null;
    }

    const data = await response.json();
    console.log(`☁️ Report saved to cloud successfully: ${data.report_id}`);
    return data.report_id;
  } catch (error) {
    console.error("☁️ Failed to save cloud report:", error);
    return null;
  }
}

/**
 * Delete a report from cloud
 */
export async function deleteCloudReport(reportId: string): Promise<boolean> {
  if (!isCloudSyncEnabled()) return false;

  try {
    const response = await fetch(`${API_BASE}/api/user/reports/${reportId}`, {
      method: "DELETE",
      headers: getAuthHeaders(),
    });

    return response.ok;
  } catch (error) {
    console.error("Failed to delete cloud report:", error);
    return false;
  }
}

/**
 * Get a single report by ID from cloud
 */
export async function getCloudReportById(reportId: string): Promise<CloudReport | null> {
  if (!isCloudSyncEnabled()) return null;

  try {
    const response = await fetch(`${API_BASE}/api/user/reports/${reportId}`, {
      headers: getAuthHeaders(),
    });

    if (!response.ok) {
      return null;
    }

    return await response.json();
  } catch (error) {
    console.error("Failed to fetch cloud report:", error);
    return null;
  }
}
