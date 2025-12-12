/**
 * Analysis page
 */
"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { AnalysisForm } from "@/components/analysis/AnalysisForm";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { ErrorAlert } from "@/components/shared/ErrorAlert";
import { useAnalysis } from "@/hooks/useAnalysis";
import { useAnalysisContext } from "@/context/AnalysisContext";
import type { AnalysisRequest } from "@/lib/types";

export default function AnalysisPage() {
  const router = useRouter();
  const { setAnalysisResult, setTaskId, setMarketType } = useAnalysisContext();
  const { runAnalysis, loading, error, result, taskId } = useAnalysis();

  // 當分析完成時自動跳轉到結果頁面
  useEffect(() => {
    if (result && !loading && !error) {
      setAnalysisResult(result);
      if (taskId) {
        setTaskId(taskId);
      }
      router.push("/analysis/results");
    }
  }, [result, loading, error, router, setAnalysisResult, taskId, setTaskId]);

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
