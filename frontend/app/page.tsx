import Link from "next/link";
import Image from "next/image";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { AgentFlowDiagram } from "@/components/AgentFlowDiagram";

export default function HomePage() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-50/30 via-pink-50/20 to-purple-50/30 dark:from-gray-950 dark:via-purple-950/40 dark:to-gray-950">
      <div className="container mx-auto px-4 py-12">
        {/* Hero Section */}
      <div className="text-center mb-16 animate-fade-in relative py-8">
        <div className="absolute inset-0 gradient-bg-radial -z-10" />
        <h1 className="text-5xl md:text-6xl font-bold mb-6 gradient-text-primary leading-tight">
          TradingAgentsX
        </h1>
        <p className="text-xl text-gray-600 dark:text-gray-400 mb-8 max-w-2xl mx-auto">
          多代理 LLM 金融交易框架
        </p>
        <div className="flex gap-4 justify-center">
          <Link href="/analysis">
            <Button
              size="lg"
              className="bg-gradient-to-r from-blue-500 to-pink-500 dark:from-blue-600 dark:to-purple-600 hover:from-blue-600 hover:to-pink-600 dark:hover:from-blue-700 dark:hover:to-purple-700 shadow-lg hover:shadow-xl transition-all animate-heartbeat"
            >
              開始分析
            </Button>
          </Link>
        </div>
      </div>

      {/* Core Features Section */}
      <div className="mb-16 animate-slide-up animate-delay-200">
        <h2 className="text-3xl font-bold text-center mb-4">🎯 核心特色</h2>
        <p className="text-center text-gray-600 dark:text-gray-400 mb-8 max-w-3xl mx-auto">
          基於 LangGraph 的智能股票交易分析平台，結合多個 AI 代理進行協作決策
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <FeatureCard
            title="多代理協作架構"
            description="12 個專業化 AI 代理團隊協同工作，模擬真實交易公司運作模式"
            icon="🤖"
          />
          <FeatureCard
            title="多模型靈活支援"
            description="支援 OpenAI、Claude、Gemini、Grok、DeepSeek、Qwen 等多家 LLM"
            icon="🌐"
          />
          <FeatureCard
            title="自訂端點配置"
            description="完整支援自訂 API 端點，可連接任何 OpenAI 兼容的服務"
            icon="🔧"
          />
          <FeatureCard
            title="全方位市場分析"
            description="整合技術面、基本面、情緒面、新聞面四大維度分析"
            icon="📊"
          />
          <FeatureCard
            title="結構化決策流程"
            description="透過看漲/看跌辯論機制減少偏見，做出更理性的決策"
            icon="🔄"
          />
          <FeatureCard
            title="長期記憶系統"
            description="使用 ChromaDB 向量資料庫儲存歷史決策，持續學習改進"
            icon="🧠"
          />
          <FeatureCard
            title="現代化 Web 介面"
            description="基於 Next.js 16 的響應式 UI，支援深色模式"
            icon="🎨"
          />
          <FeatureCard
            title="一鍵部署"
            description="支援 Docker Compose 部署，快速啟動完整服務"
            icon="🐳"
          />
          <FeatureCard
            title="報告下載"
            description="支援將完整分析報告匯出為 PDF，方便保存與分享"
            icon="📥"
          />
        </div>
      </div>

      {/* 12 Professional Agents Section */}
      <div className="mb-16">
        <h2 className="text-3xl font-bold text-center mb-4">👥 12 位專業代理團隊</h2>
        <p className="text-center text-gray-600 dark:text-gray-400 mb-8 max-w-3xl mx-auto">
          每個代理都有其專業職責，協同工作產生高質量的交易決策
        </p>
        
        {/* Analyst Team */}
        <div className="mb-8">
          <h3 className="text-2xl font-semibold mb-4 flex items-center">
            <span className="mr-2">📊</span>
            分析師團隊 (4 位)
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <AgentCard
              name="市場分析師"
              role="技術分析"
              responsibilities={["技術指標分析 (RSI, MACD, 布林通道)", "價格走勢研判", "支撐阻力位識別"]}
            />
            <AgentCard
              name="社群媒體分析師"
              role="情緒評估"
              responsibilities={["Reddit/Twitter 情緒指標", "熱度趨勢分析", "投資者信心指數"]}
            />
            <AgentCard
              name="新聞分析師"
              role="新聞分析"
              responsibilities={["最新新聞摘要", "事件影響評估", "市場反應預測"]}
            />
            <AgentCard
              name="基本面分析師"
              role="財務分析"
              responsibilities={["財報數據解析", "估值指標 (P/E, P/B)", "盈利能力評估"]}
            />
          </div>
        </div>

        {/* Research Team */}
        <div className="mb-8">
          <h3 className="text-2xl font-semibold mb-4 flex items-center">
            <span className="mr-2">🔍</span>
            研究團隊 (3 位)
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <AgentCard
              name="看漲研究員"
              role="多頭論證"
              responsibilities={["看漲理由分析", "上漲催化劑識別", "目標價位預測"]}
            />
            <AgentCard
              name="看跌研究員"
              role="空頭論證"
              responsibilities={["看跌理由分析", "下跌風險警告", "防守策略建議"]}
            />
            <AgentCard
              name="研究經理"
              role="綜合研判"
              responsibilities={["綜合雙方觀點", "研究團隊決策", "投資建議產出"]}
            />
          </div>
        </div>

        {/* Trading Team */}
        <div className="mb-8">
          <h3 className="text-2xl font-semibold mb-4 flex items-center">
            <span className="mr-2">💼</span>
            交易團隊 (1 位)
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-1 gap-4 max-w-md">
            <AgentCard
              name="交易員"
              role="決策整合"
              responsibilities={["整合所有報告", "制定交易計劃", "執行策略設計"]}
            />
          </div>
        </div>

        {/* Risk Management Team */}
        <div className="mb-8">
          <h3 className="text-2xl font-semibold mb-4 flex items-center">
            <span className="mr-2">🛡️</span>
            風險管理團隊 (4 位)
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <AgentCard
              name="激進分析師"
              role="高風險高回報"
              responsibilities={["激進策略評估", "最大收益潛力", "風險容忍度高"]}
            />
            <AgentCard
              name="保守分析師"
              role="穩健保守"
              responsibilities={["資本保全優先", "風險嚴格控制", "穩健策略建議"]}
            />
            <AgentCard
              name="中立分析師"
              role="平衡策略"
              responsibilities={["風險收益平衡", "中立客觀評估", "折衷方案設計"]}
            />
            <AgentCard
              name="風險經理"
              role="最終風控"
              responsibilities={["風險綜合評估", "倉位建議", "止損止盈設定"]}
            />
          </div>
        </div>
      </div>

      {/* Agent Flow Diagram Section */}
      <div className="mb-16">
        <h2 className="text-3xl font-bold text-center mb-4">🔄 分析師協作流程</h2>
        <p className="text-center text-gray-600 dark:text-gray-400 mb-8 max-w-3xl mx-auto">
          四大分析師代理如何從不同資料來源收集資訊，並產生綜合分析報告
        </p>
        <AgentFlowDiagram />
      </div>

      {/* LLM Support Section */}
      <div className="mb-16">
        <h2 className="text-3xl font-bold text-center mb-4">🌍 多模型支援</h2>
        <p className="text-center text-gray-600 dark:text-gray-400 mb-8 max-w-3xl mx-auto">
          支援業界領先的多家 LLM 提供商，每個模型可配置獨立的 API Key 和 Base URL
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <LLMProviderCard
            name="OpenAI"
            models={["GPT-5.1", "GPT-5 Mini/Nano", "GPT-4.1 Mini/Nano", "o4-mini"]}
            icon="🟢"
          />
          <LLMProviderCard
            name="Anthropic"
            models={["Claude Haiku 4.5", "Claude Sonnet 4.5/4.0", "Claude 3.5 Haiku"]}
            icon="🟣"
          />
          <LLMProviderCard
            name="Google Gemini"
            models={["Gemini 2.5 Pro/Flash/Lite", "Gemini 2.0 Flash/Lite"]}
            icon="🔵"
          />
          <LLMProviderCard
            name="Grok (xAI)"
            models={["Grok-4.1 Fast", "Grok-4 Fast", "Grok-3 Mini"]}
            icon="⚫"
          />
          <LLMProviderCard
            name="DeepSeek"
            models={["DeepSeek Reasoner", "DeepSeek Chat"]}
            icon="🔴"
          />
          <LLMProviderCard
            name="Qwen (Alibaba)"
            models={["Qwen3-Max", "Qwen-Plus", "Qwen Flash"]}
            icon="🟠"
          />
        </div>
        <div className="mt-6 text-center">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            ✅ 完整支援自訂端點 | ✅ 三層獨立配置（快速思維/深層思維/嵌入） | ✅ BYOK 模式
          </p>
        </div>
      </div>

      {/* Workflow Section */}
      <div className="mb-16">
        <h2 className="text-3xl font-bold text-center mb-4">⚙️ 工作流程</h2>
        <p className="text-center text-gray-600 dark:text-gray-400 mb-8 max-w-3xl mx-auto">
          TradingAgentsX 模擬真實交易公司，配備專業化的 LLM 代理
        </p>
        <Card className="shadow-lg hover-lift">
          <CardContent className="pt-6">
            <div className="space-y-4">
              <WorkflowStep
                number={1}
                title="資料收集階段"
                description="從 yfinance、Reddit、RSS 等多源獲取股價、新聞、社群情緒數據"
              />
              <WorkflowStep
                number={2}
                title="分析師團隊平行分析"
                description="市場、情緒、新聞、基本面四大分析師同時評估，產出專業報告"
              />
              <WorkflowStep
                number={3}
                title="研究團隊辯論"
                description="看漲與看跌研究員進行結構化辯論，研究經理綜合雙方觀點"
              />
              <WorkflowStep
                number={4}
                title="交易員整合分析"
                description="審查所有分析師與研究團隊報告，制定具體交易執行計劃"
              />
              <WorkflowStep
                number={5}
                title="風險管理評估"
                description="激進、保守、中立三方風險分析師評估策略，風險經理做出風控決策"
              />
              <WorkflowStep
                number={6}
                title="最終決策輸出"
                description="產生包含交易方向、倉位大小、風險控制的完整投資建議"
              />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Technical Highlights */}
      <div className="mb-16">
        <h2 className="text-3xl font-bold text-center mb-4">💡 技術亮點</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <TechnicalCard
            title="動態研究深度"
            features={[
              "淺層 (Shallow): 1 輪快速分析",
              "中等 (Medium): 2 輪平衡分析",
              "深層 (Deep): 3+ 輪全面分析"
            ]}
          />
          <TechnicalCard
            title="長期記憶系統"
            features={[
              "ChromaDB 向量資料庫",
              "歷史決策持久化",
              "持續學習與改進"
            ]}
          />
          <TechnicalCard
            title="實時資料整合"
            features={[
              "yfinance: 即時股價數據",
              "Reddit API: 社群情緒",
              "Alpha Vantage: 財務資料"
            ]}
          />
          <TechnicalCard
            title="完整 API 支援"
            features={[
              "RESTful API 架構",
              "異步任務處理",
              "Swagger 互動文檔"
            ]}
          />
        </div>
      </div>

      {/* Call to Action Section */}
      <div className="text-center py-16 relative">
        <div className="absolute inset-0 gradient-bg-radial opacity-60 -z-10" />
        <h2 className="text-3xl font-bold mb-4 gradient-text-primary">準備好開始智能交易分析了嗎？</h2>
        <p className="text-lg text-gray-600 dark:text-gray-400 mb-8 max-w-2xl mx-auto">
          立即體驗 12 位專業 AI 代理協同工作，為您提供全方位的股票分析報告
        </p>
        <Link href="/analysis">
          <Button
            size="lg"
            className="bg-gradient-to-r from-blue-500 to-pink-500 dark:from-blue-600 dark:to-purple-600 hover:from-blue-600 hover:to-pink-600 dark:hover:from-blue-700 dark:hover:to-purple-700 text-lg px-8 py-6 shadow-lg hover:shadow-2xl transition-all animate-heartbeat"
          >
            開始分析 →
          </Button>
        </Link>
      </div>
      </div>
    </div>
  );
}

