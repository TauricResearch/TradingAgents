#!/usr/bin/env python3
"""
集成缓存管理器
结合原有缓存系统和新的自适应数据库支持
提供向后兼容的接口
"""

import os
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union
import pandas as pd

# 导入原有缓存系统
from .cache_manager import StockDataCache

# 导入自适应缓存系统
try:
    from .adaptive_cache import get_cache_system
    from ..config.database_manager import get_database_manager
    ADAPTIVE_CACHE_AVAILABLE = True
except ImportError:
    ADAPTIVE_CACHE_AVAILABLE = False

class IntegratedCacheManager:
    """集成缓存管理器 - 智能选择缓存策略"""
    
    def __init__(self, cache_dir: str = None):
        self.logger = logging.getLogger(__name__)
        
        # 初始化原有缓存系统（作为备用）
        self.legacy_cache = StockDataCache(cache_dir)
        
        # 尝试初始化自适应缓存系统
        self.adaptive_cache = None
        self.use_adaptive = False
        
        if ADAPTIVE_CACHE_AVAILABLE:
            try:
                self.adaptive_cache = get_cache_system()
                self.db_manager = get_database_manager()
                self.use_adaptive = True
                self.logger.info("✅ 自适应缓存系统已启用")
            except Exception as e:
                self.logger.warning(f"自适应缓存系统初始化失败，使用传统缓存: {e}")
                self.use_adaptive = False
        else:
            self.logger.info("自适应缓存系统不可用，使用传统文件缓存")
        
        # 显示当前配置
        self._log_cache_status()
    
    def _log_cache_status(self):
        """记录缓存状态"""
        if self.use_adaptive:
            backend = self.adaptive_cache.primary_backend
            mongodb_available = self.db_manager.is_mongodb_available()
            redis_available = self.db_manager.is_redis_available()
            
            self.logger.info(f"📊 缓存配置:")
            self.logger.info(f"  主要后端: {backend}")
            self.logger.info(f"  MongoDB: {'✅ 可用' if mongodb_available else '❌ 不可用'}")
            self.logger.info(f"  Redis: {'✅ 可用' if redis_available else '❌ 不可用'}")
            self.logger.info(f"  降级支持: {'✅ 启用' if self.adaptive_cache.fallback_enabled else '❌ 禁用'}")
        else:
            self.logger.info("📁 使用传统文件缓存系统")
    
    def save_stock_data(self, symbol: str, data: Any, start_date: str = None, 
                       end_date: str = None, data_source: str = "default") -> str:
        """
        保存股票数据到缓存
        
        Args:
            symbol: 股票代码
            data: 股票数据
            start_date: 开始日期
            end_date: 结束日期
            data_source: 数据源
            
        Returns:
            缓存键
        """
        if self.use_adaptive:
            # 使用自适应缓存系统
            return self.adaptive_cache.save_data(
                symbol=symbol,
                data=data,
                start_date=start_date or "",
                end_date=end_date or "",
                data_source=data_source,
                data_type="stock_data"
            )
        else:
            # 使用传统缓存系统
            return self.legacy_cache.save_stock_data(
                symbol=symbol,
                data=data,
                start_date=start_date,
                end_date=end_date,
                data_source=data_source
            )
    
    def load_stock_data(self, cache_key: str) -> Optional[Any]:
        """
        从缓存加载股票数据
        
        Args:
            cache_key: 缓存键
            
        Returns:
            股票数据或None
        """
        if self.use_adaptive:
            # 使用自适应缓存系统
            return self.adaptive_cache.load_data(cache_key)
        else:
            # 使用传统缓存系统
            return self.legacy_cache.load_stock_data(cache_key)
    
    def find_cached_stock_data(self, symbol: str, start_date: str = None, 
                              end_date: str = None, data_source: str = "default") -> Optional[str]:
        """
        查找缓存的股票数据
        
        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            data_source: 数据源
            
        Returns:
            缓存键或None
        """
        if self.use_adaptive:
            # 使用自适应缓存系统
            return self.adaptive_cache.find_cached_data(
                symbol=symbol,
                start_date=start_date or "",
                end_date=end_date or "",
                data_source=data_source,
                data_type="stock_data"
            )
        else:
            # 使用传统缓存系统
            return self.legacy_cache.find_cached_stock_data(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                data_source=data_source
            )
    
    def save_news_data(self, symbol: str, data: Any, data_source: str = "default") -> str:
        """保存新闻数据"""
        if self.use_adaptive:
            return self.adaptive_cache.save_data(
                symbol=symbol,
                data=data,
                data_source=data_source,
                data_type="news_data"
            )
        else:
            return self.legacy_cache.save_news_data(symbol, data, data_source)
    
    def load_news_data(self, cache_key: str) -> Optional[Any]:
        """加载新闻数据"""
        if self.use_adaptive:
            return self.adaptive_cache.load_data(cache_key)
        else:
            return self.legacy_cache.load_news_data(cache_key)
    
    def save_fundamentals_data(self, symbol: str, data: Any, data_source: str = "default") -> str:
        """保存基本面数据"""
        if self.use_adaptive:
            return self.adaptive_cache.save_data(
                symbol=symbol,
                data=data,
                data_source=data_source,
                data_type="fundamentals_data"
            )
        else:
            return self.legacy_cache.save_fundamentals_data(symbol, data, data_source)
    
    def load_fundamentals_data(self, cache_key: str) -> Optional[Any]:
        """加载基本面数据"""
        if self.use_adaptive:
            return self.adaptive_cache.load_data(cache_key)
        else:
            return self.legacy_cache.load_fundamentals_data(cache_key)
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        if self.use_adaptive:
            # 获取自适应缓存统计
            adaptive_stats = self.adaptive_cache.get_cache_stats()
            
            # 添加传统缓存统计
            legacy_stats = self.legacy_cache.get_cache_stats()
            
            return {
                "cache_system": "adaptive",
                "adaptive_cache": adaptive_stats,
                "legacy_cache": legacy_stats,
                "database_available": self.db_manager.is_database_available(),
                "mongodb_available": self.db_manager.is_mongodb_available(),
                "redis_available": self.db_manager.is_redis_available()
            }
        else:
            # 只返回传统缓存统计
            legacy_stats = self.legacy_cache.get_cache_stats()
            return {
                "cache_system": "legacy",
                "legacy_cache": legacy_stats,
                "database_available": False,
                "mongodb_available": False,
                "redis_available": False
            }
    
    def clear_expired_cache(self):
        """清理过期缓存"""
        if self.use_adaptive:
            self.adaptive_cache.clear_expired_cache()
        
        # 总是清理传统缓存
        self.legacy_cache.clear_expired_cache()
    
    def get_cache_backend_info(self) -> Dict[str, Any]:
        """获取缓存后端信息"""
        if self.use_adaptive:
            return {
                "system": "adaptive",
                "primary_backend": self.adaptive_cache.primary_backend,
                "fallback_enabled": self.adaptive_cache.fallback_enabled,
                "mongodb_available": self.db_manager.is_mongodb_available(),
                "redis_available": self.db_manager.is_redis_available()
            }
        else:
            return {
                "system": "legacy",
                "primary_backend": "file",
                "fallback_enabled": False,
                "mongodb_available": False,
                "redis_available": False
            }
    
    def is_database_available(self) -> bool:
        """检查数据库是否可用"""
        if self.use_adaptive:
            return self.db_manager.is_database_available()
        return False
    
    def get_performance_mode(self) -> str:
        """获取性能模式"""
        if not self.use_adaptive:
            return "基础模式 (文件缓存)"
        
        mongodb_available = self.db_manager.is_mongodb_available()
        redis_available = self.db_manager.is_redis_available()
        
        if redis_available and mongodb_available:
            return "高性能模式 (Redis + MongoDB + 文件)"
        elif redis_available:
            return "快速模式 (Redis + 文件)"
        elif mongodb_available:
            return "持久化模式 (MongoDB + 文件)"
        else:
            return "标准模式 (智能文件缓存)"


# 全局集成缓存管理器实例
_integrated_cache = None

def get_cache() -> IntegratedCacheManager:
    """获取全局集成缓存管理器实例"""
    global _integrated_cache
    if _integrated_cache is None:
        _integrated_cache = IntegratedCacheManager()
    return _integrated_cache

# 向后兼容的函数
def get_stock_cache():
    """向后兼容：获取股票缓存"""
    return get_cache()

def create_cache_manager(cache_dir: str = None):
    """向后兼容：创建缓存管理器"""
    return IntegratedCacheManager(cache_dir)
