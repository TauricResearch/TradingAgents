/**
 * History page - browse saved analysis reports
 */
"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { format } from "date-fns";
import { zhTW } from "date-fns/locale";
import { useAnalysisContext } from "@/context/AnalysisContext";
import { useAuth } from "@/contexts/auth-context";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
  CardFooter,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Trash2, Eye, RefreshCw, TrendingUp, FileText, Download } from "lucide-react";
import {
  getReportsByMarketType,
  deleteReport,
  getReportCountByMarketType,
  type SavedReport,
} from "@/lib/reports-db";
import { getCloudReports, deleteCloudReport, saveCloudReport, isCloudSyncEnabled } from "@/lib/user-api";
// import { LoginPrompt } from "@/components/auth/login-button";
import { PendingTaskRecovery } from "@/components/PendingTaskRecovery";

// Analyst definitions for download
const ANALYSTS = [
  { key: "market", label: "市場分析師", reportKey: "market_report", description: "技術分析與市場趨勢評估" },
  { key: "social", label: "社群媒體分析師", reportKey: "sentiment_report", description: "社群情緒與市場氛圍分析" },
  { key: "news", label: "新聞分析師", reportKey: "news_report", description: "新聞事件與影響分析" },
  { key: "fundamentals", label: "基本面分析師", reportKey: "fundamentals_report", description: "財務數據與基本面分析" },
  { key: "bull", label: "看漲研究員", reportKey: "investment_debate_state.bull_history", description: "看漲觀點與投資論據" },
  { key: "bear", label: "看跌研究員", reportKey: "investment_debate_state.bear_history", description: "看跌觀點與風險警告" },
  { key: "research_manager", label: "研究經理", reportKey: "investment_debate_state.judge_decision", description: "研究團隊綜合決策" },
  { key: "trader", label: "交易員", reportKey: "trader_investment_plan", description: "交易執行計劃與策略" },
  { key: "risky", label: "激進分析師", reportKey: "risk_debate_state.risky_history", description: "高風險高回報策略分析" },
  { key: "safe", label: "保守分析師", reportKey: "risk_debate_state.safe_history", description: "穩健保守策略分析" },
  { key: "neutral", label: "中立分析師", reportKey: "risk_debate_state.neutral_history", description: "中立平衡策略分析" },
  { key: "risk_manager", label: "風險經理", reportKey: "risk_debate_state.judge_decision", description: "風險管理綜合決策" },
];

// Market type labels
const MARKET_LABELS = {
  us: { label: "🇺🇸 美股", description: "美國股市分析報告" },
  twse: { label: "🇹🇼 上市", description: "台灣證券交易所上市股票" },
  tpex: { label: "🇹🇼 上櫃/興櫃", description: "台灣櫃買中心上櫃/興櫃股票" },
};

