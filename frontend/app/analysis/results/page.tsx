"use client";

import { useState, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useAnalysisContext } from "@/context/AnalysisContext";
import { useAuth } from "@/contexts/auth-context";
import { useLanguage } from "@/contexts/LanguageContext";
import { PriceChart } from "@/components/analysis/PriceChart";
import { DownloadReports } from "@/components/analysis/DownloadReports";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { ChevronLeft, Save, Check, AlertCircle, Cloud } from "lucide-react";
import { saveReport, checkDuplicateReport } from "@/lib/reports-db";
import { saveCloudReport, isCloudSyncEnabled } from "@/lib/user-api";

// Analyst keys for mapping to translation keys
const ANALYST_KEYS = [
  // === Analysts Team ===
  { key: "market", reportKey: "market_report" },
  { key: "social", reportKey: "sentiment_report" },
  { key: "news", reportKey: "news_report" },
  { key: "fundamentals", reportKey: "fundamentals_report" },
  // === Research Team ===
  { key: "bull", reportKey: "investment_debate_state.bull_history" },
  { key: "bear", reportKey: "investment_debate_state.bear_history" },
  { key: "research_manager", reportKey: "investment_debate_state.judge_decision" },
  // === Trader ===
  { key: "trader", reportKey: "trader_investment_plan" },
  // === Risk Management Team ===
  { key: "risky", reportKey: "risk_debate_state.risky_history" },
  { key: "safe", reportKey: "risk_debate_state.safe_history" },
  { key: "neutral", reportKey: "risk_debate_state.neutral_history" },
  { key: "risk_manager", reportKey: "risk_debate_state.judge_decision" },
];

// 獲取嵌套對象的值
const getNestedValue = (obj: any, path: string) => {
  return path.split('.').reduce((current, key) => current?.[key], obj);
};

