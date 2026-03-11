/**
 * Traditional Chinese translations for TradingAgentsX
 */
export const zhTW = {
  // Common
  common: {
    loading: "載入中...",
    error: "錯誤",
    save: "儲存",
    cancel: "取消",
    confirm: "確認",
    download: "下載",
    delete: "刪除",
    back: "返回",
    next: "下一步",
    submit: "送出",
    close: "關閉",
  },
  
  // Theme
  theme: {
    toggle: "切換主題",
    light: "亮色",
    dark: "暗色",
    system: "系統",
  },
  
  // Auth / Login
  auth: {
    login: "登入",
    logout: "登出",
    loggingOut: "登出中...",
    cloudSyncEnabled: "雲端同步已啟用",
    usingLocalStorage: "目前使用本地儲存",
    loginToSync: "登入 Google 帳號以同步 API 設定和歷史報告",
    loginSync: "登入同步",
  },
  nav: {
    home: "首頁",
    analysis: "分析",
    history: "歷史報告",
    settings: "設定",
    tagline: "多代理 LLM 金融交易框架",
  },

  // Home page
  home: {
    title: "TradingAgentsX",
    subtitle: "多代理 LLM 交易分析平台",
    description: "透過多代理 AI 協作，提供全面的投資分析與見解",
    startAnalysis: "開始分析",
    viewHistory: "查看歷史",
    
    // 核心特色
    coreFeatures: "🎯 核心特色",
    coreFeaturesDesc: "基於 LangGraph 的智能股票交易分析平台，結合多個 AI 代理進行協作決策",
    
    // 特色卡片
    features: {
      multiAgent: "多代理協作架構",
      multiAgentDesc: "12 個專業化 AI 代理團隊協同工作，模擬真實交易公司運作模式",
      multiModel: "多模型靈活支援",
      multiModelDesc: "支援 OpenAI、Claude、Gemini、Grok、DeepSeek、Qwen 等多家 LLM",
      customEndpoint: "自訂端點配置",
      customEndpointDesc: "完整支援自訂 API 端點，可連接任何 OpenAI 兼容的服務",
      fullAnalysis: "全方位市場分析",
      fullAnalysisDesc: "整合技術面、基本面、情緒面、新聞面四大維度分析",
      structuredDecision: "結構化決策流程",
      structuredDecisionDesc: "透過看漲/看跌辯論機制減少偏見，做出更理性的決策",
      longTermMemory: "長期記憶系統",
      longTermMemoryDesc: "使用 ChromaDB 向量資料庫儲存歷史決策，持續學習改進",
      modernUI: "現代化 Web 介面",
      modernUIDesc: "基於 Next.js 16 的響應式 UI，支援深色模式",
      oneClickDeploy: "一鍵部署",
      oneClickDeployDesc: "支援 Docker Compose 部署，快速啟動完整服務",
      reportDownload: "報告下載",
      reportDownloadDesc: "支援將完整分析報告匯出為 PDF，方便保存與分享",
    },
    
    // 12 位專業代理團隊
    professionalAgents: "👥 12 位專業代理團隊",
    professionalAgentsDesc: "每個代理都有其專業職責，協同工作產生高質量的交易決策",
    analystsTeamTitle: "📊 分析師團隊 (4 位)",
    researchTeamTitle: "🔍 研究團隊 (3 位)",
    tradingTeamTitle: "💼 交易團隊 (1 位)",
    riskTeamTitle: "🛡️ 風險管理團隊 (4 位)",
    
    // 工作流程
    workflowTitle: "🔄 分析師協作流程",
    workflowDescription: "四大分析師代理如何從不同資料來源收集資訊，並產生綜合分析報告",
    
    // 流程步驟
    processSteps: {
      dataCollection: { title: "資料收集階段", description: "從 yfinance、Reddit、RSS 等多源獲取股價、新聞、社群情緒數據" },
      analysts: { title: "分析師團隊平行分析", description: "市場、情緒、新聞、基本面四大分析師同時評估，產出專業報告" },
      researchers: { title: "研究團隊辯論", description: "看漲與看跌研究員進行結構化辯論，研究經理綜合雙方觀點" },
      trader: { title: "交易員整合分析", description: "審查所有分析師與研究團隊報告，制定具體交易執行計劃" },
      risk: { title: "風險管理評估", description: "激進、保守、中立三方風險分析師評估策略，風險經理做出風控決策" },
      finalDecision: { title: "最終決策輸出", description: "產生包含交易方向、倉位大小、風險控制的完整投資建議" },
    },
    
    // LLM 支援
    llmSupport: "🌍 多模型支援",
    llmSupportDesc: "支援業界領先的多家 LLM 提供商，每個模型可配置獨立的 API Key 和 Base URL",
    llmFeatures: "✅ 完整支援自訂端點 | ✅ 三層獨立配置（快速思維/深層思維/嵌入） | ✅ BYOK 模式",
    
    // 技術亮點
    techHighlights: "💡 技術亮點",
    dynamicResearch: "動態研究深度",
    dynamicResearchFeatures: ["淺層 (Shallow): 1 輪快速分析", "中等 (Medium): 2 輪平衡分析", "深層 (Deep): 3+ 輪全面分析"],
    memorySystem: "長期記憶系統",
    memorySystemFeatures: ["ChromaDB 向量資料庫", "歷史決策持久化", "持續學習與改進"],
    realTimeData: "實時資料整合",
    realTimeDataFeatures: ["yfinance: 即時股價數據", "Reddit API: 社群情緒", "Alpha Vantage: 財務資料"],
    fullApiSupport: "完整 API 支援",
    fullApiSupportFeatures: ["RESTful API 架構", "異步任務處理", "Swagger 互動文檔"],
    
    // CTA Section
    readyToStart: "準備好開始智能交易分析了嗎？",
    ctaDescription: "立即體驗 12 位專業 AI 代理協同工作，為您提供全方位的股票分析報告",
  },

  // Agents
  agents: {
    // Analysts
    market_analyst: "市場分析師",
    market_analyst_role: "技術分析",
    market_analyst_desc: "技術指標分析 (RSI, MACD, 布林通道)、價格走勢研判、支撐阻力位識別",
    
    social_analyst: "社群媒體分析師",
    social_analyst_role: "情緒分析",
    social_analyst_desc: "社群情緒監測、市場氛圍評估、熱門話題追蹤",
    
    news_analyst: "新聞分析師",
    news_analyst_role: "新聞分析",
    news_analyst_desc: "新聞事件追蹤、影響評估、資訊篩選與優先排序",
    
    fundamentals_analyst: "基本面分析師",
    fundamentals_analyst_role: "基本面分析",
    fundamentals_analyst_desc: "財務數據分析、估值指標、公司基本面評估",
    
    // Researchers
    bull_researcher: "看漲研究員",
    bull_researcher_role: "多頭分析",
    bull_researcher_desc: "識別上漲潛力、成長催化劑與看漲情境",
    
    bear_researcher: "看跌研究員",
    bear_researcher_role: "空頭分析",
    bear_researcher_desc: "識別下跌風險、警示信號與看跌情境",
    
    // Managers
    research_manager: "研究經理",
    research_manager_role: "研究整合",
    research_manager_desc: "整合多空論點，產出平衡的研究結論",
    
    risk_manager: "風險經理",
    risk_manager_role: "風險決策",
    risk_manager_desc: "最終風險評估與倉位規模建議",
    
    // Risk Debaters
    aggressive_debator: "激進分析師",
    aggressive_debator_role: "高風險高回報",
    aggressive_debator_desc: "主張較高風險倉位以追求更大潛在回報",
    
    conservative_debator: "保守分析師",
    conservative_debator_role: "資本保護",
    conservative_debator_desc: "主張較安全倉位以保護資本為優先",
    
    neutral_debator: "中立分析師",
    neutral_debator_role: "平衡觀點",
    neutral_debator_desc: "提供激進與保守之間的平衡觀點",
    
    // Trader
    trader: "交易員",
    trader_role: "交易執行",
    trader_desc: "制定最終交易建議，包含進場、出場與倉位規模",
  },

  // Flow Diagram
  flowDiagram: {
    // Layer titles
    layer1: "第一層：資料來源",
    layer2: "第二層：分析師代理 (4位)",
    layer3: "第三層：研究員代理 (2位)",
    layer4: "第四層：風險辯論者 (3位)",
    finalOutput: "最終輸出：12 份詳細報告",
    
    // Data sources
    stockData: "股價數據",
    socialSentiment: "社群情緒",
    newsInfo: "新聞資訊",
    financialData: "財務數據",
    
    // Arrow labels
    dataFetch: "資料擷取與清理",
    reportIntegration: "分析報告整合",
    researchPrep: "研究整合與辯論準備",
    riskDebate: "風險評估與管理",
    finalDecision: "制定最終交易決策",
    generateReport: "生成完整投資報告",
    
    // Agent descriptions
    technicalAnalysis: "技術面分析",
    sentimentAnalysis: "情緒面分析",
    newsAnalysis: "新聞面分析",
    fundamentalsAnalysis: "基本面分析",
    bullishResearch: "看多觀點研究",
    bearishResearch: "看空觀點研究",
    integrateViews: "整合多空研究觀點",
    highRiskReward: "高風險高報酬",
    balancedRisk: "平衡風險報酬",
    lowRiskVol: "低風險低波動",
    integrateRisk: "整合風險辯論結果",
    executeTrade: "執行最終交易決策",
    
    // Tasks
    rsiIndicator: "RSI 指標",
    macdMomentum: "MACD 動能",
    priceTrend: "價格走勢",
    nlpSentiment: "NLP 情緒",
    discussionHeat: "討論熱度",
    investorConfidence: "投資者信心",
    newsSummary: "新聞摘要",
    eventAssessment: "事件評估",
    impactPrediction: "影響預測",
    financialAnalysis: "財報分析",
    valuationMetrics: "估值指標",
    profitEvaluation: "盈利評估",
    positiveFactors: "正面因素分析",
    growthOpportunities: "成長機會評估",
    buyReasons: "買入理由整理",
    negativeFactors: "負面因素分析",
    riskAssessment: "風險評估",
    sellReasons: "賣出理由整理",
    balanceArguments: "平衡雙方論點",
    comprehensiveAdvice: "綜合投資建議",
    preliminaryStrategy: "制定初步策略",
    aggressiveStrategy: "積極投資策略",
    maximizeReturns: "最大化收益",
    calculatedRisk: "承擔計算風險",
    prudentStrategy: "穩健投資策略",
    riskBalance: "風險平衡",
    rationalDecision: "理性決策",
    conservativeStrategy: "保守投資策略",
    capitalProtection: "資本保護",
    riskReduction: "降低風險",
    riskRating: "風險等級評定",
    stopLossSettings: "止損止盈設定",
    finalRiskControl: "最終風險控制",
    
    // Outputs
    tradeSignal: "交易訊號 (BUY/SELL/HOLD)",
    targetPrice: "目標價位",
    tradeQuantity: "交易數量",
    riskParams: "風險參數",
    finalOutput_label: "最終輸出:",
    completeReportSet: "完整分析報告集合",
    comprehensiveSupport: "整合 12 位專業代理的深度分析，提供全方位投資決策支援",
    
    // Report sections
    analystReports: "分析師報告 (4份)",
    researchReports: "研究報告 (3份)",
    riskTrading: "風險與交易 (5份)",
    technicalReport: "技術面分析",
    sentimentReport: "社群情緒分析",
    newsReport: "新聞面分析",
    fundamentalsReport: "基本面分析",
    bullReport: "多頭研究報告",
    bearReport: "空頭研究報告",
    researchManagerReport: "研究經理整合",
    aggressiveEval: "激進策略評估",
    balancedEval: "中立策略評估",
    conservativeEval: "保守策略評估",
    riskManagerReport: "風險經理整合",
    finalTradeDecision: "最終交易決策",
    
    // Manager titles
    researchManager: "研究經理",
    riskManager: "風險經理",
    trader: "交易員",
  },

  // Analysis form
  form: {
    ticker: "股票代碼",
    tickerPlaceholder: "輸入股票代碼 (如 AAPL, 2330)",
    analysisDate: "分析日期",
    analysts: "分析師團隊",
    selectAnalysts: "選擇要啟用的分析師",
    selectAll: "全選",
    deselectAll: "取消全選",
    startAnalysis: "開始分析",
    analyzing: "分析中...",
    
    // Analysis page
    analysisTitle: "交易分析",
    analysisSubtitle: "配置並執行全面的多代理交易分析",
    analysisLoading: "正在執行分析... 這可能需要幾分鐘時間。",
    
    advancedOptions: "進階選項",
    researchDepth: "研究深度",
    riskDebateRounds: "風險辯論回合",
    
    // Market types
    marketType: "市場類型",
    usMarket: "美股",
    twseMarket: "台股上市",
    tpexMarket: "台股上櫃/興櫃",
    selectMarket: "選擇市場",
    selectMarketDesc: "選擇分析的股票市場",
    
    // LLM Configuration
    llmSettings: "LLM 設定",
    quickThinkModel: "快速思維模型",
    deepThinkModel: "深層思維模型", 
    embeddingModel: "嵌入式模型",
    customModel: "自訂模型",
    customModelName: "自訂模型名稱",
    customDeepThinkModelName: "自訂深層思維模型名稱",
    executeAnalysis: "執行分析",
    otherCustomModel: "Other（自訂模型）",
    quickResponseModel: "快速回應模型",
    complexReasoningModel: "複雜推理模型",
    localModelNoApiKey: "🆓 本地模型不需 API Key",
    needsOpenAiApiKey: "☁️ 需要 OpenAI API Key",
    
    // Depth levels
    depthShallow: "淺層 (1 輪)",
    depthMedium: "中等 (2 輪)",
    depthDeep: "深層 (3+ 輪)",
    
    // API Keys
    apiKeySection: "API 設定",
    alphaVantageKey: "Alpha Vantage API Key",
    finmindKey: "FinMind API Key",
    
    // Ticker descriptions by market
    tickerDescUS: "輸入美股代碼（例如：NVDA、AAPL）",
    tickerDescTWSE: "輸入上市股票代碼（例如：2330、2317）",
    tickerDescTPEX: "輸入上櫃/興櫃股票代碼（例如：6488、5765）",
    selectDate: "選擇分析日期",
    selectDepth: "選擇研究深度",
    
    // Depth options
    depthShallowLabel: "淺層 - 快速研究",
    depthMediumLabel: "中等 - 適度討論",
    depthDeepLabel: "深層 - 深入研究",
    
    // Validation messages
    validation: {
      tickerRequired: "股票代碼為必填",
      dateFormat: "日期格式必須為 YYYY-MM-DD",
      selectOneAnalyst: "請至少選擇一位分析師",
      selectQuickThink: "請選擇快速思維模型",
      selectDeepThink: "請選擇深層思維模型",
      selectEmbedding: "請選擇嵌入式模型",
      invalidUrl: "請輸入有效的 URL",
    },
  },

  // Analysis results
  results: {
    title: "分析結果",
    detailedResults: "詳細分析結果",
    analysisDate: "分析日期",
    ticker: "股票代碼",
    date: "日期",
    summary: "摘要",
    recommendation: "交易建議",
    priceChart: "價格走勢",
    volumeChart: "成交量",
    noData: "無資料",
    noResults: "沒有分析結果",
    runAnalysisFirst: "請先執行分析",
    backToAnalysis: "返回分析",
    backButton: "返回分析",
    saveReport: "儲存報告",
    saving: "儲存中...",
    saved: "已儲存",
    saveError: "儲存失敗，請稍後再試",
    duplicateReport: "此報告已存在（相同股票代碼與分析日期）",
    report: "報告",
    noReportGenerated: "此分析師沒有生成報告",
    notSelectedOrNoReport: "可能此分析師未被選擇或分析過程中未產生報告",
    
    // Analyst tabs
    analysts: {
      market: "市場分析師",
      marketDesc: "技術分析與市場趨勢評估",
      social: "社群媒體分析師",
      socialDesc: "社群情緒與市場氛圍分析",
      news: "新聞分析師",
      newsDesc: "新聞事件與影響分析",
      fundamentals: "基本面分析師",
      fundamentalsDesc: "財務數據與基本面分析",
      bull: "看漲研究員",
      bullDesc: "看漲觀點與投資論據",
      bear: "看跌研究員",
      bearDesc: "看跌觀點與風險警告",
      research_manager: "研究經理",
      research_managerDesc: "研究團隊綜合決策",
      trader: "交易員",
      traderDesc: "交易執行計劃與策略",
      risky: "激進分析師",
      riskyDesc: "高風險高回報策略分析",
      safe: "保守分析師",
      safeDesc: "穩健保守策略分析",
      neutral: "中立分析師",
      neutralDesc: "中立平衡策略分析",
      risk_manager: "風險經理",
      risk_managerDesc: "風險管理綜合決策",
    },
    
    // Price chart section
    priceSection: {
      title: "價格走勢",
      growth: "增長率",
      duration: "時長",
      days: "天",
      startPrice: "起始價格",
      endPrice: "結束價格",
      lineChart: "折線圖",
      candlestick: "平均K線圖",
    },
  },

  // Tabs
  tabs: {
    analysts: "分析師",
    researchers: "研究員",
    risk: "風險辯論",
    managers: "經理",
    trader: "交易員",
    overview: "總覽",
  },

  // Download
  download: {
    fullReport: "下載完整分析報告 PDF",
    generating: "生成報告中...",
    failed: "下載失敗，請稍後再試",
    noReports: "此報告沒有可下載的分析師報告",
  },

  // History
  history: {
    title: "分析歷史",
    noHistory: "尚無分析紀錄",
    ticker: "股票代碼",
    date: "日期",
    actions: "操作",
    view: "檢視",
    downloadPdf: "下載 PDF",
    delete: "刪除",
    confirmDelete: "確定要刪除這筆紀錄嗎？",
    deleted: "紀錄已刪除",
    searchPlaceholder: "搜尋股票代碼...",
    refresh: "重新整理",
    loading: "載入中...",
    noReportsFor: "尚無",
    afterAnalysisSave: "執行分析後，可在結果頁面儲存報告",
    analysisDate: "分析日期",
    savedAt: "儲存時間",
    decision: "決策",
    downloading: "下載中",
    confirmDeleteTitle: "確認刪除",
    confirmDeleteDesc: "確定要刪除",
    on: "於",
    cannotUndo: "此操作無法復原。",
    cancel: "取消",
    deleting: "刪除中...",
    confirmDeleteBtn: "確認刪除",
    syncing: "同步中...",
  },

  // Errors
  errors: {
    required: "此欄位為必填",
    invalidTicker: "請輸入有效的股票代碼",
    analysisError: "分析失敗，請稍後再試",
    networkError: "網路錯誤，請檢查連線",
    apiKeyMissing: "API 金鑰未設定",
    selectOneAnalyst: "請至少選擇一位分析師",
    rateLimitExceeded: "已達速率限制，請稍候再試",
  },

  // Settings / API Settings Dialog
  settings: {
    title: "API 配置",
    apiConfiguration: "API 配置",
    description: "設定您的 API 金鑰。這些資訊會以加密形式儲存在瀏覽器中。",
    encryptionEnabled: "🔒 已啟用 AES-256-GCM 加密保護",
    onlyFillNeeded: "💡 僅需填寫您選擇的模型供應商的 API。例如，若使用 Claude 模型，只需填寫 Claude API。",
    
    // Sections
    stockMarketApis: "股市資料 API（依分析市場選擇填寫）",
    llmProviders: "LLM 模型供應商（依選擇的模型填寫）",
    customEndpoint: "自訂端點（進階選項）",
    
    // Form labels
    finmindToken: "FinMind API Token（台股）",
    finmindPlaceholder: "輸入 FinMind Token",
    finmindDesc: "用於獲取台灣股市資料（在 finmindtrade.com 註冊取得）",
    alphaVantageKey: "Alpha Vantage API Key（美股）",
    alphaVantagePlaceholder: "輸入 Alpha Vantage API Key",
    alphaVantageDesc: "用於獲取美股基本面數據（分析美股時建議填寫）",
    openaiDesc: "用於 OpenAI 模型（GPT-4, GPT-5, o4 等）及 OpenAI 嵌入式模型",
    anthropicDesc: "用於 Claude 模型",
    googleDesc: "用於 Gemini 模型",
    grokDesc: "用於 Grok 模型",
    deepseekDesc: "用於 DeepSeek 模型",
    qwenDesc: "用於 Qwen 模型",
    customBaseUrl: "自訂 Base URL",
    customBaseUrlDesc: "若設定此項，將覆蓋所有模型的預設端點",
    customApiKey: "自訂端點 API Key",
    customApiKeyPlaceholder: "輸入自訂端點的 API Key",
    customApiKeyDesc: "配合自訂 Base URL 使用的 API Key",
    
    // Buttons and messages
    saveSettings: "儲存設定",
    clearSettings: "清除設定",
    processing: "處理中...",
    settingsSaved: "✓ 設定已成功儲存",
    
    // General settings (legacy)
    language: "語言",
    theme: "佈景主題",
    apiKey: "API 金鑰",
    apiKeyPlaceholder: "輸入您的 API 金鑰",
    configureApi: "設定 API",
  },

  // PDF Labels
  pdf: {
    coverTitle: "TradingAgentsX 分析報告",
    coverSubtitle: "AI 驅動的多角度投資分析",
    tocTitle: "目 錄",
    reportContent: "報告內容",
    priceChart: "價格走勢圖 & 交易量柱狀圖",
    priceStats: "價格統計",
    totalReturn: "總報酬率",
    analysisPeriod: "分析期間",
    days: "天",
    startDate: "開始日期",
    endDate: "結束日期",
    startPrice: "起始價格",
    endPrice: "結束價格",
    item: "項 目",
    value: "數 值",
    chartFailed: "圖表生成失敗",
    
    // Teams
    analystsTeam: "分析師團隊",
    researchTeam: "研究團隊",
    tradingRiskTeam: "交易與風險團隊",
    members: "位",
  },

  // Chat
  chat: {
    title: "報告問答",
    placeholder: "詢問有關此分析報告的問題...",
    send: "發送",
    thinking: "思考中...",
    error: "回覆失敗，請稍後再試",
    emptyState: "對此分析報告提出任何問題",
    emptyHint: "例如：「主要的風險因素有哪些？」",
    noApiKey: "請先在設定中配置您的 API Key",
    allReports: "全部報告",
    clearChat: "清除對話",
  },
};
