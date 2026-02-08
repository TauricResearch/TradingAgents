import { useState, useEffect, useRef, useCallback } from 'react';
import { api } from '../services/api';
import type { FullPipelineData } from '../types/pipeline';

interface UsePipelinePollingResult {
  pipelineData: FullPipelineData | null;
  isLive: boolean;
  lastUpdated: Date | null;
  error: string | null;
}

/**
 * Polls pipeline data during active analysis.
 * When isAnalyzing is true, fetches fresh data every pollIntervalMs.
 * When isAnalyzing is false, stops polling.
 */
export function usePipelinePolling(
  symbol: string | undefined,
  date: string | undefined,
  isAnalyzing: boolean,
  initialData: FullPipelineData | null = null,
  pollIntervalMs: number = 5000
): UsePipelinePollingResult {
  const [pipelineData, setPipelineData] = useState<FullPipelineData | null>(initialData);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Update from initial data when it changes externally
  useEffect(() => {
    if (initialData) {
      setPipelineData(initialData);
    }
  }, [initialData]);

  const fetchData = useCallback(async () => {
    if (!symbol || !date) return;
    try {
      const data = await api.getPipelineData(date, symbol, true);
      setPipelineData(data);
      setLastUpdated(new Date());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch pipeline data');
    }
  }, [symbol, date]);

  useEffect(() => {
    if (isAnalyzing && symbol && date) {
      // Fetch immediately when analysis starts
      fetchData();

      // Then poll at interval
      intervalRef.current = setInterval(fetchData, pollIntervalMs);

      return () => {
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
      };
    } else {
      // Stop polling when not analyzing
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    }
  }, [isAnalyzing, symbol, date, fetchData, pollIntervalMs]);

  // Do a final fetch when analysis completes
  useEffect(() => {
    if (!isAnalyzing && symbol && date && lastUpdated) {
      // Small delay to ensure backend has saved final state
      const timeout = setTimeout(fetchData, 1000);
      return () => clearTimeout(timeout);
    }
  }, [isAnalyzing]);

  return {
    pipelineData,
    isLive: isAnalyzing,
    lastUpdated,
    error,
  };
}
