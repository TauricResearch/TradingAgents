/**
 * History page - browse saved analysis reports
 */
"use client";

import { useState, useEffect } from "react";
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
import { Trash2, Eye, RefreshCw, TrendingUp, Cloud, CloudOff } from "lucide-react";
import {
  getReportsByMarketType,
  deleteReport,
  getReportCountByMarketType,
  type SavedReport,
} from "@/lib/reports-db";
import { getCloudReports, deleteCloudReport, isCloudSyncEnabled } from "@/lib/user-api";
import { LoginPrompt } from "@/components/auth/login-button";

// Market type labels
const MARKET_LABELS = {
  us: { label: "🇺🇸 美股", description: "美國股市分析報告" },
  twse: { label: "🇹🇼 上市", description: "台灣證券交易所上市股票" },
  tpex: { label: "🇹🇼 上櫃/興櫃", description: "台灣櫃買中心上櫃/興櫃股票" },
};

// Helper function to extract decision from trader report
const extractDecisionFromReport = (report: SavedReport): { action: string; color: string } => {
  // First try the decision.action field
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
  
  // Fallback: try to extract from trader_investment_plan
  const traderReport = report.result.reports?.trader_investment_plan;
  if (traderReport) {
    const text = traderReport.toLowerCase();
    
    // Look for Chinese decision keywords first
    if (text.includes("最終交易提案：買入") || text.includes("建議：買入")) {
      return { action: "買入", color: "text-green-600" };
    }
    if (text.includes("最終交易提案：賣出") || text.includes("建議：賣出")) {
      return { action: "賣出", color: "text-red-600" };
    }
    if (text.includes("最終交易提案：持有") || text.includes("建議：持有")) {
      return { action: "持有", color: "text-yellow-600" };
    }
    
    // Look for English keywords
    if (text.includes("buy") && !text.includes("sell")) {
      return { action: "買入 (BUY)", color: "text-green-600" };
    }
    if (text.includes("sell") && !text.includes("buy")) {
      return { action: "賣出 (SELL)", color: "text-red-600" };
    }
    if (text.includes("hold")) {
      return { action: "持有 (HOLD)", color: "text-yellow-600" };
    }
  }
  
  // Fallback: try final_trade_decision
  const finalDecision = report.result.reports?.final_trade_decision;
  if (finalDecision) {
    const text = finalDecision.toLowerCase();
    if (text.includes("buy") || text.includes("買入")) {
      return { action: "買入", color: "text-green-600" };
    }
    if (text.includes("sell") || text.includes("賣出")) {
      return { action: "賣出", color: "text-red-600" };
    }
    if (text.includes("hold") || text.includes("持有")) {
      return { action: "持有", color: "text-yellow-600" };
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

  // Load reports when tab changes or auth state changes
  useEffect(() => {
    loadReports();
  }, [activeTab, isAuthenticated]);

  // Load counts on mount or auth change
  useEffect(() => {
    loadCounts();
  }, [isAuthenticated]);

  const loadReports = async () => {
    setLoading(true);
    try {
      // If authenticated, try to load from cloud first
      if (isAuthenticated && isCloudSyncEnabled()) {
        const cloudReports = await getCloudReports();
        if (cloudReports.length > 0) {
          // Convert cloud reports to SavedReport format and filter by market type
          const filtered = cloudReports
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
          setReports(filtered);
          setIsCloudData(true);
          return;
        }
      }
      
      // Fall back to local IndexedDB
      const data = await getReportsByMarketType(activeTab);
      setReports(data);
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
      if (isAuthenticated && isCloudSyncEnabled()) {
        const cloudReports = await getCloudReports();
        const cloudCounts = {
          us: cloudReports.filter(r => r.market_type === "us").length,
          twse: cloudReports.filter(r => r.market_type === "twse").length,
          tpex: cloudReports.filter(r => r.market_type === "tpex").length,
        };
        if (cloudReports.length > 0) {
          setCounts(cloudCounts);
          return;
        }
      }
      
      const data = await getReportCountByMarketType();
      setCounts(data);
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
      // If this is cloud data, delete from cloud
      const cloudId = (reportToDelete as any).cloudId;
      if (isCloudData && cloudId) {
        await deleteCloudReport(cloudId);
      } else if (reportToDelete.id) {
        // Delete from local IndexedDB
        await deleteReport(reportToDelete.id);
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
                            <CardFooter className="flex gap-2">
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
