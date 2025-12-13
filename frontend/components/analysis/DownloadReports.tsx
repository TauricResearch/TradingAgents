/**
 * Download Reports Component
 * Allows users to select and download analyst reports
 */
"use client";

import { useState } from "react";
import { Download, FileDown, CheckIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

interface AnalystInfo {
  key: string;
  label: string;
  reportKey: string;
  description: string;
}

interface DownloadReportsProps {
  ticker: string;
  analysisDate: string;
  taskId?: string | null;  // Now optional - if not provided, use direct data mode
  analysts: AnalystInfo[];
  reports: any;
  priceData?: any[];  // For direct download mode
  priceStats?: any;   // For direct download mode
}

export function DownloadReports({
  ticker,
  analysisDate,
  taskId,
  analysts,
  reports,
  priceData,
  priceStats,
}: DownloadReportsProps) {
  const [selectedAnalysts, setSelectedAnalysts] = useState<string[]>([]);
  const [isDownloading, setIsDownloading] = useState(false);

  // Helper to get nested value from reports object
  const getNestedValue = (obj: any, path: string) => {
    return path.split('.').reduce((current, key) => current?.[key], obj);
  };

  // Filter analysts that have actual reports
  const availableAnalysts = analysts.filter(analyst => {
    const reportContent = getNestedValue(reports, analyst.reportKey);
    return reportContent && reportContent.trim().length > 0;
  });

  // Handle select all
  const handleSelectAll = () => {
    if (selectedAnalysts.length === availableAnalysts.length) {
      setSelectedAnalysts([]);
    } else {
      setSelectedAnalysts(availableAnalysts.map(a => a.key));
    }
  };

  // Handle individual selection
  const handleToggleAnalyst = (analystKey: string) => {
    setSelectedAnalysts(prev => {
      if (prev.includes(analystKey)) {
        return prev.filter(key => key !== analystKey);
      } else {
        return [...prev, analystKey];
      }
    });
  };

  // Handle download
  const handleDownload = async () => {
    if (selectedAnalysts.length === 0) return;

    setIsDownloading(true);
    try {
      // Build request body - use taskId if available, otherwise send direct data
      const requestBody: any = {
        ticker,
        analysis_date: analysisDate,
        analysts: selectedAnalysts,
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
      let filename = `${ticker}_${analysisDate}.pdf`;
      
      if (contentDisposition) {
        const filenameMatch = contentDisposition.match(/filename=(.+)/);
        if (filenameMatch) {
          filename = filenameMatch[1];
        }
      } else if (selectedAnalysts.length > 1) {
        filename = `${ticker}_${analysisDate}.zip`;
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

  if (availableAnalysts.length === 0) {
    return null;
  }

  const isAllSelected = selectedAnalysts.length === availableAnalysts.length && availableAnalysts.length > 0;

  return (
    <Card className="hover-lift animate-scale-up">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FileDown className="h-5 w-5" />
          下載報告
        </CardTitle>
        <CardDescription>
          選擇要下載的分析師報告（支援單一PDF或多個ZIP）
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Select All */}
        <div className="flex items-center space-x-2 pb-2 border-b">
          <Checkbox
            id="select-all"
            checked={isAllSelected}
            onCheckedChange={handleSelectAll}
          />
          <Label
            htmlFor="select-all"
            className="text-sm font-medium cursor-pointer"
          >
            全選 ({availableAnalysts.length} 個報告)
          </Label>
        </div>

        {/* Analyst List */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {availableAnalysts.map(analyst => {
            const isSelected = selectedAnalysts.includes(analyst.key);
            return (
              <div
                key={analyst.key}
                onClick={() => handleToggleAnalyst(analyst.key)}
                className={cn(
                  "relative flex cursor-pointer flex-col gap-2 rounded-lg border-2 p-4 transition-all hover:bg-accent",
                  isSelected
                    ? "border-primary bg-primary/5 text-primary"
                    : "border-muted-foreground/25 bg-card text-muted-foreground"
                )}
              >
                <div className="flex items-start gap-3">
                  <div
                    className={cn(
                      "flex h-5 w-5 shrink-0 items-center justify-center rounded-sm border transition-colors",
                      isSelected
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-muted-foreground"
                    )}
                  >
                    {isSelected && <CheckIcon className="h-3.5 w-3.5" />}
                  </div>
                  <div className="flex-1">
                    <p className="text-sm font-medium select-none">
                      {analyst.label}
                    </p>
                  </div>
                </div>
                <p className="text-xs text-muted-foreground pl-8">
                  {analyst.description}
                </p>
              </div>
            );
          })}
        </div>

        {/* Download Button */}
        <div className="flex items-center justify-between pt-4 border-t">
          <div className="text-sm text-muted-foreground">
            已選擇 {selectedAnalysts.length} 個報告
          </div>
          <Button
            onClick={handleDownload}
            disabled={selectedAnalysts.length === 0 || isDownloading}
            className="gap-2"
          >
            <Download className="h-4 w-4" />
            {isDownloading ? '下載中...' : selectedAnalysts.length === 1 ? '下載 PDF' : '下載 ZIP'}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
