/**
 * Agent Flow Diagram Component
 * Visualizes the complete data flow through all 12 agents
 */
"use client";

import { Card } from "@/components/ui/card";
import { 
  ArrowDown, 
  Database, 
  MessageSquare, 
  Newspaper, 
  DollarSign, 
  TrendingUp,
  TrendingDown,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Users,
  Target,
  BarChart3
} from "lucide-react";
import { useLanguage } from "@/contexts/LanguageContext";

export function AgentFlowDiagram() {
  const { t } = useLanguage();

  return (
    <div className="w-full max-w-7xl mx-auto space-y-6">
      {/* Data Sources Layer */}
      <div>
        <h3 className="text-center text-sm font-semibold text-gray-500 dark:text-gray-400 mb-4">
          📥 {t.flowDiagram.layer1}
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <DataSourceCard
            icon={<Database className="w-5 h-5" />}
            name="yfinance"
            description={t.flowDiagram.stockData}
            color="blue"
          />
          <DataSourceCard
            icon={<MessageSquare className="w-5 h-5" />}
            name="Reddit API"
            description={t.flowDiagram.socialSentiment}
            color="orange"
          />
          <DataSourceCard
            icon={<Newspaper className="w-5 h-5" />}
            name="RSS Feed"
            description={t.flowDiagram.newsInfo}
            color="green"
          />
          <DataSourceCard
            icon={<DollarSign className="w-5 h-5" />}
            name="Alpha Vantage / FinMind"
            description={t.flowDiagram.financialData}
            color="purple"
          />
        </div>
      </div>

      {/* Arrow */}
      <FlowArrow label={t.flowDiagram.dataFetch} color="blue" />

      {/* Analysts Layer - 4 agents */}
      <div>
        <h3 className="text-center text-sm font-semibold text-gray-500 dark:text-gray-400 mb-4">
          🤖 {t.flowDiagram.layer2}
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <AgentCard
            name={t.agents.market_analyst}
            icon={<BarChart3 className="w-5 h-5" />}
            gradient="from-blue-500 to-cyan-500"
            description={t.flowDiagram.technicalAnalysis}
            tasks={[t.flowDiagram.rsiIndicator, t.flowDiagram.macdMomentum, t.flowDiagram.priceTrend]}
          />
          <AgentCard
            name={t.agents.social_analyst}
            icon={<MessageSquare className="w-5 h-5" />}
            gradient="from-orange-500 to-red-500"
            description={t.flowDiagram.sentimentAnalysis}
            tasks={[t.flowDiagram.nlpSentiment, t.flowDiagram.discussionHeat, t.flowDiagram.investorConfidence]}
          />
          <AgentCard
            name={t.agents.news_analyst}
            icon={<Newspaper className="w-5 h-5" />}
            gradient="from-green-500 to-emerald-500"
            description={t.flowDiagram.newsAnalysis}
            tasks={[t.flowDiagram.newsSummary, t.flowDiagram.eventAssessment, t.flowDiagram.impactPrediction]}
          />
          <AgentCard
            name={t.agents.fundamentals_analyst}
            icon={<DollarSign className="w-5 h-5" />}
            gradient="from-purple-500 to-pink-500"
            description={t.flowDiagram.fundamentalsAnalysis}
            tasks={[t.flowDiagram.financialAnalysis, t.flowDiagram.valuationMetrics, t.flowDiagram.profitEvaluation]}
          />
        </div>
      </div>

      {/* Arrow */}
      <FlowArrow label={t.flowDiagram.reportIntegration} color="purple" />

      {/* Researchers Layer - 2 agents */}
      <div>
        <h3 className="text-center text-sm font-semibold text-gray-500 dark:text-gray-400 mb-4">
          🔍 {t.flowDiagram.layer3}
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-4xl mx-auto">
          <AgentCard
            name={t.agents.bull_researcher}
            icon={<TrendingUp className="w-5 h-5" />}
            gradient="from-green-500 to-emerald-500"
            description={t.flowDiagram.bullishResearch}
            tasks={[t.flowDiagram.positiveFactors, t.flowDiagram.growthOpportunities, t.flowDiagram.buyReasons]}
          />
          <AgentCard
            name={t.agents.bear_researcher}
            icon={<TrendingDown className="w-5 h-5" />}
            gradient="from-red-500 to-rose-500"
            description={t.flowDiagram.bearishResearch}
            tasks={[t.flowDiagram.negativeFactors, t.flowDiagram.riskAssessment, t.flowDiagram.sellReasons]}
          />
        </div>
      </div>

      {/* Arrow */}
      <FlowArrow label={t.flowDiagram.researchPrep} color="green" />

      {/* Research Manager */}
      <div className="max-w-md mx-auto">
        <ManagerCard
          name={t.flowDiagram.researchManager}
          icon={<Users className="w-6 h-6" />}
          gradient="from-indigo-500 to-purple-500"
          description={t.flowDiagram.integrateViews}
          tasks={[t.flowDiagram.balanceArguments, t.flowDiagram.comprehensiveAdvice, t.flowDiagram.preliminaryStrategy]}
        />
      </div>

      {/* Arrow */}
      <FlowArrow label={t.flowDiagram.riskDebate} color="orange" />

      {/* Risk Debators Layer - 3 agents */}
      <div>
        <h3 className="text-center text-sm font-semibold text-gray-500 dark:text-gray-400 mb-4">
          ⚖️ {t.flowDiagram.layer4}
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <AgentCard
            name={t.agents.aggressive_debator}
            icon={<ShieldAlert className="w-5 h-5" />}
            gradient="from-red-500 to-orange-500"
            description={t.flowDiagram.highRiskReward}
            tasks={[t.flowDiagram.aggressiveStrategy, t.flowDiagram.maximizeReturns, t.flowDiagram.calculatedRisk]}
          />
          <AgentCard
            name={t.agents.neutral_debator}
            icon={<Shield className="w-5 h-5" />}
            gradient="from-blue-500 to-indigo-500"
            description={t.flowDiagram.balancedRisk}
            tasks={[t.flowDiagram.prudentStrategy, t.flowDiagram.riskBalance, t.flowDiagram.rationalDecision]}
          />
          <AgentCard
            name={t.agents.conservative_debator}
            icon={<ShieldCheck className="w-5 h-5" />}
            gradient="from-green-500 to-teal-500"
            description={t.flowDiagram.lowRiskVol}
            tasks={[t.flowDiagram.conservativeStrategy, t.flowDiagram.capitalProtection, t.flowDiagram.riskReduction]}
          />
        </div>
      </div>

      {/* Arrow */}
      <FlowArrow label={t.flowDiagram.riskDebate} color="red" />

      {/* Risk Manager */}
      <div className="max-w-md mx-auto">
        <ManagerCard
          name={t.flowDiagram.riskManager}
          icon={<Shield className="w-6 h-6" />}
          gradient="from-red-500 to-pink-500"
          description={t.flowDiagram.integrateRisk}
          tasks={[t.flowDiagram.riskRating, t.flowDiagram.stopLossSettings, t.flowDiagram.finalRiskControl]}
        />
      </div>

      {/* Arrow */}
      <FlowArrow label={t.flowDiagram.finalDecision} color="green" />

      {/* Trader */}
      <div className="max-w-md mx-auto">
        <TraderCard
          name={t.flowDiagram.trader}
          icon={<Target className="w-7 h-7" />}
          gradient="from-blue-600 via-purple-600 to-pink-600"
          description={t.flowDiagram.executeTrade}
          outputs={[t.flowDiagram.tradeSignal, t.flowDiagram.targetPrice, t.flowDiagram.tradeQuantity, t.flowDiagram.riskParams]}
        />
      </div>

      {/* Final Arrow */}
      <FlowArrow label={t.flowDiagram.generateReport} color="blue" />

      {/* Output Layer */}
      <div>
        <h3 className="text-center text-sm font-semibold text-gray-500 dark:text-gray-400 mb-4">
          📊 {t.flowDiagram.finalOutput}
        </h3>
        <Card className="bg-gradient-to-r from-blue-500/10 via-purple-500/10 to-pink-500/10 dark:from-blue-600/20 dark:via-purple-600/20 dark:to-pink-600/20 border-2 border-dashed border-blue-300 dark:border-blue-700 p-6">
          <div className="text-center mb-4">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 text-white shadow-lg mb-3">
              <BarChart3 className="w-8 h-8" />
            </div>
            <h4 className="font-bold text-lg mb-2 gradient-text-primary">{t.flowDiagram.completeReportSet}</h4>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              {t.flowDiagram.comprehensiveSupport}
            </p>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <ReportSection
              title={t.flowDiagram.analystReports}
              items={[t.flowDiagram.technicalReport, t.flowDiagram.sentimentReport, t.flowDiagram.newsReport, t.flowDiagram.fundamentalsReport]}
              color="blue"
            />
            <ReportSection
              title={t.flowDiagram.researchReports}
              items={[t.flowDiagram.bullReport, t.flowDiagram.bearReport, t.flowDiagram.researchManagerReport]}
              color="green"
            />
            <ReportSection
              title={t.flowDiagram.riskTrading}
              items={[t.flowDiagram.aggressiveEval, t.flowDiagram.balancedEval, t.flowDiagram.conservativeEval, t.flowDiagram.riskManagerReport, t.flowDiagram.finalTradeDecision]}
              color="red"
            />
          </div>
        </Card>
      </div>
    </div>
  );
}

