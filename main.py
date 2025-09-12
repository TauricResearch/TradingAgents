# TradingAgents 国内AI大模型版本
# 使用国内免费大模型进行股票分析

import os
import sys

# 尝试导入dotenv
from dotenv import load_dotenv
load_dotenv()  # 加载.env文件中的环境变量


from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

def check_environment():
    """检查环境变量和依赖"""
    print("🔍 检查环境配置...")
    
    # 检查是否有API密钥
    api_keys = {
        "通义千问": os.getenv("DASHSCOPE_API_KEY"),
        "文心一言": os.getenv("BAIDU_API_KEY") and os.getenv("BAIDU_SECRET_KEY"),
        "智谱AI": os.getenv("ZHIPU_API_KEY"),
        "月之暗面Kimi": os.getenv("MOONSHOT_API_KEY")
    }
    
    available_models = [name for name, has_key in api_keys.items() if has_key]
    
    if not available_models:
        print("❌ 错误：未找到任何AI模型的API密钥！")
        print("\n请设置以下环境变量之一：")
        print("  通义千问: export DASHSCOPE_API_KEY='your_key'")
        print("  文心一言: export BAIDU_API_KEY='your_key' && export BAIDU_SECRET_KEY='your_secret'")
        print("  智谱AI: export ZHIPU_API_KEY='your_key'")
        print("  月之暗面Kimi: export MOONSHOT_API_KEY='your_key'")
        return False
    
    print(f"✅ 找到可用的AI模型: {', '.join(available_models)}")
    return True

def create_config():
    """创建优化的配置"""
    config = DEFAULT_CONFIG.copy()
    
    # 根据可用的API密钥选择模型
    if os.getenv("DASHSCOPE_API_KEY"):
        # 使用通义千问（推荐）
        config["llm_provider"] = "qwen"
        config["deep_think_llm"] = "qwen-plus"
        config["quick_think_llm"] = "qwen-turbo"
        config["backend_url"] = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        print("🤖 使用通义千问模型")
        
    elif os.getenv("BAIDU_API_KEY") and os.getenv("BAIDU_SECRET_KEY"):
        # 使用文心一言
        config["llm_provider"] = "ernie"
        config["deep_think_llm"] = "ernie-4.0-8k"
        config["quick_think_llm"] = "ernie-3.5-8k"
        config["backend_url"] = "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat"
        print("🤖 使用文心一言模型")
        
    elif os.getenv("ZHIPU_API_KEY"):
        # 使用智谱AI
        config["llm_provider"] = "glm"
        config["deep_think_llm"] = "glm-4"
        config["quick_think_llm"] = "glm-4"
        config["backend_url"] = "https://open.bigmodel.cn/api/paas/v4"
        print("🤖 使用智谱AI模型")
        
    elif os.getenv("MOONSHOT_API_KEY"):
        # 使用月之暗面Kimi
        config["llm_provider"] = "kimi"
        config["deep_think_llm"] = "moonshot-v1-32k"
        config["quick_think_llm"] = "moonshot-v1-8k"
        config["backend_url"] = "https://api.moonshot.cn/v1"
        print("🤖 使用月之暗面Kimi模型")
    
    # 优化配置参数
    config["max_debate_rounds"] = 1  # 减少API调用次数
    config["online_tools"] = False   # 使用离线数据，减少API调用
    config["max_recur_limit"] = 50   # 限制递归次数
    
    return config

def main():
    """主函数"""
    print("🚀 TradingAgents 国内AI大模型版本")
    print("=" * 50)
    
    # 检查环境
    if not check_environment():
        sys.exit(1)
    
    # 创建配置
    config = create_config()
    
    try:
        # 初始化交易代理图
        print("\n🔧 初始化交易代理系统...")
        ta = TradingAgentsGraph(debug=True, config=config)
        print("✅ 系统初始化完成")
        
        # 运行交易分析
        print("\n📊 开始股票分析...")
        print("分析目标: NVDA (英伟达)")
        print("分析日期: 2024-05-10")
        print("-" * 30)
        
        # 执行分析
        _, decision = ta.propagate("NVDA", "2024-05-10")
        
        # 输出结果
        print("\n" + "=" * 50)
        print("📈 分析结果:")
        print("=" * 50)
        print(decision)
        print("=" * 50)
        
        print("\n✅ 分析完成！")
        
    except Exception as e:
        print(f"\n❌ 分析过程中出现错误: {str(e)}")
        print(f"错误类型: {type(e).__name__}")
        
        # 打印详细的错误信息
        import traceback
        print("\n🔍 详细错误信息:")
        traceback.print_exc()
        
        print("\n💡 可能的解决方案:")
        print("1. 检查API密钥是否正确")
        print("2. 检查网络连接")
        print("3. 检查API额度是否用完")
        print("4. 检查依赖包是否完整安装")
        print("5. 查看详细错误信息进行排查")
        sys.exit(1)

if __name__ == "__main__":
    main()
