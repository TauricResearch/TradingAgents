/**
 * Pending Task Recovery Component
 * Checks for pending tasks on page load and allows user to recover them
 */
"use client";

import { useState, useEffect, useCallback } from "react";
import { RefreshCw, Loader2, CheckCircle, XCircle, AlertCircle } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { getPendingTask, clearPendingTask, isPendingTaskValid, type PendingTask } from "@/lib/pending-task";
import { saveReport, checkDuplicateReport } from "@/lib/reports-db";
import { saveCloudReport, isCloudSyncEnabled } from "@/lib/user-api";
import { useAuth } from "@/contexts/auth-context";

export function PendingTaskRecovery() {
  const [pendingTask, setPendingTask] = useState<PendingTask | null>(null);
  const [status, setStatus] = useState<'checking' | 'found' | 'recovering' | 'success' | 'failed' | 'not_found'>('checking');
  const [message, setMessage] = useState<string>("");
  const { isAuthenticated } = useAuth();

  useEffect(() => {
    // Check for pending tasks on mount
    const task = getPendingTask();
    
    if (!task) {
      setStatus('not_found');
      return;
    }
    
    if (!isPendingTaskValid(task)) {
      // Task is too old, clear it
      clearPendingTask();
      setStatus('not_found');
      return;
    }
    
    setPendingTask(task);
    setStatus('found');
  }, []);

  const handleRecover = useCallback(async () => {
    if (!pendingTask) return;
    
    setStatus('recovering');
    setMessage("正在檢查任務狀態...");
    
    try {
      // Check task status
      const taskStatus = await api.getTaskStatus(pendingTask.taskId);
      
      if (taskStatus.status === 'completed' && taskStatus.result) {
        setMessage("分析已完成！正在儲存報告...");
        
        // Check for duplicate
        const duplicate = await checkDuplicateReport(
          taskStatus.result.ticker,
          taskStatus.result.analysis_date
        );
        
        if (duplicate) {
          setMessage("報告已存在於歷史記錄中");
          clearPendingTask();
          setStatus('success');
          return;
        }
        
        // Save to local IndexedDB
        await saveReport(
          taskStatus.result.ticker,
          pendingTask.marketType,
          taskStatus.result.analysis_date,
          taskStatus.result,
          pendingTask.taskId
        );
        
        // If authenticated, also save to cloud
        if (isAuthenticated && isCloudSyncEnabled()) {
          await saveCloudReport({
            ticker: taskStatus.result.ticker,
            market_type: pendingTask.marketType,
            analysis_date: taskStatus.result.analysis_date,
            result: taskStatus.result,
          });
        }
        
        clearPendingTask();
        setMessage("報告已成功儲存到歷史記錄！");
        setStatus('success');
        
      } else if (taskStatus.status === 'failed') {
        clearPendingTask();
        setMessage("分析任務失敗");
        setStatus('failed');
        
      } else if (taskStatus.status === 'running' || taskStatus.status === 'pending') {
        setMessage(`分析仍在進行中... (${taskStatus.progress || '處理中'})`);
        // Poll again after a delay
        setTimeout(() => {
          handleRecover();
        }, 3000);
        
      } else {
        // Unknown status, clear it
        clearPendingTask();
        setMessage("無法恢復任務");
        setStatus('failed');
      }
      
    } catch (error: any) {
      console.error("Recovery failed:", error);
      
      // If it's a 404, the task doesn't exist anymore
      if (error?.response?.status === 404) {
        clearPendingTask();
        setMessage("任務已過期或不存在");
        setStatus('failed');
      } else {
        setMessage(`恢復失敗: ${error.message || '未知錯誤'}`);
        setStatus('failed');
      }
    }
  }, [pendingTask, isAuthenticated]);

  const handleDismiss = () => {
    clearPendingTask();
    setStatus('not_found');
    setPendingTask(null);
  };

  // Don't render if no pending task or already checked
  if (status === 'checking' || status === 'not_found') {
    return null;
  }

  const bgColor = status === 'success' ? 'bg-green-500/10 border-green-500' : 
                  status === 'failed' ? 'bg-red-500/10 border-red-500' : 
                  'bg-yellow-500/10 border-yellow-500';

  const Icon = status === 'success' ? CheckCircle : 
               status === 'failed' ? XCircle : 
               status === 'recovering' ? Loader2 : AlertCircle;

  const iconColor = status === 'success' ? 'text-green-500' : 
                    status === 'failed' ? 'text-red-500' : 
                    'text-yellow-500';

  return (
    <Card className={`mb-4 border-2 ${bgColor}`}>
      <CardContent className="pt-4">
        <div className="flex items-start gap-3">
          <Icon className={`h-5 w-5 mt-0.5 ${iconColor} ${status === 'recovering' ? 'animate-spin' : ''}`} />
          <div className="flex-1">
            <p className="font-semibold">
              {status === 'found' && "發現未完成的分析任務"}
              {status === 'recovering' && "正在恢復分析結果..."}
              {status === 'success' && "報告恢復成功！"}
              {status === 'failed' && "恢復失敗"}
            </p>
            
            {status === 'found' && pendingTask && (
              <div className="mt-2 space-y-2">
                <p className="text-sm text-muted-foreground">
                  發現 <span className="font-bold">{pendingTask.ticker}</span> 的分析任務 
                  (開始於 {new Date(pendingTask.startedAt).toLocaleString('zh-TW')})
                </p>
                <div className="flex gap-2">
                  <Button size="sm" onClick={handleRecover} className="gap-1">
                    <RefreshCw className="h-3 w-3" />
                    恢復並儲存
                  </Button>
                  <Button size="sm" variant="outline" onClick={handleDismiss}>
                    忽略
                  </Button>
                </div>
              </div>
            )}
            
            {status === 'recovering' && (
              <p className="text-sm text-muted-foreground mt-1">{message}</p>
            )}
            
            {(status === 'success' || status === 'failed') && (
              <div className="mt-2 space-y-2">
                <p className="text-sm text-muted-foreground">{message}</p>
                <Button size="sm" variant="outline" onClick={handleDismiss}>
                  關閉
                </Button>
              </div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
