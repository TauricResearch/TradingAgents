#!/usr/bin/env python3
"""
Tushare数据获取工具
支持A股实时数据和历史数据，替换tushareAPI
Tushare是更稳定和专业的中国金融数据接口
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import warnings
import os
warnings.filterwarnings('ignore')

# 导入数据库管理器
try:
    from tradingagents.config.database_manager import get_database_manager
    DB_MANAGER_AVAILABLE = True
except ImportError:
    DB_MANAGER_AVAILABLE = False
    print("⚠️ 数据库缓存管理器不可用，尝试文件缓存")

try:
    from .cache_manager import get_cache
    FILE_CACHE_AVAILABLE = True
except ImportError:
    FILE_CACHE_AVAILABLE = False
    print("⚠️ 文件缓存管理器不可用，将直接从API获取数据")

try:
    import tushare as ts
    TUSHARE_AVAILABLE = True
except ImportError:
    TUSHARE_AVAILABLE = False
    print("⚠️ tushare库未安装，无法使用Tushare API")
    print("💡 安装命令: pip install tushare")

# 股票名称缓存
_stock_name_cache = {}

# 常用股票名称映射（备用）
_common_stock_names = {
    '000001': '平安银行',
    '000002': '万科A', 
    '000858': '五粮液',
    '000651': '格力电器',
    '000333': '美的集团',
    '600036': '招商银行',
    '600519': '贵州茅台',
    '601318': '中国平安',
    '600028': '中国石化',
    '601398': '工商银行',
    '600000': '浦发银行',
    '000725': '京东方A',
    '002415': '海康威视',
    '300059': '东方财富',
    '688001': '华兴源创',
    '688036': '传音控股'
}

# 全局Tushare提供器实例
_tushare_provider = None


class TushareDataProvider:
    """Tushare数据提供器"""
    
    def __init__(self):
        print(f"🔍 [DEBUG] 初始化Tushare数据提供器...")
        self.pro = None
        self.connected = False
        self.token = None

        print(f"🔍 [DEBUG] 检查tushare库可用性: {TUSHARE_AVAILABLE}")
        if not TUSHARE_AVAILABLE:
            error_msg = "tushare库未安装，请运行: pip install tushare"
            print(f"❌ [DEBUG] {error_msg}")
            raise ImportError(error_msg)
        print(f"✅ [DEBUG] tushare库检查通过")

        # 获取Tushare token
        self.token = self._get_tushare_token()
        if not self.token:
            print("⚠️ [DEBUG] Tushare token未配置，将使用免费接口（有限制）")
        
        self.connect()

    def _get_tushare_token(self) -> Optional[str]:
        """获取Tushare API token"""
        # 从环境变量获取
        token = os.getenv('TUSHARE_TOKEN')
        if token:
            return token
        
        # 从.env文件获取
        try:
            from dotenv import load_dotenv
            load_dotenv()
            token = os.getenv('TUSHARE_TOKEN')
            if token:
                return token
        except ImportError:
            pass
        
        return None

    def connect(self) -> bool:
        """连接到Tushare API"""
        try:
            if self.token:
                ts.set_token(self.token)
                self.pro = ts.pro_api()
                print(f"✅ [DEBUG] Tushare Pro API连接成功")
            else:
                # 使用免费接口
                print(f"🔍 [DEBUG] 使用Tushare免费接口")
            
            self.connected = True
            return True
            
        except Exception as e:
            print(f"❌ [DEBUG] Tushare连接失败: {e}")
            self.connected = False
            return False

    def is_connected(self) -> bool:
        """检查连接状态"""
        return self.connected

    def _format_stock_code(self, stock_code: str) -> str:
        """格式化股票代码为Tushare格式"""
        if len(stock_code) != 6:
            return stock_code
        
        # 判断交易所
        if stock_code.startswith('6'):
            return f"{stock_code}.SH"  # 上交所
        elif stock_code.startswith(('0', '3')):
            return f"{stock_code}.SZ"  # 深交所
        else:
            return f"{stock_code}.SZ"  # 默认深交所

    def _get_stock_name(self, stock_code: str) -> str:
        """获取股票名称"""
        global _stock_name_cache
        
        # 首先检查缓存
        if stock_code in _stock_name_cache:
            return _stock_name_cache[stock_code]
        
        # 检查常用股票映射表
        if stock_code in _common_stock_names:
            name = _common_stock_names[stock_code]
            _stock_name_cache[stock_code] = name
            return name
        
        # 从Tushare获取
        try:
            if self.pro:
                ts_code = self._format_stock_code(stock_code)
                df = self.pro.stock_basic(ts_code=ts_code, fields='ts_code,name')
                if not df.empty:
                    name = df.iloc[0]['name']
                    _stock_name_cache[stock_code] = name
                    return name
        except Exception as e:
            print(f"⚠️ 从Tushare获取股票名称失败: {e}")
        
        # 默认格式
        default_name = f'股票{stock_code}'
        _stock_name_cache[stock_code] = default_name
        return default_name

    def get_stock_history_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取股票历史数据"""
        try:
            ts_code = self._format_stock_code(stock_code)
            
            if self.pro:
                # 使用Pro API
                df = self.pro.daily(ts_code=ts_code, start_date=start_date.replace('-', ''), 
                                   end_date=end_date.replace('-', ''))
            else:
                # 使用免费接口
                df = ts.get_hist_data(stock_code, start=start_date, end=end_date)
                if df is not None:
                    df = df.reset_index()
                    df['trade_date'] = df['date']
                    df = df.rename(columns={
                        'open': 'open',
                        'high': 'high', 
                        'low': 'low',
                        'close': 'close',
                        'volume': 'vol'
                    })
            
            if df is None or df.empty:
                print(f"⚠️ 未获取到股票 {stock_code} 的历史数据")
                return pd.DataFrame()
            
            # 数据处理
            df = df.sort_values('trade_date')
            return df
            
        except Exception as e:
            print(f"❌ 获取历史数据失败: {e}")
            return pd.DataFrame()

    def get_real_time_data(self, stock_code: str) -> Optional[Dict]:
        """获取实时数据"""
        try:
            if self.pro:
                # Pro API获取最新交易日数据
                ts_code = self._format_stock_code(stock_code)
                df = self.pro.daily(ts_code=ts_code, trade_date='', limit=1)
                if not df.empty:
                    row = df.iloc[0]
                    return {
                        'price': row['close'],
                        'change': row['change'] if 'change' in row else 0,
                        'change_percent': row['pct_chg'] if 'pct_chg' in row else 0,
                        'volume': row['vol'],
                        'turnover': row['amount'] if 'amount' in row else 0,
                        'high': row['high'],
                        'low': row['low'],
                        'open': row['open']
                    }
            else:
                # 免费接口获取实时数据
                df = ts.get_realtime_quotes(stock_code)
                if df is not None and not df.empty:
                    row = df.iloc[0]
                    return {
                        'price': float(row['price']),
                        'change': float(row['change']),
                        'change_percent': float(row['changepercent']),
                        'volume': float(row['volume']),
                        'high': float(row['high']),
                        'low': float(row['low']),
                        'open': float(row['open'])
                    }
            
        except Exception as e:
            print(f"⚠️ 获取实时数据失败: {e}")
        
        return None

    def get_stock_technical_indicators(self, stock_code: str) -> Dict:
        """获取技术指标"""
        try:
            # 获取最近30天数据计算技术指标
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
            
            df = self.get_stock_history_data(stock_code, start_date, end_date)
            
            if df.empty:
                return {}
            
            # 计算技术指标
            closes = df['close'].astype(float)
            
            # MA均线
            ma5 = closes.rolling(5).mean().iloc[-1] if len(closes) >= 5 else closes.iloc[-1]
            ma10 = closes.rolling(10).mean().iloc[-1] if len(closes) >= 10 else closes.iloc[-1]
            ma20 = closes.rolling(20).mean().iloc[-1] if len(closes) >= 20 else closes.iloc[-1]
            
            # RSI
            def calculate_rsi(prices, period=14):
                delta = prices.diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                return rsi.iloc[-1] if not rsi.empty else 50
            
            rsi = calculate_rsi(closes)
            
            return {
                'MA5': round(ma5, 2),
                'MA10': round(ma10, 2), 
                'MA20': round(ma20, 2),
                'RSI': round(rsi, 2)
            }
            
        except Exception as e:
            print(f"⚠️ 计算技术指标失败: {e}")
            return {}

    def search_stocks(self, keyword: str) -> List[Dict]:
        """搜索股票"""
        try:
            results = []
            
            if self.pro:
                # 使用Pro API搜索
                df = self.pro.stock_basic(fields='ts_code,symbol,name')
                if not df.empty:
                    # 按关键词过滤
                    filtered = df[df['name'].str.contains(keyword, na=False)]
                    for _, row in filtered.head(10).iterrows():
                        stock_code = row['symbol']
                        realtime_data = self.get_real_time_data(stock_code)
                        results.append({
                            'code': stock_code,
                            'name': row['name'],
                            'price': realtime_data.get('price', 0) if realtime_data else 0,
                            'change_percent': realtime_data.get('change_percent', 0) if realtime_data else 0
                        })
            else:
                # 使用常见股票映射搜索
                for name, code in _common_stock_names.items():
                    if keyword.lower() in name.lower() or keyword in code:
                        realtime_data = self.get_real_time_data(code)
                        results.append({
                            'code': code,
                            'name': name,
                            'price': realtime_data.get('price', 0) if realtime_data else 0,
                            'change_percent': realtime_data.get('change_percent', 0) if realtime_data else 0
                        })
            
            return results
            
        except Exception as e:
            print(f"搜索股票失败: {e}")
            return []


