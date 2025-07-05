#!/usr/bin/env python3
"""
合并后功能测试验证脚本
测试所有新增功能和原有功能的兼容性
"""

import sys
import os
import traceback
import tempfile
import shutil
from pathlib import Path

# 添加项目路径
sys.path.insert(0, os.path.abspath('.'))

class MergedFeaturesTest:
    """合并功能测试类"""
    
    def __init__(self):
        self.test_results = {
            "passed": [],
            "failed": [],
            "warnings": []
        }
        self.temp_dir = None
    
    def setup(self):
        """测试环境设置"""
        print("🔧 设置测试环境...")
        self.temp_dir = tempfile.mkdtemp()
        print(f"   临时目录: {self.temp_dir}")
    
    def cleanup(self):
        """清理测试环境"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
            print(f"🧹 清理临时目录: {self.temp_dir}")
    
    def test_basic_imports(self):
        """测试基础模块导入"""
        print("\n📦 测试基础模块导入...")
        
        basic_modules = [
            "tradingagents.default_config",
            "tradingagents.dataflows.interface",
            "tradingagents.dataflows.config",
        ]
        
        for module in basic_modules:
            try:
                __import__(module)
                self.test_results["passed"].append(f"基础导入: {module}")
                print(f"   ✅ {module}")
            except Exception as e:
                self.test_results["failed"].append(f"基础导入: {module} - {e}")
                print(f"   ❌ {module}: {e}")
    
    def test_cache_system(self):
        """测试缓存系统"""
        print("\n💾 测试缓存系统...")
        
        try:
            # 测试原有缓存管理器
            from tradingagents.dataflows.cache_manager import StockDataCache, get_cache
            
            # 创建缓存实例
            cache = StockDataCache(cache_dir=self.temp_dir)
            
            # 测试基本功能
            test_data = "Test stock data for AAPL"
            cache_key = cache.save_stock_data("AAPL", test_data, "2024-01-01", "2024-01-31", "test")
            
            if cache_key:
                loaded_data = cache.load_stock_data(cache_key)
                if loaded_data == test_data:
                    self.test_results["passed"].append("缓存系统: 基本功能正常")
                    print("   ✅ 基本缓存功能正常")
                else:
                    self.test_results["failed"].append("缓存系统: 数据不匹配")
                    print("   ❌ 缓存数据不匹配")
            else:
                self.test_results["failed"].append("缓存系统: 保存失败")
                print("   ❌ 缓存保存失败")
            
            # 测试市场类型检测
            us_market = cache._determine_market_type("AAPL")
            china_market = cache._determine_market_type("000001")
            
            if us_market == "us" and china_market == "china":
                self.test_results["passed"].append("缓存系统: 市场类型检测正常")
                print("   ✅ 市场类型检测正常")
            else:
                self.test_results["failed"].append("缓存系统: 市场类型检测异常")
                print("   ❌ 市场类型检测异常")
                
        except Exception as e:
            self.test_results["failed"].append(f"缓存系统: {e}")
            print(f"   ❌ 缓存系统测试失败: {e}")
    
    def test_new_features_import(self):
        """测试新功能模块导入"""
        print("\n🆕 测试新功能模块导入...")
        
        new_modules = [
            # 中国市场数据
            ("tradingagents.dataflows.chinese_finance_utils", "中国财经数据工具"),
            ("tradingagents.dataflows.tdx_utils", "通达信API工具"),
            ("tradingagents.dataflows.optimized_china_data", "优化A股数据提供器"),
            
            # 高级缓存
            ("tradingagents.dataflows.adaptive_cache", "自适应缓存"),
            ("tradingagents.dataflows.integrated_cache", "集成缓存"),
            ("tradingagents.dataflows.db_cache_manager", "数据库缓存管理"),
            
            # 配置管理
            ("tradingagents.config.database_config", "数据库配置"),
            ("tradingagents.config.database_manager", "数据库管理器"),
            ("tradingagents.config.mongodb_storage", "MongoDB存储"),
            
            # LLM适配器
            ("tradingagents.llm_adapters.dashscope_adapter", "DashScope适配器"),
            
            # API服务
            ("tradingagents.api.stock_api", "股票API"),
            ("tradingagents.dataflows.stock_data_service", "股票数据服务"),
            ("tradingagents.dataflows.realtime_news_utils", "实时新闻工具"),
        ]
        
        for module_name, description in new_modules:
            try:
                __import__(module_name)
                self.test_results["passed"].append(f"新功能导入: {description}")
                print(f"   ✅ {description}")
            except ImportError as e:
                if "No module named" in str(e):
                    self.test_results["warnings"].append(f"新功能导入: {description} - 可能缺少依赖")
                    print(f"   ⚠️ {description}: 可能缺少依赖 ({e})")
                else:
                    self.test_results["failed"].append(f"新功能导入: {description} - {e}")
                    print(f"   ❌ {description}: {e}")
            except Exception as e:
                self.test_results["failed"].append(f"新功能导入: {description} - {e}")
                print(f"   ❌ {description}: {e}")
    
    def test_optimized_data_providers(self):
        """测试优化的数据提供器"""
        print("\n📊 测试优化数据提供器...")
        
        try:
            # 测试美股数据提供器
            from tradingagents.dataflows.optimized_us_data import OptimizedUSDataProvider
            
            provider = OptimizedUSDataProvider()
            self.test_results["passed"].append("数据提供器: 美股提供器初始化成功")
            print("   ✅ 美股数据提供器初始化成功")
            
            # 测试基本方法存在
            required_methods = ['get_stock_data', '_wait_for_rate_limit', '_format_stock_data']
            for method in required_methods:
                if hasattr(provider, method):
                    self.test_results["passed"].append(f"数据提供器: {method} 方法存在")
                    print(f"   ✅ {method} 方法存在")
                else:
                    self.test_results["failed"].append(f"数据提供器: {method} 方法缺失")
                    print(f"   ❌ {method} 方法缺失")
                    
        except Exception as e:
            self.test_results["failed"].append(f"数据提供器: {e}")
            print(f"   ❌ 数据提供器测试失败: {e}")
    
    def test_config_system(self):
        """测试配置系统"""
        print("\n⚙️ 测试配置系统...")
        
        try:
            # 测试默认配置
            from tradingagents.default_config import DEFAULT_CONFIG
            
            # 检查基本配置项
            required_configs = [
                "project_dir", "results_dir", "data_dir", 
                "llm_provider", "deep_think_llm", "quick_think_llm"
            ]
            
            for config_key in required_configs:
                if config_key in DEFAULT_CONFIG:
                    self.test_results["passed"].append(f"配置系统: {config_key} 存在")
                    print(f"   ✅ {config_key} 配置存在")
                else:
                    self.test_results["failed"].append(f"配置系统: {config_key} 缺失")
                    print(f"   ❌ {config_key} 配置缺失")
            
            # 测试动态配置
            from tradingagents.dataflows.config import get_config, set_config
            
            current_config = get_config()
            if current_config:
                self.test_results["passed"].append("配置系统: 动态配置获取正常")
                print("   ✅ 动态配置获取正常")
            else:
                self.test_results["failed"].append("配置系统: 动态配置获取失败")
                print("   ❌ 动态配置获取失败")
                
        except Exception as e:
            self.test_results["failed"].append(f"配置系统: {e}")
            print(f"   ❌ 配置系统测试失败: {e}")
    
    def test_main_functionality(self):
        """测试主要功能"""
        print("\n🚀 测试主要功能...")
        
        try:
            # 测试主程序导入
            import main
            self.test_results["passed"].append("主功能: main.py 导入成功")
            print("   ✅ main.py 导入成功")
            
            # 测试交易图形导入
            from tradingagents.graph.trading_graph import TradingAgentsGraph
            self.test_results["passed"].append("主功能: TradingAgentsGraph 导入成功")
            print("   ✅ TradingAgentsGraph 导入成功")
            
        except Exception as e:
            self.test_results["failed"].append(f"主功能: {e}")
            print(f"   ❌ 主功能测试失败: {e}")
    
    def test_documentation(self):
        """测试文档完整性"""
        print("\n📚 测试文档完整性...")
        
        doc_files = [
            "docs/README.md",
            "docs/en-US/configuration_guide.md",
            "docs/en-US/quick_reference.md",
            "docs/en-US/prompt_templates.md",
            "MERGE_SUMMARY.md"
        ]
        
        for doc_file in doc_files:
            if os.path.exists(doc_file):
                self.test_results["passed"].append(f"文档: {doc_file} 存在")
                print(f"   ✅ {doc_file}")
            else:
                self.test_results["failed"].append(f"文档: {doc_file} 缺失")
                print(f"   ❌ {doc_file}")
    
    def run_all_tests(self):
        """运行所有测试"""
        print("🧪 开始合并后功能测试验证")
        print("=" * 50)
        
        self.setup()
        
        try:
            self.test_basic_imports()
            self.test_cache_system()
            self.test_new_features_import()
            self.test_optimized_data_providers()
            self.test_config_system()
            self.test_main_functionality()
            self.test_documentation()
            
        finally:
            self.cleanup()
        
        self.print_summary()
    
    def print_summary(self):
        """打印测试摘要"""
        print("\n" + "=" * 50)
        print("📋 测试结果摘要")
        print("=" * 50)
        
        total_passed = len(self.test_results["passed"])
        total_failed = len(self.test_results["failed"])
        total_warnings = len(self.test_results["warnings"])
        total_tests = total_passed + total_failed + total_warnings
        
        print(f"\n📊 统计:")
        print(f"   总测试项: {total_tests}")
        print(f"   ✅ 通过: {total_passed}")
        print(f"   ❌ 失败: {total_failed}")
        print(f"   ⚠️ 警告: {total_warnings}")
        
        if total_failed == 0:
            print(f"\n🎉 所有核心功能测试通过！")
            if total_warnings > 0:
                print(f"⚠️ 有 {total_warnings} 个警告，主要是可选依赖缺失")
        else:
            print(f"\n❌ 有 {total_failed} 个测试失败，需要修复")
        
        # 详细结果
        if self.test_results["failed"]:
            print(f"\n❌ 失败的测试:")
            for failure in self.test_results["failed"]:
                print(f"   - {failure}")
        
        if self.test_results["warnings"]:
            print(f"\n⚠️ 警告:")
            for warning in self.test_results["warnings"]:
                print(f"   - {warning}")
        
        # 建议
        print(f"\n💡 建议:")
        if total_failed == 0:
            print("   1. 核心功能正常，可以进行更深入的集成测试")
            print("   2. 考虑安装可选依赖以启用完整功能")
            print("   3. 运行实际的股票数据获取测试")
        else:
            print("   1. 修复失败的测试项")
            print("   2. 检查依赖项安装")
            print("   3. 验证文件路径和导入")

def main():
    """主函数"""
    tester = MergedFeaturesTest()
    tester.run_all_tests()

if __name__ == "__main__":
    main()
