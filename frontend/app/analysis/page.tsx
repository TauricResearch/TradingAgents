/**
 * Analysis page
 */
"use client";

import { useEffect, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { AnalysisForm } from "@/components/analysis/AnalysisForm";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { ErrorAlert } from "@/components/shared/ErrorAlert";
import { useAnalysis } from "@/hooks/useAnalysis";
import { useAnalysisContext } from "@/context/AnalysisContext";
import { useAuth } from "@/contexts/auth-context";
import { saveReport, checkDuplicateReport } from "@/lib/reports-db";
import { saveCloudReport, isCloudSyncEnabled } from "@/lib/user-api";
import type { AnalysisRequest } from "@/lib/types";

export default function AnalysisPage() {
  const router = useRouter();
  const { setAnalysisResult, setTaskId, setMarketType, marketType } = useAnalysisContext();
  const { runAnalysis, loading, error, result, taskId } = useAnalysis();
  const { isAuthenticated } = useAuth();
  
  // Ref to track if we've already saved (to prevent duplicate saves)
  const hasSavedRef = useRef(false);

  // Auto-save function
  const autoSaveReport = useCallback(async () => {
    if (!result || hasSavedRef.current) return;
    
    try {
      // Check for duplicate
      const duplicate = await checkDuplicateReport(result.ticker, result.analysis_date);
      if (duplicate) {
        console.log("Report already saved, skipping auto-save");
        return;
      }
      
      // Mark as saved to prevent duplicate saves
      hasSavedRef.current = true;
      
      // Save to local IndexedDB
      await saveReport(
        result.ticker,
        marketType,
        result.analysis_date,
        result,
        taskId || undefined
      );
      console.log("📁 Auto-saved report to local storage");
      
      // If authenticated, also save to cloud
      if (isAuthenticated && isCloudSyncEnabled()) {
        const cloudId = await saveCloudReport({
          ticker: result.ticker,
          market_type: marketType,
          analysis_date: result.analysis_date,
          result: result,
        });
        if (cloudId) {
          console.log("☁️ Auto-saved report to cloud");
        }
      }
      // Note: Redis cleanup is handled immediately when analysis completes
      // in useAnalysis hook, so no need to cleanup here
    } catch (error) {
      console.error("Auto-save failed:", error);
    }
  }, [result, marketType, taskId, isAuthenticated]);

  // Auto-save when page unloads (closing tab, navigating away, etc.)
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (result && !hasSavedRef.current) {
        // Trigger auto-save synchronously (best effort)
        autoSaveReport();
        
        // Show browser's default "Leave site?" dialog only if there's unsaved analysis
        e.preventDefault();
        e.returnValue = '';
      }
    };

    // Add listener when we have a result
    if (result) {
      window.addEventListener('beforeunload', handleBeforeUnload);
    }

    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
    };
  }, [result, autoSaveReport]);

  // 當分析完成時自動跳轉到結果頁面
  useEffect(() => {
    if (result && !loading && !error) {
      // Auto-save before navigating to results
      autoSaveReport();
      
      setAnalysisResult(result);
      if (taskId) {
        setTaskId(taskId);
      }
      router.push("/analysis/results");
    }
  }, [result, loading, error, router, setAnalysisResult, taskId, setTaskId, autoSaveReport]);

  const handleSubmit = async (data: AnalysisRequest) => {
    try {
      // Store the market type for later use when saving the report
      if (data.market_type) {
        setMarketType(data.market_type);
      }
      await runAnalysis(data);
    } catch (err) {
      // Error is handled by the hook
      console.error("Analysis failed:", err);
    }
  };

  const handleViewResults = () => {
    if (result) {
      setAnalysisResult(result);
      router.push("/analysis/results");
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-50/30 via-pink-50/20 to-purple-50/30 dark:from-gray-950 dark:via-purple-950/40 dark:to-gray-950">
      <div className="container mx-auto px-4 py-12">
        <div className="max-w-6xl mx-auto space-y-8">
        {/* 標題區域 - 置中對齊 */}
        <div className="text-center relative">
          <div className="absolute inset-0 gradient-bg-radial opacity-40 -z-10" />
          <h1 className="text-4xl font-bold mb-2 gradient-text-primary">交易分析</h1>
          <p className="text-gray-600 dark:text-gray-400">
            配置並執行全面的多代理交易分析
          </p>
        </div>

        <AnalysisForm onSubmit={handleSubmit} loading={loading} />

        {loading && (
          <LoadingSpinner message="正在執行分析... 這可能需要幾分鐘時間。" />
        )}

        {error && <ErrorAlert error={error} />}
        </div>
      </div>
    </div>
  );
}
