#!/usr/bin/env python3
"""
通达信API数据获取工具
支持A股、港股实时数据和历史数据
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import warnings
warnings.filterwarnings('ignore')

# 导入数据库管理器
try:
    from tradingagents.config.database_manager import get_database_manager
    DB_MANAGER_AVAILABLE = True
except ImportError:
    DB_MANAGER_AVAILABLE = False
    print("⚠️ 数据库缓存管理器不可用，尝试文件缓存")

# 导入MongoDB股票信息查询
try:
    import os
    from pymongo import MongoClient
    MONGODB_AVAILABLE = True
except ImportError:
    MONGODB_AVAILABLE = False
    print("⚠️ pymongo未安装，无法从MongoDB获取股票名称")

try:
    from .cache_manager import get_cache
    FILE_CACHE_AVAILABLE = True
except ImportError:
    FILE_CACHE_AVAILABLE = False
    print("⚠️ 文件缓存管理器不可用，将直接从API获取数据")

try:
    # 通达信Python接口
    import pytdx
    from pytdx.hq import TdxHq_API
    from pytdx.exhq import TdxExHq_API
    TDX_AVAILABLE = True
except ImportError:
    TDX_AVAILABLE = False
    print("⚠️ pytdx库未安装，无法使用通达信API")
    print("💡 安装命令: pip install pytdx")


class TongDaXinDataProvider:
    """通达信数据提供器"""
    
    def __init__(self):
        print(f"🔍 [DEBUG] 初始化通达信数据提供器...")
        self.api = None
        self.exapi = None  # 扩展行情API
        self.connected = False

        print(f"🔍 [DEBUG] 检查pytdx库可用性: {TDX_AVAILABLE}")
        if not TDX_AVAILABLE:
            error_msg = "pytdx库未安装，请运行: pip install pytdx"
            print(f"❌ [DEBUG] {error_msg}")
            raise ImportError(error_msg)
        print(f"✅ [DEBUG] pytdx库检查通过")
    
    def connect(self):
        """连接通达信服务器"""
        print(f"🔍 [DEBUG] 开始连接通达信服务器...")
        try:
            # 尝试从配置文件加载可用服务器
            print(f"🔍 [DEBUG] 加载服务器配置...")
            working_servers = self._load_working_servers()

            # 如果没有配置文件，使用默认服务器列表
            if not working_servers:
                print(f"🔍 [DEBUG] 未找到配置文件，使用默认服务器列表")
                working_servers = [
                    {'ip': '115.238.56.198', 'port': 7709},
                    {'ip': '115.238.90.165', 'port': 7709},
                    {'ip': '180.153.18.170', 'port': 7709},
                    {'ip': '119.147.212.81', 'port': 7709},  # 备用
                ]
            else:
                print(f"🔍 [DEBUG] 从配置文件加载了 {len(working_servers)} 个服务器")

            # 尝试连接可用服务器
            print(f"🔍 [DEBUG] 创建通达信API实例...")
            self.api = TdxHq_API()
            print(f"🔍 [DEBUG] 开始尝试连接服务器...")

            for i, server in enumerate(working_servers):
                try:
                    print(f"🔍 [DEBUG] 尝试连接服务器 {i+1}/{len(working_servers)}: {server['ip']}:{server['port']}")
                    result = self.api.connect(server['ip'], server['port'])
                    print(f"🔍 [DEBUG] 连接结果: {result}")
                    if result:
                        print(f"✅ 通达信API连接成功: {server['ip']}:{server['port']}")
                        self.connected = True
                        return True
                except Exception as e:
                    print(f"⚠️ 服务器 {server['ip']}:{server['port']} 连接失败: {e}")
                    continue

            print("❌ 所有通达信服务器连接失败")
            self.connected = False
            return False

        except Exception as e:
            print(f"❌ 通达信API连接失败: {e}")
            self.connected = False
            return False

    def _load_working_servers(self):
        """加载可用服务器配置"""
        try:
            import json
            import os

            config_file = 'tdx_servers_config.json'
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    return config.get('working_servers', [])
        except Exception:
            pass
        return []
    
    def disconnect(self):
        """断开连接"""
        try:
            if self.api:
                self.api.disconnect()
            if self.exapi:
                self.exapi.disconnect()
            self.connected = False
            print("✅ 通达信API连接已断开")
        except:
            pass

    def is_connected(self):
        """检查连接状态"""
        if not self.connected or not self.api:
            return False

        # 尝试简单的API调用来验证连接是否有效
        try:
            # 获取市场信息作为连接测试
            result = self.api.get_security_count(0)  # 获取深圳市场股票数量
            return result is not None and result > 0
        except Exception as e:
            print(f"🔍 [DEBUG] 连接测试失败: {e}")
            self.connected = False
            return False
    
    def _get_stock_name(self, stock_code: str) -> str:
        """
        获取股票名称
        优先级：缓存 -> MongoDB -> 常用股票映射 -> API获取（仅深圳市场） -> 默认格式
        Args:
            stock_code: 股票代码
        Returns:
            str: 股票名称
        """
        global _stock_name_cache
        
        # 首先检查缓存
        if stock_code in _stock_name_cache:
            return _stock_name_cache[stock_code]
        
        # 优先从MongoDB获取
        mongodb_name = _get_stock_name_from_mongodb(stock_code)
        if mongodb_name:
            _stock_name_cache[stock_code] = mongodb_name
            return mongodb_name
        
        # 检查常用股票映射表
        if stock_code in _common_stock_names:
            name = _common_stock_names[stock_code]
            _stock_name_cache[stock_code] = name
            return name
        
        # 如果API不可用，直接返回默认格式
        if not self.connected:
            if not self.connect():
                default_name = f'股票{stock_code}'
                _stock_name_cache[stock_code] = default_name
                return default_name
        
        try:
            # 仅对深圳市场尝试从API获取（上海市场的get_security_list不可用）
            market = self._get_market_code(stock_code)
            if market == 0:  # 深圳市场
                try:
                    for start_pos in range(0, 2000, 1000):  # 分批获取
                        stock_list = self.api.get_security_list(market, start_pos)
                        if stock_list:
                            for stock_info in stock_list:
                                if stock_info.get('code') == stock_code:
                                    stock_name = stock_info.get('name', '').strip()
                                    if stock_name:
                                        _stock_name_cache[stock_code] = stock_name
                                        return stock_name
                except Exception as e:
                    print(f"⚠️ 获取深圳股票列表失败: {e}")
            
            # 如果都失败了，返回默认格式并缓存
            default_name = f'股票{stock_code}'
            _stock_name_cache[stock_code] = default_name
            return default_name
            
        except Exception as e:
            print(f"⚠️ 获取股票名称失败: {e}")
            default_name = f'股票{stock_code}'
            _stock_name_cache[stock_code] = default_name
            return default_name
    
    def get_real_time_data(self, stock_code: str) -> Dict:
        """
        获取股票实时数据
        Args:
            stock_code: 股票代码
        Returns:
            Dict: 实时数据
        """
        if not self.connected:
            if not self.connect():
                return {}
        
        try:
            market = self._get_market_code(stock_code)
            
            # 获取实时数据
            data = self.api.get_security_quotes([(market, stock_code)])

            if not data:
                return {}

            quote = data[0]
            
            # 安全获取字段，避免KeyError
            def safe_get(key, default=0):
                return quote.get(key, default)

            return {
                'code': stock_code,
                'name': self._get_stock_name(stock_code),  # 使用独立的股票名称获取方法
                'price': safe_get('price'),
                'last_close': safe_get('last_close'),
                'open': safe_get('open'),
                'high': safe_get('high'),
                'low': safe_get('low'),
                'volume': safe_get('vol'),
                'amount': safe_get('amount'),
                'change': safe_get('price') - safe_get('last_close'),
                'change_percent': ((safe_get('price') - safe_get('last_close')) / safe_get('last_close') * 100) if safe_get('last_close') > 0 else 0,
                'bid_prices': [safe_get(f'bid{i}') for i in range(1, 6)],
                'bid_volumes': [safe_get(f'bid_vol{i}') for i in range(1, 6)],
                'ask_prices': [safe_get(f'ask{i}') for i in range(1, 6)],
                'ask_volumes': [safe_get(f'ask_vol{i}') for i in range(1, 6)],
                'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
        except Exception as e:
            print(f"获取实时数据失败: {e}")
            return {}
    
    def get_stock_history_data(self, stock_code: str, start_date: str, end_date: str, period: str = 'D') -> pd.DataFrame:
        """
        获取股票历史数据
        Args:
            stock_code: 股票代码
            start_date: 开始日期 'YYYY-MM-DD'
            end_date: 结束日期 'YYYY-MM-DD'
            period: 周期 'D'=日线, 'W'=周线, 'M'=月线
        Returns:
            DataFrame: 历史数据
        """
        if not self.connected:
            if not self.connect():
                return pd.DataFrame()
        
        try:
            market = self._get_market_code(stock_code)
            
            # 计算需要获取的数据量
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            days_diff = (end_dt - start_dt).days
            
            # 根据周期调整数据量
            if period == 'D':
                count = min(days_diff + 10, 800)  # 日线最多800条
            elif period == 'W':
                count = min(days_diff // 7 + 10, 800)
            elif period == 'M':
                count = min(days_diff // 30 + 10, 800)
            else:
                count = 800
            
            # 获取K线数据
            category_map = {'D': 9, 'W': 5, 'M': 6}
            category = category_map.get(period, 9)
            
            data = self.api.get_security_bars(category, market, stock_code, 0, count)
            
            if not data:
                return pd.DataFrame()
            
            # 转换为DataFrame
            df = pd.DataFrame(data)
            
            # 处理数据格式
            df['datetime'] = pd.to_datetime(df['datetime'])
            df = df.set_index('datetime')
            df = df.sort_index()
            
            # 筛选日期范围
            df = df[start_date:end_date]
            
            # 重命名列以匹配Yahoo Finance格式
            df = df.rename(columns={
                'open': 'Open',
                'high': 'High', 
                'low': 'Low',
                'close': 'Close',
                'vol': 'Volume',
                'amount': 'Amount'
            })
            
            # 添加股票代码信息
            df['Symbol'] = stock_code
            
            return df
            
        except Exception as e:
            print(f"获取历史数据失败: {e}")
            return pd.DataFrame()
    
    def get_stock_technical_indicators(self, stock_code: str, period: int = 20) -> Dict:
        """
        计算技术指标
        Args:
            stock_code: 股票代码
            period: 计算周期
        Returns:
            Dict: 技术指标数据
        """
        try:
            # 获取最近的历史数据
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=period*2)).strftime('%Y-%m-%d')
            
            df = self.get_stock_history_data(stock_code, start_date, end_date)
            
            if df.empty:
                return {}
            
            # 计算技术指标
            indicators = {}
            
            # 移动平均线
            indicators['MA5'] = df['Close'].rolling(5).mean().iloc[-1] if len(df) >= 5 else None
            indicators['MA10'] = df['Close'].rolling(10).mean().iloc[-1] if len(df) >= 10 else None
            indicators['MA20'] = df['Close'].rolling(20).mean().iloc[-1] if len(df) >= 20 else None
            
            # RSI
            if len(df) >= 14:
                delta = df['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rs = gain / loss
                indicators['RSI'] = (100 - (100 / (1 + rs))).iloc[-1]
            
            # MACD
            if len(df) >= 26:
                exp1 = df['Close'].ewm(span=12).mean()
                exp2 = df['Close'].ewm(span=26).mean()
                macd = exp1 - exp2
                signal = macd.ewm(span=9).mean()
                indicators['MACD'] = macd.iloc[-1]
                indicators['MACD_Signal'] = signal.iloc[-1]
                indicators['MACD_Histogram'] = (macd - signal).iloc[-1]
            
            # 布林带
            if len(df) >= 20:
                sma = df['Close'].rolling(20).mean()
                std = df['Close'].rolling(20).std()
                indicators['BB_Upper'] = (sma + 2 * std).iloc[-1]
                indicators['BB_Middle'] = sma.iloc[-1]
                indicators['BB_Lower'] = (sma - 2 * std).iloc[-1]
            
            return indicators
            
        except Exception as e:
            print(f"计算技术指标失败: {e}")
            return {}
    
    def search_stocks(self, keyword: str) -> List[Dict]:
        """
        搜索股票
        Args:
            keyword: 搜索关键词（股票代码或名称）
        Returns:
            List[Dict]: 搜索结果
        """
        if not self.connected:
            if not self.connect():
                return []
        
        try:
            # 通达信没有直接的搜索API，这里提供一个简化的实现
            # 实际使用中可以维护一个股票代码表
            
            # 常见股票代码映射
            stock_mapping = {
                '平安银行': '000001',
                '万科A': '000002', 
                '中国平安': '601318',
                '贵州茅台': '600519',
                '招商银行': '600036',
                '五粮液': '000858',
                '格力电器': '000651',
                '美的集团': '000333',
                '中国石化': '600028',
                '工商银行': '601398'
            }
            
            results = []
            
            # 按关键词搜索
            for name, code in stock_mapping.items():
                if keyword.lower() in name.lower() or keyword in code:
                    # 获取实时数据
                    realtime_data = self.get_real_time_data(code)
                    if realtime_data:
                        results.append({
                            'code': code,
                            'name': name,
                            'price': realtime_data.get('price', 0),
                            'change_percent': realtime_data.get('change_percent', 0)
                        })
            
            return results
            
        except Exception as e:
            print(f"搜索股票失败: {e}")
            return []
    
    def _get_market_code(self, stock_code: str) -> int:
        """
        根据股票代码判断市场
        Args:
            stock_code: 股票代码
        Returns:
            int: 市场代码 (0=深圳, 1=上海)
        """
        if stock_code.startswith(('000', '002', '003', '300')):
            return 0  # 深圳
        elif stock_code.startswith(('600', '601', '603', '605', '688')):
            return 1  # 上海
        else:
            return 0  # 默认深圳
    
    def get_market_overview(self) -> Dict:
        """获取市场概览"""
        if not self.connected:
            if not self.connect():
                return {}
        
        try:
            # 获取主要指数数据
            indices = {
                '上证指数': ('1', '000001'),
                '深证成指': ('0', '399001'),
                '创业板指': ('0', '399006'),
                '科创50': ('1', '000688')
            }
            
            market_data = {}
            
            for name, (market, code) in indices.items():
                try:
                    data = self.api.get_security_quotes([(int(market), code)])
                    if data:
                        quote = data[0]
                        market_data[name] = {
                            'price': quote['price'],
                            'change': quote['price'] - quote['last_close'],
                            'change_percent': ((quote['price'] - quote['last_close']) / quote['last_close'] * 100) if quote['last_close'] > 0 else 0,
                            'volume': quote['vol']
                        }
                except:
                    continue
            
            return market_data
            
        except Exception as e:
            print(f"获取市场概览失败: {e}")
            return {}


# 全局实例和缓存
_tdx_provider = None
_stock_name_cache = {}  # 股票名称缓存，避免重复API调用
_mongodb_client = None
_mongodb_db = None

def _get_mongodb_connection():
    """获取MongoDB连接"""
    global _mongodb_client, _mongodb_db
    
    if not MONGODB_AVAILABLE:
        return None, None
    
    if _mongodb_client is None or _mongodb_db is None:
        try:
            # 从环境变量获取MongoDB配置
            config = {
                'host': os.getenv('MONGODB_HOST', 'localhost'),
                'port': int(os.getenv('MONGODB_PORT', 27018)),
                'username': os.getenv('MONGODB_USERNAME'),
                'password': os.getenv('MONGODB_PASSWORD'),
                'database': os.getenv('MONGODB_DATABASE', 'tradingagents'),
                'auth_source': os.getenv('MONGODB_AUTH_SOURCE', 'admin')
            }
            
            # 构建连接字符串
            if config.get('username') and config.get('password'):
                connection_string = f"mongodb://{config['username']}:{config['password']}@{config['host']}:{config['port']}/{config['auth_source']}"
            else:
                connection_string = f"mongodb://{config['host']}:{config['port']}/"
            
            # 创建客户端
            _mongodb_client = MongoClient(
                connection_string,
                serverSelectionTimeoutMS=3000  # 3秒超时
            )
            
            # 测试连接
            _mongodb_client.admin.command('ping')
            
            # 选择数据库
            _mongodb_db = _mongodb_client[config['database']]
            
        except Exception as e:
            print(f"⚠️ MongoDB连接失败: {e}")
            _mongodb_client = None
            _mongodb_db = None
    
    return _mongodb_client, _mongodb_db

def _get_stock_name_from_mongodb(stock_code: str) -> Optional[str]:
    """从MongoDB获取股票名称"""
    try:
        client, db = _get_mongodb_connection()
        if db is None:
            return None
        
        collection = db['stock_basic_info']
        stock_info = collection.find_one({'code': stock_code})
        
        if stock_info and 'name' in stock_info:
            return stock_info['name'].strip()
        
        return None
        
    except Exception as e:
        print(f"⚠️ 从MongoDB获取股票名称失败: {e}")
        return None

# 精简的常用股票名称映射（仅包含最常见的股票）
_common_stock_names = {
    # 深圳主板
    '000001': '平安银行',
    '000002': '万科A',
    '000858': '五粮液',
    '000895': '双汇发展',
    
    # 深圳中小板
    '002594': '比亚迪',
    '002415': '海康威视',
    '002304': '洋河股份',
    
    # 深圳创业板
    '300059': '东方财富',
    '300750': '宁德时代',
    '300015': '爱尔眼科',
    
    # 上海主板
    '600519': '贵州茅台',
    '600036': '招商银行',
    '601398': '工商银行',
    '601127': '小康股份',
    '600000': '浦发银行',
    '601318': '中国平安',
    '600276': '恒瑞医药',
    '600887': '伊利股份',
    
    # 科创板
    '688981': '中芯国际',
    '688599': '天合光能',
}

def get_tdx_provider() -> TongDaXinDataProvider:
    """获取通达信数据提供器实例"""
    global _tdx_provider
    if _tdx_provider is None:
        print(f"🔍 [DEBUG] 创建新的通达信数据提供器实例...")
        _tdx_provider = TongDaXinDataProvider()
        print(f"🔍 [DEBUG] 通达信数据提供器实例创建完成")
    else:
        print(f"🔍 [DEBUG] 使用现有的通达信数据提供器实例")
        # 检查连接状态，如果连接断开则重新创建
        if not _tdx_provider.is_connected():
            print(f"🔍 [DEBUG] 检测到连接断开，重新创建通达信数据提供器...")
            _tdx_provider = TongDaXinDataProvider()
            print(f"🔍 [DEBUG] 通达信数据提供器重新创建完成")
    return _tdx_provider


def get_china_stock_data(stock_code: str, start_date: str, end_date: str) -> str:
    """
    获取中国股票数据的主要接口函数（支持缓存）
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
        cache_key = cache.find_cached_stock_data(
            symbol=stock_code,
            start_date=start_date,
            end_date=end_date,
            data_source="tdx",
            max_age_hours=6  # 6小时内的缓存有效
        )

        if cache_key:
            cached_data = cache.load_stock_data(cache_key)
            if cached_data:
                print(f"💾 从文件缓存加载数据: {stock_code} -> {cache_key}")
                return cached_data

    print(f"🌐 从通达信API获取数据: {stock_code}")

    try:
        provider = get_tdx_provider()

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
        
        # 格式化输出
        result = f"""
# {stock_code} 股票数据分析

## 📊 实时行情
- 股票名称: {realtime_data.get('name', 'N/A')}
- 当前价格: ¥{realtime_data.get('price', 0):.2f}
- 涨跌幅: {realtime_data.get('change_percent', 0):.2f}%
- 成交量: {realtime_data.get('volume', 0):,}手
- 更新时间: {realtime_data.get('update_time', 'N/A')}

## 📈 历史数据概览
- 数据期间: {start_date} 至 {end_date}
- 数据条数: {len(df)}条
- 期间最高: ¥{df['High'].max():.2f}
- 期间最低: ¥{df['Low'].min():.2f}
- 期间涨幅: {((df['Close'].iloc[-1] - df['Close'].iloc[0]) / df['Close'].iloc[0] * 100):.2f}%

## 🔍 技术指标
- MA5: ¥{indicators.get('MA5', 0):.2f}
- MA10: ¥{indicators.get('MA10', 0):.2f}
- MA20: ¥{indicators.get('MA20', 0):.2f}
- RSI: {indicators.get('RSI', 0):.2f}
- MACD: {indicators.get('MACD', 0):.4f}

## 📋 最近5日数据
{df.tail().to_string()}

数据来源: 通达信API (实时数据)
"""

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
                            'data_source': 'tdx',
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
                data_source="tdx"
            )

        return result
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"❌ [DEBUG] 通达信API调用失败:")
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
1. 检查pytdx库是否已安装: pip install pytdx
2. 确认股票代码格式正确 (如: 000001, 600519)
3. 检查网络连接是否正常
4. 尝试重新连接通达信服务器

注: 通达信API需要网络连接到通达信服务器
"""


def get_china_market_overview() -> str:
    """获取中国股市概览"""
    try:
        provider = get_tdx_provider()
        market_data = provider.get_market_overview()
        
        if not market_data:
            return "无法获取市场概览数据"
        
        result = "# 中国股市概览\n\n"
        
        for name, data in market_data.items():
            change_symbol = "📈" if data['change'] >= 0 else "📉"
            result += f"## {change_symbol} {name}\n"
            result += f"- 当前点位: {data['price']:.2f}\n"
            result += f"- 涨跌点数: {data['change']:+.2f}\n"
            result += f"- 涨跌幅: {data['change_percent']:+.2f}%\n"
            result += f"- 成交量: {data['volume']:,}\n\n"
        
        result += f"更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        result += "数据来源: 通达信API\n"
        
        return result
        
    except Exception as e:
        return f"获取市场概览失败: {str(e)}"

# 在文件末尾添加以下函数

def get_china_stock_data_enhanced(stock_code: str, start_date: str, end_date: str) -> str:
    """
    增强版中国股票数据获取函数（完整降级机制）
    这是get_china_stock_data的增强版本
    
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

# ... existing code ...
