"""
A股交易分析系统 - FastAPI 后端服务
基于现代 Web 架构的全新实现
"""

import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 添加 TradingShared 路径
SHARED_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'TradingShared')
if SHARED_PATH not in sys.path:
    sys.path.insert(0, SHARED_PATH)
if os.path.join(SHARED_PATH, 'api') not in sys.path:
    sys.path.insert(0, os.path.join(SHARED_PATH, 'api'))

# 创建 FastAPI 应用
app = FastAPI(
    title="A股交易分析系统 API",
    description="提供股票分析、智能推荐、竞价排行等功能",
    version="2.0.0"
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== 数据模型 ====================

class StockInfo(BaseModel):
    code: str
    name: str
    price: Optional[float] = None
    change_percent: Optional[float] = None
    score: Optional[int] = None
    recommendation: Optional[str] = None


class StockAnalysisRequest(BaseModel):
    stock_code: str
    llm_model: str = "none"
    period: str = "short"  # short, medium, long


class StockAnalysisResponse(BaseModel):
    stock_code: str
    stock_name: str
    technical_score: int
    fundamental_score: int
    combined_score: int
    recommendation: str
    analysis_detail: str
    timestamp: str


class MarketOverview(BaseModel):
    total_stocks: int
    rising_stocks: int
    falling_stocks: int
    ai_recommendations: int
    last_update: str


class SystemStatus(BaseModel):
    data_source: str
    kline_data: str
    choice_terminal: str
    ai_model: str


# ==================== 模拟数据 ====================

MOCK_STOCKS = [
    {"code": "600519", "name": "贵州茅台", "price": 1856.00, "change_percent": 5.23, "score": 92},
    {"code": "000858", "name": "五粮液", "price": 168.50, "change_percent": 4.87, "score": 88},
    {"code": "601318", "name": "中国平安", "price": 48.20, "change_percent": 3.56, "score": 85},
    {"code": "600036", "name": "招商银行", "price": 35.80, "change_percent": -1.24, "score": 72},
    {"code": "600000", "name": "浦发银行", "price": 8.65, "change_percent": 2.18, "score": 78},
    {"code": "300750", "name": "宁德时代", "price": 215.00, "change_percent": 6.32, "score": 89},
    {"code": "002594", "name": "比亚迪", "price": 268.00, "change_percent": 4.15, "score": 87},
    {"code": "600276", "name": "恒瑞医药", "price": 42.30, "change_percent": -0.85, "score": 75},
]


# ==================== API 路由 ====================

@app.get("/")
async def root():
    """API 根路径"""
    return {
        "message": "A股交易分析系统 API",
        "version": "2.0.0",
        "docs": "/docs"
    }


@app.get("/api/market/overview", response_model=MarketOverview)
async def get_market_overview():
    """获取市场概览数据"""
    rising = len([s for s in MOCK_STOCKS if s["change_percent"] > 0])
    falling = len([s for s in MOCK_STOCKS if s["change_percent"] < 0])
    high_score = len([s for s in MOCK_STOCKS if s["score"] >= 80])
    
    return MarketOverview(
        total_stocks=4396,
        rising_stocks=2847,
        falling_stocks=1243,
        ai_recommendations=86,
        last_update=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )


@app.get("/api/system/status", response_model=SystemStatus)
async def get_system_status():
    """获取系统状态"""
    return SystemStatus(
        data_source="正常",
        kline_data="已更新",
        choice_terminal="待连接",
        ai_model="DeepSeek"
    )


@app.get("/api/stocks/ranking", response_model=List[StockInfo])
async def get_stock_ranking(limit: int = 10):
    """获取竞价排行榜"""
    sorted_stocks = sorted(MOCK_STOCKS, key=lambda x: x["change_percent"], reverse=True)
    return [
        StockInfo(
            code=s["code"],
            name=s["name"],
            price=s["price"],
            change_percent=s["change_percent"],
            score=s["score"]
        )
        for s in sorted_stocks[:limit]
    ]


@app.get("/api/stocks/recommendations", response_model=List[StockInfo])
async def get_recommendations(limit: int = 5):
    """获取 AI 智能推荐"""
    sorted_stocks = sorted(MOCK_STOCKS, key=lambda x: x["score"], reverse=True)
    recommendations = ["短期强势", "技术突破", "成长潜力", "价值低估", "趋势向好"]
    
    return [
        StockInfo(
            code=s["code"],
            name=s["name"],
            price=s["price"],
            change_percent=s["change_percent"],
            score=s["score"],
            recommendation=recommendations[i] if i < len(recommendations) else "潜力股"
        )
        for i, s in enumerate(sorted_stocks[:limit])
    ]


@app.get("/api/stocks/{stock_code}", response_model=StockInfo)
async def get_stock_info(stock_code: str):
    """获取单只股票信息"""
    stock = next((s for s in MOCK_STOCKS if s["code"] == stock_code), None)
    if not stock:
        raise HTTPException(status_code=404, detail=f"股票 {stock_code} 未找到")
    
    return StockInfo(
        code=stock["code"],
        name=stock["name"],
        price=stock["price"],
        change_percent=stock["change_percent"],
        score=stock["score"]
    )


@app.post("/api/stocks/analyze", response_model=StockAnalysisResponse)
async def analyze_stock(request: StockAnalysisRequest):
    """分析单只股票"""
    stock = next((s for s in MOCK_STOCKS if s["code"] == request.stock_code), None)
    
    if not stock:
        # 如果不在模拟数据中，返回一个默认分析
        stock = {"code": request.stock_code, "name": f"股票{request.stock_code}", "score": 75}
    
    # 模拟分析结果
    technical_score = min(100, stock.get("score", 75) + 5)
    fundamental_score = max(0, stock.get("score", 75) - 5)
    combined_score = stock.get("score", 75)
    
    period_map = {
        "short": "短期（1-5天）",
        "medium": "中期（1-4周）",
        "long": "长期（1-6个月）"
    }
    
    return StockAnalysisResponse(
        stock_code=request.stock_code,
        stock_name=stock["name"],
        technical_score=technical_score,
        fundamental_score=fundamental_score,
        combined_score=combined_score,
        recommendation="买入" if combined_score >= 80 else "持有" if combined_score >= 60 else "观望",
        analysis_detail=f"基于{period_map.get(request.period, '短期')}分析，该股票技术面评分{technical_score}分，"
                       f"基本面评分{fundamental_score}分，综合评分{combined_score}分。"
                       f"当前市场表现{'强势' if combined_score >= 80 else '稳健' if combined_score >= 60 else '偏弱'}。",
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )


@app.get("/api/llm/models")
async def get_llm_models():
    """获取可用的 LLM 模型列表"""
    return {
        "models": [
            {"id": "none", "name": "无 AI 分析", "status": "available"},
            {"id": "deepseek", "name": "DeepSeek", "status": "available"},
            {"id": "minimax", "name": "MiniMax", "status": "available"},
            {"id": "openrouter", "name": "OpenRouter", "status": "available"},
            {"id": "gemini", "name": "Gemini", "status": "available"},
        ],
        "default": "deepseek"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
