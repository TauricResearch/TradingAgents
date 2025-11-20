"use client";

import { useParams } from "next/navigation";
import { useEffect, useState, useCallback } from "react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { StreamUpdate, AgentStatusType } from "@/lib/types";
import { getAnalysisStatus, getAnalysisResults } from "@/lib/api";
import AgentProgress from "@/components/AgentProgress";
import ReportViewer from "@/components/ReportViewer";

export default function AnalysisPage() {
  const params = useParams();
  const analysisId = params.id as string;

  const [status, setStatus] = useState<string>("running");
  const [statusData, setStatusData] = useState<{ ticker?: string; analysis_date?: string } | null>(null);
  const [agentStatuses, setAgentStatuses] = useState<Record<string, AgentStatusType>>({});
  const [reports, setReports] = useState<Record<string, string>>({});
  const [messages, setMessages] = useState<Array<{ type: string; content: string; timestamp: string }>>([]);
  const [finalResults, setFinalResults] = useState<any>(null);

  const handleStreamUpdate = useCallback((update: StreamUpdate) => {
    switch (update.type) {
      case "status":
        if (update.data.status) {
          setStatus(update.data.status);
        }
        break;
      case "message":
        setMessages((prev) => [
          ...prev,
          {
            type: update.data.type,
            content: update.data.content,
            timestamp: update.timestamp,
          },
        ]);
        break;
      case "report":
        setReports((prev) => ({
          ...prev,
          [update.data.section_name]: update.data.content,
        }));
        break;
      case "agent_status":
        setAgentStatuses((prev) => ({
          ...prev,
          [update.data.agent]: update.data.status,
        }));
        break;
      case "final_decision":
        setStatus("completed");
        break;
    }
  }, []);

  const { isConnected } = useWebSocket(analysisId, handleStreamUpdate);

  useEffect(() => {
    // Poll for status updates
    const interval = setInterval(async () => {
      try {
        const statusData = await getAnalysisStatus(analysisId);
        setStatus(statusData.status);
        setStatusData({ ticker: statusData.ticker, analysis_date: statusData.analysis_date });

        if (statusData.status === "completed" && !finalResults) {
          const results = await getAnalysisResults(analysisId);
          setFinalResults(results);
          if (results.final_state) {
            setReports({
              market_report: results.final_state.market_report || "",
              sentiment_report: results.final_state.sentiment_report || "",
              news_report: results.final_state.news_report || "",
              fundamentals_report: results.final_state.fundamentals_report || "",
              trader_investment_plan: results.final_state.trader_investment_plan || "",
              final_trade_decision: results.final_state.final_trade_decision || "",
            });
          }
        }
      } catch (error) {
        console.error("Failed to fetch status:", error);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [analysisId, finalResults]);

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="mb-6">
          <h1 className="text-3xl font-bold mb-2">
            Analysis: {statusData?.ticker || "Loading..."} - {statusData?.analysis_date || ""}
          </h1>
          <div className="flex items-center space-x-4">
            <span className={`px-3 py-1 rounded-full text-sm ${status === "completed" ? "bg-green-100 text-green-800" :
              status === "running" ? "bg-blue-100 text-blue-800" :
                "bg-gray-100 text-gray-800"
              }`}>
              {status}
            </span>
            <span className={`px-3 py-1 rounded-full text-sm ${isConnected ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800"
              }`}>
              {isConnected ? "Connected" : "Disconnected"}
            </span>
          </div>
        </div>

        <div className="grid lg:grid-cols-3 gap-6">
          <div className="lg:col-span-1">
            <AgentProgress agentStatuses={agentStatuses} />
          </div>

          <div className="lg:col-span-2">
            {Object.keys(reports).length > 0 && (
              <div className="mb-6">
                <ReportViewer reports={reports} />
              </div>
            )}

            {messages.length > 0 && (
              <div className="bg-white rounded-lg shadow p-6">
                <h2 className="text-xl font-bold mb-4">Messages</h2>
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {messages.slice(-20).map((msg, idx) => (
                    <div key={idx} className="text-sm border-b pb-2">
                      <span className="text-gray-500">{msg.timestamp}</span>
                      <span className="ml-2 font-medium">{msg.type}:</span>
                      <span className="ml-2">{msg.content}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