def get_tushare_provider() -> TushareDataProvider:
    """获取Tushare数据提供器实例"""
    global _tushare_provider
    if _tushare_provider is None:
        print(f"🔍 [DEBUG] 创建新的Tushare数据提供器实例...")
        _tushare_provider = TushareDataProvider()
        print(f"🔍 [DEBUG] Tushare数据提供器实例创建完成")
    else:
        print(f"🔍 [DEBUG] 使用现有的Tushare数据提供器实例")
        # 检查连接状态，如果连接断开则重新创建
        if not _tushare_provider.is_connected():
            print(f"🔍 [DEBUG] 检测到连接断开，重新创建Tushare数据提供器...")
            _tushare_provider = TushareDataProvider()
            print(f"🔍 [DEBUG] Tushare数据提供器重新创建完成")
    return _tushare_provider


def get_china_stock_data(stock_code: str, start_date: str, end_date: str) -> str:
    """
    获取中国股票数据的主要接口函数（支持缓存）
    使用Tushare API替换tushareAPI
    Args:
        stock_code: 股票代码 (如 '000001')
        start_date: 开始日期 'YYYY-MM-DD'
        end_date: 结束日期 'YYYY-MM-DD'
    Returns:
        str: 格式化的股票数据
    """
    print(f"📊 正在获取中国股票数据: {stock_code} ({start_date} 到 {end_date})")

    # 优先尝试从数据库缓存加载数据（使用统一的database_manager）
    try:
        from tradingagents.config.database_manager import get_database_manager
        db_manager = get_database_manager()
        if db_manager.is_mongodb_available():
            # 直接使用MongoDB客户端查询缓存数据
            mongodb_client = db_manager.get_mongodb_client()
            if mongodb_client:
                db = mongodb_client[db_manager.mongodb_config["database"]]
                collection = db.stock_data

                # 查询最近的缓存数据
                from datetime import datetime, timedelta
                cutoff_time = datetime.utcnow() - timedelta(hours=6)

                cached_doc = collection.find_one({
                    "symbol": stock_code,
                    "market_type": "china",
                    "created_at": {"$gte": cutoff_time}
                }, sort=[("created_at", -1)])

                if cached_doc and 'data' in cached_doc:
                    print(f"🗄️ 从MongoDB缓存加载数据: {stock_code}")
                    return cached_doc['data']
    except Exception as e:
        print(f"⚠️ 从MongoDB加载缓存失败: {e}")

    # 如果数据库缓存不可用，尝试文件缓存
    if FILE_CACHE_AVAILABLE:
        cache = get_cache()
        try:
            cache_key = cache.find_cached_stock_data(
                symbol=stock_code,
                start_date=start_date,
                end_date=end_date,
                data_source="tushare",
                max_age_hours=6  # 6小时内的缓存有效
            )
        except TypeError:
            # 如果缓存管理器不支持max_age_hours参数，则忽略该参数
            print("⚠️ 缓存管理器不支持max_age_hours参数，使用默认缓存策略")
            cache_key = cache.find_cached_stock_data(
                symbol=stock_code,
                start_date=start_date,
                end_date=end_date,
                data_source="tushare"
            )

        if cache_key:
            cached_data = cache.load_stock_data(cache_key)
            if cached_data:
                print(f"💾 从文件缓存加载数据: {stock_code} -> {cache_key}")
                return cached_data

    print(f"🌐 从Tushare API获取数据: {stock_code}")

    try:
        provider = get_tushare_provider()

        # 获取历史数据
        df = provider.get_stock_history_data(stock_code, start_date, end_date)

        if df.empty:
            error_msg = f"❌ 未能获取股票 {stock_code} 的历史数据"
            print(error_msg)
            return error_msg

        # 获取实时数据
        realtime_data = provider.get_real_time_data(stock_code)

        # 获取技术指标
        indicators = provider.get_stock_technical_indicators(stock_code)

        # 获取股票名称
        stock_name = provider._get_stock_name(stock_code)

        # 格式化输出
        result = f"""
# {stock_code} ({stock_name}) 股票数据分析

## 基本信息
- 股票代码: {stock_code}
- 股票名称: {stock_name}
- 数据源: Tushare API
- 数据时间: {start_date} 到 {end_date}

## 实时行情 (最新交易日)
"""

        if realtime_data:
            result += f"""- 最新价格: ¥{realtime_data['price']:.2f}
- 涨跌幅: {realtime_data['change_percent']:.2f}%
- 成交量: {realtime_data['volume']:,.0f}
- 最高价: ¥{realtime_data['high']:.2f}
- 最低价: ¥{realtime_data['low']:.2f}
- 开盘价: ¥{realtime_data['open']:.2f}
"""
        else:
            result += "- 实时数据获取失败\n"

        # 技术指标
        if indicators:
            result += f"""
## 技术指标
- MA5: ¥{indicators.get('MA5', 'N/A')}
- MA10: ¥{indicators.get('MA10', 'N/A')}
- MA20: ¥{indicators.get('MA20', 'N/A')}
- RSI: {indicators.get('RSI', 'N/A')}
"""

        # 历史数据统计
        result += f"""
## 历史数据统计 ({len(df)}个交易日)
- 最高价: ¥{df['high'].max():.2f}
- 最低价: ¥{df['low'].min():.2f}
- 平均价: ¥{df['close'].mean():.2f}
- 总成交量: {df['vol'].sum():,.0f}

## 最近5个交易日
"""

        # 显示最近5天数据
        recent_data = df.tail(5)
        for _, row in recent_data.iterrows():
            result += f"- {row['trade_date']}: 收盘¥{row['close']:.2f}, 成交量{row['vol']:,.0f}\n"

        print(f"✅ 股票数据获取成功: {stock_code}")

        # 优先保存到数据库缓存（使用统一的database_manager）
        try:
            from tradingagents.config.database_manager import get_database_manager
            db_manager = get_database_manager()
            if db_manager.is_mongodb_available():
                # 直接使用MongoDB客户端保存数据
                mongodb_client = db_manager.get_mongodb_client()
                if mongodb_client:
                    db = mongodb_client[db_manager.mongodb_config["database"]]
                    collection = db.stock_data

                    doc = {
                        "symbol": stock_code,
                        "market_type": "china",
                        "data": result,
                        "metadata": {
                            'start_date': start_date,
                            'end_date': end_date,
                            'data_source': 'tushare',
                            'realtime_data': realtime_data,
                            'indicators': indicators,
                            'history_count': len(df)
                        },
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }

                    collection.replace_one(
                        {"symbol": stock_code, "market_type": "china"},
                        doc,
                        upsert=True
                    )
                    print(f"💾 数据已保存到MongoDB: {stock_code}")
        except Exception as e:
            print(f"⚠️ 保存到MongoDB失败: {e}")

        # 同时保存到文件缓存作为备份
        if FILE_CACHE_AVAILABLE:
            cache = get_cache()
            cache.save_stock_data(
                symbol=stock_code,
                data=result,
                start_date=start_date,
                end_date=end_date,
                data_source="tushare"
            )

        return result

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"❌ [DEBUG] Tushare API调用失败:")
        print(f"❌ [DEBUG] 错误类型: {type(e).__name__}")
        print(f"❌ [DEBUG] 错误信息: {str(e)}")
        print(f"❌ [DEBUG] 详细堆栈:")
        print(error_details)

        return f"""
❌ 中国股票数据获取失败 - {stock_code}
错误类型: {type(e).__name__}
错误信息: {str(e)}

🔍 调试信息:
{error_details}

💡 解决建议:
1. 检查tushare库是否已安装: pip install tushare
2. 确认股票代码格式正确 (如: 000001, 600519)
3. 检查网络连接是否正常
4. 配置Tushare token以获得更好的服务: TUSHARE_TOKEN=your_token
5. 检查Tushare API服务状态

📚 Tushare文档: https://tushare.pro/
"""


def get_china_stock_data_enhanced(stock_code: str, start_date: str, end_date: str) -> str:
    """
    增强版中国股票数据获取函数（完整降级机制）
    这是get_china_stock_data的增强版本，使用Tushare API

    Args:
        stock_code: 股票代码 (如 '000001')
        start_date: 开始日期 'YYYY-MM-DD'
        end_date: 结束日期 'YYYY-MM-DD'
    Returns:
        str: 格式化的股票数据
    """
    try:
        from .stock_data_service import get_stock_data_service
        service = get_stock_data_service()
        return service.get_stock_data_with_fallback(stock_code, start_date, end_date)
    except ImportError:
        # 如果新服务不可用，降级到原有函数
        print("⚠️ 增强服务不可用，使用原有函数")
        return get_china_stock_data(stock_code, start_date, end_date)
    except Exception as e:
        print(f"⚠️ 增强服务出错，降级到原有函数: {e}")
        return get_china_stock_data(stock_code, start_date, end_date)
