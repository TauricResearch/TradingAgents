"""
TradingAgents包的安装脚本
这个文件用于配置Python包的安装信息
"""

# 导入setuptools模块，用于创建和安装Python包
from setuptools import setup, find_packages

# 配置包的安装信息
setup(
    # 包的基本信息
    name="tradingagents",  # 包名
    version="0.1.0",  # 版本号
    description="Multi-Agents LLM Financial Trading Framework",  # 包描述：多代理大语言模型金融交易框架
    author="TradingAgents Team",  # 作者
    author_email="yijia.xiao@cs.ucla.edu",  # 作者邮箱
    url="https://github.com/TauricResearch",  # 项目主页
    
    # 自动查找所有包
    packages=find_packages(),
    
    # 依赖包列表（运行这个项目需要的其他Python包）
    install_requires=[
        "langchain>=0.1.0",  # LangChain：用于构建AI应用的框架
        "langchain-openai>=0.0.2",  # LangChain的OpenAI集成
        "langchain-experimental>=0.0.40",  # LangChain实验性功能
        "langgraph>=0.0.20",  # LangGraph：用于构建AI代理图
        "numpy>=1.24.0",  # NumPy：数值计算库
        "pandas>=2.0.0",  # Pandas：数据分析库
        "praw>=7.7.0",  # PRAW：Reddit API包装器
        "stockstats>=0.5.4",  # StockStats：股票技术指标计算
        "yfinance>=0.2.31",  # Yahoo Finance：获取股票数据
        "typer>=0.9.0",  # Typer：命令行界面库
        "rich>=13.0.0",  # Rich：美化终端输出
        "questionary>=2.0.1",  # Questionary：交互式命令行提示
    ],
    
    # Python版本要求
    python_requires=">=3.10",  # 需要Python 3.10或更高版本
    
    # 命令行入口点
    entry_points={
        "console_scripts": [
            # 安装后可以在命令行直接使用"tradingagents"命令
            "tradingagents=cli.main:app",  # 指向cli/main.py中的app函数
        ],
    },
    
    # 包的分类标签
    classifiers=[
        "Development Status :: 3 - Alpha",  # 开发状态：Alpha版本
        "Intended Audience :: Financial and Trading Industry",  # 目标用户：金融和交易行业
        "License :: OSI Approved :: Apache Software License",  # 许可证：Apache许可证
        "Programming Language :: Python :: 3",  # 编程语言：Python 3
        "Programming Language :: Python :: 3.10",  # 支持的Python版本
        "Topic :: Office/Business :: Financial :: Investment",  # 主题：金融投资
    ],
)
