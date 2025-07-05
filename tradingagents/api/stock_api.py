#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票数据API接口
提供便捷的股票数据获取接口，支持完整的降级机制
"""

import sys
import os
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

# 添加dataflows目录到路径
dataflows_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'dataflows')
if dataflows_path not in sys.path:
    sys.path.append(dataflows_path)

try:
    from stock_data_service import get_stock_data_service
    SERVICE_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ 股票数据服务不可用: {e}")
    SERVICE_AVAILABLE = False

def get_stock_info(stock_code: str) -> Dict[str, Any]:
    """
    获取单个股票的基础信息
    
    Args:
        stock_code: 股票代码（如 '000001'）
    
    Returns:
        Dict: 股票基础信息
    
    Example:
        >>> info = get_stock_info('000001')
        >>> print(info['name'])  # 平安银行
    """
    if not SERVICE_AVAILABLE:
        return {
            'error': '股票数据服务不可用',
            'code': stock_code,
            'suggestion': '请检查服务配置'
        }
    
    service = get_stock_data_service()
    result = service.get_stock_basic_info(stock_code)
    
    if result is None:
        return {
            'error': f'未找到股票{stock_code}的信息',
            'code': stock_code,
            'suggestion': '请检查股票代码是否正确'
        }
    
    return result

def get_all_stocks() -> List[Dict[str, Any]]:
    """
    获取所有股票的基础信息
    
    Returns:
        List[Dict]: 所有股票的基础信息列表
    
    Example:
        >>> stocks = get_all_stocks()
        >>> print(f"共有{len(stocks)}只股票")
    """
    if not SERVICE_AVAILABLE:
        return [{
            'error': '股票数据服务不可用',
            'suggestion': '请检查服务配置'
        }]
    
    service = get_stock_data_service()
    result = service.get_stock_basic_info()
    
    if result is None or (isinstance(result, dict) and 'error' in result):
        return [{
            'error': '无法获取股票列表',
            'suggestion': '请检查网络连接和数据库配置'
        }]
    
    return result if isinstance(result, list) else [result]

def get_stock_data(stock_code: str, start_date: str = None, end_date: str = None) -> str:
    """
    获取股票历史数据（带降级机制）
    
    Args:
        stock_code: 股票代码
        start_date: 开始日期（格式：YYYY-MM-DD），默认为30天前
        end_date: 结束日期（格式：YYYY-MM-DD），默认为今天
    
    Returns:
        str: 股票数据的字符串表示或错误信息
    
    Example:
        >>> data = get_stock_data('000001', '2024-01-01', '2024-01-31')
        >>> print(data)
    """
    if not SERVICE_AVAILABLE:
        return "❌ 股票数据服务不可用，请检查服务配置"
    
    # 设置默认日期
    if end_date is None:
        end_date = datetime.now().strftime('%Y-%m-%d')
    
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    
    service = get_stock_data_service()
    return service.get_stock_data_with_fallback(stock_code, start_date, end_date)

def search_stocks(keyword: str) -> List[Dict[str, Any]]:
    """
    根据关键词搜索股票
    
    Args:
        keyword: 搜索关键词（股票代码或名称的一部分）
    
    Returns:
        List[Dict]: 匹配的股票信息列表
    
    Example:
        >>> results = search_stocks('平安')
        >>> for stock in results:
        ...     print(f"{stock['code']}: {stock['name']}")
    """
    all_stocks = get_all_stocks()
    
    if not all_stocks or (len(all_stocks) == 1 and 'error' in all_stocks[0]):
        return all_stocks
    
    # 搜索匹配的股票
    matches = []
    keyword_lower = keyword.lower()
    
    for stock in all_stocks:
        if 'error' in stock:
            continue
            
        code = stock.get('code', '').lower()
        name = stock.get('name', '').lower()
        
        if keyword_lower in code or keyword_lower in name:
            matches.append(stock)
    
    return matches

def get_market_summary() -> Dict[str, Any]:
    """
    获取市场概览信息
    
    Returns:
        Dict: 市场统计信息
    
    Example:
        >>> summary = get_market_summary()
        >>> print(f"沪市股票数量: {summary['shanghai_count']}")
    """
    all_stocks = get_all_stocks()
    
    if not all_stocks or (len(all_stocks) == 1 and 'error' in all_stocks[0]):
        return {
            'error': '无法获取市场数据',
            'suggestion': '请检查网络连接和数据库配置'
        }
    
    # 统计市场信息
    shanghai_count = 0
    shenzhen_count = 0
    category_stats = {}
    
    for stock in all_stocks:
        if 'error' in stock:
            continue
            
        market = stock.get('market', '')
        category = stock.get('category', '未知')
        
        if market == '上海':
            shanghai_count += 1
        elif market == '深圳':
            shenzhen_count += 1
        
        category_stats[category] = category_stats.get(category, 0) + 1
    
    return {
        'total_count': len([s for s in all_stocks if 'error' not in s]),
        'shanghai_count': shanghai_count,
        'shenzhen_count': shenzhen_count,
        'category_stats': category_stats,
        'data_source': all_stocks[0].get('source', 'unknown') if all_stocks else 'unknown',
        'updated_at': datetime.now().isoformat()
    }

def check_service_status() -> Dict[str, Any]:
    """
    检查服务状态
    
    Returns:
        Dict: 服务状态信息
    
    Example:
        >>> status = check_service_status()
        >>> print(f"MongoDB状态: {status['mongodb_status']}")
    """
    if not SERVICE_AVAILABLE:
        return {
            'service_available': False,
            'error': '股票数据服务不可用',
            'suggestion': '请检查服务配置和依赖'
        }
    
    service = get_stock_data_service()
    
    # 检查MongoDB状态
    mongodb_status = 'disconnected'
    if service.db_manager and service.db_manager.mongodb_db:
        try:
            # 尝试执行一个简单的查询来测试连接
            service.db_manager.mongodb_db.list_collection_names()
            mongodb_status = 'connected'
        except Exception:
            mongodb_status = 'error'
    
    # 检查通达信API状态
    tdx_status = 'unavailable'
    if service.tdx_provider:
        try:
            # 尝试获取一个股票名称来测试API
            test_name = service.tdx_provider._get_stock_name('000001')
            if test_name and test_name != '000001':
                tdx_status = 'available'
            else:
                tdx_status = 'limited'
        except Exception:
            tdx_status = 'error'
    
    return {
        'service_available': True,
        'mongodb_status': mongodb_status,
        'tdx_api_status': tdx_status,
        'enhanced_fetcher_available': hasattr(service, '_get_from_tdx_api'),
        'fallback_available': True,
        'checked_at': datetime.now().isoformat()
    }

# 便捷的别名函数
get_stock = get_stock_info  # 别名
get_stocks = get_all_stocks  # 别名
search = search_stocks  # 别名
status = check_service_status  # 别名

if __name__ == '__main__':
    # 简单的命令行测试
    print("🔍 股票数据API测试")
    print("=" * 50)
    
    # 检查服务状态
    print("\n📊 服务状态检查:")
    status_info = check_service_status()
    for key, value in status_info.items():
        print(f"  {key}: {value}")
    
    # 测试获取单个股票信息
    print("\n🏢 获取平安银行信息:")
    stock_info = get_stock_info('000001')
    if 'error' not in stock_info:
        print(f"  代码: {stock_info.get('code')}")
        print(f"  名称: {stock_info.get('name')}")
        print(f"  市场: {stock_info.get('market')}")
        print(f"  类别: {stock_info.get('category')}")
        print(f"  数据源: {stock_info.get('source')}")
    else:
        print(f"  错误: {stock_info.get('error')}")
    
    # 测试搜索功能
    print("\n🔍 搜索'平安'相关股票:")
    search_results = search_stocks('平安')
    for i, stock in enumerate(search_results[:3]):  # 只显示前3个结果
        if 'error' not in stock:
            print(f"  {i+1}. {stock.get('code')}: {stock.get('name')}")
    
    # 测试市场概览
    print("\n📈 市场概览:")
    summary = get_market_summary()
    if 'error' not in summary:
        print(f"  总股票数: {summary.get('total_count')}")
        print(f"  沪市股票: {summary.get('shanghai_count')}")
        print(f"  深市股票: {summary.get('shenzhen_count')}")
        print(f"  数据源: {summary.get('data_source')}")
    else:
        print(f"  错误: {summary.get('error')}")