# 导入操作系统模块，用于处理文件路径
import os

# 默认配置字典
# 这个文件包含了TradingAgents项目的所有默认设置
DEFAULT_CONFIG = {
    # 项目目录设置
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),  # 项目根目录的绝对路径
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),  # 结果保存目录，默认是./results
    "data_dir": "/Users/yluo/Documents/Code/ScAI/FR1-data",  # 数据存储目录（需要根据实际情况修改）
    "data_cache_dir": os.path.join(  # 数据缓存目录
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),  # 项目根目录
        "dataflows/data_cache",  # 缓存子目录
    ),
    
    # AI模型设置
    "llm_provider": "qwen",  # AI模型提供商，默认使用通义千问（国内免费）
    "deep_think_llm": "qwen-plus",  # 深度思考模型，用于复杂分析任务
    "quick_think_llm": "qwen-turbo",  # 快速思考模型，用于简单任务
    "backend_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",  # 通义千问API地址
    
    # 辩论和讨论设置
    "max_debate_rounds": 1,  # 代理之间最大辩论轮数
    "max_risk_discuss_rounds": 1,  # 风险管理讨论最大轮数
    "max_recur_limit": 100,  # 最大递归限制，防止无限循环
    
    # 工具设置
    "online_tools": True,  # 是否使用在线工具（获取实时数据）
}
