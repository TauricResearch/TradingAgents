"""
Setup script for the TradingAgents package.
"""

from setuptools import setup, find_packages

setup(
    name="tradingagents",
    version="0.1.0",
    description="Multi-Agent LLM Financial Trading Framework with AI-powered stock analysis, structured debates, and backtesting",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="Hemang Joshi",
    author_email="hemangjoshi37a@gmail.com",
    url="https://hjlabs.in",
    project_urls={
        "Source": "https://github.com/hemangjoshi37a/TradingAgents",
        "Issues": "https://github.com/hemangjoshi37a/TradingAgents/issues",
        "Research Paper": "https://arxiv.org/abs/2412.20138",
    },
    packages=find_packages(),
    install_requires=[
        "langchain>=0.1.0",
        "langchain-openai>=0.0.2",
        "langchain-experimental>=0.0.40",
        "langgraph>=0.0.20",
        "numpy>=1.24.0",
        "pandas>=2.0.0",
        "praw>=7.7.0",
        "stockstats>=0.5.4",
        "yfinance>=0.2.31",
        "typer>=0.9.0",
        "rich>=13.0.0",
        "questionary>=2.0.1",
    ],
    python_requires=">=3.10",
    entry_points={
        "console_scripts": [
            "tradingagents=cli.main:app",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Financial and Insurance Industry",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Topic :: Office/Business :: Financial :: Investment",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    keywords=[
        "trading", "ai", "multi-agent", "llm", "stock-analysis",
        "nifty50", "backtesting", "langchain", "langgraph",
        "algorithmic-trading", "quantitative-finance",
    ],
)
