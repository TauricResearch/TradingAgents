/**
 * Analyst reports display component
 */
"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { Reports } from "@/lib/types";
import { useLanguage } from "@/contexts/LanguageContext";

interface AnalystReportProps {
  reports: Reports;
}

export function AnalystReport({ reports }: AnalystReportProps) {
  const { t } = useLanguage();

  const hasAnalystReports =
    reports.market_report ||
    reports.sentiment_report ||
    reports.news_report ||
    reports.fundamentals_report;

  const hasResearchReports =
    reports.investment_debate_state?.bull_history ||
    reports.investment_debate_state?.bear_history ||
    reports.investment_debate_state?.judge_decision;

  const hasRiskReports =
    reports.risk_debate_state?.risky_history ||
    reports.risk_debate_state?.safe_history ||
    reports.risk_debate_state?.neutral_history;

  if (!hasAnalystReports && !hasResearchReports && !hasRiskReports) {
    return null;
  }

  return (
    <Card className="shadow-lg hover-lift animate-scale-up">
      <CardHeader>
        <CardTitle>{t.results.title}</CardTitle>
        <CardDescription>{t.home.professionalAgentsDesc}</CardDescription>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="analysts" className="w-full">
          <TabsList className="grid w-full grid-cols-4">
            <TabsTrigger value="analysts">{t.tabs.analysts}</TabsTrigger>
            <TabsTrigger value="research">{t.tabs.researchers}</TabsTrigger>
            <TabsTrigger value="trader">{t.tabs.trader}</TabsTrigger>
            <TabsTrigger value="risk">{t.tabs.risk}</TabsTrigger>
          </TabsList>

          <TabsContent value="analysts" className="space-y-4">
            {reports.market_report && (
              <ReportSection title={t.agents.market_analyst} content={reports.market_report} />
            )}
            {reports.sentiment_report && (
              <ReportSection title={t.agents.social_analyst} content={reports.sentiment_report} />
            )}
            {reports.news_report && (
              <ReportSection title={t.agents.news_analyst} content={reports.news_report} />
            )}
            {reports.fundamentals_report && (
              <ReportSection title={t.agents.fundamentals_analyst} content={reports.fundamentals_report} />
            )}
          </TabsContent>

          <TabsContent value="research" className="space-y-4">
            {reports.investment_debate_state?.bull_history && (
              <ReportSection
                title={t.agents.bull_researcher}
                content={reports.investment_debate_state.bull_history}
              />
            )}
            {reports.investment_debate_state?.bear_history && (
              <ReportSection
                title={t.agents.bear_researcher}
                content={reports.investment_debate_state.bear_history}
              />
            )}
            {reports.investment_debate_state?.judge_decision && (
              <ReportSection
                title={t.agents.research_manager}
                content={reports.investment_debate_state.judge_decision}
              />
            )}
          </TabsContent>

          <TabsContent value="trader" className="space-y-4">
            {reports.trader_investment_plan && (
              <ReportSection title={t.agents.trader} content={reports.trader_investment_plan} />
            )}
          </TabsContent>

          <TabsContent value="risk" className="space-y-4">
            {reports.risk_debate_state?.risky_history && (
              <ReportSection
                title={t.agents.aggressive_debator}
                content={reports.risk_debate_state.risky_history}
              />
            )}
            {reports.risk_debate_state?.safe_history && (
              <ReportSection
                title={t.agents.conservative_debator}
                content={reports.risk_debate_state.safe_history}
              />
            )}
            {reports.risk_debate_state?.neutral_history && (
              <ReportSection
                title={t.agents.neutral_debator}
                content={reports.risk_debate_state.neutral_history}
              />
            )}
            {reports.risk_debate_state?.judge_decision && (
              <ReportSection
                title={t.agents.risk_manager}
                content={reports.risk_debate_state.judge_decision}
              />
            )}
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}

function ReportSection({ title, content }: { title: string; content: string }) {
  return (
    <div className="border rounded-lg p-4 bg-gradient-to-br from-blue-50/50 to-purple-50/50 dark:from-blue-900/10 dark:to-purple-900/10 hover:shadow-md transition-shadow">
      <h3 className="font-semibold text-lg mb-2">{title}</h3>
      <div className="prose prose-sm xl:prose-base dark:prose-invert max-w-none overflow-x-auto prose-table:border-collapse prose-table:w-full prose-td:border prose-td:border-gray-300 dark:prose-td:border-gray-600 prose-td:p-2 prose-th:border prose-th:border-gray-300 dark:prose-th:border-gray-600 prose-th:p-2 prose-th:bg-gray-100 dark:prose-th:bg-gray-800">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {content}
        </ReactMarkdown>
      </div>
    </div>
  );
}
