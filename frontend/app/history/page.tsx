"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listHistoricalAnalyses } from "@/lib/api";
import { HistoricalAnalysisSummary } from "@/lib/types";

export default function HistoryPage() {
  const [analyses, setAnalyses] = useState<HistoricalAnalysisSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadAnalyses() {
      try {
        const data = await listHistoricalAnalyses();
        setAnalyses(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load analyses");
      } finally {
        setIsLoading(false);
      }
    }
    loadAnalyses();
  }, []);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading analyses...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-600">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <h1 className="text-3xl font-bold mb-6">Analysis History</h1>

        {analyses.length === 0 ? (
          <div className="bg-white rounded-lg shadow p-8 text-center">
            <p className="text-gray-600">No historical analyses found.</p>
          </div>
        ) : (
          <div className="grid gap-4">
            {analyses.map((analysis) => (
              <Link
                key={`${analysis.ticker}-${analysis.analysis_date}`}
                href={`/history/${analysis.ticker}/${analysis.analysis_date}`}
                className="bg-white rounded-lg shadow p-6 hover:shadow-lg transition-shadow"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-xl font-semibold">{analysis.ticker}</h2>
                    <p className="text-gray-600">{analysis.analysis_date}</p>
                  </div>
                  <div className="flex items-center space-x-2">
                    {analysis.has_results && (
                      <span className="px-3 py-1 bg-green-100 text-green-800 rounded-full text-sm">
                        Has Results
                      </span>
                    )}
                    <span className="text-gray-400">→</span>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