function FeatureCard({
  title,
  description,
  icon,
}: {
  title: string;
  description: string;
  icon: string;
}) {
  return (
    <Card className="hover-lift animate-slide-up">
      <CardHeader>
        <div className="text-4xl mb-2">{icon}</div>
        <CardTitle className="text-lg">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          {description}
        </p>
      </CardContent>
    </Card>
  );
}

function AgentCard({
  name,
  role,
  responsibilities,
}: {
  name: string;
  role: string;
  responsibilities: string[];
}) {
  return (
    <Card className="hover-lift animate-scale-up">
      <CardHeader>
        <CardTitle className="text-base">{name}</CardTitle>
        <CardDescription className="text-xs">{role}</CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="space-y-1 text-xs text-gray-600 dark:text-gray-400">
          {responsibilities.map((item, index) => (
            <li key={index} className="flex items-start">
              <span className="mr-1">•</span>
              <span>{item}</span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function LLMProviderCard({
  name,
  models,
  icon,
}: {
  name: string;
  models: string[];
  icon: string;
}) {
  // Map provider names to logo filenames
  const logoMap: Record<string, string> = {
    "OpenAI": "/logos/openai.svg",
    "Anthropic": "/logos/claude-color.svg",
    "Google Gemini": "/logos/gemini-color.svg",
    "Grok (xAI)": "/logos/grok.svg",
    "DeepSeek": "/logos/deepseek-color.svg",
    "Qwen (Alibaba)": "/logos/qwen-color.svg",
  };

  const logoSrc = logoMap[name];

  return (
    <Card className="hover-lift animate-slide-up animate-delay-100">
      <CardHeader>
        <div className="flex items-center gap-3">
          {logoSrc ? (
            <div className="relative w-8 h-8 flex-shrink-0 transition-transform duration-300 hover:scale-110">
              <Image
                src={logoSrc}
                alt={`${name} logo`}
                width={32}
                height={32}
                className="object-contain"
              />
            </div>
          ) : (
            <span className="text-2xl">{icon}</span>
          )}
          <CardTitle className="text-lg">{name}</CardTitle>
        </div>
      </CardHeader>
      <CardContent>
        <ul className="space-y-1 text-xs text-gray-600 dark:text-gray-400">
          {models.map((model, index) => (
            <li key={index} className="flex items-start">
              <span className="mr-1">✓</span>
              <span>{model}</span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function TechnicalCard({
  title,
  features,
}: {
  title: string;
  features: string[];
}) {
  return (
    <Card className="hover-lift animate-slide-up animate-delay-300">
      <CardHeader>
        <CardTitle className="text-lg">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="space-y-2 text-sm text-gray-600 dark:text-gray-400">
          {features.map((feature, index) => (
            <li key={index} className="flex items-start">
              <span className="mr-2 text-green-500">✓</span>
              <span>{feature}</span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function WorkflowStep({
  number,
  title,
  description,
}: {
  number: number;
  title: string;
  description: string;
}) {
  return (
    <div className="flex gap-4 items-start">
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-gradient-to-r from-blue-500 to-pink-500 dark:from-blue-600 dark:to-purple-600 text-white flex items-center justify-center font-bold">
        {number}
      </div>
      <div>
        <h4 className="font-semibold mb-1">{title}</h4>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          {description}
        </p>
      </div>
    </div>
  );
}
