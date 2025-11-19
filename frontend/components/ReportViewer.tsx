"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface ReportViewerProps {
  reports: Record<string, string>;
}

const REPORT_TITLES: Record<string, string> = {
  market_report: "Market Analysis",
  sentiment_report: "Social Sentiment",
  news_report: "News Analysis",
  fundamentals_report: "Fundamentals Analysis",
  trader_investment_plan: "Trading Team Plan",
  final_trade_decision: "Final Trade Decision",
};

export default function ReportViewer({ reports }: ReportViewerProps) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const toggleSection = (section: string) => {
    setExpanded((prev) => ({
      ...prev,
      [section]: !prev[section],
    }));
  };

  return (
    <div className="space-y-4">
      {Object.entries(reports).map(([section, content]) => (
        <div key={section} className="bg-white rounded-lg shadow">
          <button
            onClick={() => toggleSection(section)}
            className="w-full px-6 py-4 text-left flex items-center justify-between hover:bg-gray-50 rounded-t-lg"
          >
            <h3 className="text-lg font-semibold">
              {REPORT_TITLES[section] || section}
            </h3>
            <span className="text-gray-500">
              {expanded[section] ? "▼" : "▶"}
            </span>
          </button>
          {expanded[section] && (
            <div className="px-6 py-4 border-t">
              <div className="prose max-w-none">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {content}
                </ReactMarkdown>
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

