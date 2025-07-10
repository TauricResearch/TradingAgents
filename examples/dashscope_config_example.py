#!/usr/bin/env python3
"""
DashScope (Alibaba Cloud) Configuration Example
阿里云百炼模型配置示例

This example shows how to configure TradingAgents to use DashScope models.
这个示例展示如何配置TradingAgents使用阿里云百炼模型。
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tradingagents.default_config import DEFAULT_CONFIG

def create_dashscope_config():
    """
    Create configuration for DashScope models
    创建百炼模型配置
    """
    
    # Copy default config
    config = DEFAULT_CONFIG.copy()
    
    # Configure for DashScope
    config.update({
        # LLM Provider Settings
        "llm_provider": "dashscope",
        "backend_url": "https://dashscope.aliyuncs.com/api/v1",
        
        # Model Selection
        # 模型选择 - 根据需要调整
        "deep_think_llm": "qwen-plus",      # For complex analysis 复杂分析
        "quick_think_llm": "qwen-turbo",    # For quick tasks 快速任务
        
        # Optional: Reduce rounds for faster execution
        # 可选：减少轮次以加快执行速度
        "max_debate_rounds": 1,
        "max_risk_discuss_rounds": 1,
        
        # Enable online tools
        "online_tools": True,
    })
    
    return config

def check_dashscope_setup():
    """
    Check if DashScope is properly configured
    检查百炼配置是否正确
    """
    
    print("🔍 Checking DashScope Configuration")
    print("🔍 检查百炼配置")
    print("=" * 50)
    
    # Check API key
    api_key = os.getenv('DASHSCOPE_API_KEY')
    if api_key:
        print(f"✅ DASHSCOPE_API_KEY: {api_key[:10]}...")
    else:
        print("❌ DASHSCOPE_API_KEY not found in environment variables")
        print("❌ 环境变量中未找到 DASHSCOPE_API_KEY")
        print("\n💡 To fix this:")
        print("💡 解决方法:")
        print("1. Get API key from: https://dashscope.aliyun.com/")
        print("1. 从以下网址获取API密钥: https://dashscope.aliyun.com/")
        print("2. Add to .env file: DASHSCOPE_API_KEY=your_key_here")
        print("2. 添加到.env文件: DASHSCOPE_API_KEY=your_key_here")
        return False
    
    # Check DashScope package
    try:
        import dashscope
        print("✅ dashscope package installed")
        print("✅ dashscope包已安装")
    except ImportError:
        print("❌ dashscope package not installed")
        print("❌ dashscope包未安装")
        print("\n💡 To install:")
        print("💡 安装方法:")
        print("pip install dashscope")
        return False
    
    # Check adapter
    try:
        from tradingagents.llm_adapters.dashscope_adapter import ChatDashScope
        print("✅ DashScope adapter available")
        print("✅ 百炼适配器可用")
    except ImportError:
        print("❌ DashScope adapter not available")
        print("❌ 百炼适配器不可用")
        return False
    
    print("\n🎉 DashScope configuration is ready!")
    print("🎉 百炼配置已就绪!")
    return True

def test_dashscope_connection():
    """
    Test connection to DashScope
    测试百炼连接
    """
    
    print("\n🧪 Testing DashScope Connection")
    print("🧪 测试百炼连接")
    print("=" * 50)
    
    try:
        from tradingagents.llm_adapters.dashscope_adapter import ChatDashScope
        from langchain_core.messages import HumanMessage
        
        # Create model instance
        llm = ChatDashScope(
            model="qwen-turbo",
            temperature=0.1,
            max_tokens=100
        )
        
        # Test simple query
        test_message = HumanMessage(content="Hello, please respond with 'DashScope connection successful!'")
        response = llm.invoke([test_message])
        
        print(f"✅ Connection successful!")
        print(f"✅ 连接成功!")
        print(f"📝 Response: {response.content}")
        print(f"📝 响应: {response.content}")
        
        return True
        
    except Exception as e:
        print(f"❌ Connection failed: {str(e)}")
        print(f"❌ 连接失败: {str(e)}")
        return False

def main():
    """
    Main function to demonstrate DashScope configuration
    主函数演示百炼配置
    """
    
    print("🚀 DashScope Configuration Example")
    print("🚀 百炼配置示例")
    print("=" * 50)
    
    # Check setup
    if not check_dashscope_setup():
        print("\n❌ Please fix the configuration issues above")
        print("❌ 请修复上述配置问题")
        return
    
    # Test connection
    if not test_dashscope_connection():
        print("\n❌ Connection test failed")
        print("❌ 连接测试失败")
        return
    
    # Show configuration
    config = create_dashscope_config()
    
    print(f"\n📋 DashScope Configuration:")
    print(f"📋 百炼配置:")
    print(f"   Provider: {config['llm_provider']}")
    print(f"   Deep Think Model: {config['deep_think_llm']}")
    print(f"   Quick Think Model: {config['quick_think_llm']}")
    print(f"   Backend URL: {config['backend_url']}")
    
    print(f"\n💡 Usage Example:")
    print(f"💡 使用示例:")
    print(f"""
from tradingagents.graph.trading_graph import TradingAgentsGraph

# Create config
config = create_dashscope_config()

# Initialize trading graph
ta = TradingAgentsGraph(config)

# Run analysis
result, decision = ta.propagate("AAPL", "2024-01-15")
print(result)
""")
    
    print(f"\n🎯 Available DashScope Models:")
    print(f"🎯 可用的百炼模型:")
    
    models = {
        "qwen-turbo": "Fast response, suitable for daily conversations",
        "qwen-plus": "Balanced performance and cost",
        "qwen-max": "Best performance",
        "qwen-max-longcontext": "Supports ultra-long context"
    }
    
    for model, description in models.items():
        print(f"   • {model}: {description}")

if __name__ == "__main__":
    main()
