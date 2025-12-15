/**
 * Download Reports Component
 * Simple unified PDF download button
 */
"use client";

import { useState } from "react";
import { Download, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";

interface AnalystInfo {
  key: string;
  label: string;
  reportKey: string;
  description: string;
}

interface DownloadReportsProps {
  ticker: string;
  analysisDate: string;
  taskId?: string | null;
  analysts: AnalystInfo[];
  reports: any;
  priceData?: any[];
  priceStats?: any;
  /** Compact mode - just the button, no card wrapper */
  compact?: boolean;
}

export function DownloadReports({
  ticker,
  analysisDate,
  taskId,
  analysts,
  reports,
  priceData,
  priceStats,
  compact = false,
}: DownloadReportsProps) {
  const [isDownloading, setIsDownloading] = useState(false);

  // Helper to get nested value from reports object
  const getNestedValue = (obj: any, path: string) => {
    return path.split('.').reduce((current, key) => current?.[key], obj);
  };

  // Get all available analyst keys (those with actual reports)
  const availableAnalystKeys = analysts
    .filter(analyst => {
      const reportContent = getNestedValue(reports, analyst.reportKey);
      return reportContent && reportContent.trim().length > 0;
    })
    .map(a => a.key);

  // Handle download - always download all available reports as combined PDF
  const handleDownload = async () => {
    if (availableAnalystKeys.length === 0) return;

    setIsDownloading(true);
    try {
      // Build request body with all available analysts
      const requestBody: any = {
        ticker,
        analysis_date: analysisDate,
        analysts: availableAnalystKeys,  // Always include all available analysts
      };
      
      if (taskId) {
        // Task-based mode: API will look up reports from task
        requestBody.task_id = taskId;
      } else {
        // Direct mode: send report data directly
        requestBody.reports = reports;
        requestBody.price_data = priceData;
        requestBody.price_stats = priceStats;
      }
      
      const response = await fetch('/api/download/reports', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        const errorMessage = errorData.detail || `下載失敗 (${response.status})`;
        throw new Error(errorMessage);
      }

      // Get the blob
      const blob = await response.blob();
      
      // Get filename from Content-Disposition header if available
      const contentDisposition = response.headers.get('Content-Disposition');
      let filename = `${ticker}_Combined_Report_${analysisDate}.pdf`;
      
      if (contentDisposition) {
        const filenameMatch = contentDisposition.match(/filename=(.+)/);
        if (filenameMatch) {
          filename = filenameMatch[1];
        }
      }

      // Create download link
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      
      // Cleanup
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (error: any) {
      console.error('Download error:', error);
      alert(error.message || '下載失敗，請稍後再試');
    } finally {
      setIsDownloading(false);
    }
  };

  if (availableAnalystKeys.length === 0) {
    return null;
  }

  // Compact mode - just the button
  if (compact) {
    return (
      <Button
        onClick={handleDownload}
        disabled={isDownloading}
        variant="outline"
        className="gap-2 hover-lift"
      >
        {isDownloading ? (
          <>
            <Download className="h-4 w-4 animate-bounce" />
            下載中...
          </>
        ) : (
          <>
            <FileText className="h-4 w-4" />
            下載 PDF
          </>
        )}
      </Button>
    );
  }

  // Full mode - with description
  return (
    <div className="flex items-center justify-center p-4">
      <Button
        onClick={handleDownload}
        disabled={isDownloading}
        size="lg"
        className="gap-2 bg-gradient-to-r from-blue-500 to-purple-500 hover:from-blue-600 hover:to-purple-600"
      >
        {isDownloading ? (
          <>
            <Download className="h-5 w-5 animate-bounce" />
            生成報告中...
          </>
        ) : (
          <>
            <FileText className="h-5 w-5" />
            下載完整分析報告 PDF
          </>
        )}
      </Button>
    </div>
  );
}
