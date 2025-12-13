/**
 * Custom hook for trading analysis with async task support
 */
"use client";

import { useState, useEffect, useRef } from "react";
import { api } from "@/lib/api";
import type { AnalysisRequest, AnalysisResponse } from "@/lib/types";

export function useAnalysis() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | {
    error: string;
    error_type?: string;
    retry_after?: number;
    quota_limit?: number;
  } | null>(null);
  const [result, setResult] = useState<AnalysisResponse | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [progress, setProgress] = useState<string | null>(null);
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Poll for task status
  const pollTaskStatus = async (id: string) => {
    try {
      const status = await api.getTaskStatus(id);
      
      // Update progress
      if (status.progress) {
        setProgress(status.progress);
      }
      
      // Check if completed
      if (status.status === "completed") {
        if (status.result) {
          setResult(status.result);
        }
        setLoading(false);
        setProgress(null);
        
        // Clear pending task since it's completed
        const { clearPendingTask } = await import('@/lib/pending-task');
        clearPendingTask();
        
        // Stop polling
        if (pollingIntervalRef.current) {
          clearInterval(pollingIntervalRef.current);
          pollingIntervalRef.current = null;
        }
        return true;
      }
      
      // Check if failed
      if (status.status === "failed") {
        // Check if we have structured error data from result
        if (status.result && status.result.error) {
          setError({
            error: status.result.error,
            error_type: status.result.error_type,
            retry_after: status.result.retry_after,
            quota_limit: status.result.quota_limit,
          });
        } else {
          setError(status.error || "Analysis failed");
        }
        setLoading(false);
        setProgress(null);
        
        // Clear pending task since it failed
        const { clearPendingTask } = await import('@/lib/pending-task');
        clearPendingTask();
        
        // Stop polling
        if (pollingIntervalRef.current) {
          clearInterval(pollingIntervalRef.current);
          pollingIntervalRef.current = null;
        }
        return true;
      }
      
      return false; // Still running
    } catch (err: any) {
      console.error("Error polling task status:", err);
      // Don't stop polling on temporary errors
      return false;
    }
  };

  // Start polling
  const startPolling = (id: string) => {
    // Clear any existing interval
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
    }
    
    // Poll every 3 seconds
    pollingIntervalRef.current = setInterval(async () => {
      await pollTaskStatus(id);
    }, 3000);
    
    // Also poll immediately
    pollTaskStatus(id);
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
        pollingIntervalRef.current = null;
      }
    };
  }, []);

  const runAnalysis = async (request: AnalysisRequest) => {
    setLoading(true);
    setError(null);
    setResult(null);
    setProgress("Submitting analysis request...");

    try {
      // Start analysis task
      const taskResponse = await api.runAnalysis(request);
      setTaskId(taskResponse.task_id);
      setProgress("Analysis started, waiting for results...");
      
      // Save pending task to localStorage for recovery if page closes
      const { savePendingTask } = await import('@/lib/pending-task');
      savePendingTask({
        taskId: taskResponse.task_id,
        ticker: request.ticker,
        marketType: request.market_type || 'us',
        analysisDate: request.analysis_date,
        startedAt: new Date().toISOString(),
      });
      
      // Start polling for status
      startPolling(taskResponse.task_id);
      
      return taskResponse;
    } catch (err: any) {
      const errorMessage =
        err.response?.data?.detail || err.message || "Failed to start analysis";
      setError(errorMessage);
      setLoading(false);
      setProgress(null);
      throw err;
    }
  };

  const reset = () => {
    // Stop polling
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
    
    setLoading(false);
    setError(null);
    setResult(null);
    setTaskId(null);
    setProgress(null);
  };

  return {
    runAnalysis,
    loading,
    error,
    result,
    taskId,
    progress,
    reset,
  };
}