export default function AnalysisResultsPage() {
  const router = useRouter();
  const { analysisResult, taskId, marketType } = useAnalysisContext();
  const { isAuthenticated } = useAuth();
  const { t, locale } = useLanguage();
  const [selectedAnalyst, setSelectedAnalyst] = useState("market");
  
  // Save report states
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedToCloud, setSavedToCloud] = useState(false);

  // Debug: log received analysis data structure
  useEffect(() => {
    if (analysisResult) {
      console.log("[Results] analysisResult.reports keys:", Object.keys(analysisResult.reports || {}));
      const ids = analysisResult.reports?.investment_debate_state;
      const rds = analysisResult.reports?.risk_debate_state;
      if (ids) console.log("[Results] investment_debate_state keys:", Object.keys(ids));
      if (rds) console.log("[Results] risk_debate_state keys:", Object.keys(rds));
      // Log which reports are populated
      ANALYST_KEYS.forEach(a => {
        const val = getNestedValue(analysisResult.reports, a.reportKey);
        console.log(`[Results] ${a.key} (${a.reportKey}):`, val ? "populated" : "EMPTY/MISSING");
      });
    }
  }, [analysisResult]);

  // Build analysts array with translations
  const ANALYSTS = useMemo(() => ANALYST_KEYS.map(analyst => ({
    key: analyst.key,
    label: t.results.analysts[analyst.key as keyof typeof t.results.analysts] || analyst.key,
    description: t.results.analysts[`${analyst.key}Desc` as keyof typeof t.results.analysts] || "",
    reportKey: analyst.reportKey,
  })), [t]);

  // 如果沒有結果，重定向到分析頁面
  useEffect(() => {
    if (!analysisResult) {
      router.push("/analysis");
    }
  }, [analysisResult, router]);

  // Handle save report
  const handleSaveReport = async () => {
    if (!analysisResult) return;
    
    setSaving(true);
    setSaveError(null);
    setSaveSuccess(false);
    setSavedToCloud(false);
    
    try {
      // Check for duplicate in local storage
      const duplicate = await checkDuplicateReport(
        analysisResult.ticker,
        analysisResult.analysis_date
      );
      
      if (duplicate) {
        setSaveError(t.results.duplicateReport);
        setSaving(false);
        return;
      }
      
      // Save to local IndexedDB
      await saveReport(
        analysisResult.ticker,
        marketType,
        analysisResult.analysis_date,
        analysisResult,
        taskId || undefined,
        locale as "en" | "zh-TW"  // Pass current language for filtering
      );
      
      // If authenticated, also save to cloud
      if (isAuthenticated && isCloudSyncEnabled()) {
        const cloudId = await saveCloudReport({
          ticker: analysisResult.ticker,
          market_type: marketType,
          analysis_date: analysisResult.analysis_date,
          result: analysisResult,
          language: locale as "en" | "zh-TW",
        });
        if (cloudId) {
          setSavedToCloud(true);
        }
      }
      
      setSaveSuccess(true);
      // Reset success message after 3 seconds
      setTimeout(() => {
        setSaveSuccess(false);
        setSavedToCloud(false);
      }, 3000);
    } catch (error) {
      console.error("Save report error:", error);
      setSaveError(t.results.saveError);
    } finally {
      setSaving(false);
    }
  };

  if (!analysisResult) {
    return (
      <div className="container mx-auto px-4 py-12">
        <div className="text-center">
          <h1 className="text-2xl font-bold mb-4">{t.results.noResults}</h1>
          <p className="text-gray-600 mb-4">{t.results.runAnalysisFirst}</p>
          <Button onClick={() => router.push("/analysis")}>
            {t.results.backToAnalysis}
          </Button>
        </div>
      </div>
    );
  }


  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-50/30 via-pink-50/20 to-purple-50/30 dark:from-gray-950 dark:via-purple-950/40 dark:to-gray-950">
      <div className="container mx-auto px-4 py-12">
        <div className="max-w-7xl mx-auto space-y-8">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:justify-between md:items-center gap-4 animate-fade-in relative">
          <div className="absolute inset-0 gradient-bg-radial opacity-30 -z-10 rounded-lg" />
          <div>
            <h1 className="text-4xl font-bold mb-2 gradient-text-primary">
              {analysisResult.ticker} {t.results.detailedResults}
            </h1>
            <p className="text-gray-600 dark:text-gray-400">
              {t.results.analysisDate}：{analysisResult.analysis_date}
            </p>
          </div>
          <div className="flex gap-2 items-center flex-wrap">
            {/* Save success/error feedback */}
            {saveSuccess && (
              <span className="flex items-center gap-1 text-green-600 dark:text-green-400 text-sm animate-fade-in">
                <Check className="h-4 w-4" />
                {t.results.saved}
              </span>
            )}
            {saveError && (
              <span className="flex items-center gap-1 text-red-500 text-sm animate-fade-in">
                <AlertCircle className="h-4 w-4" />
                {saveError}
              </span>
            )}
            
            {/* Download PDF Button */}
            {analysisResult.reports && (
              <DownloadReports
                ticker={analysisResult.ticker}
                analysisDate={analysisResult.analysis_date}
                taskId={taskId}
                analysts={ANALYSTS}
                reports={analysisResult.reports}
                priceData={analysisResult.price_data}
                priceStats={analysisResult.price_stats}
                compact={true}
                language={locale}
              />
            )}
            
            {/* Save Report Button */}
            <Button
              variant="default"
              onClick={handleSaveReport}
              disabled={saving || saveSuccess}
              className="gap-2 hover-lift bg-gradient-to-r from-green-500 to-emerald-500 hover:from-green-600 hover:to-emerald-600"
            >
              {saving ? (
                <>{t.results.saving}</>
              ) : saveSuccess ? (
                <>
                  <Check className="h-4 w-4" />
                  {t.results.saved}
                </>
              ) : (
                <>
                  <Save className="h-4 w-4" />
                  {t.results.saveReport}
                </>
              )}
            </Button>
            
            <Button 
              variant="outline" 
              onClick={() => router.push("/analysis")}
              className="gap-2 hover-lift"
            >
              <ChevronLeft className="h-4 w-4" />
              {t.results.backButton}
            </Button>
          </div>
        </div>

        {/* 分析師選擇 Tabs */}
        <Tabs value={selectedAnalyst} onValueChange={setSelectedAnalyst} className="w-full animate-slide-up animate-delay-200">
          <TabsList className="grid w-full grid-cols-2 md:grid-cols-3 lg:grid-cols-4 h-auto gap-2">
            {ANALYSTS.map(analyst => (
              <TabsTrigger 
                key={analyst.key} 
                value={analyst.key}
                className="text-sm md:text-base py-2 transition-all duration-300 hover:scale-105"
              >
                {analyst.label}
              </TabsTrigger>
            ))}
          </TabsList>

          {ANALYSTS.map(analyst => (
            <TabsContent key={analyst.key} value={analyst.key} className="mt-6">
              <div className="space-y-6">
                {/* 價格圖表 - 每個分析師都有 */}
                {analysisResult.price_data && analysisResult.price_stats && (
                  <PriceChart
                    priceData={analysisResult.price_data}
                    priceStats={analysisResult.price_stats}
                    ticker={analysisResult.ticker}
                  />
                )}

                {/* 分析師報告 */}
                <Card className="animate-scale-up hover-lift">
                  <CardHeader>
                    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                      <div>
                        <CardTitle>{analyst.label} {t.results.report}</CardTitle>
                        <CardDescription>
                          {analyst.description}
                        </CardDescription>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent>
                    {getNestedValue(analysisResult.reports, analyst.reportKey) ? (
                      <div className="prose prose-sm xl:prose-base max-w-none dark:prose-invert animate-fade-in overflow-x-auto prose-table:border-collapse prose-table:w-full prose-td:border prose-td:border-gray-300 dark:prose-td:border-gray-600 prose-td:p-2 prose-th:border prose-th:border-gray-300 dark:prose-th:border-gray-600 prose-th:p-2 prose-th:bg-gray-100 dark:prose-th:bg-gray-800">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {getNestedValue(analysisResult.reports, analyst.reportKey)}
                        </ReactMarkdown>
                      </div>
                    ) : (
                      <div className="text-center py-8">
                        <p className="text-gray-500 dark:text-gray-400">
                          {t.results.noReportGenerated}
                        </p>
                        <p className="text-sm text-gray-400 dark:text-gray-500 mt-2">
                          {t.results.notSelectedOrNoReport}
                        </p>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>
            </TabsContent>
          ))}
        </Tabs>
        </div>
      </div>
    </div>
  );
}