// Helper function to extract decision from Risk Manager's final decision
const extractDecisionFromReport = (report: SavedReport): { action: string; color: string } => {
  
  // DEBUG: Log the actual data structure to diagnose issues
  console.log("📊 DEBUG extractDecisionFromReport for:", report.ticker);
  console.log("  - result type:", typeof report.result);
  console.log("  - result.reports exists:", !!report.result?.reports);
  console.log("  - trader_investment_plan exists:", !!report.result?.reports?.trader_investment_plan);
  console.log("  - decision.action exists:", !!report.result?.decision?.action);
  
  if (report.result?.reports?.trader_investment_plan) {
    const traderText = report.result.reports.trader_investment_plan;
    console.log("  - trader_investment_plan type:", typeof traderText);
    console.log("  - trader_investment_plan length:", traderText.length);
    // Show last 150 chars to see the final decision
    console.log("  - last 150 chars:", traderText.slice(-150));
    // Check if it contains the key phrase
    const hasProposal = traderText.includes("最終交易提案");
    console.log("  - contains '最終交易提案':", hasProposal);
  } else {
    console.log("  - trader_investment_plan is NULL or undefined");
  }
  // Helper function to find "最終交易提案" specifically
  const findFinalProposal = (text: string): { action: string; color: string } | null => {
    if (!text || typeof text !== 'string') return null;
    
    // Match "最終交易提案：持有" - handle markdown ** bold markers
    // Pattern handles: 最終交易提案：持有, 最終交易提案：**持有**, **最終交易提案：持有**
    // Use global flag to find ALL matches, then take the LAST one (final decision)
    const regex = /\*{0,2}最終交易提案[：:]\s*\*{0,2}(買入|賣出|持有)\*{0,2}/g;
    const matches = [...text.matchAll(regex)];
    
    if (matches.length > 0) {
      // Take the LAST match (the final decision at the end of the report)
      const lastMatch = matches[matches.length - 1];
      const decision = lastMatch[1];
      console.log(`  ✅ Matched pattern: "${lastMatch[0]}" -> decision: "${decision}"`);
      if (decision === "買入") return { action: "買入", color: "text-green-600" };
      if (decision === "賣出") return { action: "賣出", color: "text-red-600" };
      if (decision === "持有") return { action: "持有", color: "text-yellow-600" };
    }
    return null;
  };
  
  // Helper function to find other decision patterns
  const findOtherDecision = (text: string): { action: string; color: string } | null => {
    if (!text || typeof text !== 'string') return null;
    
    const lowerText = text.toLowerCase();
    
    // Look for "最終決策" or "最終建議"
    const finalDecisionMatch = text.match(/最終(?:決策|建議)[：:]\s*(買入|賣出|持有)/);
    if (finalDecisionMatch) {
      const decision = finalDecisionMatch[1];
      if (decision === "買入") return { action: "買入", color: "text-green-600" };
      if (decision === "賣出") return { action: "賣出", color: "text-red-600" };
      if (decision === "持有") return { action: "持有", color: "text-yellow-600" };
    }
    
    // English patterns
    if (lowerText.match(/(?:final|recommendation|decision)[:\s]*(buy|long)/i)) {
      return { action: "買入", color: "text-green-600" };
    }
    if (lowerText.match(/(?:final|recommendation|decision)[:\s]*(sell|short)/i)) {
      return { action: "賣出", color: "text-red-600" };
    }
    if (lowerText.match(/(?:final|recommendation|decision)[:\s]*(hold)/i)) {
      return { action: "持有", color: "text-yellow-600" };
    }
    
    return null;
  };
  
  // ====== PRIORITY 1: Trader's "最終交易提案" - HIGHEST PRIORITY ======
  const traderReport = report.result.reports?.trader_investment_plan;
  if (traderReport) {
    const decision = findFinalProposal(traderReport);
    if (decision) {
      console.log(`📊 Found trader decision: ${decision.action}`);
      return decision;
    }
  }
  
  // ====== PRIORITY 2: Check final_trade_decision ======
  const finalTradeDecision = report.result.reports?.final_trade_decision;
  if (finalTradeDecision) {
    const decision = findFinalProposal(finalTradeDecision) || findOtherDecision(finalTradeDecision);
    if (decision) return decision;
  }
  
  // ====== PRIORITY 3: Check risk_debate_state judge decision ======
  const riskJudge = report.result.reports?.risk_debate_state?.judge_decision;
  if (riskJudge) {
    const decision = findOtherDecision(riskJudge);
    if (decision) return decision;
  }
  
  // ====== PRIORITY 4: Fall back to decision.action field ======
  if (report.result.decision?.action) {
    const action = report.result.decision.action;
    const actionLower = action.toLowerCase();
    const color = actionLower.includes("buy") 
      ? "text-green-600" 
      : actionLower.includes("sell") 
        ? "text-red-600" 
        : "text-yellow-600";
    return { action, color };
  }
  
  // ====== PRIORITY 5: Search in other report fields ======
  const allReports = report.result.reports;
  if (allReports) {
    const reportTexts = [
      allReports.market_report,
      allReports.sentiment_report,
      allReports.news_report,
      allReports.fundamentals_report,
    ].filter(t => t && typeof t === 'string');
    
    for (const text of reportTexts) {
      const decision = findFinalProposal(text);
      if (decision) return decision;
    }
  }
  
  return { action: "N/A", color: "text-gray-500" };
};

