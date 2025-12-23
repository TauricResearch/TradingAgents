/**
 * English translations for TradingAgentsX
 */
export const en = {
  // Common
  common: {
    loading: "Loading...",
    error: "Error",
    save: "Save",
    cancel: "Cancel",
    confirm: "Confirm",
    download: "Download",
    delete: "Delete",
    back: "Back",
    next: "Next",
    submit: "Submit",
    close: "Close",
  },

  // Theme
  theme: {
    toggle: "Toggle theme",
    light: "Light",
    dark: "Dark",
    system: "System",
  },

  // Auth / Login
  auth: {
    login: "Login",
    logout: "Logout",
    loggingOut: "Logging out...",
    cloudSyncEnabled: "Cloud sync enabled",
    usingLocalStorage: "Using local storage",
    loginToSync: "Login with Google to sync API settings and history reports",
    loginSync: "Login to sync",
  },

  // API Settings Dialog
  settings: {
    title: "API Settings",
    apiConfiguration: "API Configuration",
    description:
      "Configure your API keys. They are stored encrypted in your browser.",
    encryptionEnabled: "🔒 AES-256-GCM encryption enabled",
    onlyFillNeeded:
      "💡 Only fill in the API keys for the model providers you want to use. For example, if using Claude, only fill in the Claude API key.",

    // Sections
    stockMarketApis: "Stock Market Data APIs (fill based on market)",
    llmProviders: "LLM Model Providers (fill based on selected model)",
    customEndpoint: "Custom Endpoint (Advanced)",

    // Form labels
    finmindToken: "FinMind API Token (Taiwan Stocks)",
    finmindPlaceholder: "Enter FinMind Token",
    finmindDesc: "For Taiwan stock data (register at finmindtrade.com)",
    alphaVantageKey: "Alpha Vantage API Key (US Stocks)",
    alphaVantagePlaceholder: "Enter Alpha Vantage API Key",
    alphaVantageDesc:
      "For US stock fundamental data (recommended for US stocks)",
    openaiDesc:
      "For OpenAI models (GPT-4, GPT-5, o4, etc.) and OpenAI embeddings",
    anthropicDesc: "For Claude models",
    googleDesc: "For Gemini models",
    grokDesc: "For Grok models",
    deepseekDesc: "For DeepSeek models",
    qwenDesc: "For Qwen models",
    customBaseUrl: "Custom Base URL",
    customBaseUrlDesc:
      "If set, this will override the default endpoint for all models",
    customApiKey: "Custom Endpoint API Key",
    customApiKeyPlaceholder: "Enter custom endpoint API Key",
    customApiKeyDesc: "API Key for use with custom Base URL",

    // Buttons and messages
    saveSettings: "Save Settings",
    clearSettings: "Clear Settings",
    processing: "Processing...",
    settingsSaved: "✓ Settings saved successfully",
  },

  // Navigation
  nav: {
    home: "Home",
    analysis: "Analysis",
    history: "History",
    settings: "Settings",
    tagline: "Multi-Agent LLM Trading Framework",
  },

  // Home page
  home: {
    title: "TradingAgentsX",
    subtitle: "Multi-Agent LLM Trading Analysis Platform",
    description:
      "Powered by multi-agent AI collaboration for comprehensive investment analysis and insights",
    startAnalysis: "Start Analysis",
    viewHistory: "View History",

    // Core features section
    coreFeatures: "Core Features",
    coreFeaturesDesc:
      "Intelligent stock trading analysis platform based on LangGraph, combining multiple AI agents for collaborative decision-making",

    // Feature cards
    features: {
      multiAgent: "Multi-Agent Collaboration",
      multiAgentDesc:
        "12 specialized AI agent teams working together, simulating real trading firm operations",
      multiModel: "Multi-Model Support",
      multiModelDesc:
        "Support for OpenAI, Claude, Gemini, Grok, DeepSeek, Qwen and more LLMs",
      customEndpoint: "Custom Endpoint Configuration",
      customEndpointDesc:
        "Full support for custom API endpoints, connect to any OpenAI-compatible service",
      fullAnalysis: "Comprehensive Market Analysis",
      fullAnalysisDesc:
        "Integrated technical, fundamental, sentiment, and news analysis across four dimensions",
      structuredDecision: "Structured Decision Process",
      structuredDecisionDesc:
        "Bull/Bear debate mechanism reduces bias for more rational decisions",
      longTermMemory: "Long-Term Memory System",
      longTermMemoryDesc:
        "ChromaDB vector database stores historical decisions for continuous learning",
      modernUI: "Modern Web Interface",
      modernUIDesc: "Responsive UI based on Next.js 16, supports dark mode",
      oneClickDeploy: "One-Click Deploy",
      oneClickDeployDesc:
        "Docker Compose deployment support, quickly launch complete service",
      reportDownload: "Report Download",
      reportDownloadDesc:
        "Export full analysis reports to PDF for easy saving and sharing",
    },

    // 12 Professional Agents Section
    professionalAgents: "12 Professional Agent Teams",
    professionalAgentsDesc:
      "Each agent has specialized responsibilities, collaborating to produce high-quality trading decisions",
    analystsTeamTitle: "Analysts Team (4)",
    researchTeamTitle: "Research Team (3)",
    tradingTeamTitle: "Trading Team (1)",
    riskTeamTitle: "Risk Management Team (4)",

    // Workflow section
    workflowTitle: "Analyst Collaboration Flow",
    workflowDescription:
      "How the four analyst agents collect information from different data sources and produce comprehensive analysis reports",

    // Process steps
    processSteps: {
      dataCollection: {
        title: "Data Collection Phase",
        description:
          "Gather stock prices, news, social sentiment from yfinance, Reddit, RSS and more",
      },
      analysts: {
        title: "Parallel Analysis by Analysts Team",
        description:
          "Market, Sentiment, News, and Fundamentals analysts evaluate simultaneously, producing professional reports",
      },
      researchers: {
        title: "Research Team Debate",
        description:
          "Bullish and Bearish researchers conduct structured debate, Research Manager synthesizes both views",
      },
      trader: {
        title: "Trader Integration",
        description:
          "Reviews all analyst and research reports, formulates specific trading execution plan",
      },
      risk: {
        title: "Risk Management Assessment",
        description:
          "Aggressive, Conservative, and Neutral risk analysts evaluate strategy, Risk Manager makes final call",
      },
      finalDecision: {
        title: "Final Decision Output",
        description:
          "Produces complete investment recommendation with trading direction, position size, and risk controls",
      },
    },

    // LLM Support Section
    llmSupport: "Multi-Model Support",
    llmSupportDesc:
      "Support for multiple industry-leading LLM providers, each model can be configured with independent API Key and Base URL",
    llmFeatures:
      "Full custom endpoint support | Three-tier independent config (Quick Think/Deep Think/Embedding) | BYOK mode",

    // Technical Highlights
    techHighlights: "Technical Highlights",
    dynamicResearch: "Dynamic Research Depth",
    dynamicResearchFeatures: [
      "Shallow: 1 round quick analysis",
      "Medium: 2 rounds balanced analysis",
      "Deep: 3+ rounds comprehensive analysis",
    ],
    memorySystem: "Long-Term Memory System",
    memorySystemFeatures: [
      "ChromaDB vector database",
      "Historical decision persistence",
      "Continuous learning and improvement",
    ],
    realTimeData: "Real-Time Data Integration",
    realTimeDataFeatures: [
      "yfinance: Real-time stock data",
      "Reddit API: Social sentiment",
      "Alpha Vantage: Financial data",
    ],
    fullApiSupport: "Full API Support",
    fullApiSupportFeatures: [
      "RESTful API architecture",
      "Async task processing",
      "Swagger interactive docs",
    ],

    // CTA Section
    readyToStart: "Ready to Start Smart Trading Analysis?",
    ctaDescription:
      "Experience 12 professional AI agents working together to provide comprehensive stock analysis reports",
  },

  // Agents
  agents: {
    // Analysts
    market_analyst: "Market Analyst",
    market_analyst_role: "Technical Analysis",
    market_analyst_desc:
      "Technical indicators (RSI, MACD, Bollinger Bands), price trend analysis, support/resistance identification",

    social_analyst: "Social Media Analyst",
    social_analyst_role: "Sentiment Analysis",
    social_analyst_desc:
      "Social sentiment monitoring, market atmosphere assessment, trending topic analysis",

    news_analyst: "News Analyst",
    news_analyst_role: "News Analysis",
    news_analyst_desc:
      "News event tracking, impact assessment, information filtering and prioritization",

    fundamentals_analyst: "Fundamentals Analyst",
    fundamentals_analyst_role: "Fundamental Analysis",
    fundamentals_analyst_desc:
      "Financial data analysis, valuation metrics, company fundamentals evaluation",

    // Researchers
    bull_researcher: "Bull Researcher",
    bull_researcher_role: "Bullish Analysis",
    bull_researcher_desc:
      "Identifies upside potential, growth catalysts, and bullish scenarios",

    bear_researcher: "Bear Researcher",
    bear_researcher_role: "Bearish Analysis",
    bear_researcher_desc:
      "Identifies downside risks, warning signals, and bearish scenarios",

    // Managers
    research_manager: "Research Manager",
    research_manager_role: "Research Synthesis",
    research_manager_desc:
      "Synthesizes bull and bear arguments, produces balanced research conclusion",

    risk_manager: "Risk Manager",
    risk_manager_role: "Risk Decision",
    risk_manager_desc:
      "Final risk assessment and position sizing recommendation",

    // Risk Debaters
    aggressive_debator: "Aggressive Analyst",
    aggressive_debator_role: "High Risk/Reward",
    aggressive_debator_desc:
      "Advocates for higher risk positions with greater potential returns",

    conservative_debator: "Conservative Analyst",
    conservative_debator_role: "Capital Preservation",
    conservative_debator_desc:
      "Advocates for safer positions with capital protection focus",

    neutral_debator: "Neutral Analyst",
    neutral_debator_role: "Balanced View",
    neutral_debator_desc:
      "Provides balanced perspective between aggressive and conservative views",

    // Trader
    trader: "Trader",
    trader_role: "Trade Execution",
    trader_desc:
      "Formulates final trading recommendation with entry, exit, and position sizing",
  },

  // Flow Diagram
  flowDiagram: {
    // Layer titles
    layer1: "Layer 1: Data Sources",
    layer2: "Layer 2: Analyst Agents (4)",
    layer3: "Layer 3: Researcher Agents (2)",
    layer4: "Layer 4: Risk Debaters (3)",
    finalOutput: "Final Output: 12 Detailed Reports",

    // Data sources
    stockData: "Stock Data",
    socialSentiment: "Social Sentiment",
    newsInfo: "News Info",
    financialData: "Financial Data",

    // Arrow labels
    dataFetch: "Data Fetching & Cleaning",
    reportIntegration: "Report Integration",
    researchPrep: "Research Integration & Debate Prep",
    riskDebate: "Risk Assessment & Management",
    finalDecision: "Final Trading Decision",
    generateReport: "Generate Complete Investment Report",

    // Agent descriptions
    technicalAnalysis: "Technical Analysis",
    sentimentAnalysis: "Sentiment Analysis",
    newsAnalysis: "News Analysis",
    fundamentalsAnalysis: "Fundamentals Analysis",
    bullishResearch: "Bullish View Research",
    bearishResearch: "Bearish View Research",
    integrateViews: "Integrate Bull/Bear Views",
    highRiskReward: "High Risk/High Return",
    balancedRisk: "Balanced Risk/Return",
    lowRiskVol: "Low Risk/Low Volatility",
    integrateRisk: "Integrate Risk Debate Results",
    executeTrade: "Execute Final Trading Decision",

    // Tasks
    rsiIndicator: "RSI Indicator",
    macdMomentum: "MACD Momentum",
    priceTrend: "Price Trend",
    nlpSentiment: "NLP Sentiment",
    discussionHeat: "Discussion Heat",
    investorConfidence: "Investor Confidence",
    newsSummary: "News Summary",
    eventAssessment: "Event Assessment",
    impactPrediction: "Impact Prediction",
    financialAnalysis: "Financial Analysis",
    valuationMetrics: "Valuation Metrics",
    profitEvaluation: "Profit Evaluation",
    positiveFactors: "Positive Factors Analysis",
    growthOpportunities: "Growth Opportunities",
    buyReasons: "Buy Reasons Summary",
    negativeFactors: "Negative Factors Analysis",
    riskAssessment: "Risk Assessment",
    sellReasons: "Sell Reasons Summary",
    balanceArguments: "Balance Both Arguments",
    comprehensiveAdvice: "Comprehensive Investment Advice",
    preliminaryStrategy: "Preliminary Strategy",
    aggressiveStrategy: "Aggressive Investment Strategy",
    maximizeReturns: "Maximize Returns",
    calculatedRisk: "Take Calculated Risks",
    prudentStrategy: "Prudent Investment Strategy",
    riskBalance: "Risk Balance",
    rationalDecision: "Rational Decision",
    conservativeStrategy: "Conservative Investment Strategy",
    capitalProtection: "Capital Protection",
    riskReduction: "Risk Reduction",
    riskRating: "Risk Level Rating",
    stopLossSettings: "Stop Loss/Take Profit Settings",
    finalRiskControl: "Final Risk Control",

    // Outputs
    tradeSignal: "Trade Signal (BUY/SELL/HOLD)",
    targetPrice: "Target Price",
    tradeQuantity: "Trade Quantity",
    riskParams: "Risk Parameters",
    finalOutput_label: "Final Output:",
    completeReportSet: "Complete Analysis Report Set",
    comprehensiveSupport:
      "Integrating 12 professional agents for comprehensive investment decision support",

    // Report sections
    analystReports: "Analyst Reports (4)",
    researchReports: "Research Reports (3)",
    riskTrading: "Risk & Trading (5)",
    technicalReport: "Technical Analysis",
    sentimentReport: "Sentiment Analysis",
    newsReport: "News Analysis",
    fundamentalsReport: "Fundamentals Analysis",
    bullReport: "Bull Research Report",
    bearReport: "Bear Research Report",
    researchManagerReport: "Research Manager Integration",
    aggressiveEval: "Aggressive Strategy Evaluation",
    balancedEval: "Balanced Strategy Evaluation",
    conservativeEval: "Conservative Strategy Evaluation",
    riskManagerReport: "Risk Manager Integration",
    finalTradeDecision: "Final Trading Decision",

    // Manager titles
    researchManager: "Research Manager",
    riskManager: "Risk Manager",
    trader: "Trader",
  },

  // Analysis form
  form: {
    ticker: "Stock Ticker",
    tickerPlaceholder: "Enter stock symbol (e.g., AAPL, 2330)",
    analysisDate: "Analysis Date",
    analysts: "Analyst Team",
    selectAnalysts: "Select analysts to include",
    selectAll: "Select All",
    deselectAll: "Deselect All",
    startAnalysis: "Start Analysis",
    analyzing: "Analyzing...",

    // Analysis page
    analysisTitle: "Trading Analysis",
    analysisSubtitle:
      "Configure and execute comprehensive multi-agent trading analysis",
    analysisLoading: "Running analysis... This may take a few minutes.",

    advancedOptions: "Advanced Options",
    researchDepth: "Research Depth",
    riskDebateRounds: "Risk Debate Rounds",

    // Market types
    marketType: "Market Type",
    usMarket: "US Stocks",
    twseMarket: "TWSE",
    tpexMarket: "TPEX",
    selectMarket: "Select Market",
    selectMarketDesc: "Select the stock market to analyze",

    // LLM Configuration
    llmSettings: "LLM Settings",
    quickThinkModel: "Quick Think Model",
    deepThinkModel: "Deep Think Model",
    embeddingModel: "Embedding Model",
    customModel: "Custom Model",
    customModelName: "Custom Model Name",
    customDeepThinkModelName: "Custom Deep Think Model Name",
    executeAnalysis: "Execute Analysis",
    otherCustomModel: "Other (Custom Model)",
    quickResponseModel: "Quick response model",
    complexReasoningModel: "Complex reasoning model",
    localModelNoApiKey: "🆓 Local model - No API Key needed",
    needsOpenAiApiKey: "☁️ Requires OpenAI API Key",

    // Depth levels
    depthShallow: "Shallow (1 round)",
    depthMedium: "Medium (2 rounds)",
    depthDeep: "Deep (3+ rounds)",

    // API Keys
    apiKeySection: "API Configuration",
    alphaVantageKey: "Alpha Vantage API Key",
    finmindKey: "FinMind API Key",

    // Ticker descriptions by market
    tickerDescUS: "Enter US stock symbol (e.g., NVDA, AAPL)",
    tickerDescTWSE: "Enter TWSE stock code (e.g., 2330, 2317)",
    tickerDescTPEX: "Enter TPEx stock code (e.g., 6488, 5765)",
    selectDate: "Select analysis date",
    selectDepth: "Select research depth",

    // Depth options
    depthShallowLabel: "Shallow - Quick research",
    depthMediumLabel: "Medium - Moderate discussion",
    depthDeepLabel: "Deep - In-depth research",

    // Validation messages
    validation: {
      tickerRequired: "Stock ticker is required",
      dateFormat: "Date format must be YYYY-MM-DD",
      selectOneAnalyst: "Please select at least one analyst",
      selectQuickThink: "Please select a quick think model",
      selectDeepThink: "Please select a deep think model",
      selectEmbedding: "Please select an embedding model",
      invalidUrl: "Please enter a valid URL",
    },
  },

  // Analysis results
  results: {
    title: "Analysis Results",
    detailedResults: "Detailed Analysis Results",
    analysisDate: "Analysis Date",
    ticker: "Ticker",
    date: "Date",
    summary: "Summary",
    recommendation: "Trading Recommendation",
    priceChart: "Price Chart",
    volumeChart: "Volume Chart",
    noData: "No data available",
    noResults: "No Analysis Results",
    runAnalysisFirst: "Please run analysis first",
    backToAnalysis: "Back to Analysis",
    backButton: "Back to Analysis",
    saveReport: "Save Report",
    saving: "Saving...",
    saved: "Saved",
    saveError: "Save failed, please try again",
    duplicateReport: "This report already exists (same ticker and date)",
    report: "Report",
    noReportGenerated: "No report generated for this analyst",
    notSelectedOrNoReport:
      "Analyst may not have been selected or did not produce a report",

    // Analyst tabs
    analysts: {
      market: "Market Analyst",
      marketDesc: "Technical analysis and market trends",
      social: "Social Media Analyst",
      socialDesc: "Social sentiment and market atmosphere",
      news: "News Analyst",
      newsDesc: "News events and impact analysis",
      fundamentals: "Fundamentals Analyst",
      fundamentalsDesc: "Financial data and fundamentals analysis",
      bull: "Bull Researcher",
      bullDesc: "Bullish views and investment arguments",
      bear: "Bear Researcher",
      bearDesc: "Bearish views and risk warnings",
      research_manager: "Research Manager",
      research_managerDesc: "Research team synthesis",
      trader: "Trader",
      traderDesc: "Trade execution plan and strategy",
      risky: "Aggressive Analyst",
      riskyDesc: "High risk/high return strategy",
      safe: "Conservative Analyst",
      safeDesc: "Prudent conservative strategy",
      neutral: "Neutral Analyst",
      neutralDesc: "Balanced neutral strategy",
      risk_manager: "Risk Manager",
      risk_managerDesc: "Risk management decision",
    },

    // Price chart section
    priceSection: {
      title: "Price Trend",
      growth: "Growth Rate",
      duration: "Duration",
      days: "days",
      startPrice: "Start Price",
      endPrice: "End Price",
      lineChart: "Line Chart",
      candlestick: "Candlestick",
    },
  },

  // Tabs
  tabs: {
    analysts: "Analysts",
    researchers: "Researchers",
    risk: "Risk Debate",
    managers: "Managers",
    trader: "Trader",
    overview: "Overview",
  },

  // Download
  download: {
    fullReport: "Download Full Analysis Report PDF",
    generating: "Generating Report...",
    failed: "Download failed, please try again",
    noReports: "No analyst reports available for download",
  },

  // History
  history: {
    title: "Analysis History",
    noHistory: "No analysis history yet",
    ticker: "Ticker",
    date: "Date",
    actions: "Actions",
    view: "View",
    downloadPdf: "Download PDF",
    delete: "Delete",
    confirmDelete: "Are you sure you want to delete this record?",
    deleted: "Record deleted successfully",
    searchPlaceholder: "Search by ticker...",
    refresh: "Refresh",
    loading: "Loading...",
    noReportsFor: "No analysis reports for",
    afterAnalysisSave:
      "After running analysis, you can save reports from the results page",
    analysisDate: "Analysis Date",
    savedAt: "Saved",
    decision: "Decision",
    downloading: "Downloading",
    confirmDeleteTitle: "Confirm Delete",
    confirmDeleteDesc:
      "Are you sure you want to delete the analysis report for",
    on: "on",
    cannotUndo: "This action cannot be undone.",
    cancel: "Cancel",
    deleting: "Deleting...",
    confirmDeleteBtn: "Confirm Delete",
  },

  // Errors
  errors: {
    required: "This field is required",
    invalidTicker: "Please enter a valid stock ticker",
    analysisError: "Analysis failed, please try again",
    networkError: "Network error, please check your connection",
    apiKeyMissing: "API key is not configured",
    selectOneAnalyst: "Please select at least one analyst",
    rateLimitExceeded: "Rate limit exceeded. Please wait and try again.",
  },

  // PDF Labels
  pdf: {
    coverTitle: "TradingAgentsX Analysis Report",
    coverSubtitle: "AI-Powered Multi-Perspective Investment Analysis",
    tocTitle: "Table of Contents",
    reportContent: "Report Content",
    priceChart: "Price Chart & Volume",
    priceStats: "Price Statistics",
    totalReturn: "Total Return",
    analysisPeriod: "Analysis Period",
    days: "days",
    startDate: "Start Date",
    endDate: "End Date",
    startPrice: "Start Price",
    endPrice: "End Price",
    item: "Item",
    value: "Value",
    chartFailed: "Chart generation failed",

    // Teams
    analystsTeam: "Analysts Team",
    researchTeam: "Research Team",
    tradingRiskTeam: "Trading & Risk Team",
    members: "members",
  },
};

export type TranslationKeys = typeof en;