function DataSourceCard({
  icon,
  name,
  description,
  color,
}: {
  icon: React.ReactNode;
  name: string;
  description: string;
  color: "blue" | "orange" | "green" | "purple";
}) {
  const colorClasses = {
    blue: "from-blue-500 to-cyan-500 border-blue-300 dark:border-blue-700",
    orange: "from-orange-500 to-red-500 border-orange-300 dark:border-orange-700",
    green: "from-green-500 to-emerald-500 border-green-300 dark:border-green-700",
    purple: "from-purple-500 to-pink-500 border-purple-300 dark:border-purple-700",
  };

  return (
    <Card className={`p-3 hover-lift animate-slide-up border-2 ${colorClasses[color]}`}>
      <div className="flex flex-col items-center justify-center">
        <div className={`inline-flex items-center justify-center w-10 h-10 rounded-full bg-gradient-to-br ${colorClasses[color].split(' ')[0]} ${colorClasses[color].split(' ')[1]} text-white mb-2 shadow-lg`}>
          {icon}
        </div>
        <h4 className="font-semibold text-xs mb-0.5">{name}</h4>
        <p className="text-xs text-gray-600 dark:text-gray-400">{description}</p>
      </div>
    </Card>
  );
}

function AgentCard({
  name,
  icon,
  gradient,
  description,
  tasks,
}: {
  name: string;
  icon: React.ReactNode;
  gradient: string;
  description: string;
  tasks: string[];
}) {
  return (
    <Card className="p-4 hover-lift animate-scale-up relative overflow-hidden group">
      <div className={`absolute inset-0 bg-gradient-to-br ${gradient} opacity-0 group-hover:opacity-10 transition-opacity duration-300`} />
      
      <div className="relative z-10">
        <div className="text-center mb-3">
          <div className={`inline-flex items-center justify-center w-10 h-10 rounded-full bg-gradient-to-br ${gradient} text-white mb-2 shadow-lg`}>
            {icon}
          </div>
          <h4 className="font-bold text-sm mb-0.5">{name}</h4>
          <p className="text-xs text-gray-500 dark:text-gray-400">{description}</p>
        </div>

        <div className="space-y-0.5">
          {tasks.map((task, index) => (
            <div key={index} className="flex items-start text-xs text-gray-600 dark:text-gray-400">
              <span className="mr-1">•</span>
              <span>{task}</span>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}

function ManagerCard({
  name,
  icon,
  gradient,
  description,
  tasks,
}: {
  name: string;
  icon: React.ReactNode;
  gradient: string;
  description: string;
  tasks: string[];
}) {
  return (
    <Card className={`p-5 hover-lift relative overflow-hidden border-2 bg-gradient-to-br ${gradient} bg-opacity-5`}>
      <div className="text-center mb-3">
        <div className={`inline-flex items-center justify-center w-12 h-12 rounded-full bg-gradient-to-br ${gradient} text-white mb-2 shadow-xl`}>
          {icon}
        </div>
        <h4 className="font-bold text-base mb-1">{name}</h4>
        <p className="text-sm text-gray-600 dark:text-gray-400">{description}</p>
      </div>

      <div className="space-y-1">
        {tasks.map((task, index) => (
          <div key={index} className="flex items-start text-sm text-gray-700 dark:text-gray-300">
            <span className="mr-2">✓</span>
            <span>{task}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}

function TraderCard({
  name,
  icon,
  gradient,
  description,
  outputs,
}: {
  name: string;
  icon: React.ReactNode;
  gradient: string;
  description: string;
  outputs: string[];
}) {
  return (
    <Card className={`p-6 hover-lift relative overflow-hidden border-4 border-double bg-gradient-to-br ${gradient}`}>
      <div className="absolute inset-0 bg-white dark:bg-gray-900 opacity-95" />
      
      <div className="relative z-10">
        <div className="text-center mb-4">
          <div className={`inline-flex items-center justify-center w-14 h-14 rounded-full bg-gradient-to-br ${gradient} text-white mb-3 shadow-2xl animate-pulse-slow`}>
            {icon}
          </div>
          <h4 className="font-bold text-lg mb-1 bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">{name}</h4>
          <p className="text-sm text-gray-600 dark:text-gray-400 font-medium">{description}</p>
        </div>

        <div className="space-y-2 bg-gray-50 dark:bg-gray-800/50 p-3 rounded-lg">
          <div className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2">最終輸出:</div>
          {outputs.map((output, index) => (
            <div key={index} className="flex items-start text-sm font-medium text-gray-700 dark:text-gray-300">
              <span className="mr-2 text-green-600 dark:text-green-400">▸</span>
              <span>{output}</span>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}

function FlowArrow({ label, color }: { label: string; color: string }) {
  const colorClasses = {
    blue: "text-blue-500 dark:text-blue-400",
    purple: "text-purple-500 dark:text-purple-400",
    green: "text-green-500 dark:text-green-400",
    orange: "text-orange-500 dark:text-orange-400",
    red: "text-red-500 dark:text-red-400",
  };

  return (
    <div className="flex justify-center">
      <div className="flex flex-col items-center">
        <div className="text-xs text-gray-500 dark:text-gray-400 mb-1 font-medium">{label}</div>
        <ArrowDown className={`w-7 h-7 ${colorClasses[color as keyof typeof colorClasses]} animate-bounce`} />
      </div>
    </div>
  );
}

function ReportSection({
  title,
  items,
  color,
}: {
  title: string;
  items: string[];
  color: "blue" | "green" | "red";
}) {
  const colorClasses = {
    blue: "bg-blue-50 dark:bg-blue-950/30 border-blue-200 dark:border-blue-800",
    green: "bg-green-50 dark:bg-green-950/30 border-green-200 dark:border-green-800",
    red: "bg-red-50 dark:bg-red-950/30 border-red-200 dark:border-red-800",
  };

  return (
    <div className={`p-3 rounded-lg border ${colorClasses[color]}`}>
      <h5 className="font-semibold text-xs mb-2 text-gray-800 dark:text-gray-200">{title}</h5>
      <div className="space-y-1">
        {items.map((item, index) => (
          <div key={index} className="text-xs text-gray-600 dark:text-gray-400 flex items-start">
            <span className="mr-1">•</span>
            <span>{item}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
