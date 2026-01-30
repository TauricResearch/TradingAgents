# A股交易分析系统 - Web UI

现代化的 Web 界面，用于替代原有的 tkinter GUI。

## 技术栈

### 后端
- **FastAPI** - 高性能异步 Web 框架
- **Uvicorn** - ASGI 服务器
- **Pydantic** - 数据验证

### 前端
- **React 18** - UI 框架
- **TypeScript** - 类型安全
- **Vite** - 构建工具
- **Tailwind CSS** - 样式框架
- **Lucide React** - 图标库

## 快速启动

### Windows
双击运行 `启动Web界面.bat`

### 手动启动

1. 启动后端：
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

2. 启动前端：
```bash
cd frontend
npm install
npm run dev
```

3. 访问 http://localhost:3000

## 项目结构

```
web-ui/
├── backend/
│   ├── main.py              # FastAPI 主入口
│   └── requirements.txt     # Python 依赖
├── frontend/
│   ├── src/
│   │   ├── components/      # React 组件
│   │   │   ├── Header.tsx
│   │   │   ├── Sidebar.tsx
│   │   │   ├── MetricCards.tsx
│   │   │   ├── StockAnalysis.tsx
│   │   │   ├── StockTable.tsx
│   │   │   ├── Recommendations.tsx
│   │   │   └── SystemStatus.tsx
│   │   ├── App.tsx          # 主应用组件
│   │   ├── main.tsx         # 入口文件
│   │   └── index.css        # 全局样式
│   ├── package.json
│   ├── tailwind.config.js
│   └── vite.config.ts
└── 启动Web界面.bat
```

## API 端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/market/overview` | GET | 获取市场概览数据 |
| `/api/stocks/ranking` | GET | 获取股票排行榜 |
| `/api/stocks/recommendations` | GET | 获取 AI 推荐 |
| `/api/stocks/analyze` | POST | 分析指定股票 |
| `/api/system/status` | GET | 获取系统状态 |

## 设计规范

- **主题色**: Vermillion Red (#E42313)
- **字体**: Space Grotesk (标题) + Inter (正文)
- **圆角**: 0px (Swiss Clean 风格)
- **边框**: 1px #E8E8E8
