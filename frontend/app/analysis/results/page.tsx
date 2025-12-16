"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useAnalysisContext } from "@/context/AnalysisContext";
import { useAuth } from "@/contexts/auth-context";
import { PriceChart } from "@/components/analysis/PriceChart";
import { DownloadReports } from "@/components/analysis/DownloadReports";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { ChevronLeft, Save, Check, AlertCircle, Cloud } from "lucide-react";
import { saveReport, checkDuplicateReport } from "@/lib/reports-db";
import { saveCloudReport, isCloudSyncEnabled } from "@/lib/user-api";

const ANALYSTS = [
  // === 分析師團隊 ===
  { 
    key: "market", 
    label: "市場分析師", 
    reportKey: "market_report",
    description: "技術分析與市場趨勢評估"
  },
  { 
    key: "social", 
    label: "社群媒體分析師", 
    reportKey: "sentiment_report",
    description: "社群情緒與市場氛圍分析"
  },
  { 
    key: "news", 
    label: "新聞分析師", 
    reportKey: "news_report",
    description: "新聞事件與影響分析"
  },
  { 
    key: "fundamentals", 
    label: "基本面分析師", 
    reportKey: "fundamentals_report",
    description: "財務數據與基本面分析"
  },
  
  // === 研究團隊 ===
  { 
    key: "bull", 
    label: "看漲研究員", 
    reportKey: "investment_debate_state.bull_history",
    description: "看漲觀點與投資論據"
  },
  { 
    key: "bear", 
    label: "看跌研究員", 
    reportKey: "investment_debate_state.bear_history",
    description: "看跌觀點與風險警告"
  },
  { 
    key: "research_manager", 
    label: "研究經理", 
    reportKey: "investment_debate_state.judge_decision",
    description: "研究團隊綜合決策"
  },
  
  // === 交易員 ===
  { 
    key: "trader", 
    label: "交易員", 
    reportKey: "trader_investment_plan",
    description: "交易執行計劃與策略"
  },
  
  // === 風險管理團隊 ===
  { 
    key: "risky", 
    label: "激進分析師", 
    reportKey: "risk_debate_state.risky_history",
    description: "高風險高回報策略分析"
  },
  { 
    key: "safe", 
    label: "保守分析師", 
    reportKey: "risk_debate_state.safe_history",
    description: "穩健保守策略分析"
  },
  { 
    key: "neutral", 
    label: "中立分析師", 
    reportKey: "risk_debate_state.neutral_history",
    description: "中立平衡策略分析"
  },
  { 
    key: "risk_manager", 
    label: "風險經理", 
    reportKey: "risk_debate_state.judge_decision",
    description: "風險管理綜合決策"
  },
];

// 獲取嵌套對象的值
const getNestedValue = (obj: any, path: string) => {
  return path.split('.').reduce((current, key) => current?.[key], obj);
};

export default function AnalysisResultsPage() {
  const router = useRouter();
  const { analysisResult, taskId, marketType } = useAnalysisContext();
  const { isAuthenticated } = useAuth();
  const [selectedAnalyst, setSelectedAnalyst] = useState("market");
  
  // Save report states
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedToCloud, setSavedToCloud] = useState(false);

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
        setSaveError("此報告已存在（相同股票代碼與分析日期）");
        setSaving(false);
        return;
      }
      
      // Save to local IndexedDB
      await saveReport(
        analysisResult.ticker,
        marketType,
        analysisResult.analysis_date,
        analysisResult,
        taskId || undefined
      );
      
      // If authenticated, also save to cloud
      if (isAuthenticated && isCloudSyncEnabled()) {
        const cloudId = await saveCloudReport({
          ticker: analysisResult.ticker,
          market_type: marketType,
          analysis_date: analysisResult.analysis_date,
          result: analysisResult,
        });
        if (cloudId) {
          setSavedToCloud(true);
        }
      }
      // Note: Redis cleanup is handled immediately when analysis completes
      // in useAnalysis hook, so no need to cleanup here
      
      setSaveSuccess(true);
      // Reset success message after 3 seconds
      setTimeout(() => {
        setSaveSuccess(false);
        setSavedToCloud(false);
      }, 3000);
    } catch (error) {
      console.error("Save report error:", error);
      setSaveError("儲存失敗，請稍後再試");
    } finally {
      setSaving(false);
    }
  };

  if (!analysisResult) {
    return (
      <div className="container mx-auto px-4 py-12">
        <div className="text-center">
          <h1 className="text-2xl font-bold mb-4">沒有分析結果</h1>
          <p className="text-gray-600 mb-4">請先執行分析</p>
          <Button onClick={() => router.push("/analysis")}>
            返回分析頁面
          </Button>
        </div>
      </div>
    );
  }

  const currentAnalyst = ANALYSTS.find(a => a.key === selectedAnalyst);
  const currentReport = getNestedValue(analysisResult.reports, currentAnalyst?.reportKey || "");

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-50/30 via-pink-50/20 to-purple-50/30 dark:from-gray-950 dark:via-purple-950/40 dark:to-gray-950">
      <div className="container mx-auto px-4 py-12">
        <div className="max-w-7xl mx-auto space-y-8">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:justify-between md:items-center gap-4 animate-fade-in relative">
          <div className="absolute inset-0 gradient-bg-radial opacity-30 -z-10 rounded-lg" />
          <div>
            <h1 className="text-4xl font-bold mb-2 gradient-text-primary">
              {analysisResult.ticker} 詳細分析結果
            </h1>
            <p className="text-gray-600 dark:text-gray-400">
              分析日期：{analysisResult.analysis_date}
            </p>
          </div>
          <div className="flex gap-2 items-center flex-wrap">
            {/* Save success/error feedback */}
            {saveSuccess && (
              <span className="flex items-center gap-1 text-green-600 dark:text-green-400 text-sm animate-fade-in">
                <Check className="h-4 w-4" />
                已儲存
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
                <>儲存中...</>
              ) : saveSuccess ? (
                <>
                  <Check className="h-4 w-4" />
                  已儲存
                </>
              ) : (
                <>
                  <Save className="h-4 w-4" />
                  儲存報告
                </>
              )}
            </Button>
            
            <Button 
              variant="outline" 
              onClick={() => router.push("/analysis")}
              className="gap-2 hover-lift"
            >
              <ChevronLeft className="h-4 w-4" />
              返回分析
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
                    <CardTitle>{analyst.label} 報告</CardTitle>
                    <CardDescription>
                      {analyst.description}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    {currentReport ? (
                      <div className="prose prose-sm max-w-none dark:prose-invert animate-fade-in">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {currentReport}
                        </ReactMarkdown>
                      </div>
                    ) : (
                      <div className="text-center py-8">
                        <p className="text-gray-500 dark:text-gray-400">
                          此分析師沒有生成報告
                        </p>
                        <p className="text-sm text-gray-400 dark:text-gray-500 mt-2">
                          可能此分析師未被選擇或分析過程中未產生報告
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
