import { Link } from 'react-router-dom';
import { ArrowLeft, Brain, BarChart2, TrendingUp, MessageSquare, Shield, Database, Sparkles, Target, Users, Zap, Clock } from 'lucide-react';

const agents = [
  {
    name: 'Technical Analyst',
    icon: BarChart2,
    color: 'from-purple-500 to-purple-600',
    bgColor: 'bg-purple-50 dark:bg-purple-900/20',
    description: 'Analyzes price charts, volume patterns, and technical indicators like RSI, MACD, Bollinger Bands, and moving averages to identify trends and momentum.',
    capabilities: ['Chart pattern recognition', 'Support/resistance levels', 'Momentum indicators', 'Volume analysis'],
  },
  {
    name: 'Fundamental Analyst',
    icon: TrendingUp,
    color: 'from-green-500 to-green-600',
    bgColor: 'bg-green-50 dark:bg-green-900/20',
    description: 'Evaluates company financials, earnings reports, P/E ratios, debt levels, and industry position to assess intrinsic value.',
    capabilities: ['Earnings analysis', 'Valuation metrics', 'Financial health', 'Growth trajectory'],
  },
  {
    name: 'Sentiment Analyst',
    icon: MessageSquare,
    color: 'from-amber-500 to-amber-600',
    bgColor: 'bg-amber-50 dark:bg-amber-900/20',
    description: 'Monitors news sentiment, social media trends, analyst ratings, and market psychology to gauge investor sentiment.',
    capabilities: ['News sentiment', 'Social media trends', 'Analyst ratings', 'Market psychology'],
  },
  {
    name: 'Risk Manager',
    icon: Shield,
    color: 'from-red-500 to-red-600',
    bgColor: 'bg-red-50 dark:bg-red-900/20',
    description: 'Assesses volatility, sector risks, market conditions, and potential downsides to determine appropriate risk levels.',
    capabilities: ['Volatility assessment', 'Sector correlation', 'Downside risk', 'Position sizing'],
  },
];

const features = [
  {
    icon: Users,
    title: 'Multi-Agent Collaboration',
    description: 'Multiple specialized AI agents work together, each bringing unique expertise to the analysis.',
  },
  {
    icon: Brain,
    title: 'AI Debate System',
    description: 'Agents debate their findings, challenge assumptions, and reach consensus through reasoned discussion.',
  },
  {
    icon: Database,
    title: 'Real-Time Data',
    description: 'Analysis is based on current market data, company financials, and news from reliable sources.',
  },
  {
    icon: Target,
    title: 'Clear Recommendations',
    description: 'Final decisions are clear BUY, SELL, or HOLD with confidence levels and risk assessments.',
  },
];

const dataFlow = [
  { step: 1, title: 'Data Collection', description: 'Market data, financials, and news are gathered', icon: Database },
  { step: 2, title: 'Independent Analysis', description: 'Each agent analyzes data from their perspective', icon: BarChart2 },
  { step: 3, title: 'AI Debate', description: 'Agents discuss and challenge findings', icon: MessageSquare },
  { step: 4, title: 'Consensus Decision', description: 'Final recommendation with confidence rating', icon: Target },
];

