# TradingAgentsX - 多代理交易分析系統

<div align="center">

**基於 LangGraph 的智能股票交易分析平台，結合多個 AI 代理進行協作決策**

[![GitHub](https://img.shields.io/badge/GitHub-MarkLo127/TradingAgentsX-blue?logo=github)](https://github.com/MarkLo127/TradingAgentsX)
[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)](https://www.python.org/)
[![Next.js](https://img.shields.io/badge/Next.js-16-black?logo=next.js)](https://nextjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Latest-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)

[![Deploy on Railway](https://railway.app/button.svg)](https://tradingagentsx.up.railway.app)

</div>

## 📖 簡介

**TradingAgentsX** 是一個先進的多代理 AI 交易分析系統，模擬真實世界的交易公司運作模式。透過 LangGraph 編排多個專業化的 AI 代理（分析師、研究員、交易員、風險管理者），系統能夠從不同角度分析股票市場，並通過結構化的辯論與協作流程產生高質量的交易決策。

> 💡 **致敬原作**: 本專案基於 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) 進行改進和擴展，加入了完整的 Web 前端介面、RESTful API、Docker 部署支援等功能。並且支援台股上市櫃資料，感謝原作者的卓越工作和開源貢獻！

### 🎯 核心特色

- 🤖 **多代理協作架構** - 專業化的 AI 代理團隊協同工作
- 🌐 **多模型靈活支援** - 支援 OpenAI、Anthropic、Gemini、Grok、DeepSeek、Qwen 等多家 LLM 提供商
- 🔧 **自訂端點配置** - 完整支援自訂 API 端點，可連接任何 OpenAI 兼容的服務
- 📊 **全方位市場分析** - 完整支援**美股**與**台股**(FinMind)技術面、基本面、情緒面、新聞面分析
- 🔄 **結構化決策流程** - 透過看漲/看跌辯論機制減少偏見
- 🧠 **長期記憶系統** - 使用 ChromaDB 向量數據庫儲存歷史決策
- 🎨 **現代化 Web 介面** - 基於 Next.js 16 的響應式 UI
- 🔌 **RESTful API** - 完整的後端 API 支援
- 🐳 **一鍵部署** - 支援 Docker Compose 部署
- 🔑 **BYOK (Bring Your Own Key)** - 使用者自帶 API 金鑰，保障隱私與成本控制
- 💰 **JSON 轉 Toon 優化** - 將 JSON 數據轉換為 Toon 格式，大幅降低 API 調用開支 [TOON](https://github.com/toon-format/toon)
- ⬇️ **一鍵下載報告** - 支援將分析結果匯出為 JSON 檔案，方便保存與分享

---

## 🤖 LLM 模型支援

TradingAgentsX 支援業界領先的多家 LLM 提供商，並為每個模型配置**獨立的 API Key 和 Base URL**，實現最大靈活性。

<div align="center">

<p>
  <img src="llm_logo/openai.svg" alt="OpenAI" height="50" style="margin: 10px;"/>
  <img src="llm_logo/claude-color.svg" alt="Anthropic Claude" height="50" style="margin: 10px;"/>
  <img src="llm_logo/gemini-color.svg" alt="Google Gemini" height="50" style="margin: 10px;"/>
  <img src="llm_logo/grok.svg" alt="xAI Grok" height="50" style="margin: 10px;"/>
  <img src="llm_logo/deepseek-color.svg" alt="DeepSeek" height="50" style="margin: 10px;"/>
  <img src="llm_logo/qwen-color.svg" alt="Alibaba Qwen" height="50" style="margin: 10px;"/>
</p>

</div>

### 📋 支援的 LLM 提供商矩陣

| 提供商             | 支援模型                                                                                         | Base URL                                                  | 是否支援自訂端點 |
| ------------------ | ------------------------------------------------------------------------------------------------ | --------------------------------------------------------- | ---------------- |
| **OpenAI**         | GPT-5.1, GPT-5 Mini/Nano, GPT-4.1 Mini/Nano, o4-mini                                             | `https://api.openai.com/v1`                               | ✅ 是            |
| **Anthropic**      | Claude Haiku 4.5, Claude Sonnet 4.5/4.0, Claude 3.5 Haiku, Claude 3 Haiku                        | `https://api.anthropic.com/v1`                               | ✅ 是            |
| **Gemini**         | Gemini 2.5 Pro, Gemini 2.5 Flash, Gemini 2.5 Flash Lite, Gemini 2.0 Flash, Gemini 2.0 Flash Lite | `https://generativelanguage.googleapis.com/v1beta/openai` | ✅ 是            |
| **Grok (xAI)**     | Grok-4.1 Fast, Grok-4 Fast, Grok-4, Grok-3, Grok-3 Mini                                          | `https://api.x.ai/v1`                                     | ✅ 是            |
| **DeepSeek**       | DeepSeek Reasoner, DeepSeek Chat                                                                 | `https://api.deepseek.com/v1`                             | ✅ 是            |
| **Qwen (Alibaba)** | Qwen3-Max, Qwen-Plus, Qwen Flash                                                                 | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`  | ✅ 是            |
| **自訂端點**       | 上述列表中的模型                                                                                 | 使用者自訂                                                | ✅ 完全支援      |

### 🔧 三層獨立配置

系統支援**三個獨立的 LLM 配置點**，每個都可使用不同的提供商和 API Key：

#### 1️⃣ 快速思維模型 (Quick Thinking)

用於快速分析和即時回應（市場分析師、情緒分析師等）

#### 2️⃣ 深層思維模型 (Deep Thinking)

用於複雜推理和深度分析（研究團隊辯論、風險管理等）

#### 3️⃣ 嵌入模型 (Embedding)

用於向量記憶體系統（ChromaDB 嵌入生成）

**配置示例：**

```yaml
快速思維: OpenAI GPT-5 Mini @ api.openai.com
深層思維: Anthropic Claude Sonnet 4.5 @ api.anthropic.com/v1
嵌入模型: 自訂端點 @ your-custom-endpoint.com
```

### 🌍 自訂端點支援

**完整支援自訂 API 端點**，任何實現 OpenAI Chat Completions API 規範的服務都可以使用：

✅ **支援場景：**

- 私有化部署的 LLM 服務
- 第三方 OpenAI 兼容代理

**配置方式：**

1. 在前端表單的 Base URL 輸入框直接輸入自訂 URL
2. 填入對應的 API Key
3. 系統自動使用您的端點進行推理

---

## 🏗️ 系統架構

TradingAgentsX 採用前後端分離架構，後端使用 FastAPI 提供 RESTful API，前端使用 Next.js 打造現代化的使用者介面。

### 📂 專案結構概覽

```
TradingAgentsX/
├── backend/                   # FastAPI 後端服務
│   ├── __main__.py           # 後端應用入口
│   ├── requirements.txt      # Python 依賴列表
│   └── app/
│       ├── main.py           # FastAPI 應用主程式
│       ├── api/              # API 路由層
│       │   ├── routes.py     # API 端點定義
│       │   └── dependencies.py  # 依賴注入
│       ├── core/             # 核心配置
│       │   ├──config.py     # 環境變數與設定
│       │   └── cors.py       # CORS 中間件配置
│       ├── models/           # 資料模型
│       │   └── schemas.py    # Pydantic 資料結構
│       └── services/         # 業務邏輯層
│           ├── trading_service.py  # TradingAgentsX 核心整合
│           └── task_manager.py    # 異步任務管理

├── frontend/                  # Next.js 前端應用
│   ├── app/                  # Next.js App Router
│   │   ├── layout.tsx        # 根佈局組件
│   │   ├── page.tsx          # 首頁
│   │   └── analysis/         # 分析功能模組
│   │       ├── page.tsx      # 分析配置頁面
│   │       └── results/      # 分析結果展示頁面
│   ├── components/           # React 組件庫
│   │   ├── analysis/         # 分析相關組件
│   │   │   ├── AnalysisForm.tsx    # 參數配置表單
│   │   │   ├── TradingDecision.tsx # 交易決策卡片
│   │   │   ├── AnalystReport.tsx   # 分析師報告展示
│   │   │   └── PriceChart.tsx      # 股價圖表組件
│   │   ├── layout/           # 佈局組件
│   │   │   ├── Header.tsx    # 頂部導航欄
│   │   │   └── Footer.tsx    # 頁腳
│   │   └── ui/               # shadcn/ui 基礎組件
│   ├── hooks/                # 自定義 React Hooks
│   │   ├── useAnalysis.ts    # 分析請求管理
│   │   └── useConfig.ts      # 配置資料獲取
│   └── lib/                  # 工具函式庫
│       ├── api.ts            # API 客戶端封裝
│       ├── types.ts          # TypeScript 型別定義
│       └── utils.ts          # 通用輔助函式

└── tradingagents/            # 核心 Python 套件
    ├── agents/               # AI 代理定義
    ├── dataflows/            # 資料流處理
    ├── graph/                # LangGraph 工作流
    └── default_config.py     # 預設配置
```

### 🔧 後端技術棧

| 技術              | 用途                   | 版本     |
| ----------------- | ---------------------- | -------- |
| **FastAPI**       | 現代化異步 Web 框架    | ≥0.104.0 |
| **Pydantic**      | 資料驗證與序列化       | ≥2.9.0   |
| **LangGraph**     | 多代理工作流編排引擎   | ≥0.4.8   |
| **LangChain**     | LLM 應用開發框架       | Latest   |
| **ChromaDB**      | 向量資料庫（記憶系統） | ≥1.0.12  |
| **yfinance**      | 股票市場資料獲取       | ≥0.2.63  |
| **Uvicorn**       | ASGI 伺服器            | ≥0.24.0  |
| **python-dotenv** | 環境變數管理           | 1.0.0    |
| **Redis**         | 任務隊列與緩存         | Latest   |

#### 其他整合

- **stockstats**: 技術指標計算
- **feedparser**: RSS 新聞抓取
- **praw**: Reddit 社群情緒分析
- **finnhub-python**: 金融資料 API
- **beautifulsoup4**: 網頁內容解析

### 🎨 前端技術棧

| 技術                | 用途                       | 版本   |
| ------------------- | -------------------------- | ------ |
| **Next.js**         | React 全端框架             | 16.x   |
| **TypeScript**      | 靜態型別檢查               | Latest |
| **Tailwind CSS**    | 實用優先的 CSS 框架        | Latest |
| **shadcn/ui**       | 可高度客製化的 UI 組件庫   | Latest |
| **React Hook Form** | 高效能表單管理             | Latest |
| **Zod**             | TypeScript 優先的結構驗證  | Latest |
| **Recharts**        | 資料視覺化圖表庫           | Latest |
| **Axios**           | Promise 基礎的 HTTP 客戶端 | Latest |
| **react-markdown**  | Markdown 內容渲染          | Latest |

---

## 🚀 快速開始

### 📋 前置要求

在開始之前，請確保您的系統已安裝以下軟體：

- **Python** 3.10 或更高版本
- **Node.js** 18.x 或更高版本
- **pnpm** 最新版本（推薦）或 npm
- **Conda** (可選，但強烈推薦用於 Python 環境管理)
- **Git** 用於克隆專案

#### 必要的 API 金鑰

根據您選擇的 LLM 提供商，準備相應的 API 金鑰：

- **OpenAI API Key** - GPT 系列模型
  - 申請網址: https://platform.openai.com/api-keys
- **Anthropic API Key** - Claude 系列模型
  - 申請網址: https://console.anthropic.com
- **Grok API Key** - Grok 系列模型
  - 申請網址: https://console.x.ai
- **DeepSeek API Key** - DeepSeek 系列模型
  - 申請網址: https://platform.deepseek.com
- **Qwen API Key** - Qwen 系列模型
  - 申請網址: https://www.alibabacloud.com
- **Alpha Vantage API Key** (必需) - 美股基本面資料
  - 申請網址: https://www.alphavantage.co/support/#api-key
- **FinMind API Key** (選填) - 台股上市櫃資料
  - 申請網址: https://finmindtrade.com/

> 💡 **提示**: 本系統採用 BYOK (Bring Your Own Key) 模式，您可以在前端介面直接輸入 API 金鑰，無需設定環境變數（適合快速測試）。

### 📥 安裝步驟

#### 1️⃣ 克隆專案

```bash
git clone https://github.com/MarkLo127/TradingAgentsX.git
cd TradingAgentsX
```

#### 2️⃣ 後端設置

##### 2.1 創建 Python 虛擬環境

**使用 Conda (推薦)**

```bash
conda create -n tradingagents python=3.13
conda activate tradingagents
```

**或使用 venv**

```bash
python3 -m venv tradingagents
source tradingagents/bin/activate  # macOS/Linux
# 或
tradingagents\Scripts\activate  # Windows
```

##### 2.2 安裝 Python 依賴

```bash
# 安裝 TradingAgentsX 核心套件
pip install -e .

# 安裝後端 API 依賴
pip install -r backend/requirements.txt
```

##### 2.3 配置環境變數（可選）

複製範例環境變數檔案並編輯：

```bash
cp .env.example .env
```

編輯 `.env` 檔案，填入您的 API 金鑰：

```bash
# ============ LLM API 金鑰配置 ============
# OpenAI (可選 - 可在前端直接輸入)
OPENAI_API_KEY=sk-your-openai-api-key-here

# Anthropic Claude (可選)
ANTHROPIC_API_KEY=sk-ant-your-claude-key

# Grok / xAI (可選)
XAI_API_KEY=your-grok-key

# DeepSeek (可選)
DEEPSEEK_API_KEY=your-deepseek-key

# Qwen / Alibaba Cloud (可選)
DASHSCOPE_API_KEY=your-qwen-key

# Alpha Vantage (強烈建議 - 用於美股基本面數據)
ALPHA_VANTAGE_API_KEY=your-alpha-vantage-key

# FinMind (選填 - 用於台股數據)
FINMIND_API_KEY=your-finmind-key

# ============ 後端服務配置 ============
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000

# ============ CORS 配置 ============
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

# ============ 資料儲存配置 ============
TRADINGAGENTS_RESULTS_DIR=./results
```

> 📝 **注意**: 環境變數中的 API Key 為可選配置。您可以在前端表單中直接輸入，系統會優先使用前端輸入的 Key。

##### 2.4 啟動後端服務

```bash
# 從專案根目錄執行
python -m backend
```

✅ 後端服務成功啟動後，您可以訪問：

- **應用根目錄**: http://localhost:8000
- **API 互動式文檔 (Swagger UI)**: http://localhost:8000/docs
- **API 文檔 (ReDoc)**: http://localhost:8000/redoc
- **健康檢查端點**: http://localhost:8000/api/health

#### 3️⃣ 前端設置

##### 3.1 安裝前端依賴

```bash
# 使用 pnpm (推薦)
pnpm -C frontend install

# 或使用 npm
npm --prefix frontend install
```

##### 3.2 配置前端環境變數 (可選)

如果您需要自訂 API 端點，可以建立 `frontend/.env.local`：

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

> 💡 預設情況下，前端會自動連接到 `http://localhost:8000`

##### 3.3 啟動前端開發伺服器

```bash
# 使用 pnpm (推薦)
pnpm -C frontend dev

# 或使用 npm
npm --prefix frontend run dev
```

✅ 前端應用成功啟動後，訪問：

- **應用首頁**: http://localhost:3000

---

## 🐳 部署方案

### Docker Compose 本地部署

最簡單的部署方式，一鍵啟動前後端服務：

**前置要求：**

- Docker Engine 20.10+
- Docker Compose V2

**部署步驟：**

```bash
# 1. 確保 .env 文件已配置（至少包含 Alpha Vantage API Key）
cp .env.example .env
# 編輯 .env，填入必要的 API 金鑰

# 2. 啟動所有服務（首次執行會自動構建映像）
docker compose up -d --build

# 3. 查看服務運行狀態
docker compose ps

# 4. 查看即時日誌
docker compose logs -f

# 5. 查看特定服務日誌
docker compose logs -f backend
docker compose logs -f frontend

# 停止服務
docker compose down

# 停止服務並清除資料卷
docker compose down -v
```

**Docker Compose 配置說明**：

- 後端服務運行於: `http://localhost:8000`
- 前端服務運行於: `http://localhost:3000`
- 分析結果會持久化儲存在 `./results` 目錄
- 環境變數從 `.env` 文件自動載入

---

## 📱 使用指南

### 基本工作流程

1. **訪問首頁**

   - 開啟瀏覽器，訪問 http://localhost:3000
   - 查看系統介紹與功能說明

2. **進入分析頁面**

   - 點擊首頁的「開始分析」按鈕
   - 或直接訪問 http://localhost:3000/analysis

3. **配置分析參數**

   #### 📊 基本設定

   - **選擇分析師團隊**: 勾選您需要的分析師類型

     - ✅ 市場分析師 (Market Analyst) - 技術分析與價格走勢
     - ✅ 情緒分析師 (Sentiment Analyst) - 社交媒體情緒評估
     - ✅ 新聞分析師 (News Analyst) - 新聞事件影響分析
     - ✅ 基本面分析師 (Fundamental Analyst) - 財務數據與估值分析

   - **輸入股票代碼**: 例如 `NVDA`, `AAPL`, `TSLA`, `GOOGL`

     - 支援美股股票代號

   - **選擇分析日期**: 選擇要分析的特定日期

     - 預設為當前日期

   - **設定研究深度**:
     - 🟢 **淺層 (Shallow)**: 快速分析，適合即時決策
     - 🟡 **中等 (Medium)**: 平衡速度與深度
     - 🔴 **深層 (Deep)**: 全面深入分析，耗時較長

   #### 🤖 LLM 模型配置

   系統提供**三個獨立的 LLM 配置選項**，每個都可使用不同的提供商：

   **1. 快速思維模型配置**

   - **模型選擇**: 從下拉選單選擇模型（OpenAI, Anthropic, Grok, DeepSeek, Qwen）
   - **Base URL**: 直接輸入自訂端點 URL（例如：`https://api.your-custom-endpoint.com/v1`）
   - **API Key**: 輸入對應的 API 金鑰

   **2. 深層思維模型配置**

   - **模型選擇**: 可選擇與快速思維不同的模型
   - **Base URL**: 支援不同的端點
   - **API Key**: 支援不同的金鑰

   **3. 嵌入模型配置**

   - **Base URL**: 下拉選擇 OpenAI 或自訂端點
   - **API Key**: 若留空則使用環境變數 `OPENAI_API_KEY`

   **配置示例：**

   ```
   快速思維模型: gpt-5-mini
   快速思維 Base URL: https://api.openai.com/v1
   快速思維 API Key: sk-your-openai-key

   深層思維模型: claude-sonnet-4-5
   深層思維 Base URL: https://api.anthropic.com/v1
   深層思維 API Key: sk-ant-your-claude-key

   嵌入模型 Base URL: 自訂 → https://api.your-embedding-service.com/v1
   嵌入模型 API Key: your-embedding-key
   ```

   > 💡 **靈活性**: 您可以混合使用不同提供商的模型，例如用 OpenAI 做快速分析，用 Claude 做深度推理，用自訂端點做嵌入生成。

   #### 🔑 API 金鑰配置

   - **Alpha Vantage API Key** (必填): 用於獲取美股基本面數據
   - **FinMind API Key** (選填): 用於獲取台股數據
   - 如未在環境變數中配置 LLM API Key，需在此填入

4. **執行分析**

   - 檢查所有參數無誤後，點擊「執行分析」按鈕
   - 系統會顯示載入動畫，處理時間依研究深度而定（1-5 分鐘）

5. **查看分析結果**

   - 分析完成後自動跳轉至結果頁面
   - 結果包含以下內容：

   **📊 交易決策摘要**

   - 最終決策: BUY / SELL / HOLD
   - 建議倉位大小
   - 風險等級評估
   - 核心理由總結

   **📈 股價走勢圖表**

   - 互動式價格圖表（支援折線圖/K 線圖切換）
   - 交易量變化
   - 關鍵技術指標

   **📄 各分析師詳細報告**

   系統提供 **12 個專業代理** 的完整分析報告，分為四大團隊：

   **分析師團隊 (4)**

   - 市場分析師: 技術面分析與趨勢判斷
   - 社群媒體分析師: 社群媒體情緒指標
   - 新聞分析師: 最新新聞事件影響評估
   - 基本面分析師: 財務健康度與估值分析

   **研究團隊 (3)**

   - 看漲研究員: 多頭觀點論證與上漲催化劑分析
   - 看跌研究員: 空頭觀點論證與下跌風險警告
   - 研究經理: 綜合看漲與看跌觀點的研究決策

   **交易團隊 (1)**

   - 交易員: 整合所有報告的交易執行計劃

   **風險管理團隊 (4)**

   - 激進分析師: 高風險高回報策略分析
   - 保守分析師: 穩健保守策略與風險控制
   - 中立分析師: 中立平衡策略評估
   - 風險經理: 風險管理綜合決策與最終建議

### API 使用範例

如果您想要透過 API 整合 TradingAgentsX，可以參考以下範例：

#### 健康檢查

```bash
curl http://localhost:8000/api/health
```

#### 執行股票分析（使用自訂端點）

```bash
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "ticker": "NVDA",
    "analysis_date": "2024-01-15",
    "research_depth": 2,
    "deep_think_llm": "claude-sonnet-4-5",
    "quick_think_llm": "gpt-5-mini",
    "analysts": ["market", "sentiment", "news", "fundamental"],
    "quick_think_base_url": "https://api.openai.com/v1",
    "deep_think_base_url": "https://api.anthropic.com/v1",
    "embedding_base_url": "https://api.openai.com/v1",
    "quick_think_api_key": "sk-your-openai-key",
    "deep_think_api_key": "sk-ant-your-claude-key",
    "embedding_api_key": "sk-your-embedding-key",
    "alpha_vantage_api_key": "your-alpha-vantage-key"
  }'
```

#### 獲取股價資料

```bash
curl "http://localhost:8000/api/price-data/NVDA?start_date=2024-01-01&end_date=2024-01-31"
```

完整的 API 文檔請訪問: http://localhost:8000/docs

---

## 🧠 核心功能詳解

### 多代理協作系統

TradingAgentsX 模擬真實交易公司的組織架構，每個代理都有其專業職責：

| 代理角色         | 主要職責 | 輸出內容                                              |
| ---------------- | -------- | ----------------------------------------------------- |
| **市場分析師**   | 技術分析 | 技術指標（RSI, MACD, 布林通道）、價格走勢、支撐阻力位 |
| **情緒分析師**   | 情緒評估 | Reddit/Twitter 情緒指標、熱度趨勢、投資者信心指數     |
| **新聞分析師**   | 新聞分析 | 最新新聞摘要、事件影響評估、市場反應預測              |
| **基本面分析師** | 財務分析 | 財報數據、估值指標（P/E, P/B）、盈利能力評估          |
| **看漲研究員**   | 多頭論證 | 看漲理由、上漲催化劑、目標價位                        |
| **看跌研究員**   | 空頭論證 | 看跌理由、下跌風險、防守策略                          |
| **交易員**       | 決策整合 | 綜合所有報告，制定交易計劃                            |
| **風險管理**     | 風險控制 | 風險評估、倉位建議、止損止盈設定                      |
| **投資組合經理** | 最終決策 | 最終交易決定（批准/拒絕），執行指令                   |

### 工作流程圖

```
┌─────────────────┐
│  使用者輸入參數   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  資料收集階段    │ ◄── yfinance, Reddit, RSS
└────────┬────────┘
         │
         ▼
┌──────────────────────────────┐
│     分析師團隊平行分析        │
│  ┌────┬────┬────┬────────┐ │
│  │市場│情緒│新聞│基本面│ │
│  └────┴────┴────┴────────┘ │
└────────┬─────────────────────┘
         │
         ▼
┌─────────────────┐
│  研究團隊辯論    │
│  看漲 vs 看跌   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  交易員整合分析  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  風險管理評估    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 投資組合經理決策 │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  輸出最終報告    │
└─────────────────┘
```

### 智能特性

#### 1. 動態研究深度調整

- **Shallow (1)**: 每個代理進行 1 輪分析，適合快速決策
- **Medium (2)**: 每個代理進行 2 輪分析，平衡深度與速度
- **Deep (3+)**: 每個代理進行 3+ 輪分析，全面深入研究

#### 2. 長期記憶系統

- 使用 ChromaDB 向量資料庫儲存歷史決策
- 代理可以參考過去類似情況的決策
- 持續學習與改進分析品質

#### 3. 結構化輸出

- 所有報告均採用 Markdown 格式
- 清晰的章節結構
- 支援表格、列表、程式碼區塊等豐富格式

#### 4. 實時資料整合

- yfinance: 即時股價與歷史資料
- Reddit API: 社群情緒分析
- RSS Feeds: 財經新聞抓取
- Alpha Vantage: 美股詳細財務資料（必需）
- FinMind: 台股上市櫃資料 integration (https://finmindtrade.com)

---

## 📸 應用截圖

### 首頁 - 系統介紹

展示 TradingAgentsX 的核心功能與多代理協作工作流程

![首頁](web_screenshot/1.png)

---

### 分析配置頁面

直觀的表單介面，支援完整的 LLM 多模型配置與自訂端點設定

![分析配置頁面](web_screenshot/2.png)

---

### 代理觀點選擇

**12 個專業代理標籤**，點擊可切換查看不同代理的分析報告：

- **分析師團隊 (4)**: 市場分析師、社群媒體分析師、新聞分析師、基本面分析師
- **研究團隊 (3)**: 看漲研究員、看跌研究員、研究經理
- **交易團隊 (1)**: 交易員
- **風險管理團隊 (4)**: 激進分析師、保守分析師、中立分析師、風險經理

![代理觀點選擇](web_screenshot/3.png)

---

### 股價走勢圖表 (K 線圖)

互動式價格走勢與成交量圖表(K 線圖)，清晰呈現股票歷史數據

![股價走勢圖表 - K線圖](web_screenshot/4.png)

---

### 股價走勢圖表 (折線圖)

互動式價格走勢與成交量圖表(折線圖)，清晰呈現股票歷史數據

![股價走勢圖表 - 折線圖](web_screenshot/5.png)

---

### 市場分析師報告

技術面深度分析，包含技術指標、價格走勢、支撐阻力位評估

![市場分析師報告](web_screenshot/6.png)

---

### 社群媒體分析師報告

社交媒體情緒指標與投資者信心評估

![社群媒體分析師報告](web_screenshot/7.png)

---

### 新聞分析師報告

最新財經新聞摘要與事件影響分析

![新聞分析師報告](web_screenshot/8.png)

---

### 基本面分析師報告

詳細的財務數據解析與價值評估

![基本面分析師報告](web_screenshot/9.png)

---

### 看漲研究員報告

多頭觀點論證、上漲催化劑分析與目標價位預測

![看漲研究員報告](web_screenshot/10.png)

---

### 看跌研究員報告

空頭觀點論證、下跌風險警告與防守策略建議

![看跌研究員報告](web_screenshot/11.png)

---

### 研究經理報告

綜合看漲與看跌觀點的研究團隊決策

![研究經理報告](web_screenshot/12.png)

---

### 交易員報告

整合所有分析師報告後的交易執行計劃與策略

![交易員報告](web_screenshot/13.png)

---

### 激進分析師報告

高風險高回報策略的分析與評估

![激進分析師報告](web_screenshot/14.png)

---

### 保守分析師報告

穩健保守策略的分析與風險控制建議

![保守分析師報告](web_screenshot/15.png)

---

### 中立分析師報告

中立平衡策略的分析與風險評估

![中立分析師報告](web_screenshot/16.png)

---

### 風險經理報告

風險管理團隊的綜合決策與最終交易建議

![風險經理報告](web_screenshot/17.png)

---

### 下載報告

![下載報告](web_screenshot/18.png)

---

## 🙏 致謝

### 特別感謝

本專案基於 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) 的原始專案進行改進和擴展。衷心感謝原作者創建了如此優秀的多代理交易分析框架，為我們提供了堅實的基礎。

### 使用的開源專案

本專案使用了以下優秀的開源專案：

- [LangChain](https://github.com/langchain-ai/langchain) - LLM 應用開發框架
- [LangGraph](https://github.com/langchain-ai/langgraph) - 多代理工作流編排
- [FastAPI](https://github.com/tiangolo/fastapi) - 現代化 Python Web 框架
- [Next.js](https://github.com/vercel/next.js) - React 全端框架
- [shadcn/ui](https://github.com/shadcn/ui) - 精美的 React 組件庫
- [ChromaDB](https://github.com/chroma-core/chroma) - AI 原生向量資料庫
- [yfinance](https://github.com/ranaroussi/yfinance) - Yahoo Finance 資料下載工具

---

## 📄 License

本專案採用 Apache 2.0 許可證 - 查看 [LICENSE](LICENSE) 文件了解詳情。
