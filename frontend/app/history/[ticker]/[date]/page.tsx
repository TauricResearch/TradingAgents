"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { getHistoricalAnalysis } from "@/lib/api";
import ReportViewer from "@/components/ReportViewer";

export default function HistoricalAnalysisPage() {
  const params = useParams();
  const ticker = params.ticker as string;
  const date = params.date as string;

  const [reports, setReports] = useState<Record<string, string>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadAnalysis() {
      try {
        const data = await getHistoricalAnalysis(ticker, date);
        setReports(data.reports || {});
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load analysis");
      } finally {
        setIsLoading(false);
      }
    }
    loadAnalysis();
  }, [ticker, date]);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading analysis...</p>
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
        <h1 className="text-3xl font-bold mb-2">
          {ticker} - {date}
        </h1>

        {Object.keys(reports).length === 0 ? (
          <div className="bg-white rounded-lg shadow p-8 text-center">
            <p className="text-gray-600">No reports available for this analysis.</p>
          </div>
        ) : (
          <ReportViewer reports={reports} />
        )}
      </div>
    </div>
  );
}