export default function About() {
  return (
    <div className="space-y-6">
      {/* Back Button */}
      <Link
        to="/"
        className="inline-flex items-center gap-1.5 text-sm text-gray-500 dark:text-gray-400 hover:text-nifty-600 dark:hover:text-nifty-400 transition-colors"
      >
        <ArrowLeft className="w-3.5 h-3.5" />
        Back to Dashboard
      </Link>

      {/* Hero Section */}
      <section className="card overflow-hidden">
        <div className="bg-gradient-to-r from-indigo-500 via-purple-500 to-nifty-600 p-6 text-white">
          <div className="flex items-center gap-3 mb-3">
            <div className="p-2 bg-white/20 rounded-xl">
              <Sparkles className="w-8 h-8" />
            </div>
            <div>
              <h1 className="text-2xl font-display font-bold">How TradingAgents Works</h1>
              <p className="text-white/80 text-sm">AI-powered stock analysis for Nifty 50</p>
            </div>
          </div>
          <p className="text-white/90 text-sm leading-relaxed max-w-2xl">
            TradingAgents uses a team of specialized AI agents that analyze stocks from multiple perspectives,
            debate their findings, and reach consensus recommendations. This multi-agent approach provides
            more balanced and thoroughly reasoned analysis than any single model.
          </p>
        </div>

        {/* Key Features */}
        <div className="p-4 bg-white dark:bg-slate-800 grid grid-cols-2 md:grid-cols-4 gap-3">
          {features.map((feature) => {
            const Icon = feature.icon;
            return (
              <div key={feature.title} className="text-center p-3">
                <div className="w-10 h-10 mx-auto mb-2 bg-nifty-100 dark:bg-nifty-900/30 rounded-xl flex items-center justify-center">
                  <Icon className="w-5 h-5 text-nifty-600 dark:text-nifty-400" />
                </div>
                <h3 className="font-semibold text-xs text-gray-900 dark:text-gray-100 mb-1">{feature.title}</h3>
                <p className="text-[10px] text-gray-500 dark:text-gray-400 leading-relaxed">{feature.description}</p>
              </div>
            );
          })}
        </div>
      </section>

      {/* Analysis Flow */}
      <section className="card p-4">
        <div className="flex items-center gap-2 mb-4">
          <Zap className="w-5 h-5 text-nifty-600 dark:text-nifty-400" />
          <h2 className="font-semibold text-gray-900 dark:text-gray-100">Analysis Process</h2>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {dataFlow.map((item, index) => {
            const Icon = item.icon;
            return (
              <div key={item.step} className="relative">
                <div className="p-3 rounded-lg border border-gray-100 dark:border-slate-700 bg-gray-50/50 dark:bg-slate-700/50">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="w-5 h-5 rounded-full bg-nifty-600 text-white text-xs font-bold flex items-center justify-center">
                      {item.step}
                    </span>
                    <Icon className="w-4 h-4 text-gray-400 dark:text-gray-500" />
                  </div>
                  <h3 className="font-semibold text-xs text-gray-900 dark:text-gray-100 mb-1">{item.title}</h3>
                  <p className="text-[10px] text-gray-500 dark:text-gray-400">{item.description}</p>
                </div>
                {index < dataFlow.length - 1 && (
                  <div className="hidden md:block absolute top-1/2 -right-2 w-4 text-gray-300 dark:text-gray-600">
                    →
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {/* Agent Cards */}
      <section>
        <div className="flex items-center gap-2 mb-3">
          <Brain className="w-5 h-5 text-nifty-600 dark:text-nifty-400" />
          <h2 className="font-semibold text-gray-900 dark:text-gray-100">Meet the AI Agents</h2>
        </div>

        <div className="grid md:grid-cols-2 gap-3">
          {agents.map((agent) => {
            const Icon = agent.icon;
            return (
              <div key={agent.name} className="card overflow-hidden">
                <div className={`bg-gradient-to-r ${agent.color} p-3 text-white`}>
                  <div className="flex items-center gap-2">
                    <Icon className="w-5 h-5" />
                    <h3 className="font-semibold text-sm">{agent.name}</h3>
                  </div>
                </div>
                <div className={`p-3 ${agent.bgColor}`}>
                  <p className="text-xs text-gray-600 dark:text-gray-300 mb-2">{agent.description}</p>
                  <div className="flex flex-wrap gap-1.5">
                    {agent.capabilities.map((cap) => (
                      <span
                        key={cap}
                        className="text-[10px] px-2 py-0.5 bg-white dark:bg-slate-700 rounded-full text-gray-600 dark:text-gray-300"
                      >
                        {cap}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* Debate Section */}
      <section className="card p-4 bg-gradient-to-br from-indigo-50 to-purple-50 dark:from-indigo-900/20 dark:to-purple-900/20 border-indigo-100 dark:border-indigo-800">
        <div className="flex items-center gap-3 mb-3">
          <div className="p-2 bg-indigo-100 dark:bg-indigo-900/30 rounded-lg">
            <Brain className="w-6 h-6 text-indigo-600 dark:text-indigo-400" />
          </div>
          <div>
            <h2 className="font-semibold text-gray-900 dark:text-gray-100">The AI Debate Process</h2>
            <p className="text-xs text-gray-500 dark:text-gray-400">How agents reach consensus</p>
          </div>
        </div>
        <div className="space-y-2 text-sm text-gray-600 dark:text-gray-300">
          <p>
            After each agent completes their analysis, they engage in a structured debate. The Technical
            Analyst might argue for a BUY based on strong momentum, while the Risk Manager highlights
            elevated volatility concerns.
          </p>
          <p>
            Through multiple rounds of discussion, agents refine their positions, consider counterarguments,
            and ultimately reach a consensus. This process mimics how investment committees at professional
            firms make decisions.
          </p>
          <p className="text-xs text-gray-500 dark:text-gray-400 italic">
            The final recommendation reflects the collective intelligence of all agents, weighted by the
            strength of their arguments and supporting evidence.
          </p>
        </div>
      </section>

      {/* Data Sources */}
      <section className="card p-4">
        <div className="flex items-center gap-2 mb-3">
          <Database className="w-5 h-5 text-nifty-600 dark:text-nifty-400" />
          <h2 className="font-semibold text-gray-900 dark:text-gray-100">Data Sources</h2>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
          <div className="p-2 rounded-lg bg-gray-50 dark:bg-slate-700">
            <span className="text-gray-500 dark:text-gray-400">Price Data:</span>
            <span className="ml-1 text-gray-900 dark:text-gray-100">NSE/BSE</span>
          </div>
          <div className="p-2 rounded-lg bg-gray-50 dark:bg-slate-700">
            <span className="text-gray-500 dark:text-gray-400">Financials:</span>
            <span className="ml-1 text-gray-900 dark:text-gray-100">Quarterly Reports</span>
          </div>
          <div className="p-2 rounded-lg bg-gray-50 dark:bg-slate-700">
            <span className="text-gray-500 dark:text-gray-400">News:</span>
            <span className="ml-1 text-gray-900 dark:text-gray-100">Financial Media</span>
          </div>
          <div className="p-2 rounded-lg bg-gray-50 dark:bg-slate-700">
            <span className="text-gray-500 dark:text-gray-400">Updates:</span>
            <span className="ml-1 text-gray-900 dark:text-gray-100">Daily</span>
          </div>
        </div>
      </section>

      {/* Disclaimer */}
      <section className="card p-4 bg-amber-50 dark:bg-amber-900/20 border-amber-100 dark:border-amber-800">
        <div className="flex items-start gap-3">
          <Clock className="w-5 h-5 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
          <div>
            <h2 className="font-semibold text-amber-800 dark:text-amber-300 text-sm mb-1">Important Disclaimer</h2>
            <p className="text-xs text-amber-700 dark:text-amber-400 leading-relaxed">
              TradingAgents provides AI-generated stock analysis for educational and informational purposes only.
              These recommendations do not constitute financial advice. Always conduct your own research and consult
              with a qualified financial advisor before making investment decisions. Past performance does not
              guarantee future results. Investing in stocks involves risk, including potential loss of principal.
            </p>
          </div>
        </div>
      </section>

      {/* CTA */}
      <Link
        to="/"
        className="card flex items-center justify-center p-4 bg-gradient-to-r from-nifty-600 to-nifty-700 text-white hover:from-nifty-700 hover:to-nifty-800 transition-all"
      >
        <span className="font-semibold">View Today's Recommendations →</span>
      </Link>
    </div>
  );
}
