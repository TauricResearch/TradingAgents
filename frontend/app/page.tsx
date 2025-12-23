"use client";

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
import { useLanguage } from "@/contexts/LanguageContext";

export default function HomePage() {
  const { t } = useLanguage();

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-50/30 via-pink-50/20 to-purple-50/30 dark:from-gray-950 dark:via-purple-950/40 dark:to-gray-950">
      <div className="container mx-auto px-4 py-12">
        {/* Hero Section */}
        <div className="text-center mb-16 animate-fade-in relative py-8">
          <div className="absolute inset-0 gradient-bg-radial -z-10" />
          <div className="mb-6">
            <Image
              src="/logo.png"
              alt="TradingAgentsX Logo"
              width={120}
              height={120}
              className="mx-auto rounded-2xl shadow-2xl hover:scale-105 transition-transform duration-300"
              priority
            />
          </div>
          <h1 className="text-4xl sm:text-5xl md:text-6xl font-bold mb-6 gradient-text-primary leading-tight">
            {t.home.title}
          </h1>
          <p className="text-xl text-gray-600 dark:text-gray-400 mb-8 max-w-2xl mx-auto">
            {t.nav.tagline}
          </p>
          <div className="flex gap-4 justify-center">
            <Link href="/analysis">
              <Button
                size="lg"
                className="bg-gradient-to-r from-blue-500 to-pink-500 dark:from-blue-600 dark:to-purple-600 hover:from-blue-600 hover:to-pink-600 dark:hover:from-blue-700 dark:hover:to-purple-700 shadow-lg hover:shadow-xl transition-all animate-heartbeat"
              >
                {t.home.startAnalysis}
              </Button>
            </Link>
          </div>
        </div>

        {/* Core Features Section */}
        <div className="mb-16 animate-slide-up animate-delay-200">
          <h2 className="text-3xl font-bold text-center mb-4">{t.home.coreFeatures}</h2>
          <p className="text-center text-gray-600 dark:text-gray-400 mb-8 max-w-3xl mx-auto">
            {t.home.coreFeaturesDesc}
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <FeatureCard
              title={t.home.features.multiAgent}
              description={t.home.features.multiAgentDesc}
              icon="🤖"
            />
            <FeatureCard
              title={t.home.features.multiModel}
              description={t.home.features.multiModelDesc}
              icon="🌐"
            />
            <FeatureCard
              title={t.home.features.customEndpoint}
              description={t.home.features.customEndpointDesc}
              icon="🔧"
            />
            <FeatureCard
              title={t.home.features.fullAnalysis}
              description={t.home.features.fullAnalysisDesc}
              icon="📊"
            />
            <FeatureCard
              title={t.home.features.structuredDecision}
              description={t.home.features.structuredDecisionDesc}
              icon="🔄"
            />
            <FeatureCard
              title={t.home.features.longTermMemory}
              description={t.home.features.longTermMemoryDesc}
              icon="🧠"
            />
            <FeatureCard
              title={t.home.features.modernUI}
              description={t.home.features.modernUIDesc}
              icon="🎨"
            />
            <FeatureCard
              title={t.home.features.oneClickDeploy}
              description={t.home.features.oneClickDeployDesc}
              icon="🐳"
            />
            <FeatureCard
              title={t.home.features.reportDownload}
              description={t.home.features.reportDownloadDesc}
              icon="📥"
            />
          </div>
        </div>

        {/* 12 Professional Agents Section */}
        <div className="mb-16">
          <h2 className="text-3xl font-bold text-center mb-4">
            {t.home.professionalAgents}
          </h2>
          <p className="text-center text-gray-600 dark:text-gray-400 mb-8 max-w-3xl mx-auto">
            {t.home.professionalAgentsDesc}
          </p>

          {/* Analyst Team */}
          <div className="mb-8">
            <h3 className="text-2xl font-semibold mb-4 flex items-center">
              {t.home.analystsTeamTitle}
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <AgentCard
                name={t.agents.market_analyst}
                role={t.agents.market_analyst_role}
                description={t.agents.market_analyst_desc}
              />
              <AgentCard
                name={t.agents.social_analyst}
                role={t.agents.social_analyst_role}
                description={t.agents.social_analyst_desc}
              />
              <AgentCard
                name={t.agents.news_analyst}
                role={t.agents.news_analyst_role}
                description={t.agents.news_analyst_desc}
              />
              <AgentCard
                name={t.agents.fundamentals_analyst}
                role={t.agents.fundamentals_analyst_role}
                description={t.agents.fundamentals_analyst_desc}
              />
            </div>
          </div>

          {/* Research Team */}
          <div className="mb-8">
            <h3 className="text-2xl font-semibold mb-4 flex items-center">
              {t.home.researchTeamTitle}
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <AgentCard
                name={t.agents.bull_researcher}
                role={t.agents.bull_researcher_role}
                description={t.agents.bull_researcher_desc}
              />
              <AgentCard
                name={t.agents.bear_researcher}
                role={t.agents.bear_researcher_role}
                description={t.agents.bear_researcher_desc}
              />
              <AgentCard
                name={t.agents.research_manager}
                role={t.agents.research_manager_role}
                description={t.agents.research_manager_desc}
              />
            </div>
          </div>

          {/* Trading Team */}
          <div className="mb-8">
            <h3 className="text-2xl font-semibold mb-4 flex items-center">
              {t.home.tradingTeamTitle}
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-1 gap-4 max-w-md">
              <AgentCard
                name={t.agents.trader}
                role={t.agents.trader_role}
                description={t.agents.trader_desc}
              />
            </div>
          </div>

          {/* Risk Management Team */}
          <div className="mb-8">
            <h3 className="text-2xl font-semibold mb-4 flex items-center">
              {t.home.riskTeamTitle}
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <AgentCard
                name={t.agents.aggressive_debator}
                role={t.agents.aggressive_debator_role}
                description={t.agents.aggressive_debator_desc}
              />
              <AgentCard
                name={t.agents.conservative_debator}
                role={t.agents.conservative_debator_role}
                description={t.agents.conservative_debator_desc}
              />
              <AgentCard
                name={t.agents.neutral_debator}
                role={t.agents.neutral_debator_role}
                description={t.agents.neutral_debator_desc}
              />
              <AgentCard
                name={t.agents.risk_manager}
                role={t.agents.risk_manager_role}
                description={t.agents.risk_manager_desc}
              />
            </div>
          </div>
        </div>

        {/* Agent Flow Diagram Section */}
        <div className="mb-16">
          <h2 className="text-3xl font-bold text-center mb-4">
            {t.home.workflowTitle}
          </h2>
          <p className="text-center text-gray-600 dark:text-gray-400 mb-8 max-w-3xl mx-auto">
            {t.home.workflowDescription}
          </p>
          <AgentFlowDiagram />
        </div>

        {/* LLM Support Section */}
        <div className="mb-16">
          <h2 className="text-3xl font-bold text-center mb-4">{t.home.llmSupport}</h2>
          <p className="text-center text-gray-600 dark:text-gray-400 mb-8 max-w-3xl mx-auto">
            {t.home.llmSupportDesc}
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <LLMProviderCard
              name="OpenAI"
              models={[
                "GPT-5.1",
                "GPT-5 Mini/Nano",
                "GPT-4.1 Mini/Nano",
                "o4-mini",
              ]}
              icon="🟢"
            />
            <LLMProviderCard
              name="Anthropic"
              models={[
                "Claude Haiku 4.5",
                "Claude Sonnet 4.5/4.0",
                "Claude 3.5 Haiku",
              ]}
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
              {t.home.llmFeatures}
            </p>
          </div>
        </div>

        {/* Workflow Section */}
        <div className="mb-16">
          <h2 className="text-3xl font-bold text-center mb-4">⚙️ {t.home.workflowTitle}</h2>
          <p className="text-center text-gray-600 dark:text-gray-400 mb-8 max-w-3xl mx-auto">
            {t.home.coreFeaturesDesc}
          </p>
          <Card className="shadow-lg hover-lift">
            <CardContent className="pt-6">
              <div className="space-y-4">
                <WorkflowStep
                  number={1}
                  title={t.home.processSteps.dataCollection.title}
                  description={t.home.processSteps.dataCollection.description}
                />
                <WorkflowStep
                  number={2}
                  title={t.home.processSteps.analysts.title}
                  description={t.home.processSteps.analysts.description}
                />
                <WorkflowStep
                  number={3}
                  title={t.home.processSteps.researchers.title}
                  description={t.home.processSteps.researchers.description}
                />
                <WorkflowStep
                  number={4}
                  title={t.home.processSteps.trader.title}
                  description={t.home.processSteps.trader.description}
                />
                <WorkflowStep
                  number={5}
                  title={t.home.processSteps.risk.title}
                  description={t.home.processSteps.risk.description}
                />
                <WorkflowStep
                  number={6}
                  title={t.home.processSteps.finalDecision.title}
                  description={t.home.processSteps.finalDecision.description}
                />
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Technical Highlights */}
        <div className="mb-16">
          <h2 className="text-3xl font-bold text-center mb-4">{t.home.techHighlights}</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <TechnicalCard
              title={t.home.dynamicResearch}
              features={t.home.dynamicResearchFeatures}
            />
            <TechnicalCard
              title={t.home.memorySystem}
              features={t.home.memorySystemFeatures}
            />
            <TechnicalCard
              title={t.home.realTimeData}
              features={t.home.realTimeDataFeatures}
            />
            <TechnicalCard
              title={t.home.fullApiSupport}
              features={t.home.fullApiSupportFeatures}
            />
          </div>
        </div>

        {/* Call to Action Section */}
        <div className="text-center py-16 relative">
          <div className="absolute inset-0 gradient-bg-radial opacity-60 -z-10" />
          <h2 className="text-3xl font-bold mb-4 gradient-text-primary">
            {t.home.readyToStart}
          </h2>
          <p className="text-lg text-gray-600 dark:text-gray-400 mb-8 max-w-2xl mx-auto">
            {t.home.ctaDescription}
          </p>
          <Link href="/analysis">
            <Button
              size="lg"
              className="bg-gradient-to-r from-blue-500 to-pink-500 dark:from-blue-600 dark:to-purple-600 hover:from-blue-600 hover:to-pink-600 dark:hover:from-blue-700 dark:hover:to-purple-700 text-lg px-8 py-6 shadow-lg hover:shadow-2xl transition-all animate-heartbeat"
            >
              {t.home.startAnalysis} →
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
  description,
}: {
  name: string;
  role: string;
  description: string;
}) {
  return (
    <Card className="hover-lift animate-scale-up">
      <CardHeader>
        <CardTitle className="text-base">{name}</CardTitle>
        <CardDescription className="text-xs">{role}</CardDescription>
      </CardHeader>
      <CardContent>
        <p className="text-xs text-gray-600 dark:text-gray-400">
          {description}
        </p>
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
  const logoMap: Record<string, string> = {
    OpenAI: "/logos/openai.svg",
    Anthropic: "/logos/claude-color.svg",
    "Google Gemini": "/logos/gemini-color.svg",
    "Grok (xAI)": "/logos/grok.svg",
    DeepSeek: "/logos/deepseek-color.svg",
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
