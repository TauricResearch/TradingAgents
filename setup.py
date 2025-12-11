# -*- coding: utf-8 -*-
"""
TradingAgentsX 套件的安裝腳本。

這個檔案包含了套件的元數據，例如名稱、版本、依賴項等，
setuptools 會使用這些資訊來建構和安裝套件。
"""

# 從 setuptools 匯入 setup 和 find_packages 函式
from setuptools import setup, find_packages

# 呼叫 setup 函式來設定套件
setup(
    # 套件的名稱
    name="tradingagents",
    # 套件的版本
    version="0.1.0",
    # 套件的簡短描述
    description="多代理 LLM 金融交易框架",
    # 作者名稱
    author="TradingAgentsX",
    # 專案的首頁 URL
    url="https://github.com/MarkLo127/TradingAgentsX",
    # 自動尋找專案中的所有套件
    packages=find_packages(),
    # 套件的安裝依賴項
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
    # 要求的 Python 版本
    python_requires=">=3.10",
    # 設定命令列腳本的進入點
    entry_points={
        "console_scripts": [
            "tradingagents=cli.main:app",
        ],
    },
    # 套件的分類器，提供給 PyPI 用於分類
    classifiers=[
        "Development Status :: 3 - Alpha",  # 開發狀態：Alpha
        "Intended Audience :: Financial and Trading Industry",  # 目標受眾：金融和交易行業
        "License :: OSI Approved :: Apache Software License",  # 授權條款：Apache 軟體授權
        "Programming Language :: Python :: 3",  # 程式語言：Python 3
        "Programming Language :: Python :: 3.10", # 程式語言：Python 3.10
        "Topic :: Office/Business :: Financial :: Investment",  # 主題：金融投資
    ],
)