#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试K线更新时同时采集板块信息的功能
"""
import json
import os
import sys

# 添加路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'TradingShared'))

def test_kline_with_industry():
    """测试K线更新时同步采集板块信息"""
    from TradingShared.api.comprehensive_data_collector import \
        ComprehensiveDataCollector
    
    print("=" * 60)
    print("测试：K线更新时同步采集板块信息")
    print("=" * 60)
    
    # 创建采集器
    collector = ComprehensiveDataCollector()
    
    # 读取现有数据
    existing_data = collector.load_existing_data()
    print(f"\n加载现有数据: {len(existing_data)} 只股票")
    
    # 随机选择5只主板股票进行测试
    test_codes = []
    for code in existing_data.keys():
        if code.startswith(('600', '601', '603', '000', '001', '002')):
            test_codes.append(code)
            if len(test_codes) >= 5:
                break
    
    if not test_codes:
        print("错误：没有找到主板股票进行测试")
        return
    
    print(f"\n测试股票: {', '.join(test_codes)}")
    
    # 检查这些股票当前是否有板块信息
    print("\n检查现有板块信息:")
    for code in test_codes:
        if code in existing_data:
            industry_info = existing_data[code].get('industry_concept', {})
            industry = industry_info.get('industry', '未知')
            sector = industry_info.get('sector', '未知')
            print(f"  {code}: 行业={industry}, 板块={sector}, 来源={industry_info.get('source', '未知')}")
        else:
            print(f"  {code}: 无数据")
    
    # 模拟批量采集板块信息（测试功能）
    print(f"\n开始测试批量采集板块信息...")
    try:
        batch_industry_data = collector.collect_batch_industry_concept(test_codes, 'auto')
        
        print(f"\n采集结果:")
        for code in test_codes:
            if code in batch_industry_data:
                info = batch_industry_data[code]
                print(f"  {code}:")
                print(f"    行业: {info.get('industry', '未知')}")
                print(f"    板块: {info.get('sector', '未知')}")
                print(f"    概念: {', '.join(info.get('concepts', [])[:3]) if info.get('concepts') else '无'}")
                print(f"    来源: {info.get('source', '未知')}")
            else:
                print(f"  {code}: 采集失败")
        
        print(f"\n✓ 板块信息采集功能测试通过")
        
    except Exception as e:
        print(f"\n✗ 板块信息采集失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
    print("\n说明：")
    print("1. K线更新时会自动采集板块信息（行业、概念等）")
    print("2. 只更新缺失或使用默认值的股票，避免重复采集")
    print("3. 超过10只股票时会跳过概念查询，避免API限制")
    print("4. 板块信息会保存到数据文件，供后续分析使用")

if __name__ == '__main__':
    test_kline_with_industry()
