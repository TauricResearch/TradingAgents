# TradingAgentsX - 多代理智能交易分析系統

<div align="center">

<img src="frontend/public/icon.png" alt="TradingAgentsX Logo" width="150" />

**基於 LangGraph 的 AI 股票交易分析平台，結合多個專業 AI 代理進行協作決策**

[![GitHub](https://img.shields.io/badge/GitHub-MarkLo127/TradingAgentsX-blue?logo=github)](https://github.com/MarkLo127/TradingAgentsX)
[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)](https://www.python.org/)
[![Next.js](https://img.shields.io/badge/Next.js-16-black?logo=next.js)](https://nextjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Latest-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)

[![Deploy on Railway](https://railway.app/button.svg)](https://tradingagentsx.up.railway.app)

</div>

---

## 📖 簡介

**TradingAgentsX** 是一個先進的多代理 AI 交易分析系統，模擬真實世界的交易公司運作模式。透過 LangGraph 編排多個專業化的 AI 代理（分析師、研究員、交易員、風險管理者），系統能夠從不同角度分析股票市場，並通過結構化的辯論與協作流程產生高質量的交易決策。

> 💡 **致敬原作**: 本專案基於 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) 進行改進和擴展。

### 🎯 核心特色

| 功能 | 說明 |
|------|------|
| 🤖 **多代理協作架構** | 12 個專業化 AI 代理（分析師、研究員、交易員、風險管理）協同工作 |
| 🌐 **多模型支援** | OpenAI、Anthropic、Gemini、Grok、DeepSeek、Qwen 等 LLM 提供商 |
| 🔒 **Google OAuth 登入** | 雲端同步 API 設定與歷史報告，支援多裝置同步 |
| 📊 **美股與台股支援** | 完整支援美股（Yahoo Finance）與台股（FinMind）資料 |
| 🔑 **BYOK 模式** | 使用者自帶 API 金鑰，前端加密儲存，保障隱私 |
| 🛡️ **安全防護** | Rate Limiting、Security Headers、API Key 遮罩 |
| 📱 **響應式設計** | 支援桌面與手機瀏覽器 |
| 🐳 **Docker 部署** | 一鍵啟動前後端服務 |

---

## 🏗️ 系統架構

```
TradingAgentsX/
├── frontend/                 # Next.js 16 前端應用
│   ├── app/                  # App Router 頁面
│   │   ├── page.tsx          # 首頁
│   │   ├── analysis/         # 分析功能
│   │   ├── history/          # 歷史報告
│   │   ├── auth/             # OAuth 回調
│   │   └── api/              # API 路由（config, auth）
│   ├── components/           # React 組件
│   │   ├── analysis/         # 分析相關組件
│   │   ├── auth/             # 登入按鈕、登入提示
│   │   ├── layout/           # Header、Footer
│   │   ├── settings/         # API 設定對話框
│   │   └── ui/               # shadcn/ui 基礎組件
│   ├── contexts/             # React Context（認證狀態）
│   ├── hooks/                # 自定義 Hooks
│   └── lib/                  # 工具函式（API、加密、儲存）
│
├── backend/                  # FastAPI 後端服務
│   └── app/
│       ├── main.py           # 應用入口（中間件、路由）
│       ├── api/              # API 路由
│       │   ├── routes.py     # 分析 API
│       │   ├── auth.py       # Google OAuth
│       │   └── user.py       # 使用者資料同步
│       ├── core/             # 配置、CORS
│       ├── db/               # PostgreSQL 資料庫
│       ├── models/           # Pydantic 模型
│       └── services/         # 業務邏輯
│
└── tradingagents/           # 核心 AI 代理套件
    ├── agents/               # AI 代理定義
    │   ├── analysts/         # 分析師團隊
    │   ├── researchers/      # 研究團隊
    │   ├── trader/           # 交易員
    │   ├── risk_mgmt/        # 風險管理團隊
    │   └── managers/         # 經理決策者
    ├── dataflows/            # 資料獲取與處理
    ├── graph/                # LangGraph 工作流
    └── default_config.py     # 預設配置
```

---

## 🤖 AI 代理團隊

### 分析師團隊 (4 位)
| 代理 | 職責 | 輸出 |
|------|------|------|
| 市場分析師 | 技術分析 | RSI、MACD、布林通道、支撐阻力位 |
| 社群媒體分析師 | 情緒評估 | Reddit/Twitter 情緒指標、投資者信心 |
| 新聞分析師 | 新聞分析 | 最新新聞摘要、事件影響評估 |
| 基本面分析師 | 財務分析 | 財報數據、P/E、P/B、盈利能力 |

### 研究團隊 (3 位)
| 代理 | 職責 |
|------|------|
| 看漲研究員 | 多頭觀點論證、上漲催化劑分析 |
| 看跌研究員 | 空頭觀點論證、下跌風險警告 |
| 研究經理 | 綜合看漲與看跌觀點的決策 |

### 交易與風險團隊 (5 位)
| 代理 | 職責 |
|------|------|
| 交易員 | 整合所有報告，制定交易計劃 |
| 激進分析師 | 高風險高回報策略分析 |
| 保守分析師 | 穩健保守策略與風險控制 |
| 中立分析師 | 中立平衡策略評估 |
| 風險經理 | 風險管理綜合決策與最終建議 |

---

## 🚀 快速開始

### 前置要求

- **Python** 3.10+
- **Node.js** 18.x+
- **pnpm** 或 npm

### 必要的 API 金鑰

| API | 用途 | 申請網址 |
|-----|------|----------|
| OpenAI | GPT 模型 | https://platform.openai.com/api-keys |
| Alpha Vantage（選填） | 美股基本面資料 | https://www.alphavantage.co/support/#api-key |
| FinMind（選填） | 台股資料 | https://finmindtrade.com/ |

### 安裝步驟

#### 1️⃣ 克隆專案

```bash
git clone https://github.com/MarkLo127/TradingAgentsX.git
cd TradingAgentsX
```

#### 2️⃣ 後端設置

```bash
# 創建虛擬環境
conda create -n tradingagents python=3.13
conda activate tradingagents

# 安裝依賴
pip install -e .
pip install -r backend/requirements.txt

# 配置環境變數
cp .env.example .env
# 編輯 .env 填入 API 金鑰

# 啟動後端
python -m backend
```

後端服務：
- API: http://localhost:8000
- Swagger 文檔: http://localhost:8000/docs

#### 3️⃣ 前端設置

```bash
# 安裝依賴
pnpm -C frontend install

# 啟動開發伺服器
pnpm -C frontend dev
```

前端應用: http://localhost:3000

---

## 🐳 Docker 部署

```bash
# 配置環境變數
cp .env.example .env

# 啟動服務
docker compose up -d --build

# 查看日誌
docker compose logs -f

# 停止服務
docker compose down -v
```

服務端口：
- 後端: http://localhost:8000
- 前端: http://localhost:3000

---

## 🔒 安全特性

### 本地開發 vs 生產環境

| 功能 | 本地開發 (localhost) | 生產環境 (Railway 等) |
|------|----------------------|----------------------|
| Google 登入 | 選用（可不設定） | 建議啟用 |
| 資料自動清除 | ❌ 不會清除 | ✅ 未登入時離開會清除 |
| PostgreSQL | 選用 | 必需 |
| API 設定儲存 | 永久保留 | 登入後雲端同步 |
| 歷史報告儲存 | 永久保留 | 登入後雲端同步 |

### 前端安全

- **API Key 加密儲存** - 使用 AES-GCM 加密 localStorage 中的敏感資料
- **自動清除（僅生產環境）** - 未登入用戶離開頁面時自動清除本地資料
- **Safari 觸控優化** - 修復 iOS Safari 的觸控事件問題

### 後端安全
- **Rate Limiting** - 每分鐘 30 次請求限制
- **Security Headers** - X-Content-Type-Options、X-Frame-Options 等
- **敏感資料遮罩** - API Key 在日誌中自動遮罩
- **CORS 配置** - 限制跨域請求來源

### 雲端同步
- **Google OAuth 2.0** - 安全的第三方登入
- **JWT Token** - 無狀態認證
- **雲端備份** - API 設定與歷史報告同步到伺服器

---

## 📱 使用指南

### 1. 配置 API 金鑰
點擊右上角「設定」按鈕，輸入您的 API 金鑰。

### 2. 選擇分析參數
- **市場類型**: 美股 / 台股上市 / 台股上櫃
- **股票代碼**: 如 NVDA、2330
- **分析師團隊**: 選擇需要的分析師
- **研究深度**: 淺層（快速）/ 中等 / 深層（詳細）
- **LLM 模型**: 快速思維模型 + 深層思維模型

### 3. 執行分析
點擊「執行分析」，等待 1-5 分鐘（依研究深度而定）。

### 4. 查看結果
- **交易決策摘要** - BUY / SELL / HOLD 建議
- **股價走勢圖** - 折線圖 / K 線圖切換
- **12 位代理報告** - 點擊標籤查看詳細分析

### 5. 儲存與下載
- **儲存報告** - 保存到本地 / 雲端
- **下載 PDF 報告** - 匯出完整 PDF 分析報告

### 📄 範例報告

查看完整的 PDF 分析報告範例：

📥 **[AVGO 博通公司分析報告 (2025-12-15)](report/AVGO_Combined_Report_2025-12-15.pdf)**

---

## 🔌 API 文檔

### 健康檢查
```bash
GET /api/health
```

### 執行分析
```bash
POST /api/analyze
Content-Type: application/json

{
  "ticker": "NVDA",
  "market_type": "us",
  "analysis_date": "2024-01-15",
  "research_depth": 2,
  "analysts": ["market", "social", "news", "fundamentals"],
  "quick_think_llm": "gpt-5-mini",
  "deep_think_llm": "claude-sonnet-4-5",
  "quick_think_api_key": "sk-...",
  "deep_think_api_key": "sk-ant-...",
  "embedding_api_key": "sk-...",
  "alpha_vantage_api_key": "..."
}
```

### 查詢任務狀態
```bash
GET /api/task/{task_id}
```

完整文檔: http://localhost:8000/docs

---

## 🛠️ 技術棧

### 後端
| 技術 | 用途 |
|------|------|
| FastAPI | 異步 Web 框架 |
| LangGraph | 多代理工作流編排 |
| LangChain | LLM 應用開發 |
| ChromaDB | 向量資料庫（記憶系統）|
| PostgreSQL | 使用者資料儲存 |
| SQLAlchemy + asyncpg | 異步資料庫 ORM |
| Pydantic | 資料驗證 |

### 前端
| 技術 | 用途 |
|------|------|
| Next.js 16 | React 全端框架 |
| TypeScript | 靜態型別 |
| Tailwind CSS | 樣式框架 |
| shadcn/ui | UI 組件庫 |
| Dexie.js | IndexedDB 封裝 |
| Recharts | 資料視覺化 |

---

## 📸 應用截圖

### 首頁

![首頁](web_screenshot/1.png)

---

### API配置頁面

![API配置頁面](web_screenshot/2.png)

---
### 任務配置頁面

![任務配置頁面](web_screenshot/3.png)

---

### 代理觀點選擇

**12 個專業代理標籤**，點擊可切換查看不同代理的分析報告：

- **分析師團隊 (4)**: 市場分析師、社群媒體分析師、新聞分析師、基本面分析師
- **研究團隊 (3)**: 看漲研究員、看跌研究員、研究經理
- **交易團隊 (1)**: 交易員
- **風險管理團隊 (4)**: 激進分析師、保守分析師、中立分析師、風險經理

![代理觀點選擇](web_screenshot/4.png)

---

### 股價走勢圖表 (K 線圖)

![股價走勢圖表 - K線圖](web_screenshot/5.png)

---

### 股價走勢圖表 (折線圖)

![股價走勢圖表 - 折線圖](web_screenshot/6.png)

---

### 市場分析師報告

![市場分析師報告](web_screenshot/7.png)

---

### 社群媒體分析師報告


![社群媒體分析師報告](web_screenshot/8.png)

---

### 新聞分析師報告


![新聞分析師報告](web_screenshot/9.png)

---

### 基本面分析師報告


![基本面分析師報告](web_screenshot/10.png)

---

### 看漲研究員報告


![看漲研究員報告](web_screenshot/11.png)

---

### 看跌研究員報告


![看跌研究員報告](web_screenshot/12.png)

---

### 研究經理報告


![研究經理報告](web_screenshot/13.png)

---

### 交易員報告


![交易員報告](web_screenshot/14.png)

---

### 激進分析師報告


![激進分析師報告](web_screenshot/15.png)

---

### 保守分析師報告


![保守分析師報告](web_screenshot/16.png)

---

### 中立分析師報告


![中立分析師報告](web_screenshot/17.png)

---

### 風險經理報告


![風險經理報告](web_screenshot/18.png)

---

## 歷史報告（需登錄才能查看）

![歷史報告](web_screenshot/19.png)

---

## 🙏 致謝

- [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) - 原始專案
- [LangChain](https://github.com/langchain-ai/langchain) - LLM 應用框架
- [LangGraph](https://github.com/langchain-ai/langgraph) - 多代理編排
- [FastAPI](https://github.com/tiangolo/fastapi) - Web 框架
- [Next.js](https://github.com/vercel/next.js) - React 框架
- [shadcn/ui](https://github.com/shadcn/ui) - UI 組件庫

---

## 📄 License

本專案採用 Apache 2.0 許可證 - 查看 [LICENSE](LICENSE) 文件了解詳情。
