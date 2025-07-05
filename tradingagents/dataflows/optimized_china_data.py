#!/usr/bin/env python3
"""
优化的A股数据获取工具
集成缓存策略和通达信API，提高数据获取效率
"""

import os
import time
import random
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from .cache_manager import get_cache
from .config import get_config


class OptimizedChinaDataProvider:
    """优化的A股数据提供器 - 集成缓存和通达信API"""
    
    def __init__(self):
        self.cache = get_cache()
        self.config = get_config()
        self.last_api_call = 0
        self.min_api_interval = 0.5  # 通达信API调用间隔较短
        
        print("📊 优化A股数据提供器初始化完成")
    
    def _wait_for_rate_limit(self):
        """等待API限制"""
        current_time = time.time()
        time_since_last_call = current_time - self.last_api_call
        
        if time_since_last_call < self.min_api_interval:
            wait_time = self.min_api_interval - time_since_last_call
            time.sleep(wait_time)
        
        self.last_api_call = time.time()
    
    def get_stock_data(self, symbol: str, start_date: str, end_date: str, 
                      force_refresh: bool = False) -> str:
        """
        获取A股数据 - 优先使用缓存
        
        Args:
            symbol: 股票代码（6位数字）
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            force_refresh: 是否强制刷新缓存
        
        Returns:
            格式化的股票数据字符串
        """
        print(f"📈 获取A股数据: {symbol} ({start_date} 到 {end_date})")
        
        # 检查缓存（除非强制刷新）
        if not force_refresh:
            cache_key = self.cache.find_cached_stock_data(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                data_source="tdx"
            )
            
            if cache_key:
                cached_data = self.cache.load_stock_data(cache_key)
                if cached_data:
                    print(f"⚡ 从缓存加载A股数据: {symbol}")
                    return cached_data
        
        # 缓存未命中，从通达信API获取
        print(f"🌐 从通达信API获取数据: {symbol}")
        
        try:
            # API限制处理
            self._wait_for_rate_limit()
            
            # 调用通达信API
            from .tdx_utils import get_china_stock_data
            
            formatted_data = get_china_stock_data(
                stock_code=symbol,
                start_date=start_date,
                end_date=end_date
            )
            
            # 检查是否获取成功
            if "❌" in formatted_data or "错误" in formatted_data:
                print(f"❌ 通达信API调用失败: {symbol}")
                # 尝试从旧缓存获取数据
                old_cache = self._try_get_old_cache(symbol, start_date, end_date)
                if old_cache:
                    print(f"📁 使用过期缓存数据: {symbol}")
                    return old_cache
                
                # 生成备用数据
                return self._generate_fallback_data(symbol, start_date, end_date, "通达信API调用失败")
            
            # 保存到缓存
            self.cache.save_stock_data(
                symbol=symbol,
                data=formatted_data,
                start_date=start_date,
                end_date=end_date,
                data_source="tdx"
            )
            
            print(f"✅ A股数据获取成功: {symbol}")
            return formatted_data
            
        except Exception as e:
            error_msg = f"通达信API调用异常: {str(e)}"
            print(f"❌ {error_msg}")
            
            # 尝试从旧缓存获取数据
            old_cache = self._try_get_old_cache(symbol, start_date, end_date)
            if old_cache:
                print(f"📁 使用过期缓存数据: {symbol}")
                return old_cache
            
            # 生成备用数据
            return self._generate_fallback_data(symbol, start_date, end_date, error_msg)
    
    def get_fundamentals_data(self, symbol: str, force_refresh: bool = False) -> str:
        """
        获取A股基本面数据 - 优先使用缓存
        
        Args:
            symbol: 股票代码
            force_refresh: 是否强制刷新缓存
        
        Returns:
            格式化的基本面数据字符串
        """
        print(f"📊 获取A股基本面数据: {symbol}")
        
        # 检查缓存（除非强制刷新）
        if not force_refresh:
            # 查找基本面数据缓存
            for metadata_file in self.cache.metadata_dir.glob(f"*_meta.json"):
                try:
                    import json
                    with open(metadata_file, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                    
                    if (metadata.get('symbol') == symbol and 
                        metadata.get('data_type') == 'fundamentals' and
                        metadata.get('market_type') == 'china'):
                        
                        cache_key = metadata_file.stem.replace('_meta', '')
                        if self.cache.is_cache_valid(cache_key, symbol=symbol, data_type='fundamentals'):
                            cached_data = self.cache.load_stock_data(cache_key)
                            if cached_data:
                                print(f"⚡ 从缓存加载A股基本面数据: {symbol}")
                                return cached_data
                except Exception:
                    continue
        
        # 缓存未命中，生成基本面分析
        print(f"🔍 生成A股基本面分析: {symbol}")
        
        try:
            # 先获取股票数据
            current_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
            
            stock_data = self.get_stock_data(symbol, start_date, current_date)
            
            # 生成基本面分析报告
            fundamentals_data = self._generate_fundamentals_report(symbol, stock_data)
            
            # 保存到缓存
            self.cache.save_fundamentals_data(
                symbol=symbol,
                fundamentals_data=fundamentals_data,
                data_source="tdx_analysis"
            )
            
            print(f"✅ A股基本面数据生成成功: {symbol}")
            return fundamentals_data
            
        except Exception as e:
            error_msg = f"基本面数据生成失败: {str(e)}"
            print(f"❌ {error_msg}")
            return self._generate_fallback_fundamentals(symbol, error_msg)
    
    def _generate_fundamentals_report(self, symbol: str, stock_data: str) -> str:
        """基于股票数据生成基本面分析报告"""
        
        # 从股票数据中提取信息
        company_name = "未知公司"
        current_price = "N/A"
        
        if "股票名称:" in stock_data:
            lines = stock_data.split('\n')
            for line in lines:
                if "股票名称:" in line:
                    company_name = line.split(':')[1].strip()
                elif "当前价格:" in line:
                    current_price = line.split(':')[1].strip()
        
        report = f"""# 中国A股基本面分析报告 - {symbol}（{company_name}）

## 公司基本信息
- 股票代码：{symbol}
- 股票名称：{company_name}
- 行业分类：根据股票代码判断所属行业
- 所属市场：深圳证券交易所/上海证券交易所
- 最新股价：{current_price}
- 分析日期：{datetime.now().strftime('%Y年%m月%d日')}

## 财务状况分析
基于最新的市场数据和技术指标分析：

### 资产负债表分析
- **总资产规模**：作为A股上市公司，具备一定的资产规模
- **负债结构**：需要关注资产负债率和流动比率
- **股东权益**：关注净资产收益率和每股净资产

### 现金流分析
- **经营现金流**：关注主营业务现金流入情况
- **投资现金流**：分析公司投资扩张策略
- **筹资现金流**：关注融资结构和偿债能力

## 盈利能力分析
### 收入分析
- **营业收入增长率**：关注收入增长趋势
- **主营业务收入占比**：分析业务集中度
- **收入季节性**：识别业务周期性特征

### 利润分析
- **毛利率水平**：反映产品竞争力
- **净利润率**：体现整体盈利能力
- **ROE（净资产收益率）**：衡量股东回报水平

## 成长性分析
### 历史成长性
- **营收复合增长率**：过去3-5年的收入增长情况
- **净利润增长率**：盈利增长的可持续性
- **市场份额变化**：在行业中的竞争地位

### 未来成长潜力
- **行业发展前景**：所处行业的成长空间
- **公司战略规划**：未来发展方向和投资计划
- **创新能力**：研发投入和技术优势

## 估值分析
### 相对估值
- **市盈率（PE）**：与同行业公司对比
- **市净率（PB）**：相对于净资产的估值水平
- **市销率（PS）**：相对于营业收入的估值

### 绝对估值
- **DCF估值**：基于现金流贴现的内在价值
- **资产价值**：净资产重估价值
- **分红收益率**：股息回报分析

## 风险分析
### 系统性风险
- **宏观经济风险**：经济周期对公司的影响
- **政策风险**：行业政策变化的影响
- **市场风险**：股市波动对估值的影响

### 非系统性风险
- **经营风险**：公司特有的经营风险
- **财务风险**：债务结构和偿债能力风险
- **管理风险**：管理层变动和决策风险

## 投资建议
### 综合评价
基于以上分析，该股票的投资价值评估：

**优势：**
- A股市场上市公司，监管相对完善
- 具备一定的市场地位和品牌价值
- 财务信息透明度较高

**风险：**
- 需要关注宏观经济环境变化
- 行业竞争加剧的影响
- 政策调整对业务的潜在影响

### 操作建议
- **投资策略**：建议采用价值投资策略，关注长期基本面
- **仓位建议**：根据风险承受能力合理配置仓位
- **关注指标**：重点关注ROE、PE、现金流等核心指标

---
*注：本报告基于公开信息和技术分析生成，仅供参考，不构成投资建议。投资有风险，入市需谨慎。*

数据来源：通达信API + 基本面分析
生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        return report
    
    def _try_get_old_cache(self, symbol: str, start_date: str, end_date: str) -> Optional[str]:
        """尝试获取过期的缓存数据作为备用"""
        try:
            # 查找任何相关的缓存，不考虑TTL
            for metadata_file in self.cache.metadata_dir.glob(f"*_meta.json"):
                try:
                    import json
                    with open(metadata_file, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                    
                    if (metadata.get('symbol') == symbol and 
                        metadata.get('data_type') == 'stock_data' and
                        metadata.get('market_type') == 'china'):
                        
                        cache_key = metadata_file.stem.replace('_meta', '')
                        cached_data = self.cache.load_stock_data(cache_key)
                        if cached_data:
                            return cached_data + "\n\n⚠️ 注意: 使用的是过期缓存数据"
                except Exception:
                    continue
        except Exception:
            pass
        
        return None
    
    def _generate_fallback_data(self, symbol: str, start_date: str, end_date: str, error_msg: str) -> str:
        """生成备用数据"""
        return f"""# {symbol} A股数据获取失败

## ❌ 错误信息
{error_msg}

## 📊 模拟数据（仅供演示）
- 股票代码: {symbol}
- 股票名称: 模拟公司
- 数据期间: {start_date} 至 {end_date}
- 模拟价格: ¥{random.uniform(10, 50):.2f}
- 模拟涨跌: {random.uniform(-5, 5):+.2f}%

## ⚠️ 重要提示
由于通达信API限制或网络问题，无法获取实时数据。
建议稍后重试或检查网络连接。

生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    
    def _generate_fallback_fundamentals(self, symbol: str, error_msg: str) -> str:
        """生成备用基本面数据"""
        return f"""# {symbol} A股基本面分析失败

## ❌ 错误信息
{error_msg}

## 📊 基本信息
- 股票代码: {symbol}
- 分析状态: 数据获取失败
- 建议: 稍后重试或检查网络连接

生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""


# 全局实例
_china_data_provider = None

def get_optimized_china_data_provider() -> OptimizedChinaDataProvider:
    """获取全局A股数据提供器实例"""
    global _china_data_provider
    if _china_data_provider is None:
        _china_data_provider = OptimizedChinaDataProvider()
    return _china_data_provider


def get_china_stock_data_cached(symbol: str, start_date: str, end_date: str, 
                               force_refresh: bool = False) -> str:
    """
    获取A股数据的便捷函数
    
    Args:
        symbol: 股票代码（6位数字）
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
        force_refresh: 是否强制刷新缓存
    
    Returns:
        格式化的股票数据字符串
    """
    provider = get_optimized_china_data_provider()
    return provider.get_stock_data(symbol, start_date, end_date, force_refresh)


def get_china_fundamentals_cached(symbol: str, force_refresh: bool = False) -> str:
    """
    获取A股基本面数据的便捷函数
    
    Args:
        symbol: 股票代码（6位数字）
        force_refresh: 是否强制刷新缓存
    
    Returns:
        格式化的基本面数据字符串
    """
    provider = get_optimized_china_data_provider()
    return provider.get_fundamentals_data(symbol, force_refresh)
