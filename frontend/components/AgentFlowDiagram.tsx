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

export function AgentFlowDiagram() {
  return (
    <div className="w-full max-w-7xl mx-auto space-y-6">
      {/* Data Sources Layer */}
      <div>
        <h3 className="text-center text-sm font-semibold text-gray-500 dark:text-gray-400 mb-4">
          📥 第一層：資料來源
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <DataSourceCard
            icon={<Database className="w-5 h-5" />}
            name="yfinance"
            description="股價數據"
            color="blue"
          />
          <DataSourceCard
            icon={<MessageSquare className="w-5 h-5" />}
            name="Reddit API"
            description="社群情緒"
            color="orange"
          />
          <DataSourceCard
            icon={<Newspaper className="w-5 h-5" />}
            name="RSS Feed"
            description="新聞資訊"
            color="green"
          />
          <DataSourceCard
            icon={<DollarSign className="w-5 h-5" />}
            name="Alpha Vantage"
            description="財務數據"
            color="purple"
          />
        </div>
      </div>

      {/* Arrow */}
      <FlowArrow label="資料擷取與清理" color="blue" />

      {/* Analysts Layer - 4 agents */}
      <div>
        <h3 className="text-center text-sm font-semibold text-gray-500 dark:text-gray-400 mb-4">
          🤖 第二層：分析師代理 (4位)
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <AgentCard
            name="市場分析師"
            icon={<BarChart3 className="w-5 h-5" />}
            gradient="from-blue-500 to-cyan-500"
            description="技術面分析"
            tasks={["RSI 指標", "MACD 動能", "價格走勢"]}
          />
          <AgentCard
            name="社群媒體分析師"
            icon={<MessageSquare className="w-5 h-5" />}
            gradient="from-orange-500 to-red-500"
            description="情緒面分析"
            tasks={["NLP 情緒", "討論熱度", "投資者信心"]}
          />
          <AgentCard
            name="新聞分析師"
            icon={<Newspaper className="w-5 h-5" />}
            gradient="from-green-500 to-emerald-500"
            description="新聞面分析"
            tasks={["新聞摘要", "事件評估", "影響預測"]}
          />
          <AgentCard
            name="基本面分析師"
            icon={<DollarSign className="w-5 h-5" />}
            gradient="from-purple-500 to-pink-500"
            description="基本面分析"
            tasks={["財報分析", "估值指標", "盈利評估"]}
          />
        </div>
      </div>

      {/* Arrow */}
      <FlowArrow label="分析報告整合" color="purple" />

      {/* Researchers Layer - 2 agents */}
      <div>
        <h3 className="text-center text-sm font-semibold text-gray-500 dark:text-gray-400 mb-4">
          🔍 第三層：研究員代理 (2位)
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-4xl mx-auto">
          <AgentCard
            name="多頭研究員"
            icon={<TrendingUp className="w-5 h-5" />}
            gradient="from-green-500 to-emerald-500"
            description="看多觀點研究"
            tasks={["正面因素分析", "成長機會評估", "買入理由整理"]}
          />
          <AgentCard
            name="空頭研究員"
            icon={<TrendingDown className="w-5 h-5" />}
            gradient="from-red-500 to-rose-500"
            description="看空觀點研究"
            tasks={["負面因素分析", "風險評估", "賣出理由整理"]}
          />
        </div>
      </div>

      {/* Arrow */}
      <FlowArrow label="研究整合與辯論準備" color="green" />

      {/* Research Manager */}
      <div className="max-w-md mx-auto">
        <ManagerCard
          name="研究經理"
          icon={<Users className="w-6 h-6" />}
          gradient="from-indigo-500 to-purple-500"
          description="整合多空研究觀點"
          tasks={["平衡雙方論點", "綜合投資建議", "制定初步策略"]}
        />
      </div>

      {/* Arrow */}
      <FlowArrow label="進入風險辯論階段" color="orange" />

      {/* Risk Debators Layer - 3 agents */}
      <div>
        <h3 className="text-center text-sm font-semibold text-gray-500 dark:text-gray-400 mb-4">
          ⚖️ 第四層：風險辯論者 (3位)
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <AgentCard
            name="激進辯論者"
            icon={<ShieldAlert className="w-5 h-5" />}
            gradient="from-red-500 to-orange-500"
            description="高風險高報酬"
            tasks={["積極投資策略", "最大化收益", "承擔計算風險"]}
          />
          <AgentCard
            name="中立辯論者"
            icon={<Shield className="w-5 h-5" />}
            gradient="from-blue-500 to-indigo-500"
            description="平衡風險報酬"
            tasks={["穩健投資策略", "風險平衡", "理性決策"]}
          />
          <AgentCard
            name="保守辯論者"
            icon={<ShieldCheck className="w-5 h-5" />}
            gradient="from-green-500 to-teal-500"
            description="低風險低波動"
            tasks={["保守投資策略", "資本保護", "降低風險"]}
          />
        </div>
      </div>

      {/* Arrow */}
      <FlowArrow label="風險評估與管理" color="red" />

      {/* Risk Manager */}
      <div className="max-w-md mx-auto">
        <ManagerCard
          name="風險經理"
          icon={<Shield className="w-6 h-6" />}
          gradient="from-red-500 to-pink-500"
          description="整合風險辯論結果"
          tasks={["風險等級評定", "止損止盈設定", "最終風險控制"]}
        />
      </div>

      {/* Arrow */}
      <FlowArrow label="制定最終交易決策" color="green" />

      {/* Trader */}
      <div className="max-w-md mx-auto">
        <TraderCard
          name="交易員"
          icon={<Target className="w-7 h-7" />}
          gradient="from-blue-600 via-purple-600 to-pink-600"
          description="執行最終交易決策"
          outputs={["交易訊號 (BUY/SELL/HOLD)", "目標價位", "交易數量", "風險參數"]}
        />
      </div>

      {/* Final Arrow */}
      <FlowArrow label="生成完整投資報告" color="blue" />

      {/* Output Layer */}
      <div>
        <h3 className="text-center text-sm font-semibold text-gray-500 dark:text-gray-400 mb-4">
          📊 最終輸出：12 份詳細報告
        </h3>
        <Card className="bg-gradient-to-r from-blue-500/10 via-purple-500/10 to-pink-500/10 dark:from-blue-600/20 dark:via-purple-600/20 dark:to-pink-600/20 border-2 border-dashed border-blue-300 dark:border-blue-700 p-6">
          <div className="text-center mb-4">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 text-white shadow-lg mb-3">
              <BarChart3 className="w-8 h-8" />
            </div>
            <h4 className="font-bold text-lg mb-2 gradient-text-primary">完整分析報告集合</h4>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              整合 12 位專業代理的深度分析，提供全方位投資決策支援
            </p>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <ReportSection
              title="分析師報告 (4份)"
              items={["技術面分析", "社群情緒分析", "新聞面分析", "基本面分析"]}
              color="blue"
            />
            <ReportSection
              title="研究報告 (3份)"
              items={["多頭研究報告", "空頭研究報告", "研究經理整合"]}
              color="green"
            />
            <ReportSection
              title="風險與交易 (5份)"
              items={["激進策略評估", "中立策略評估", "保守策略評估", "風險經理整合", "最終交易決策"]}
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