export default function HistoryPage() {
  const router = useRouter();
  const { setAnalysisResult, setTaskId, setMarketType } = useAnalysisContext();
  const { isAuthenticated } = useAuth();

  const [activeTab, setActiveTab] = useState<"us" | "twse" | "tpex">("us");
  const [reports, setReports] = useState<SavedReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [counts, setCounts] = useState({ us: 0, twse: 0, tpex: 0 });
  const [isCloudData, setIsCloudData] = useState(false);

  // Delete confirmation dialog
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [reportToDelete, setReportToDelete] = useState<SavedReport | null>(
    null
  );
  const [deleting, setDeleting] = useState(false);
  
  // Auto-sync tracking ref
  const hasAutoSyncedRef = useRef(false);

  // Load reports when tab changes or auth state changes
  useEffect(() => {
    loadReports();
  }, [activeTab, isAuthenticated]);

  // Load counts on mount or auth change
  useEffect(() => {
    loadCounts();
  }, [isAuthenticated]);
  
  // Auto-sync local reports to cloud when page loads (if authenticated)
  useEffect(() => {
    const autoSync = async () => {
      // Only sync once per session, and only if authenticated
      if (hasAutoSyncedRef.current || !isAuthenticated || !isCloudSyncEnabled()) {
        return;
      }
      
      hasAutoSyncedRef.current = true;
      
      try {
        // Get all local reports
        const [usLocal, twseLocal, tpexLocal] = await Promise.all([
          getReportsByMarketType("us"),
          getReportsByMarketType("twse"),
          getReportsByMarketType("tpex"),
        ]);
        const allLocal = [...usLocal, ...twseLocal, ...tpexLocal];
        
        if (allLocal.length === 0) return;
        
        // Get cloud reports to check for duplicates
        const cloudReports = await getCloudReports();
        const cloudKeys = new Set(
          cloudReports.map(r => `${r.ticker}_${r.analysis_date}`)
        );
        
        // Find local-only reports to upload
        const toUpload = allLocal.filter(
          r => !cloudKeys.has(`${r.ticker}_${r.analysis_date}`)
        );
        
        if (toUpload.length === 0) {
          console.log("☁️ Auto-sync: All reports already in cloud");
          return;
        }
        
        console.log(`☁️ Auto-sync: Uploading ${toUpload.length} local reports to cloud...`);
        
        // Upload each report silently
        let success = 0;
        for (const report of toUpload) {
          try {
            const cloudId = await saveCloudReport({
              ticker: report.ticker,
              market_type: report.market_type,
              analysis_date: report.analysis_date,
              result: report.result,
            });
            if (cloudId) success++;
          } catch (e) {
            // Silently continue on error
          }
        }
        
        if (success > 0) {
          console.log(`☁️ Auto-sync: Successfully uploaded ${success} reports`);
          // Reload to show updated data
          await loadReports();
          await loadCounts();
        }
      } catch (error) {
        console.error("☁️ Auto-sync failed:", error);
      }
    };
    
    autoSync();
  }, [isAuthenticated]);

  const loadReports = async () => {
    setLoading(true);
    try {
      // Always load local IndexedDB reports first
      const localData = await getReportsByMarketType(activeTab);
      
      // If authenticated, also load from cloud and merge
      if (isAuthenticated && isCloudSyncEnabled()) {
        const cloudReports = await getCloudReports();
        
        // Convert cloud reports to SavedReport format and filter by market type
        const cloudFiltered = cloudReports
          .filter(r => r.market_type === activeTab)
          .map(r => ({
            id: parseInt(r.id.replace(/-/g, '').slice(0, 8), 16), // Convert UUID to number
            cloudId: r.id, // Keep cloud ID for deletion
            ticker: r.ticker,
            market_type: r.market_type as "us" | "twse" | "tpex",
            analysis_date: r.analysis_date,
            saved_at: new Date(r.created_at),
            result: r.result,
          })) as (SavedReport & { cloudId?: string })[];
        
        if (cloudFiltered.length > 0) {
          // Merge: prefer cloud data, but include local-only reports
          // Create a Set of cloud report keys (ticker + date) for deduplication
          const cloudKeys = new Set(
            cloudFiltered.map(r => `${r.ticker}_${r.analysis_date}`)
          );
          
          // Find local reports that don't exist in cloud
          const localOnly = localData.filter(
            r => !cloudKeys.has(`${r.ticker}_${r.analysis_date}`)
          );
          
          // Combine: cloud reports + local-only reports
          const merged = [...cloudFiltered, ...localOnly];
          
          // Sort by saved_at descending
          merged.sort((a, b) => 
            new Date(b.saved_at).getTime() - new Date(a.saved_at).getTime()
          );
          
          setReports(merged);
          setIsCloudData(true);
          return;
        }
      }
      
      // If no cloud data or not authenticated, use local only
      setReports(localData);
      setIsCloudData(false);
    } catch (error) {
      console.error("Failed to load reports:", error);
      // Fall back to local on error
      const data = await getReportsByMarketType(activeTab);
      setReports(data);
      setIsCloudData(false);
    } finally {
      setLoading(false);
    }
  };

  const loadCounts = async () => {
    try {
      // Always get local counts first
      const localCounts = await getReportCountByMarketType();
      
      if (isAuthenticated && isCloudSyncEnabled()) {
        const cloudReports = await getCloudReports();
        
        if (cloudReports.length > 0) {
          // Get local reports to check for duplicates
          const [usLocal, twseLocal, tpexLocal] = await Promise.all([
            getReportsByMarketType("us"),
            getReportsByMarketType("twse"),
            getReportsByMarketType("tpex"),
          ]);
          
          // Cloud report keys for deduplication
          const cloudKeys = new Set(
            cloudReports.map(r => `${r.ticker}_${r.analysis_date}_${r.market_type}`)
          );
          
          // Count local-only reports (not in cloud)
          const usLocalOnly = usLocal.filter(
            r => !cloudKeys.has(`${r.ticker}_${r.analysis_date}_us`)
          ).length;
          const twseLocalOnly = twseLocal.filter(
            r => !cloudKeys.has(`${r.ticker}_${r.analysis_date}_twse`)
          ).length;
          const tpexLocalOnly = tpexLocal.filter(
            r => !cloudKeys.has(`${r.ticker}_${r.analysis_date}_tpex`)
          ).length;
          
          // Cloud counts
          const usCoud = cloudReports.filter(r => r.market_type === "us").length;
          const twseCloud = cloudReports.filter(r => r.market_type === "twse").length;
          const tpexCloud = cloudReports.filter(r => r.market_type === "tpex").length;
          
          // Merged counts: cloud + local-only
          setCounts({
            us: usCoud + usLocalOnly,
            twse: twseCloud + twseLocalOnly,
            tpex: tpexCloud + tpexLocalOnly,
          });
          return;
        }
      }
      
      setCounts(localCounts);
    } catch (error) {
      console.error("Failed to load counts:", error);
    }
  };

  const handleViewReport = (report: SavedReport) => {
    // Set the context with the saved report data
    setAnalysisResult(report.result);
    setTaskId(report.task_id || null);
    setMarketType(report.market_type);
    // Navigate to results page
    router.push("/analysis/results");
  };

  const handleDeleteClick = (report: SavedReport) => {
    setReportToDelete(report);
    setDeleteDialogOpen(true);
  };

  const handleConfirmDelete = async () => {
    if (!reportToDelete) return;

    setDeleting(true);
    try {
      const cloudId = (reportToDelete as any).cloudId;
      
      // IMPORTANT: Delete from BOTH cloud AND local to prevent re-sync issues
      // 1. If cloud ID exists, delete from cloud
      if (cloudId) {
        console.log("🗑️ Deleting from cloud:", cloudId);
        await deleteCloudReport(cloudId);
      }
      
      // 2. Always try to delete from local IndexedDB as well
      // Find matching local report by ticker + analysis_date
      try {
        const localReports = await getReportsByMarketType(reportToDelete.market_type);
        const matchingLocal = localReports.find(
          r => r.ticker === reportToDelete.ticker && 
               r.analysis_date === reportToDelete.analysis_date
        );
        if (matchingLocal && matchingLocal.id) {
          console.log("🗑️ Deleting from local IndexedDB:", matchingLocal.id);
          await deleteReport(matchingLocal.id);
        }
      } catch (localError) {
        console.warn("Could not delete local copy:", localError);
      }
      
      // Refresh reports and counts
      await loadReports();
      await loadCounts();
      setDeleteDialogOpen(false);
      setReportToDelete(null);
    } catch (error) {
      console.error("Failed to delete report:", error);
    } finally {
      setDeleting(false);
    }
  };

  // Download PDF handler
  const [downloadingId, setDownloadingId] = useState<number | null>(null);
  
  const handleDownloadPdf = async (report: SavedReport) => {
    setDownloadingId(report.id ?? null);
    try {
      // Get all available analyst keys
      const getNestedValue = (obj: any, path: string) => {
        return path.split('.').reduce((current, key) => current?.[key], obj);
      };
      
      const availableAnalystKeys = ANALYSTS
        .filter(analyst => {
          const reportContent = getNestedValue(report.result.reports, analyst.reportKey);
          return reportContent && reportContent.trim().length > 0;
        })
        .map(a => a.key);
      
      if (availableAnalystKeys.length === 0) {
        alert('此報告沒有可下載的分析師報告');
        return;
      }
      
      // Build request body
      const requestBody = {
        ticker: report.ticker,
        analysis_date: report.analysis_date,
        analysts: availableAnalystKeys,
        reports: report.result.reports,
        price_data: report.result.price_data,
        price_stats: report.result.price_stats,
      };
      
      const response = await fetch('/api/download/reports', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `下載失敗 (${response.status})`);
      }

      // Get the blob
      const blob = await response.blob();
      
      // Get filename from header
      const contentDisposition = response.headers.get('Content-Disposition');
      let filename = `${report.ticker}_Combined_Report_${report.analysis_date}.pdf`;
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
      setDownloadingId(null);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-50/30 via-pink-50/20 to-purple-50/30 dark:from-gray-950 dark:via-purple-950/40 dark:to-gray-950">
      <div className="container mx-auto px-4 py-12">
        <div className="max-w-6xl mx-auto space-y-8">
          {/* Header */}
          <div className="text-center relative animate-fade-in">
            <div className="absolute inset-0 gradient-bg-radial opacity-40 -z-10" />
            <h1 className="text-4xl font-bold mb-2 gradient-text-primary">
              歷史報告
            </h1>
            <p className="text-gray-600 dark:text-gray-400">
              瀏覽已儲存的分析報告
            </p>
          </div>

          {/* Pending Task Recovery Notice */}
          <PendingTaskRecovery />

          {/* Market Type Tabs */}
          <Tabs
            value={activeTab}
            onValueChange={(v) => setActiveTab(v as typeof activeTab)}
            className="w-full animate-slide-up animate-delay-200"
          >
            <TabsList className="grid w-full grid-cols-3 h-auto gap-2">
              {(Object.keys(MARKET_LABELS) as Array<keyof typeof MARKET_LABELS>).map(
                (key) => (
                  <TabsTrigger
                    key={key}
                    value={key}
                    className="py-3 text-base transition-all duration-300 hover:scale-105"
                  >
                    <span className="mr-2">{MARKET_LABELS[key].label}</span>
                    <span className="px-2 py-0.5 rounded-full bg-white/20 text-xs">
                      {counts[key]}
                    </span>
                  </TabsTrigger>
                )
              )}
            </TabsList>

            {(Object.keys(MARKET_LABELS) as Array<keyof typeof MARKET_LABELS>).map(
              (marketType) => (
                <TabsContent key={marketType} value={marketType} className="mt-6">
                  <div className="space-y-4">
                    {/* Refresh button */}
                    <div className="flex justify-end">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={loadReports}
                        disabled={loading}
                        className="gap-2"
                      >
                        <RefreshCw
                          className={`h-4 w-4 ${loading ? "animate-spin" : ""}`}
                        />
                        重新整理
                      </Button>
                    </div>

                    {/* Report List */}
                    {loading ? (
                      <div className="text-center py-12">
                        <RefreshCw className="h-8 w-8 animate-spin mx-auto text-gray-400" />
                        <p className="text-gray-500 mt-4">載入中...</p>
                      </div>
                    ) : reports.length === 0 ? (
                      <Card className="animate-fade-in">
                        <CardContent className="py-12 text-center">
                          <TrendingUp className="h-12 w-12 mx-auto text-gray-300 dark:text-gray-600 mb-4" />
                          <p className="text-gray-500 dark:text-gray-400">
                            尚無{MARKET_LABELS[marketType].label}的分析報告
                          </p>
                          <p className="text-sm text-gray-400 dark:text-gray-500 mt-2">
                            執行分析後，可在結果頁面儲存報告
                          </p>
                          <Button
                            variant="outline"
                            className="mt-4"
                            onClick={() => router.push("/analysis")}
                          >
                            開始分析
                          </Button>
                        </CardContent>
                      </Card>
                    ) : (
                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                        {reports.map((report) => (
                          <Card
                            key={report.id}
                            className="hover-lift animate-scale-up transition-all duration-300"
                          >
                            <CardHeader>
                              <CardTitle className="flex items-center justify-between">
                                <span className="text-xl font-bold gradient-text-primary">
                                  {report.ticker}
                                </span>
                                <span className="text-xs px-2 py-1 rounded-full bg-gradient-to-r from-blue-100 to-pink-100 dark:from-blue-900 dark:to-purple-900 text-gray-600 dark:text-gray-300">
                                  {MARKET_LABELS[report.market_type].label}
                                </span>
                              </CardTitle>
                              <CardDescription>
                                分析日期：{report.analysis_date}
                              </CardDescription>
                            </CardHeader>
                            <CardContent>
                              <p className="text-sm text-gray-500 dark:text-gray-400">
                                儲存時間：
                                {format(
                                  new Date(report.saved_at),
                                  "yyyy/MM/dd HH:mm",
                                  { locale: zhTW }
                                )}
                              </p>
                              {(() => {
                                const decision = extractDecisionFromReport(report);
                                return (
                                  <p className="text-sm mt-2">
                                    <span className="font-medium">決策：</span>
                                    <span className={`ml-1 font-semibold ${decision.color}`}>
                                      {decision.action}
                                    </span>
                                  </p>
                                );
                              })()}
                            </CardContent>
                            <CardFooter className="flex gap-2 flex-wrap">
                              <Button
                                variant="default"
                                size="sm"
                                className="flex-1 gap-1"
                                onClick={() => handleViewReport(report)}
                              >
                                <Eye className="h-4 w-4" />
                                檢視
                              </Button>
                              <Button
                                variant="outline"
                                size="sm"
                                className="gap-1"
                                onClick={() => handleDownloadPdf(report)}
                                disabled={downloadingId === report.id}
                              >
                                {downloadingId === report.id ? (
                                  <>
                                    <Download className="h-4 w-4 animate-bounce" />
                                    下載中
                                  </>
                                ) : (
                                  <>
                                    <FileText className="h-4 w-4" />
                                    PDF
                                  </>
                                )}
                              </Button>
                              <Button
                                variant="destructive"
                                size="sm"
                                className="gap-1"
                                onClick={() => handleDeleteClick(report)}
                              >
                                <Trash2 className="h-4 w-4" />
                                刪除
                              </Button>
                            </CardFooter>
                          </Card>
                        ))}
                      </div>
                    )}
                  </div>
                </TabsContent>
              )
            )}
          </Tabs>
        </div>
      </div>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>確認刪除</DialogTitle>
            <DialogDescription>
              確定要刪除 <strong>{reportToDelete?.ticker}</strong> 於{" "}
              <strong>{reportToDelete?.analysis_date}</strong> 的分析報告嗎？
              <br />
              <span className="text-red-500">此操作無法復原。</span>
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteDialogOpen(false)}
              disabled={deleting}
            >
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={handleConfirmDelete}
              disabled={deleting}
            >
              {deleting ? "刪除中..." : "確認刪除"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
