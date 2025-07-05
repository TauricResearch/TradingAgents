#!/usr/bin/env python3
"""
MongoDB存储适配器
用于将token使用记录存储到MongoDB数据库
"""

import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import asdict
from .config_manager import UsageRecord

try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
    MONGODB_AVAILABLE = True
except ImportError:
    MONGODB_AVAILABLE = False
    MongoClient = None


class MongoDBStorage:
    """MongoDB存储适配器"""
    
    def __init__(self, connection_string: str = None, database_name: str = "tradingagents"):
        if not MONGODB_AVAILABLE:
            raise ImportError("pymongo is not installed. Please install it with: pip install pymongo")
        
        # 修复硬编码问题 - 如果没有提供连接字符串且环境变量也未设置，则抛出错误
        self.connection_string = connection_string or os.getenv("MONGODB_CONNECTION_STRING")
        if not self.connection_string:
            raise ValueError(
                "MongoDB连接字符串未配置。请通过以下方式之一进行配置：\n"
                "1. 设置环境变量 MONGODB_CONNECTION_STRING\n"
                "2. 在初始化时传入 connection_string 参数\n"
                "例如: MONGODB_CONNECTION_STRING=mongodb://localhost:27017/"
            )
        
        self.database_name = database_name
        self.collection_name = "token_usage"
        
        self.client = None
        self.db = None
        self.collection = None
        self._connected = False
        
        # 尝试连接
        self._connect()
    
    def _connect(self):
        """连接到MongoDB"""
        try:
            self.client = MongoClient(
                self.connection_string,
                serverSelectionTimeoutMS=5000  # 5秒超时
            )
            # 测试连接
            self.client.admin.command('ping')
            
            self.db = self.client[self.database_name]
            self.collection = self.db[self.collection_name]
            
            # 创建索引以提高查询性能
            self._create_indexes()
            
            self._connected = True
            print(f"✅ MongoDB连接成功: {self.database_name}.{self.collection_name}")
            
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            print(f"❌ MongoDB连接失败: {e}")
            print("将使用本地JSON文件存储")
            self._connected = False
        except Exception as e:
            print(f"❌ MongoDB初始化失败: {e}")
            self._connected = False
    
    def _create_indexes(self):
        """创建数据库索引"""
        try:
            # 创建复合索引
            self.collection.create_index([
                ("timestamp", -1),  # 按时间倒序
                ("provider", 1),
                ("model_name", 1)
            ])
            
            # 创建会话ID索引
            self.collection.create_index("session_id")
            
            # 创建分析类型索引
            self.collection.create_index("analysis_type")
            
        except Exception as e:
            print(f"创建MongoDB索引失败: {e}")
    
    def is_connected(self) -> bool:
        """检查是否连接到MongoDB"""
        return self._connected
    
    def save_usage_record(self, record: UsageRecord) -> bool:
        """保存单个使用记录到MongoDB"""
        if not self._connected:
            return False
        
        try:
            # 转换为字典格式
            record_dict = asdict(record)
            
            # 添加MongoDB特有的字段
            record_dict['_created_at'] = datetime.now()
            
            # 插入记录
            result = self.collection.insert_one(record_dict)
            
            if result.inserted_id:
                return True
            else:
                print("MongoDB插入失败：未返回插入ID")
                return False
                
        except Exception as e:
            print(f"保存记录到MongoDB失败: {e}")
            return False
    
    def load_usage_records(self, limit: int = 10000, days: int = None) -> List[UsageRecord]:
        """从MongoDB加载使用记录"""
        if not self._connected:
            return []
        
        try:
            # 构建查询条件
            query = {}
            if days:
                from datetime import timedelta
                cutoff_date = datetime.now() - timedelta(days=days)
                query['timestamp'] = {'$gte': cutoff_date.isoformat()}
            
            # 查询记录，按时间倒序
            cursor = self.collection.find(query).sort('timestamp', -1).limit(limit)
            
            records = []
            for doc in cursor:
                # 移除MongoDB特有的字段
                doc.pop('_id', None)
                doc.pop('_created_at', None)
                
                # 转换为UsageRecord对象
                try:
                    record = UsageRecord(**doc)
                    records.append(record)
                except Exception as e:
                    print(f"解析记录失败: {e}, 记录: {doc}")
                    continue
            
            return records
            
        except Exception as e:
            print(f"从MongoDB加载记录失败: {e}")
            return []
    
    def get_usage_statistics(self, days: int = 30) -> Dict[str, Any]:
        """从MongoDB获取使用统计"""
        if not self._connected:
            return {}
        
        try:
            from datetime import timedelta
            cutoff_date = datetime.now() - timedelta(days=days)
            
            # 聚合查询
            pipeline = [
                {
                    '$match': {
                        'timestamp': {'$gte': cutoff_date.isoformat()}
                    }
                },
                {
                    '$group': {
                        '_id': None,
                        'total_cost': {'$sum': '$cost'},
                        'total_input_tokens': {'$sum': '$input_tokens'},
                        'total_output_tokens': {'$sum': '$output_tokens'},
                        'total_requests': {'$sum': 1}
                    }
                }
            ]
            
            result = list(self.collection.aggregate(pipeline))
            
            if result:
                stats = result[0]
                return {
                    'period_days': days,
                    'total_cost': round(stats.get('total_cost', 0), 4),
                    'total_input_tokens': stats.get('total_input_tokens', 0),
                    'total_output_tokens': stats.get('total_output_tokens', 0),
                    'total_requests': stats.get('total_requests', 0)
                }
            else:
                return {
                    'period_days': days,
                    'total_cost': 0,
                    'total_input_tokens': 0,
                    'total_output_tokens': 0,
                    'total_requests': 0
                }
                
        except Exception as e:
            print(f"获取MongoDB统计失败: {e}")
            return {}
    
    def get_provider_statistics(self, days: int = 30) -> Dict[str, Dict[str, Any]]:
        """按供应商获取统计信息"""
        if not self._connected:
            return {}
        
        try:
            from datetime import timedelta
            cutoff_date = datetime.now() - timedelta(days=days)
            
            # 按供应商聚合
            pipeline = [
                {
                    '$match': {
                        'timestamp': {'$gte': cutoff_date.isoformat()}
                    }
                },
                {
                    '$group': {
                        '_id': '$provider',
                        'cost': {'$sum': '$cost'},
                        'input_tokens': {'$sum': '$input_tokens'},
                        'output_tokens': {'$sum': '$output_tokens'},
                        'requests': {'$sum': 1}
                    }
                }
            ]
            
            results = list(self.collection.aggregate(pipeline))
            
            provider_stats = {}
            for result in results:
                provider = result['_id']
                provider_stats[provider] = {
                    'cost': round(result.get('cost', 0), 4),
                    'input_tokens': result.get('input_tokens', 0),
                    'output_tokens': result.get('output_tokens', 0),
                    'requests': result.get('requests', 0)
                }
            
            return provider_stats
            
        except Exception as e:
            print(f"获取供应商统计失败: {e}")
            return {}
    
    def cleanup_old_records(self, days: int = 90) -> int:
        """清理旧记录"""
        if not self._connected:
            return 0
        
        try:
            from datetime import timedelta
            cutoff_date = datetime.now() - timedelta(days=days)
            
            result = self.collection.delete_many({
                'timestamp': {'$lt': cutoff_date.isoformat()}
            })
            
            deleted_count = result.deleted_count
            if deleted_count > 0:
                print(f"清理了 {deleted_count} 条超过 {days} 天的记录")
            
            return deleted_count
            
        except Exception as e:
            print(f"清理旧记录失败: {e}")
            return 0
    
    def close(self):
        """关闭MongoDB连接"""
        if self.client:
            self.client.close()
            self._connected = False
            print("MongoDB连接已关闭")